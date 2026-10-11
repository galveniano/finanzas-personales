"""Asistente: modelo de IA (OpenAI o Claude) con acceso de solo lectura a los datos de la app.

En cada conversación recibe un resumen (patrimonio, autónomo del año, nóminas, Hacienda...) y
puede pedir más detalle con herramientas que llaman a las mismas funciones que usa el frontal.
No puede cambiar nada.
"""
import json
from datetime import date

from sqlalchemy.orm import Session

from finanzas import api, config, ia

# Tiempo máximo por pregunta, herramientas incluidas: Vercel corta la petición a los 60 s; en local hay margen
PLAZO_S = 50 if config.EN_VERCEL else 170

HERRAMIENTAS = [
    {"name": "movimientos", "description": "Busca movimientos bancarios por texto del concepto. Devuelve los más recientes.",
     "parameters": {"type": "object", "properties": {
         "texto": {"type": "string", "description": "Texto a buscar en el concepto (vacío = todos)"},
         "limite": {"type": "integer", "description": "Máximo de movimientos (por defecto 50, máximo 300)"}}}},
    {"name": "autonomo", "description": "Modelos 303 y 130 de un año: lo presentado en Hacienda (fuente 'presentado', manda) y, si no, lo estimado con facturas y gastos.",
     "parameters": {"type": "object", "properties": {"anio": {"type": "integer"}}, "required": ["anio"]}},
    {"name": "nominas", "description": "Nóminas de un año: las registradas o, si no hay, los cobros de nómina del banco con bruto e IRPF estimados.",
     "parameters": {"type": "object", "properties": {"anio": {"type": "integer"}}, "required": ["anio"]}},
    {"name": "inmuebles", "description": "Inmuebles (con su id), hipotecas, alquiler y rendimiento fiscal del alquiler de un año.",
     "parameters": {"type": "object", "properties": {"anio": {"type": "integer"}}, "required": ["anio"]}},
    {"name": "vender_o_alquilar", "description": "Para un inmueble (activo_id, de la herramienta inmuebles): compara venderlo "
     "(lo que quedaría en mano tras gastos de venta, IRPF de la ganancia e hipoteca) con seguir alquilándolo.",
     "parameters": {"type": "object", "properties": {
         "activo_id": {"type": "integer"},
         "precio": {"type": "number", "description": "Precio de venta a probar; vacío = lo que vale ahora"}},
         "required": ["activo_id"]}},
    {"name": "planificacion", "description": "Objetivos de ahorro (boda, viajes...) y pagos previstos.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "inversiones", "description": "Inversiones privadas (private equity, p. ej. Concrescenta): compromiso, "
     "desembolsado, NAV, TVPI y calendario de llamadas de capital.", "parameters": {"type": "object", "properties": {}}},
    {"name": "indexa", "description": "Cartera de Indexa Capital: fondos con su peso, valor, coste y plusvalía; "
     "rentabilidad anualizada, total y esperada, volatilidad y perfil de riesgo.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "prevision", "description": "Previsión de los próximos meses: nómina, cobros de clientes, alquiler, gastos, "
     "IVA, 130 y renta estimada, y liquidez mes a mes según los supuestos del usuario.",
     "parameters": {"type": "object", "properties": {"meses": {"type": "integer", "description": "1 a 24, por defecto 12"}}}},
    {"name": "gastos", "description": "Análisis de gastos de los últimos meses completos: media mensual de ingresos, gastos "
     "y ahorro, gasto por categoría y por sitio comparado con el periodo anterior, mayores gastos, y suscripciones y "
     "recibos fijos (una vez cada uno, con su importe mensual y anual).",
     "parameters": {"type": "object", "properties": {"meses": {"type": "integer", "description": "1 a 12, por defecto 6"}}}},
    {"name": "hacienda", "description": "Modelos ya presentados a Hacienda (303, 130, renta) con sus importes, año a año.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "hacienda_hoy", "description": "La situación con Hacienda hoy: lo que debes y aún no has pagado (IVA, 130 y "
     "renta pendientes), la hucha para impuestos (cuánto tienes apartado y cuánto falta), la revisión de la cuota de "
     "autónomos, la renta estimada de este año (base, cuota, tipo medio y marginal) y los próximos plazos.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "ahorro_fiscal", "description": "Cuánto bajaría la renta de este año aportando al plan de pensiones o al plan "
     "de empleo simplificado (PPES), o apuntando más gastos de la actividad. Importes anuales en euros; devuelve la cuota "
     "con y sin la aportación, el ahorro y los límites legales.",
     "parameters": {"type": "object", "properties": {
         "pensiones": {"type": "number", "description": "Aportación anual al plan de pensiones individual"},
         "ppes": {"type": "number", "description": "Aportación anual al plan de pensiones de empleo simplificado"},
         "gastos": {"type": "number", "description": "Gastos de la actividad adicionales en el año"}}}},
    {"name": "calcular_sueldo", "description": "Neto mensual a partir de un bruto anual, o bruto necesario para un neto.",
     "parameters": {"type": "object", "properties": {
         "bruto_anual": {"type": "number"}, "neto_mes": {"type": "number"},
         "pagas": {"type": "integer", "enum": [12, 14]}, "hijos": {"type": "integer"}}}},
]


def _numero(v, defecto: float = 0) -> float:
    try:
        return float(v) if v is not None else defecto
    except (TypeError, ValueError):
        return defecto


def _ejecutar(s: Session, nombre: str, args: dict):
    if nombre == "movimientos":
        return api.listar_movimientos(q=args.get("texto", ""), limite=min(int(args.get("limite") or 50), 300),
                                      solo_tuyas=True, s=s)["movimientos"]
    if nombre == "autonomo":
        return api.ver_autonomo(anio=args["anio"], s=s)
    if nombre == "nominas":
        return api.listar_nominas(anio=args["anio"], s=s)
    if nombre == "inmuebles":
        return api.listar_inmuebles(anio=args["anio"], s=s)
    if nombre == "vender_o_alquilar":
        precio = _numero(args.get("precio"), 0) or None
        return api.vender_o_alquilar(activo_id=int(args["activo_id"]), precio=precio, s=s)
    if nombre == "planificacion":
        return api.ver_planificacion(s=s)
    if nombre == "inversiones":
        return api.listar_inversiones(s=s)
    if nombre == "indexa":
        return api.detalle_indexa(s=s)
    if nombre == "gastos":
        from finanzas import gastos
        return gastos.analisis(s, max(1, min(int(args.get("meses") or 6), 12)))
    if nombre == "prevision":
        return api.ver_prevision(meses=int(args.get("meses") or 12), s=s)
    if nombre == "hacienda":
        return api.ver_declaraciones(s=s)
    if nombre == "hacienda_hoy":
        return api.ver_hacienda(s=s)
    if nombre == "ahorro_fiscal":
        return api.simular_ahorro(pensiones=_numero(args.get("pensiones")), ppes=_numero(args.get("ppes")),
                                  gastos=_numero(args.get("gastos")), s=s)
    if nombre == "calcular_sueldo":
        return api.calcular_nomina(bruto_anual=args.get("bruto_anual"), neto_mes=args.get("neto_mes"),
                                   pagas=args.get("pagas", 14), hijos=args.get("hijos", 0))
    raise ValueError(f"Herramienta desconocida: {nombre}")


def _contexto(s: Session) -> str:
    hoy = date.today()
    r = api.resumen(s=s)
    r.pop("historico", None)
    a = api.ver_autonomo(anio=hoy.year, s=s)
    autonomo = {k: a[k] for k in ("anio", "trimestres", "ingresos_declarados", "pagado_iva", "pagado_irpf", "total_facturado", "por_cliente")}
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

Qué herramienta usar: para «cuánto debo / cuánto me toca pagar / tengo dinero apartado», hacienda_hoy (ya trae \
pendiente, hucha, cuota de autónomos y plazos). Para «cuánto me ahorro aportando al plan de pensiones», \
ahorro_fiscal. Para «vendo o sigo alquilando el piso», inmuebles (para el id) y luego vender_o_alquilar. \
Para «en qué gasto», gastos. Para «cómo voy a ir de dinero», prevision. Si una herramienta devuelve un error, \
di qué ha fallado en vez de inventar.

Formato: texto corrido o listas con «- »; títulos cortos con «## » solo si la respuesta tiene varias partes; \
negritas con ** para la cifra clave. Nada de tablas ni HTML.

Datos actuales de la app (JSON):
"""


# Mensajes del historial que se mandan al modelo (el frontal guarda los mismos)
TOPE_MENSAJES = 20


def recortar(mensajes: list[dict], tope: int = TOPE_MENSAJES) -> list[dict]:
    """Los últimos `tope` mensajes, de forma que el primero sea del usuario y no haya dos seguidos del mismo
    papel (la API de Claude rechaza las dos cosas): los repetidos se juntan en uno."""
    limpios: list[dict] = []
    for m in mensajes:
        papel, texto = m.get("role"), str(m.get("content") or "").strip()
        if papel not in ("user", "assistant") or not texto:
            continue
        if limpios and limpios[-1]["role"] == papel:
            limpios[-1] = {"role": papel, "content": limpios[-1]["content"] + "\n\n" + texto}
        else:
            limpios.append({"role": papel, "content": texto})
    limpios = limpios[-tope:]
    while limpios and limpios[0]["role"] != "user":
        limpios.pop(0)
    return limpios


def responder(s: Session, mensajes: list[dict], transport=None, plazo_s: float | None = PLAZO_S) -> dict:
    """mensajes: historial [{role: user|assistant, content: str}]. Devuelve la respuesta y qué consultó."""
    cfg = ia.configuracion(s)

    def ejecutar(nombre: str, args: dict) -> str:
        return json.dumps(_ejecutar(s, nombre, args), ensure_ascii=False, default=str)[:60000]

    conversacion = recortar(mensajes)
    if not conversacion:
        raise ia.ErrorIA("Falta la pregunta")
    texto, consultas = ia.conversar(cfg, SISTEMA + _contexto(s), conversacion, HERRAMIENTAS, ejecutar,
                                    plazo_s=plazo_s, transport=transport)
    return {"respuesta": texto, "consultas": consultas, "proveedor": ia.PROVEEDORES[cfg.proveedor]["nombre"]}
