"""Lo ya presentado a Hacienda: casillas del justificante y si un modelo está presentado (y por cuánto)."""
import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas.models import Declaracion


def casillas(d) -> dict:
    """Casillas (JSON) de una declaración o de cualquier cosa con `casillas`; `{}` si no hay o no se pueden leer."""
    try:
        return json.loads(d.casillas) if d and d.casillas else {}
    except ValueError:
        return {}


def presentada(s: Session, modelo: str, anio: int, periodo: str) -> bool:
    return s.scalar(select(Declaracion.id).where(Declaracion.modelo == modelo, Declaracion.ejercicio == anio,
                                                 Declaracion.periodo == periodo).limit(1)) is not None


def importe_presentado(s: Session, modelo: str, anio: int, periodo: str) -> float | None:
    """Lo ingresado por ese modelo y periodo («1T», «0A»...); con complementarias, la suma de todas. None si no está."""
    decl = s.scalars(select(Declaracion).where(Declaracion.modelo == modelo, Declaracion.ejercicio == anio,
                                               Declaracion.periodo == periodo)).all()
    return float(sum((d.importe for d in decl), Decimal(0))) if decl else None
