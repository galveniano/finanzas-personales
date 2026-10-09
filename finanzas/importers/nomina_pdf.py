"""Lee el recibo de salarios (la nómina en PDF) y saca bruto, Seguridad Social, IRPF y líquido.

Casi todas las nóminas siguen el modelo oficial de recibo (Orden ESS/2098/2014): un bloque de
devengos con su "TOTAL DEVENGADO", las deducciones (contingencias comunes, desempleo, formación
profesional, MEI, IRPF...) con su "TOTAL A DEDUCIR" y el "LÍQUIDO TOTAL A PERCIBIR". Se leen con
reglas fijas; si algo no cuadra, quien llama puede pedírselo al modelo de IA (`HERRAMIENTA`).
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from finanzas.fechas import MESES

IMPORTE =r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}"
# Conceptos de cotización del trabajador
SS = ["CONTINGENCIAS COMUNES", "CONT. COMUNES", "CONT.COMUNES", "C.COMUNES", "DESEMPLEO", "FORMACION PROFESIONAL",
      "FORMACION PROF", "FORM. PROF", "FORMACION", "MEI", "MECANISMO DE EQUIDAD", "SOLIDARIDAD"]


class ErrorNomina(ValueError):
    pass


@dataclass
class LecturaNomina:
    empresa: str
    fecha: date
    bruto: Decimal
    seguridad_social: Decimal
    retencion_irpf: Decimal
    neto: Decimal
    tipo_irpf: Decimal | None = None
    base_irpf: Decimal | None = None
    especie: Decimal = Decimal("0")
    otras_deducciones: Decimal = Decimal("0")
    paga_extra: bool = False
    avisos: list[str] = field(default_factory=list)

    @property
    def cuadra(self) -> bool:
        return abs(self.bruto - self.seguridad_social - self.retencion_irpf - self.otras_deducciones - self.neto) <= 1


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").upper()


def _importe(texto: str) -> Decimal:
    return Decimal(texto.replace(".", "").replace(",", "."))


def _tras(texto: str, etiquetas: list[str], ventana: int = 120) -> Decimal | None:
    """Primer importe que sigue a alguna de las etiquetas (en la misma línea o en las siguientes)."""
    for etiqueta in etiquetas:
        for m in re.finditer(re.escape(etiqueta), texto):
            trozo = texto[m.end():m.end() + ventana]
            importe = re.search(IMPORTE, trozo)
            if importe:
                return _importe(importe.group())
    return None


def _ultimo(linea: str) -> Decimal | None:
    importes = re.findall(IMPORTE, linea)
    return _importe(importes[-1]) if importes else None


def _fecha(texto: str) -> date | None:
    m = re.search(r"\bAL\s+(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", texto) or re.search(
        r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\s*(?:A|AL|-)\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", texto)
    if m:
        g = m.groups()[-3:]
        anio = int(g[2]) + (2000 if len(g[2]) == 2 else 0)
        return date(anio, int(g[1]), int(g[0]))
    for i, mes in enumerate(MESES):
        m = re.search(mes.upper() + r"\s*(?:DE\s*|/|-)?\s*(20\d{2})", texto)
        if m:
            anio, n = int(m.group(1)), i + 1
            siguiente = date(anio + n // 12, n % 12 + 1, 1)
            return date.fromordinal(siguiente.toordinal() - 1)
    return None


def _empresa(paginas: list[str]) -> str:
    texto = paginas[0] if paginas else ""
    if "INDRA" in _sin_tildes(texto):
        return "Indra"
    m = re.search(r"(?:EMPRESA|RAZON SOCIAL)\s*:?\s*([A-Z0-9][^\n]{2,60}?)(?:\s{2,}|\n|C\.?I\.?F)", _sin_tildes(texto))
    if m:
        nombre = re.sub(r",?\s*S\.?\s*[AL]\.?\s*U?\.?$", "", m.group(1).strip()).title()
        return nombre[:80] or "Empresa"
    return "Empresa"


def interpretar(paginas: list[str]) -> LecturaNomina:
    original = "\n".join(paginas)
    if not original.strip():
        raise ErrorNomina("El PDF no tiene texto (¿es una imagen escaneada?)")
    texto = _sin_tildes(original)
    if not any(p in texto for p in ("DEVENGADO", "DEVENGOS", "LIQUIDO", "A PERCIBIR")):
        raise ErrorNomina("No parece una nómina (no encuentro el total devengado ni el líquido)")

    bruto = _tras(texto, ["TOTAL DEVENGADO", "TOTAL DEVENGOS", "TOTAL BRUTO", "IMPORTE BRUTO"])
    deducir = _tras(texto, ["TOTAL A DEDUCIR", "TOTAL DEDUCCIONES", "TOTAL DEDUCIDO"])
    neto = _tras(texto, ["LIQUIDO TOTAL A PERCIBIR", "LIQUIDO A PERCIBIR", "TOTAL A PERCIBIR", "LIQUIDO TOTAL",
                         "NETO A PERCIBIR", "TOTAL NETO", "LIQUIDO"])

    irpf = tipo = None
    ss = Decimal("0")
    ss_encontrada = False
    for linea in texto.splitlines():
        if "BASE" in linea or "TOTAL" in linea or "ACUMULAD" in linea:
            continue
        if re.search(r"I\.?\s?R\.?\s?P\.?\s?F|RETENCION", linea) and irpf is None:
            irpf = _ultimo(linea)
            t = re.search(r"(\d{1,2}[,.]\d{1,2})\s*%", linea) or re.search(
                r"I\.?R\.?P\.?F\.?\D{0,25}?(\d{1,2},\d{2})\b", linea)
            if t:
                tipo = Decimal(t.group(1).replace(",", "."))
        elif any(re.search(r"\b" + re.escape(p), linea) for p in SS):
            importe = _ultimo(linea)
            if importe is not None:
                ss += importe
                ss_encontrada = True

    base_irpf = _tras(texto, ["BASE SUJETA A RETENCION DEL IRPF", "BASE SUJETA A RETENCION", "BASE I.R.P.F",
                              "BASE IRPF", "BASE RETENCION"])
    especie = Decimal("0")
    for linea in texto.splitlines():
        if "ESPECIE" in linea and not re.search(r"BASE|TOTAL|DESCUENTO|DTO|DEDUC", linea):
            especie += _ultimo(linea) or 0

    avisos = []
    if bruto is None and neto is not None and deducir is not None:
        bruto = neto + deducir
    if neto is None and bruto is not None and deducir is not None:
        neto = bruto - deducir
    if bruto is None or neto is None:
        raise ErrorNomina("No encuentro el total devengado o el líquido a percibir")
    if irpf is None:
        irpf = Decimal("0")
        avisos.append("No encuentro la retención de IRPF; la dejo a 0")
    if not ss_encontrada:
        avisos.append("No encuentro las cotizaciones a la Seguridad Social")
    # El tipo es el que aplica la empresa; si no viene, sale de la base (o del bruto)
    if tipo is None and irpf:
        tipo = (irpf / (base_irpf or bruto) * 100).quantize(Decimal("0.01"))
    # Lo que no es Seguridad Social ni IRPF: la especie que se descuenta porque no se cobra en dinero,
    # anticipos, cuotas sindicales, retribución flexible...
    total_ded = deducir if deducir is not None else bruto - neto
    otras = total_ded - ss - irpf
    if otras < -1:
        avisos.append("Las deducciones no cuadran con el total a deducir; revisa la Seguridad Social")
        otras = Decimal("0")
    fecha = _fecha(texto)
    if fecha is None:
        raise ErrorNomina("No encuentro el mes de la nómina")
    extra = bool(re.search(r"PAGA\s*EXTRA|P\.\s?EXTRA|EXTRAORDINARIA|EXTRA\s+(DE\s+)?(JUNIO|JULIO|DICIEMBRE|NAVIDAD|VERANO)",
                           texto))
    lectura = LecturaNomina(
        empresa=_empresa(paginas), fecha=fecha, bruto=bruto, seguridad_social=ss, retencion_irpf=irpf, neto=neto,
        tipo_irpf=tipo, base_irpf=base_irpf, especie=especie, otras_deducciones=max(otras, Decimal("0")),
        paga_extra=extra, avisos=avisos)
    if not lectura.cuadra:
        lectura.avisos.append("Bruto menos deducciones no da el líquido; revisa los importes")
    return lectura


def leer_pdf(contenido: bytes) -> LecturaNomina:
    from finanzas.documentos import texto_pdf

    try:
        paginas = texto_pdf(contenido)
    except Exception as e:  # pypdf lanza muchos tipos distintos con PDFs rotos
        raise ErrorNomina("No puedo abrir el PDF") from e
    return interpretar(paginas)


# --- Con IA, cuando las reglas no bastan ---------------------------------------

HERRAMIENTA = {
    "name": "registrar_nomina",
    "description": "Registra los datos de la nómina (recibo de salarios) leída.",
    "parameters": {
        "type": "object",
        "properties": {
            "empresa": {"type": "string", "description": "Nombre comercial corto de la empresa, sin S.A./S.L."},
            "fecha": {"type": "string", "description": "Último día del periodo de liquidación, AAAA-MM-DD"},
            "paga_extra": {"type": "boolean", "description": "true si es una paga extraordinaria suelta"},
            "bruto": {"type": "number", "description": "Total devengado en euros"},
            "seguridad_social": {"type": "number", "description": "Suma de las cotizaciones del trabajador "
                                 "(contingencias comunes, desempleo, formación, MEI, solidaridad)"},
            "retencion_irpf": {"type": "number", "description": "Retención de IRPF en euros"},
            "tipo_irpf": {"type": "number", "description": "Porcentaje de retención de IRPF"},
            "base_irpf": {"type": "number", "description": "Base sujeta a retención de IRPF"},
            "especie": {"type": "number", "description": "Retribución en especie incluida en el devengado; 0 si no hay"},
            "otras_deducciones": {"type": "number", "description": "Resto de deducciones: especie descontada, "
                                  "anticipos, retribución flexible, cuota sindical..."},
            "neto": {"type": "number", "description": "Líquido total a percibir"},
            "avisos": {"type": "array", "items": {"type": "string"},
                       "description": "Incoherencias que veas, en frases cortas en español"},
        },
        "required": ["empresa", "fecha", "bruto", "seguridad_social", "retencion_irpf", "neto"],
    },
}
PROMPT = ("Lees nóminas españolas (recibos de salarios) para la app de finanzas del trabajador. Extrae los "
          "datos con la herramienta registrar_nomina. Importes en euros; si algo no cuadra, apúntalo en avisos.")


def desde_ia(datos: dict) -> LecturaNomina:
    def d(k: str) -> Decimal:
        return Decimal(str(datos.get(k) or 0)).quantize(Decimal("0.01"))

    try:
        fecha = date.fromisoformat(str(datos.get("fecha"))[:10])
    except ValueError as e:
        raise ErrorNomina("El modelo no ha sabido leer el mes de la nómina") from e
    tipo = datos.get("tipo_irpf")
    lectura = LecturaNomina(
        empresa=str(datos.get("empresa") or "Empresa")[:80], fecha=fecha, bruto=d("bruto"),
        seguridad_social=d("seguridad_social"), retencion_irpf=d("retencion_irpf"), neto=d("neto"),
        tipo_irpf=Decimal(str(tipo)).quantize(Decimal("0.01")) if tipo else None,
        base_irpf=d("base_irpf") or None, especie=d("especie"), otras_deducciones=d("otras_deducciones"),
        paga_extra=bool(datos.get("paga_extra")), avisos=[str(a) for a in datos.get("avisos") or []])
    if not lectura.bruto or not lectura.neto:
        raise ErrorNomina("El modelo no ha encontrado el bruto o el líquido")
    if not lectura.cuadra:
        lectura.avisos.append("Bruto menos deducciones no da el líquido; revisa los importes")
    return lectura
