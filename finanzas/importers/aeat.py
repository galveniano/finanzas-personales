"""Lee los justificantes PDF que descarga la sede de la Agencia Tributaria al presentar un modelo.

La primera página ("Información de la presentación de la declaración") trae el modelo, la fecha,
el CSV, el número de justificante y el resultado (INGRESAR / DEVOLVER... e IMPORTE). El ejercicio
y el periodo están en la cabecera del propio modelo.
"""
import io
import logging
import re
from dataclasses import dataclass
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
    if m := re.search(r"IMPORTE:?\s*(-?[\d.]+,\d{2})", portada, re.IGNORECASE):
        importe = abs(_importe(m.group(1))) * signo

    return Justificante(modelo, ejercicio, periodo, resultado, importe, fecha, justificante, csv)


def leer_pdf(contenido: bytes) -> Justificante:
    from pypdf import PdfReader

    try:
        lector = PdfReader(io.BytesIO(contenido))
        paginas = [p.extract_text() or "" for p in lector.pages[:4]]
    except Exception as e:
        raise ErrorAEAT(f"No se puede leer el PDF: {e}")
    return interpretar(paginas)
