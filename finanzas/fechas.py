"""Fechas y horas. Las horas se guardan en UTC (sin zona) y se mandan al frontal con la Z,
así se ven en tu hora tanto en Vercel (que va en UTC) como en tu ordenador."""
from datetime import date, datetime, timezone

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
MESES_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
            "November", "December"]


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_utc(valor: datetime | None) -> str | None:
    return valor.isoformat(timespec="minutes") + "Z" if valor else None


def sumar_meses(d: date, n: int) -> date:
    """`n` meses después (o antes, en negativo), con el día recortado a 28 para que exista en cualquier mes."""
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, min(d.day, 28))
