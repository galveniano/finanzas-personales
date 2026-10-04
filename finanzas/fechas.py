"""Fechas y horas. Las horas se guardan en UTC (sin zona) y se mandan al frontal con la Z,
así se ven en tu hora tanto en Vercel (que va en UTC) como en tu ordenador."""
from datetime import datetime, timezone


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_utc(valor: datetime | None) -> str | None:
    return valor.isoformat(timespec="minutes") + "Z" if valor else None
