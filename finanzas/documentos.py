"""Lee un documento (factura emitida o recibida, justificante de Hacienda) y saca sus datos.

Los justificantes de la AEAT se leen con reglas fijas (importers/aeat.py). Para las facturas se
usa el modelo de IA configurado (OpenAI o Claude), porque cada proveedor tiene un formato distinto y las tuyas también varían.
"""
import io
import logging
from dataclasses import dataclass, field

from finanzas import config, ia
from finanzas.importers import aeat

logging.getLogger("pypdf").setLevel(logging.ERROR)

HERRAMIENTA = {
    "name": "registrar_documento",
    "description": "Registra los datos del documento leído.",
    "parameters": {
        "type": "object",
        "properties": {
            "tipo": {"type": "string", "enum": ["emitida", "recibida", "otro"],
                     "description": "emitida: factura que emite el titular a un cliente. recibida: factura o "
                                    "recibo de un proveedor a nombre del titular. otro: cualquier otra cosa."},
            "numero": {"type": "string"},
            "fecha": {"type": "string", "description": "Fecha de la factura, AAAA-MM-DD"},
            "contraparte": {"type": "string", "description": "Cliente si es emitida, proveedor si es recibida. "
                                                             "Nombre comercial corto, sin S.L./Limited."},
            "pais_contraparte": {"type": "string", "description": "Código ISO de dos letras"},
            "concepto": {"type": "string", "description": "Resumen corto de lo facturado"},
            "base": {"type": "number", "description": "Base imponible (neto sin IVA) en euros"},
            "tipo_iva": {"type": "number", "description": "Porcentaje de IVA; 0 si no lleva"},
            "cuota_iva": {"type": "number"},
            "tipo_retencion": {"type": "number", "description": "Porcentaje de retención de IRPF; 0 si no lleva"},
            "total": {"type": "number"},
            "categoria_gasto": {"type": "string", "enum": ["cuota_reta", "gestoria", "software", "equipos",
                                                           "formacion", "suministros", "otros"],
                                "description": "Solo para recibidas"},
            "avisos": {"type": "array", "items": {"type": "string"},
                       "description": "Incoherencias que veas: importes que no cuadran, fechas raras, falta de "
                                      "IVA o retención donde debería haberla, etc. Frases cortas en español."},
        },
        "required": ["tipo", "fecha", "contraparte", "base", "tipo_iva", "total"],
    },
}


@dataclass
class Documento:
    tipo: str  # emitida | recibida | aeat | otro
    datos: dict = field(default_factory=dict)
    justificante: aeat.Justificante | None = None


def texto_pdf(contenido: bytes, max_paginas: int = 4) -> list[str]:
    from pypdf import PdfReader

    lector = PdfReader(io.BytesIO(contenido))
    return [p.extract_text() or "" for p in lector.pages[:max_paginas]]


def _prompt() -> str:
    titular = ", ".join(x for x in (config.NOMBRE_TITULAR, config.NIF_TITULAR) if x)
    quien = (f"El titular es {titular}." if titular else
             "El titular es la persona física que usa la app: en sus facturas emitidas aparece como emisor.")
    return ("Lees documentos de un autónomo español para su app de finanzas. " + quien +
            " Extrae los datos con la herramienta registrar_documento. Usa la base imponible que dice la "
            "factura aunque alguna línea no cuadre, y apunta la incoherencia en avisos. Importes en euros.")


def interpretar(paginas: list[str], nombre: str, cfg: "ia.ConfigIA", transport=None) -> Documento:
    texto = "\n".join(paginas)
    if "Agencia Tributaria" in texto or "Código Seguro de Verificación" in texto:
        try:
            return Documento("aeat", justificante=aeat.interpretar(paginas))
        except aeat.ErrorAEAT:
            pass
    if not texto.strip():
        return Documento("otro", {"avisos": ["El PDF no tiene texto (¿es una imagen escaneada?)"]})
    datos = ia.extraer(cfg, _prompt(), f"Fichero: {nombre}\n\n{texto[:12000]}", HERRAMIENTA, transport)
    return Documento(datos.get("tipo", "otro"), datos)
