"""Modelos de lenguaje para el asistente y para leer documentos: OpenAI o Claude (Anthropic).

El proveedor, la clave y el modelo se eligen desde la app (Ajustes) y se guardan cifrados;
si no, se usan las variables de entorno. El resto del código no sabe qué proveedor hay detrás:
usa `conversar` (bucle con herramientas) y `extraer` (datos estructurados).
"""
import json
import time
from dataclasses import dataclass
from typing import Callable

import httpx
from sqlalchemy.orm import Session

from finanzas import ajustes, config

PROVEEDORES = {
    "openai": {"nombre": "OpenAI", "modelo": "gpt-5.4-mini", "url": "https://api.openai.com/v1/chat/completions"},
    "anthropic": {"nombre": "Claude", "modelo": "claude-sonnet-5-5", "url": "https://api.anthropic.com/v1/messages"},
}
# Vueltas de herramientas por pregunta y tamaño máximo de cada respuesta del asistente
MAX_VUELTAS = 6
MAX_TOKENS = 4096
TIMEOUT_S = 90.0
SIN_TIEMPO = ("Me he quedado sin tiempo mirando tus datos. Pregunta algo más concreto "
              "(un año, un trimestre, un cliente) y lo resuelvo.")


class ErrorIA(RuntimeError):
    pass


class SinClave(ErrorIA):
    """No hay clave de API para el proveedor elegido."""


class SinTiempo(ErrorIA):
    """Se ha agotado el plazo de la conversación (`plazo_s`)."""


@dataclass
class ConfigIA:
    proveedor: str
    clave: str
    modelo: str

    @property
    def lista(self) -> bool:
        return bool(self.clave)


def _clave_entorno(proveedor: str) -> str:
    return config.OPENAI_API_KEY if proveedor == "openai" else config.ANTHROPIC_API_KEY


def clave(s: Session, proveedor: str) -> str:
    return ajustes.leer(s, f"{proveedor}_api_key") or _clave_entorno(proveedor)


def configuracion(s: Session) -> ConfigIA:
    elegido = ajustes.leer(s, "ia_proveedor")
    if elegido not in PROVEEDORES:  # sin elegir: el que tenga clave, OpenAI primero
        elegido = next((p for p in PROVEEDORES if clave(s, p)), "openai")
    modelo = (ajustes.leer(s, f"{elegido}_modelo")
              or (config.OPENAI_MODEL if elegido == "openai" else config.ANTHROPIC_MODEL)
              or PROVEEDORES[elegido]["modelo"])
    return ConfigIA(elegido, clave(s, elegido), modelo)


def disponible(s: Session) -> bool:
    return configuracion(s).lista


# --- Llamadas HTTP -------------------------------------------------------------

def _post(cfg: ConfigIA, cuerpo: dict, transport=None, timeout: float = TIMEOUT_S) -> dict:
    nombre = PROVEEDORES[cfg.proveedor]["nombre"]
    if not cfg.clave:
        raise SinClave(f"Falta la clave de {nombre}: ponla en Ajustes > Asistente")
    if cfg.proveedor == "openai":
        cabeceras = {"Authorization": f"Bearer {cfg.clave}"}
    else:
        cabeceras = {"x-api-key": cfg.clave, "anthropic-version": "2023-06-01"}
    try:
        with httpx.Client(timeout=timeout, transport=transport) as http:
            r = http.post(PROVEEDORES[cfg.proveedor]["url"], json=cuerpo, headers=cabeceras)
    except httpx.TimeoutException:
        raise SinTiempo(f"{nombre} ha tardado más de {timeout:.0f} segundos en responder")
    except httpx.HTTPError as e:
        raise ErrorIA(f"No se puede conectar con {nombre}: {e}")
    if r.status_code != 200:
        try:
            detalle = r.json()["error"]["message"]
        except Exception:
            detalle = r.text[:200]
        raise ErrorIA(f"{nombre} respondió {r.status_code}: {detalle}")
    return r.json()


def _herramientas(cfg: ConfigIA, tools: list[dict]) -> list[dict]:
    """tools en formato neutro: {name, description, parameters (JSON Schema)}."""
    if cfg.proveedor == "openai":
        return [{"type": "function", "function": t} for t in tools]
    return [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]


def _texto_claude(r: dict) -> str:
    texto = "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text").strip()
    if r.get("stop_reason") == "refusal" and not texto:
        return "El modelo ha preferido no responder a eso."
    return texto


class _Plazo:
    """Tiempo que queda para toda la conversación; cada llamada al modelo recibe como tope lo que falta."""

    def __init__(self, segundos: float | None):
        self.fin = time.monotonic() + segundos if segundos else None

    def restante(self) -> float:
        if self.fin is None:
            return TIMEOUT_S
        queda = self.fin - time.monotonic()
        if queda <= 1:
            raise SinTiempo("Se ha agotado el tiempo de la conversación")
        return min(TIMEOUT_S, queda)


