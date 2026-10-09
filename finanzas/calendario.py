"""Plazos de Hacienda como calendario .ics al que suscribirte desde Google Calendar.

Google Calendar no puede iniciar sesión en la app, así que la dirección lleva un token secreto
derivado de SESSION_SECRET. Solo enseña los plazos, sin importes."""
import hashlib
import hmac
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Response

from finanzas import avisos, config

router = APIRouter()


def token() -> str:
    if len(config.SESSION_SECRET) < 32 and config.AUTH_REQUERIDA:
        raise HTTPException(503, "Falta SESSION_SECRET (al menos 32 caracteres)")
    secreto = (config.SESSION_SECRET or "finanzas-local").encode()
    return hmac.new(secreto, b"calendario-plazos", hashlib.sha256).hexdigest()[:32]


def _texto(v: str) -> str:
    return v.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics(hoy: date | None = None) -> str:
    hoy = hoy or date.today()
    lineas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//finanzas-personales//plazos//ES",
              "X-WR-CALNAME:Plazos de Hacienda", "CALSCALE:GREGORIAN"]
    for p in avisos.plazos(hoy - timedelta(days=30), hoy + timedelta(days=400)):
        dia = p["fecha"].strftime("%Y%m%d")
        lineas += ["BEGIN:VEVENT", f"UID:{dia}-{hashlib.sha1(p['titulo'].encode()).hexdigest()[:10]}@finanzas",
                   f"DTSTAMP:{hoy:%Y%m%d}T000000Z", f"DTSTART;VALUE=DATE:{dia}",
                   f"DTEND;VALUE=DATE:{(p['fecha'] + timedelta(days=1)):%Y%m%d}",
                   f"SUMMARY:{_texto(p['titulo'])}", f"DESCRIPTION:{_texto(p['detalle'])}",
                   "BEGIN:VALARM", "TRIGGER:-P5D", "ACTION:DISPLAY", f"DESCRIPTION:{_texto(p['titulo'])}", "END:VALARM",
                   "END:VEVENT"]
    lineas.append("END:VCALENDAR")
    return "\r\n".join(lineas) + "\r\n"


@router.get("/calendario/{clave}.ics")
def calendario(clave: str):
    if not hmac.compare_digest(clave, token()):
        raise HTTPException(404)
    return Response(ics(), media_type="text/calendar; charset=utf-8")
