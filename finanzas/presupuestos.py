"""Presupuestos por categoría, suscripciones ocultas y evolución de las inversiones.

Los presupuestos y las suscripciones ocultas se guardan como JSON en la tabla de ajustes, sin modelo propio:
son dos listas pequeñas que cambian poco."""
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas import ajustes, auth, db, sync
from finanzas.fechas import sumar_meses
from finanzas.models import Instantanea

router = APIRouter(prefix="/api", dependencies=[Depends(auth.requiere_sesion)])

CLAVE_PRESUPUESTOS = "presupuestos"
CLAVE_IGNORADAS = "suscripciones_ignoradas"


def _json(s: Session, clave: str, defecto):
    try:
        datos = json.loads(ajustes.leer(s, clave, "") or "null")
    except ValueError:
        return defecto
    return datos if isinstance(datos, type(defecto)) else defecto


def _eur(x: float) -> str:
    return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


# --- Presupuestos ----------------------------------------------------------------

def leer_presupuestos(s: Session) -> dict[str, float]:
    """{categoría: importe al mes}, solo las categorías con presupuesto."""
    limpio = {}
    for categoria, importe in _json(s, CLAVE_PRESUPUESTOS, {}).items():
        try:
            importe = float(importe)
        except (TypeError, ValueError):
            continue
        if importe > 0:
            limpio[categoria] = round(importe, 2)
    return limpio


def guardar_presupuestos(s: Session, datos: dict[str, float | None]) -> dict[str, float]:
    """Vacío, cero o None quitan el presupuesto de esa categoría."""
    limpio = {k.strip(): round(float(v), 2) for k, v in datos.items() if k.strip() and v}
    ajustes.guardar(s, CLAVE_PRESUPUESTOS, json.dumps(limpio, ensure_ascii=False))
    return limpio


@router.get("/gastos/presupuestos")
def ver_presupuestos(s: Session = Depends(db.get_session)):
    return leer_presupuestos(s)


@router.put("/gastos/presupuestos")
def cambiar_presupuestos(datos: dict[str, float | None], s: Session = Depends(db.get_session)):
    """Cuerpo: {categoría: importe al mes}. Sustituye todos los presupuestos."""
    if any(v is not None and v < 0 for v in datos.values()):
        raise HTTPException(400, "Un presupuesto no puede ser negativo")
    return guardar_presupuestos(s, datos)


# --- Suscripciones ocultas ---------------------------------------------------------

def claves_ignoradas(s: Session) -> set[str]:
    return {str(x) for x in _json(s, CLAVE_IGNORADAS, [])}


def ignorar_suscripcion(s: Session, clave: str, ignorada: bool) -> set[str]:
    claves = claves_ignoradas(s)
    (claves.add if ignorada else claves.discard)(clave)
    ajustes.guardar(s, CLAVE_IGNORADAS, json.dumps(sorted(claves), ensure_ascii=False))
    return claves


class SuscripcionPatch(BaseModel):
    ignorada: bool


@router.put("/gastos/suscripciones/{clave}")
def ocultar_suscripcion(clave: str, datos: SuscripcionPatch, s: Session = Depends(db.get_session)):
    """Oculta (o recupera) un cargo que no es una suscripción de verdad; sus cargos pasan a contar como variable."""
    if not clave.strip():
        raise HTTPException(400, "Falta la clave de la suscripción")
    return {"ok": True, "ignoradas": sorted(ignorar_suscripcion(s, clave.strip(), datos.ignorada))}


# --- Avisos de Inicio --------------------------------------------------------------

def avisos(s: Session) -> list[dict]:
    """Suscripciones que suben o se cobran dos veces y presupuestos pasados este mes."""
    from finanzas import gastos  # perezoso: gastos importa este módulo
    lista = []
    for x in gastos.suscripciones(s):
        if not x["activa"]:
            continue
        if x["subida"]:
            lista.append({"nivel": "info", "ir": "/gastos",
                          "texto": f"{x['nombre']} te ha subido de {_eur(x['subida']['antes'])} a {_eur(x['subida']['ahora'])} al mes."})
        if x["cobro_doble"]:
            lista.append({"nivel": "aviso", "texto": f"{x['nombre']} cobrado en dos cuentas este mes.", "ir": "/gastos"})
    presupuestos = leer_presupuestos(s)
    if presupuestos:
        _, por_categoria = gastos.gasto_mes_en_curso(s)
        for categoria, limite in presupuestos.items():
            llevas = por_categoria.get(categoria, 0.0)
            if llevas > limite:
                lista.append({"nivel": "aviso", "ir": "/gastos",
                              "texto": f"Te has pasado del presupuesto de {categoria}: llevas {_eur(llevas)} de {_eur(limite)} este mes."})
    return lista


# --- Evolución de las inversiones ---------------------------------------------------

@router.get("/inversiones/evolucion")
def evolucion_inversiones(meses: int = 12, s: Session = Depends(db.get_session)):
    """Valor de las inversiones (Indexa y private equity) en las fotos diarias de los últimos meses.
    Más ligero que /resumen, que calcula toda la previsión."""
    hoy = date.today()
    desde = sumar_meses(hoy, -max(1, min(meses, 60)))
    fotos = s.execute(select(Instantanea.fecha, Instantanea.inversiones)
                      .where(Instantanea.fecha >= desde).order_by(Instantanea.fecha)).all()
    puntos = [{"fecha": f.isoformat(), "inversiones": float(v or 0)} for f, v in sync.muestrear(fotos, hoy)]
    return {"desde": desde.isoformat(), "hasta": hoy.isoformat(), "puntos": puntos,
            "cambio": round(puntos[-1]["inversiones"] - puntos[0]["inversiones"], 2) if len(puntos) > 1 else None}
