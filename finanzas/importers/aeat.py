"""Lee los justificantes PDF que descarga la sede de la Agencia Tributaria al presentar un modelo.

La primera página ("Información de la presentación de la declaración") trae el modelo, la fecha,
el CSV, el número de justificante y el resultado (INGRESAR / DEVOLVER... e IMPORTE). El ejercicio
y el periodo están en la cabecera del propio modelo.
"""
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

logging.getLogger("pypdf").setLevel(logging.ERROR)

# Palabra del justificante -> resultado y signo del importe
RESULTADOS = [
    ("A COMPENSAR", "compensar", -1),
    ("COMPENSAR", "compensar", -1),
    ("DEVOLVER", "devolver", -1),
    ("DEVOLUCI", "devolver", -1),
    ("RENUNCIA", "devolver", -1),
    ("DOMICILIA", "domiciliar", 1),
    ("INGRESAR", "ingresar", 1),
    ("INGRESO", "ingresar", 1),
    ("NEGATIVA", "negativa", 0),
    ("SIN ACTIVIDAD", "cero", 0),
    ("RESULTADO CERO", "cero", 0),
]
ANUALES = {"100", "180", "184", "190", "347", "349", "390", "714", "720"}


class ErrorAEAT(ValueError):
    pass


@dataclass
class Justificante:
    modelo: str
    ejercicio: int
    periodo: str
    resultado: str
    importe: Decimal
    fecha_presentacion: date | None
    justificante: str
    csv: str
    casillas: dict = field(default_factory=dict)


def _importe(texto: str) -> Decimal:
    return Decimal(texto.replace(".", "").replace(",", "."))


def interpretar(paginas: list[str]) -> Justificante:
    portada = paginas[0] if paginas else ""
    todo = "\n".join(paginas)

    m = re.search(r"Modelo\s*(\d{3})", portada) or re.search(r"Modelo\s*\n?\s*(\d{3})", todo)
    if not m:
        raise ErrorAEAT("No parece un justificante de la Agencia Tributaria (no encuentro el modelo)")
    modelo = m.group(1)

    fecha = None
    if m := re.search(r"Presentaci[oó]n realizada el:?\s*(\d{2}-\d{2}-\d{4})", portada):
        fecha = datetime.strptime(m.group(1), "%d-%m-%Y").date()
    justificante = m.group(1) if (m := re.search(r"N[uú]mero de justificante:?\s*(\w+)", portada)) else ""
    csv = m.group(1) if (m := re.search(r"C[oó]digo Seguro de Verificaci[oó]n:?\s*([A-Z0-9]{8,})", portada)) else ""

    # Ejercicio y periodo: "2024 4T" en la cabecera del modelo; si no, el ejercicio sale del
    # número de expediente (empieza por el año) y el periodo del tipo de modelo.
    ejercicio, periodo = None, None
    if m := re.search(r"\b(20\d{2})\s+(0A|[1-4]T|0[1-9]|1[0-2])\b", todo):
        ejercicio, periodo = int(m.group(1)), m.group(2)
    elif m := re.search(r"Expediente/Referencia[^:]*:\s*(20\d{2})", portada):
        ejercicio = int(m.group(1))
    if ejercicio is None:
        raise ErrorAEAT("No encuentro el ejercicio en el justificante")
    if periodo is None:
        periodo = "0A" if modelo in ANUALES else ""

    resultado, signo = "otro", 1
    arriba = portada.upper()
    for clave, nombre, s in RESULTADOS:
        if re.search(rf"^\s*{clave}", arriba, re.MULTILINE):
            resultado, signo = nombre, s
            break
    importe = Decimal("0")
    casillas = _casillas_renta(todo) if modelo == "100" else {}
    if modelo == "100":
        casillas["plazos"] = plazos_renta(todo)
    if m := re.search(r"IMPORTE:?\s*(-?[\d.]+,\d{2})", portada, re.IGNORECASE):
        importe = abs(_importe(m.group(1))) * signo
    elif "resultado" in casillas:
        # La renta no trae el importe en la portada: sale de la casilla 670 (negativa si es a devolver)
        importe = Decimal(str(casillas["resultado"]))
        if importe < 0:
            resultado = "devolver"
        elif resultado in ("otro", "devolver", "compensar"):
            resultado = "ingresar"

    return Justificante(modelo, ejercicio, periodo, resultado, importe, fecha, justificante, csv, casillas)


# Casillas de la renta (modelo 100) que usa la app para comparar con su estimación
CASILLAS_RENTA = {
    "0022": "rendimiento_trabajo", "0180": "ingresos_actividad", "0186": "ss_autonomo", "0218": "gastos_actividad",
    "0224": "rendimiento_actividad", "0156": "rendimiento_alquiler", "0155": "imputacion_inmuebles",
    "0435": "base_general", "0460": "base_ahorro", "0595": "cuota", "0596": "retenciones_trabajo",
    "0604": "pagos_130", "0609": "pagos_a_cuenta", "0670": "resultado",
}


def _casillas_renta(texto: str) -> dict:
    """En el PDF de la renta cada importe va seguido de su número de casilla: «38.232,00 0003»."""
    valores = {}
    for cifra, casilla in re.findall(r"(-?[\d.]+,\d{2})\s+(\d{4})\b", texto):
        if casilla in CASILLAS_RENTA and CASILLAS_RENTA[casilla] not in valores:
            valores[CASILLAS_RENTA[casilla]] = float(_importe(cifra))
    return valores


def plazos_renta(texto: str) -> list[dict]:
    """Pagos de una renta a ingresar: los dos plazos si la fraccionaste (60 % y 40 %) o el pago único,
    con el día en que se carga si está domiciliada (si no, la fecha queda vacía)."""
    cargos = [(m.start(), datetime.strptime(m.group(1), "%d/%m/%Y").date().isoformat())
              for m in re.finditer(r"se cargar[aá] el d[ií]a\s*:?\s*(\d{2}/\d{2}/\d{4})", texto)]
    plazos = list(re.finditer(r"Importe del (primer|segundo) plazo[^:]*:\s*([\d.]+,\d{2})", texto))
    lista = []
    for i, m in enumerate(plazos):
        fin = plazos[i + 1].start() if i + 1 < len(plazos) else len(texto)
        fecha = next((f for pos, f in cargos if m.end() <= pos < fin), None)
        lista.append({"plazo": 1 if m.group(1) == "primer" else 2, "importe": float(_importe(m.group(2))), "fecha": fecha})
    if not lista and cargos and (m := re.search(r"Resultado a ingresar o devolver\s*:?\s*([\d.]+,\d{2})", texto)):
        lista.append({"plazo": 1, "importe": float(_importe(m.group(1))), "fecha": cargos[0][1]})
    return lista


def leer_pdf(contenido: bytes) -> Justificante:
    from pypdf import PdfReader

    try:
        lector = PdfReader(io.BytesIO(contenido))
        paginas = [p.extract_text() or "" for p in lector.pages[:20]]
    except Exception as e:
        raise ErrorAEAT(f"No se puede leer el PDF: {e}")
    return interpretar(paginas)
