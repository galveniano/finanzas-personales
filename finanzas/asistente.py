"""Asistente: Claude con acceso de solo lectura a los datos de la app.

En cada conversación recibe un resumen (patrimonio, autónomo del año, nóminas, Hacienda...) y
puede pedir más detalle con herramientas que llaman a las mismas funciones que usa el frontal.
No puede cambiar nada.
"""
import json
from datetime import date

from sqlalchemy.orm import Session

from finanzas import api, config, ia

MAX_VUELTAS = 6

HERRAMIENTAS = [
    {"name": "movimientos", "description": "Busca movimientos bancarios por texto del concepto. Devuelve los más recientes.",
     "input_schema": {"type": "object", "properties": {
         "texto": {"type": "string", "description": "Texto a buscar en el concepto (vacío = todos)"},
         "limite": {"type": "integer", "description": "Máximo de movimientos (por defecto 50, máximo 300)"}}}},
    {"name": "autonomo", "description": "Facturas emitidas, gastos y estimación de los modelos 303 y 130 de un año.",
     "input_schema": {"type": "object", "properties": {"anio": {"type": "integer"}}, "required": ["anio"]}},
    {"name": "nominas", "description": "Nóminas registradas y totales de un año.",
     "input_schema": {"type": "object", "properties": {"anio": {"type": "integer"}}, "required": ["anio"]}},
    {"name": "inmuebles", "description": "Inmuebles, hipotecas, alquiler y rendimiento fiscal del alquiler de un año.",
     "input_schema": {"type": "object", "properties": {"anio": {"type": "integer"}}, "required": ["anio"]}},
    {"name": "planificacion", "description": "Objetivos de ahorro (boda, viajes...) y pagos previstos.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "hacienda", "description": "Modelos presentados a Hacienda (303, 130, renta) con sus importes.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "calcular_sueldo", "description": "Neto mensual a partir de un bruto anual, o bruto necesario para un neto.",
     "input_schema": {"type": "object", "properties": {
         "bruto_anual": {"type": "number"}, "neto_mes": {"type": "number"},
         "pagas": {"type": "integer", "enum": [12, 14]}, "hijos": {"type": "integer"}}}},
]


def _ejecutar(s: Session, nombre: str, args: dict):
    if nombre == "movimientos":
        return api.listar_movimientos(q=args.get("texto", ""), limite=min(int(args.get("limite") or 50), 300), s=s)
    if nombre == "autonomo":
        return api.ver_autonomo(anio=args["anio"], s=s)
    if nombre == "nominas":
        return api.listar_nominas(anio=args["anio"], s=s)
    if nombre == "inmuebles":
        return api.listar_inmuebles(anio=args["anio"], s=s)
    if nombre == "planificacion":
        return api.ver_planificacion(s=s)
    if nombre == "hacienda":
        return api.ver_declaraciones(s=s)
    if nombre == "calcular_sueldo":
        return api.calcular_nomina(bruto_anual=args.get("bruto_anual"), neto_mes=args.get("neto_mes"),
                                   pagas=args.get("pagas", 14), hijos=args.get("hijos", 0))
    raise ValueError(f"Herramienta desconocida: {nombre}")


def _contexto(s: Session) -> str:
    hoy = date.today()
    r = api.resumen(s=s)
    r.pop("historico", None)
    a = api.ver_autonomo(anio=hoy.year, s=s)
    autonomo = {k: a[k] for k in ("anio", "trimestres", "total_facturado", "por_cliente")}
    n = api.listar_nominas(anio=hoy.year, s=s)
    datos = {"hoy": hoy.isoformat(), "comunidad_autonoma": config.CCAA, "resumen": r, "autonomo_este_anio": autonomo,
             "nominas_este_anio": {"totales": n["totales"], "bruto_12_meses": n.get("bruto_12_meses")},
             "hacienda": api.ver_declaraciones(s=s)["por_anio"]}
    return json.dumps(datos, ensure_ascii=False, default=str)


SISTEMA = """Eres el asistente de la app de finanzas personales de su dueño. Es empleado por cuenta ajena y también \
autónomo en España, tiene un piso alquilado con hipoteca y está comprando una vivienda de obra nueva. \
Responde en español, claro y breve, como un asesor cercano. Usa los datos de abajo y las herramientas para \
mirar el detalle; no inventes cifras. Si algo es una estimación o depende de normativa, dilo. Para decisiones \
fiscales importantes recomienda confirmarlo con su gestor. Importes con formato español (1.234,56 €).

Datos actuales de la app (JSON):
"""


def responder(s: Session, mensajes: list[dict], transport=None) -> dict:
    """mensajes: historial [{role: user|assistant, content: str}]. Devuelve la respuesta y qué consultó."""
    sistema = SISTEMA + _contexto(s)
    conversacion = [{"role": m["role"], "content": m["content"]} for m in mensajes[-20:]]
    consultas = []
    for _ in range(MAX_VUELTAS):
        r = ia.mensaje(sistema, conversacion, tools=HERRAMIENTAS, max_tokens=2048, transport=transport)
        usos = [b for b in r.get("content", []) if b.get("type") == "tool_use"]
        if r.get("stop_reason") != "tool_use" or not usos:
            return {"respuesta": ia.texto(r), "consultas": consultas}
        conversacion.append({"role": "assistant", "content": r["content"]})
        resultados = []
        for u in usos:
            consultas.append(u["name"])
            try:
                salida = json.dumps(_ejecutar(s, u["name"], u.get("input") or {}), ensure_ascii=False, default=str)
                resultados.append({"type": "tool_result", "tool_use_id": u["id"], "content": salida[:60000]})
            except Exception as e:
                resultados.append({"type": "tool_result", "tool_use_id": u["id"], "content": str(e), "is_error": True})
        conversacion.append({"role": "user", "content": resultados})
    return {"respuesta": "He tenido que hacer demasiadas consultas para responder. ¿Puedes concretar la pregunta?",
            "consultas": consultas}
