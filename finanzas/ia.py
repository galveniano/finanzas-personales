"""Llamadas a la API de mensajes de Anthropic (Claude) para el asistente y para leer documentos."""
import httpx

from finanzas import config

URL = "https://api.anthropic.com/v1/messages"


class ErrorIA(RuntimeError):
    pass


def disponible() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


def mensaje(system: str, mensajes: list[dict], tools: list[dict] | None = None, tool_choice: dict | None = None,
            max_tokens: int = 2048, transport=None) -> dict:
    if not disponible():
        raise ErrorIA("Falta ANTHROPIC_API_KEY en la configuración")
    cuerpo = {"model": config.ANTHROPIC_MODEL, "max_tokens": max_tokens, "system": system, "messages": mensajes}
    if tools:
        cuerpo["tools"] = tools
    if tool_choice:
        cuerpo["tool_choice"] = tool_choice
    try:
        with httpx.Client(timeout=90, transport=transport) as http:
            r = http.post(URL, json=cuerpo, headers={
                "x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                "content-type": "application/json"})
    except httpx.HTTPError as e:
        raise ErrorIA(f"No se puede conectar con Claude: {e}")
    if r.status_code != 200:
        try:
            detalle = r.json()["error"]["message"]
        except Exception:
            detalle = r.text[:200]
        raise ErrorIA(f"Claude respondió {r.status_code}: {detalle}")
    return r.json()


def texto(respuesta: dict) -> str:
    return "".join(b.get("text", "") for b in respuesta.get("content", []) if b.get("type") == "text").strip()
