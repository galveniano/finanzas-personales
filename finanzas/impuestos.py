"""Impuestos: editar una declaración ya apuntada (resultado, importe, fecha y notas)."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finanzas import auth, db
from finanzas.models import Declaracion

router = APIRouter(prefix="/api", dependencies=[Depends(auth.requiere_sesion)])
SesionDB = Depends(db.get_session)
RESULTADOS = ("ingresar", "devolver", "compensar", "negativa", "cero", "domiciliar", "otro")


class DeclaracionPatch(BaseModel):
    resultado: str | None = None
    importe: Decimal | None = None
    fecha_presentacion: date | None = None
    notas: str | None = None


@router.patch("/declaraciones/{declaracion_id}")
def actualizar_declaracion(declaracion_id: int, datos: DeclaracionPatch, s: Session = SesionDB):
    """Lo que no llegue (None) no se toca. El importe se guarda con signo según el resultado: negativo si es a
    devolver o a compensar, positivo si es a ingresar o domiciliar."""
    d = s.get(Declaracion, declaracion_id)
    if d is None:
        raise HTTPException(404, f"No existe la declaración {declaracion_id}")
    if datos.resultado is not None:
        if datos.resultado not in RESULTADOS:
            raise HTTPException(400, "Ese resultado no existe")
        d.resultado = datos.resultado
    if datos.importe is not None:
        d.importe = datos.importe
    if datos.fecha_presentacion is not None:
        d.fecha_presentacion = datos.fecha_presentacion
    if datos.notas is not None:
        d.notas = datos.notas.strip()
    if d.resultado in ("devolver", "compensar"):
        d.importe = -abs(d.importe)
    elif d.resultado in ("ingresar", "domiciliar"):
        d.importe = abs(d.importe)
    s.commit()
    return {"ok": True, "importe": float(d.importe), "resultado": d.resultado}
