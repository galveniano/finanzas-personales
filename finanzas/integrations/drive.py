"""Importa facturas y justificantes de Hacienda desde tu Google Drive.

El navegador pide a Google un permiso de solo lectura de Drive (dura una hora) y nos pasa el
token en cada importación. El servidor no lo guarda.

- Facturas emitidas: se crean solas en Autónomo.
- Justificantes de la AEAT: se crean solos en Hacienda (no hace falta clave de IA).
- Facturas recibidas: quedan pendientes para que decidas si son gasto de la actividad.

Un documento se lee una vez. Se vuelve a leer solo si cambia en Drive o si pulsas «Volver a leer»;
los que dieron error no se reintentan en cada importación. Lo que ya has revisado (factura o gasto
apuntados) no vuelve a «pendiente» aunque el fichero cambie.
"""
import json
from datetime import date, datetime
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas import documentos, ia
from finanzas.fechas import ahora_utc
from finanzas.models import Cliente, Declaracion, DocumentoDrive, Factura, GastoAutonomo

API = "https://www.googleapis.com/drive/v3"
CONSULTA = ("mimeType = 'application/pdf' and trashed = false and modifiedTime > '{desde}' and ("
            "name contains 'factura' or name contains 'Factura' or name contains 'FACTURA' or "
            "name contains 'invoice' or name contains 'Invoice' or name contains 'MOD' or "
            "fullText contains 'Agencia Tributaria' or fullText contains 'factura' or fullText contains 'invoice')")
POR_LLAMADA = 5  # ficheros por petición, para no pasar del tiempo máximo de Vercel
DESDE_DEFECTO = "2024-01-01"
# Mensaje de las facturas que esperan a que haya clave de IA (se releen solas cuando la pones)
SIN_CLAVE = "Falta la clave de IA para leerla"


class ErrorDrive(RuntimeError):
    pass


class NumeroRepetido(ValueError):
    """La factura leída lleva un número que ya tiene otra factura: no se crea, se deja para revisar."""


class Drive:
    def __init__(self, token: str, transport=None):
        self.http = httpx.Client(base_url=API, timeout=30, transport=transport,
                                 headers={"Authorization": f"Bearer {token}"})

    def _get(self, ruta: str, **params) -> httpx.Response:
        r = self.http.get(ruta, params=params)
        if r.status_code == 401:
            raise ErrorDrive("El permiso de Google Drive ha caducado. Vuelve a pulsar Importar.")
        if r.status_code != 200:
            raise ErrorDrive(f"Google Drive respondió {r.status_code}: {r.text[:200]}")
        return r

    def candidatos(self, desde: str) -> list[dict]:
        ficheros, pagina = [], None
        while True:
            params = {"q": CONSULTA.format(desde=desde), "pageSize": 200, "orderBy": "modifiedTime desc",
                      "fields": "nextPageToken, files(id, name, modifiedTime, webViewLink)"}
            if pagina:
                params["pageToken"] = pagina
            datos = self._get("/files", **params).json()
            ficheros += datos.get("files", [])
            pagina = datos.get("nextPageToken")
            if not pagina or len(ficheros) >= 1000:
                return ficheros

    def descargar(self, file_id: str) -> bytes:
        return self._get(f"/files/{file_id}", alt="media").content