def conversar(cfg: ConfigIA, sistema: str, mensajes: list[dict], tools: list[dict],
              ejecutar: Callable[[str, dict], str], max_vueltas: int = MAX_VUELTAS, plazo_s: float | None = None,
              transport=None) -> tuple[str, list[str]]:
    """Conversación con herramientas. mensajes: [{role: user|assistant, content: str}].
    Devuelve el texto final y los nombres de las herramientas usadas. Si `plazo_s` se agota (el tiempo que
    da Vercel a una petición, por ejemplo) responde con un texto claro en vez de cortarse a medias."""
    consultas: list[str] = []
    plazo = _Plazo(plazo_s)
    try:
        if cfg.proveedor == "openai":
            conv = [{"role": "system", "content": sistema}] + mensajes
            for _ in range(max_vueltas):
                cuerpo = {"model": cfg.modelo, "messages": conv, "max_completion_tokens": MAX_TOKENS}
                if tools:
                    cuerpo["tools"] = _herramientas(cfg, tools)
                r = _post(cfg, cuerpo, transport, timeout=plazo.restante())
                msg = r["choices"][0]["message"]
                llamadas = msg.get("tool_calls") or []
                if not llamadas:
                    return (msg.get("content") or "").strip(), consultas
                conv.append({"role": "assistant", "content": msg.get("content"), "tool_calls": llamadas})
                for ll in llamadas:
                    nombre = ll["function"]["name"]
                    consultas.append(nombre)
                    try:
                        args = json.loads(ll["function"].get("arguments") or "{}")
                        salida = ejecutar(nombre, args)
                    except Exception as e:
                        salida = f"Error: {e}"
                    conv.append({"role": "tool", "tool_call_id": ll["id"], "content": salida})
        else:
            conv = list(mensajes)
            for _ in range(max_vueltas):
                cuerpo = {"model": cfg.modelo, "max_tokens": MAX_TOKENS, "system": sistema, "messages": conv}
                if tools:
                    cuerpo["tools"] = _herramientas(cfg, tools)
                r = _post(cfg, cuerpo, transport, timeout=plazo.restante())
                usos = [b for b in r.get("content", []) if b.get("type") == "tool_use"]
                if r.get("stop_reason") != "tool_use" or not usos:
                    return _texto_claude(r), consultas
                # Se devuelve el contenido entero (con sus bloques de razonamiento) para seguir la misma conversación
                conv.append({"role": "assistant", "content": r["content"]})
                resultados = []
                for u in usos:
                    consultas.append(u["name"])
                    try:
                        resultados.append({"type": "tool_result", "tool_use_id": u["id"],
                                           "content": ejecutar(u["name"], u.get("input") or {})})
                    except Exception as e:
                        resultados.append({"type": "tool_result", "tool_use_id": u["id"], "content": str(e), "is_error": True})
                conv.append({"role": "user", "content": resultados})
    except SinTiempo:
        return SIN_TIEMPO, consultas
    return "He tenido que hacer demasiadas consultas para responder. ¿Puedes concretar la pregunta?", consultas


def extraer(cfg: ConfigIA, sistema: str, texto: str, tool: dict, transport=None) -> dict:
    """Pide al modelo que rellene `tool` (formato neutro) y devuelve sus argumentos."""
    if cfg.proveedor == "openai":
        r = _post(cfg, {"model": cfg.modelo, "max_completion_tokens": 2000,
                        "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": texto}],
                        "tools": _herramientas(cfg, [tool]),
                        "tool_choice": {"type": "function", "function": {"name": tool["name"]}}}, transport)
        llamadas = r["choices"][0]["message"].get("tool_calls") or []
        if llamadas:
            return json.loads(llamadas[0]["function"].get("arguments") or "{}")
    else:
        # Los modelos actuales de Claude no admiten forzar una herramienta (tool_choice tool/any devuelve 400):
        # se le pide en el sistema que la llame y se comprueba que lo ha hecho.
        orden = f"{sistema}\n\nResponde únicamente llamando a la herramienta {tool['name']}, sin texto aparte."
        r = _post(cfg, {"model": cfg.modelo, "max_tokens": 2048, "system": orden,
                        "messages": [{"role": "user", "content": texto}], "tools": _herramientas(cfg, [tool]),
                        "tool_choice": {"type": "auto", "disable_parallel_tool_use": True}}, transport)
        for b in r.get("content", []):
            if b.get("type") == "tool_use":
                return b["input"]
    raise ErrorIA("El modelo no ha devuelto los datos del documento")


def probar(cfg: ConfigIA, transport=None) -> str:
    """Pregunta mínima para comprobar clave y modelo."""
    if cfg.proveedor == "openai":
        r = _post(cfg, {"model": cfg.modelo, "max_completion_tokens": 200,
                        "messages": [{"role": "user", "content": "Responde solo con: OK"}]}, transport)
        return (r["choices"][0]["message"].get("content") or "").strip()
    r = _post(cfg, {"model": cfg.modelo, "max_tokens": 20,
                    "messages": [{"role": "user", "content": "Responde solo con: OK"}]}, transport)
    return _texto_claude(r)
