"""Modelos de lenguaje para el asistente y para leer documentos: OpenAI o Claude (Anthropic).

El proveedor, la clave y el modelo se eligen desde la app (Conexiones) y se guardan cifrados;
si no, se usan las variables de entorno. El resto del código no sabe qué proveedor hay detrás:
usa `conversar` (bucle con herramientas) y `extraer` (datos estructurados).
"""
import json
from dataclasses import dataclass
from typing import Callable

import httpx
from sqlalchemy.orm import Session

from finanzas import ajustes, config

PROVEEDORES = {
    "openai": {"nombre": "OpenAI", "modelo": "gpt-5.4-mini", "url": "https://api.openai.com/v1/chat/completions"},
    "anthropic": {"nombre": "Claude", "modelo": "claude-sonnet-5-5", "url": "https://api.anthropic.com/v1/messages"},
}


class ErrorIA(RuntimeError):
    pass


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

def _post(cfg: ConfigIA, cuerpo: dict, transport=None) -> dict:
    if not cfg.clave:
        raise ErrorIA(f"Falta la clave de {PROVEEDORES[cfg.proveedor]['nombre']}: ponla en Conexiones > Asistente")
    if cfg.proveedor == "openai":
        cabeceras = {"Authorization": f"Bearer {cfg.clave}"}
    else:
        cabeceras = {"x-api-key": cfg.clave, "anthropic-version": "2023-06-01"}
    try:
        with httpx.Client(timeout=90, transport=transport) as http:
            r = http.post(PROVEEDORES[cfg.proveedor]["url"], json=cuerpo, headers=cabeceras)
    except httpx.HTTPError as e:
        raise ErrorIA(f"No se puede conectar con {PROVEEDORES[cfg.proveedor]['nombre']}: {e}")
    if r.status_code != 200:
        try:
            detalle = r.json()["error"]["message"]
        except Exception:
            detalle = r.text[:200]
        raise ErrorIA(f"{PROVEEDORES[cfg.proveedor]['nombre']} respondió {r.status_code}: {detalle}")
    return r.json()


def _herramientas(cfg: ConfigIA, tools: list[dict]) -> list[dict]:
    """tools en formato neutro: {name, description, parameters (JSON Schema)}."""
    if cfg.proveedor == "openai":
        return [{"type": "function", "function": t} for t in tools]
    return [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]


def conversar(cfg: ConfigIA, sistema: str, mensajes: list[dict], tools: list[dict],
              ejecutar: Callable[[str, dict], str], max_vueltas: int = 6, transport=None) -> tuple[str, list[str]]:
    """Conversación con herramientas. mensajes: [{role: user|assistant, content: str}].
    Devuelve el texto final y los nombres de las herramientas usadas."""
    consultas: list[str] = []
    if cfg.proveedor == "openai":
        conv = [{"role": "system", "content": sistema}] + mensajes
        for _ in range(max_vueltas):
            cuerpo = {"model": cfg.modelo, "messages": conv, "max_completion_tokens": 4000}
            if tools:
                cuerpo["tools"] = _herramientas(cfg, tools)
            r = _post(cfg, cuerpo, transport)
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
            cuerpo = {"model": cfg.modelo, "max_tokens": 2048, "system": sistema, "messages": conv}
            if tools:
                cuerpo["tools"] = _herramientas(cfg, tools)
            r = _post(cfg, cuerpo, transport)
            usos = [b for b in r.get("content", []) if b.get("type") == "tool_use"]
            if r.get("stop_reason") != "tool_use" or not usos:
                return "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text").strip(), consultas
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
    return "He tenido que hacer demasiadas consultas para responder. ¿Puedes concretar la pregunta?", consultas


def extraer(cfg: ConfigIA, sistema: str, texto: str, tool: dict, transport=None) -> dict:
    """Obliga al modelo a rellenar `tool` (formato neutro) y devuelve sus argumentos."""
    if cfg.proveedor == "openai":
        r = _post(cfg, {"model": cfg.modelo, "max_completion_tokens": 2000,
                        "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": texto}],
                        "tools": _herramientas(cfg, [tool]),
                        "tool_choice": {"type": "function", "function": {"name": tool["name"]}}}, transport)
        llamadas = r["choices"][0]["message"].get("tool_calls") or []
        if llamadas:
            return json.loads(llamadas[0]["function"].get("arguments") or "{}")
    else:
        r = _post(cfg, {"model": cfg.modelo, "max_tokens": 1024, "system": sistema,
                        "messages": [{"role": "user", "content": texto}], "tools": _herramientas(cfg, [tool]),
                        "tool_choice": {"type": "tool", "name": tool["name"]}}, transport)
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
    return "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text").strip()