def _dec(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def _fecha(v: str | None) -> date:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return date.today()


def _crear_factura(s: Session, d: dict) -> Factura:
    nombre = (d.get("contraparte") or "Cliente").strip()[:120]
    cliente = s.scalar(select(Cliente).where(Cliente.nombre.ilike(nombre)))
    if cliente is None:
        cliente = Cliente(nombre=nombre)
        s.add(cliente)
        s.flush()
    numero, fecha = str(d.get("numero") or "")[:40], _fecha(d.get("fecha"))
    existente = s.scalar(select(Factura).where(Factura.cliente_id == cliente.id, Factura.numero == numero,
                                               Factura.fecha == fecha))
    if existente:
        return existente
    if numero and s.scalar(select(Factura.id).where(Factura.numero == numero)):
        raise NumeroRepetido(f"El número {numero} ya existe: revísala")
    f = Factura(numero=numero, cliente_id=cliente.id, fecha=fecha, concepto=d.get("concepto") or "",
                base=_dec(d.get("base")), tipo_iva=_dec(d.get("tipo_iva")), tipo_retencion=_dec(d.get("tipo_retencion")))
    s.add(f)
    s.flush()
    return f


def _crear_declaracion(s: Session, j, contenido: bytes, nombre: str) -> Declaracion:
    d = s.scalar(select(Declaracion).where(Declaracion.modelo == j.modelo, Declaracion.ejercicio == j.ejercicio,
                                           Declaracion.periodo == j.periodo, Declaracion.justificante == j.justificante))
    if d is None:
        d = Declaracion(modelo=j.modelo, ejercicio=j.ejercicio, periodo=j.periodo, justificante=j.justificante)
    d.resultado, d.importe, d.fecha_presentacion, d.csv = j.resultado, j.importe, j.fecha_presentacion, j.csv
    d.nombre_fichero, d.pdf = nombre[:200], contenido
    s.add(d)
    s.flush()
    return d


def procesar(s: Session, doc: DocumentoDrive, contenido: bytes, cfg: ia.ConfigIA, transport=None) -> None:
    try:
        leido = documentos.interpretar(documentos.texto_pdf(contenido), doc.nombre, cfg, transport=transport, s=s)
    except ia.SinClave:
        # Los justificantes de la AEAT ya se han reconocido sin IA; una factura espera a que pongas la clave
        doc.tipo, doc.datos = "otro", "{}"
        doc.estado, doc.mensaje = "pendiente", f"{SIN_CLAVE}: ponla en Ajustes → Asistente (IA)"
        return
    except ia.ErrorIA as e:
        doc.estado, doc.mensaje = "error", str(e)
        return
    except Exception as e:  # PDF roto o protegido
        doc.estado, doc.mensaje = "error", f"No se puede leer el PDF: {e}"
        return
    doc.tipo = leido.tipo
    if leido.tipo == "aeat":
        j = leido.justificante
        doc.declaracion_id = _crear_declaracion(s, j, contenido, doc.nombre).id
        doc.datos = json.dumps({"modelo": j.modelo, "ejercicio": j.ejercicio, "periodo": j.periodo,
                                "importe": float(j.importe), "resultado": j.resultado})
        doc.estado, doc.mensaje = "importado", f"Modelo {j.modelo} {j.periodo} {j.ejercicio}"
        return
    doc.datos = json.dumps(leido.datos, ensure_ascii=False)
    contraparte = leido.datos.get("contraparte")
    if leido.tipo == "emitida":
        try:
            f = _crear_factura(s, leido.datos)
        except NumeroRepetido as e:
            doc.estado, doc.mensaje = "pendiente", str(e)
            return
        doc.factura_id, doc.estado = f.id, "importado"
        doc.mensaje = f"Factura {f.numero} a {contraparte}"
    elif leido.tipo == "recibida" and doc.gasto_id:
        doc.estado, doc.mensaje = "importado", f"Gasto de {contraparte} (ya apuntado)"
    elif leido.tipo == "recibida":
        doc.estado, doc.mensaje = "pendiente", f"Factura de {contraparte}: ¿es gasto de la actividad?"
    else:
        doc.estado, doc.mensaje = "ignorado", "No es una factura"


def _fecha_desde(desde: str) -> str:
    try:
        return date.fromisoformat(desde).isoformat()
    except (TypeError, ValueError):
        raise ErrorDrive(f"La fecha «desde» no es válida: {desde!r} (usa AAAA-MM-DD)")


def importar(s: Session, token: str, desde: str = DESDE_DEFECTO, transport=None) -> dict:
    """Revisa como mucho POR_LLAMADA ficheros nuevos o cambiados desde `desde`. Devuelve cuántos quedan."""
    cfg = ia.configuracion(s)
    drive = Drive(token, transport)
    vistos = {d.drive_id: d for d in s.scalars(select(DocumentoDrive))}
    nuevos = []
    for f in drive.candidatos(f"{_fecha_desde(desde)}T00:00:00"):
        d = vistos.get(f["id"])
        if d is None or d.modificado != f["modifiedTime"]:
            nuevos.append(f)
        elif cfg.lista and d.mensaje.startswith(SIN_CLAVE):  # esperaba la clave de IA y ya la hay
            nuevos.append(f)
    hechos = []
    for f in nuevos[:POR_LLAMADA]:
        doc = vistos.get(f["id"]) or DocumentoDrive(drive_id=f["id"])
        ya_revisado = doc.modificado != f["modifiedTime"] and bool(doc.gasto_id or doc.factura_id)
        doc.nombre, doc.modificado, doc.enlace = f["name"][:250], f["modifiedTime"], f.get("webViewLink", "")[:300]
        doc.revisado = ahora_utc()
        s.add(doc)
        if ya_revisado:  # ya lo apuntaste: un cambio en Drive no lo devuelve a «pendiente»
            doc.estado = "importado"
        else:
            procesar(s, doc, drive.descargar(f["id"]), cfg, transport)
        s.commit()
        hechos.append({"nombre": doc.nombre, "estado": doc.estado, "mensaje": doc.mensaje})
    return {"procesados": hechos, "quedan": max(len(nuevos) - POR_LLAMADA, 0)}


def releer(s: Session, doc: DocumentoDrive, token: str, transport=None) -> DocumentoDrive:
    """«Volver a leer»: descarga el fichero otra vez y lo procesa, esté en error, pendiente o ya leído."""
    cfg = ia.configuracion(s)
    doc.revisado = ahora_utc()
    procesar(s, doc, Drive(token, transport).descargar(doc.drive_id), cfg, transport)
    s.commit()
    return doc


def crear_gasto(s: Session, doc: DocumentoDrive, deducible_pct: Decimal, categoria: str | None = None) -> GastoAutonomo:
    d = json.loads(doc.datos or "{}")
    g = GastoAutonomo(fecha=_fecha(d.get("fecha")), proveedor=(d.get("contraparte") or "")[:120],
                      concepto=d.get("concepto") or doc.nombre, categoria=categoria or d.get("categoria_gasto") or "otros",
                      base=_dec(d.get("base")), tipo_iva=_dec(d.get("tipo_iva")), deducible_pct=deducible_pct)
    s.add(g)
    s.flush()
    doc.gasto_id, doc.estado, doc.mensaje = g.id, "importado", f"Gasto de {g.proveedor}"
    s.commit()
    return g
