"""Calendario .ics al que suscribirte desde Google Calendar: los plazos de Hacienda, tus pagos previstos, las
llamadas de capital pendientes, los objetivos con fecha y la caducidad del permiso del banco.

Google Calendar no puede iniciar sesión en la app, así que la dirección lleva un token secreto
derivado de SESSION_SECRET. Solo enseña conceptos y fechas, sin importes."""
import hashlib
import hmac
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas import avisos, config, db
from finanzas.models import ConexionBancaria, InversionPrivada, Objetivo, PagoPrevisto

router = APIRouter()


def token() -> str:
    if len(config.SESSION_SECRET) < 32 and config.AUTH_REQUERIDA:
        raise HTTPException(503, "Falta SESSION_SECRET (al menos 32 caracteres)")
    secreto = (config.SESSION_SECRET or "finanzas-local").encode()
    return hmac.new(secreto, b"calendario-plazos", hashlib.sha256).hexdigest()[:32]


def _texto(v: str) -> str:
    return v.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def eventos(s: Session, hoy: date) -> list[dict]:
    """Lo que va al calendario (desde hace un mes): fecha, título, detalle, un `uid` estable para que Google no
    duplique el evento al actualizar y con cuántos días de antelación avisar."""
    desde = hoy - timedelta(days=30)
    lista = [{"uid": f"{p['fecha']:%Y%m%d}-{hashlib.sha1(p['titulo'].encode()).hexdigest()[:10]}",
              "fecha": p["fecha"], "titulo": p["titulo"], "detalle": p["detalle"], "aviso": 5}
             for p in avisos.plazos(desde, hoy + timedelta(days=400))]
    fondos = {i.id: i for i in s.scalars(select(InversionPrivada))}
    for p in s.scalars(select(PagoPrevisto).where(~PagoPrevisto.pagado, PagoPrevisto.fecha >= desde)):
        fondo = fondos.get(p.inversion_id) if p.inversion_id else None
        detalle = (f"Llamada de capital de {fondo.nombre}" + (f" ({fondo.gestora})" if fondo.gestora else "") + "."
                   if fondo else "Pago previsto apuntado en el Plan.")
        lista.append({"uid": f"pago-{p.id}", "fecha": p.fecha, "titulo": p.concepto, "detalle": detalle, "aviso": 5})
    for o in s.scalars(select(Objetivo).where(Objetivo.fecha_objetivo >= desde)):
        lista.append({"uid": f"objetivo-{o.id}", "fecha": o.fecha_objetivo, "titulo": f"Objetivo: {o.nombre}",
                      "detalle": "La fecha que te pusiste en el Plan.", "aviso": 30})
    for c in s.scalars(select(ConexionBancaria).where(ConexionBancaria.activa, ConexionBancaria.valida_hasta.is_not(None))):
        if c.valida_hasta.date() >= desde:
            lista.append({"uid": f"conexion-{c.id}", "fecha": c.valida_hasta.date(),
                          "titulo": f"Caduca el permiso de {c.banco}",
                          "detalle": "Vuelve a conectar el banco en Ajustes para que las cuentas se sigan sincronizando.",
                          "aviso": 15})
    return sorted(lista, key=lambda e: (e["fecha"], e["titulo"]))


def ics(s: Session, hoy: date | None = None) -> str:
    hoy = hoy or date.today()
    lineas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//finanzas-personales//plazos//ES",
              "X-WR-CALNAME:Plazos de Hacienda y pagos", "CALSCALE:GREGORIAN"]
    for e in eventos(s, hoy):
        dia = e["fecha"]
        lineas += ["BEGIN:VEVENT", f"UID:{e['uid']}@finanzas", f"DTSTAMP:{hoy:%Y%m%d}T000000Z",
                   f"DTSTART;VALUE=DATE:{dia:%Y%m%d}", f"DTEND;VALUE=DATE:{(dia + timedelta(days=1)):%Y%m%d}",
                   f"SUMMARY:{_texto(e['titulo'])}", f"DESCRIPTION:{_texto(e['detalle'])}",
                   "BEGIN:VALARM", f"TRIGGER:-P{e['aviso']}D", "ACTION:DISPLAY", f"DESCRIPTION:{_texto(e['titulo'])}",
                   "END:VALARM", "END:VEVENT"]
    lineas.append("END:VCALENDAR")
    return "\r\n".join(lineas) + "\r\n"


@router.get("/calendario/{clave}.ics")
def calendario(clave: str):
    if not hmac.compare_digest(clave, token()):
        raise HTTPException(404)
    db.asegurar_tablas()
    with db.SessionLocal() as s:
        return Response(ics(s), media_type="text/calendar; charset=utf-8")
