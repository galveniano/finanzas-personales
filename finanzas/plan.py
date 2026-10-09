"""Plan: los pagos previstos frente al banco (conciliar) y sus avisos.

Un pago previsto «visto en el banco» es un cargo del mismo importe a pocos días de su fecha
(`prevision.emparejar_pagos`, lo mismo que deja esos cargos fuera del gasto habitual)."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas import auth, db, prevision, sync
from finanzas.models import Movimiento, PagoPrevisto

router = APIRouter(prefix="/api", dependencies=[Depends(auth.requiere_sesion)])
SesionDB = Depends(db.get_session)

DIAS_MARGEN = 20  # entre la fecha prevista y el cargo en el banco
DIAS_VENCIDO = 7  # vencido desde hace más de una semana sin marcar ni ver en el banco: aviso


def vistos_en_banco(s: Session) -> dict[int, dict]:
    """Para cada pago previsto que aparece cargado en el banco, el cargo: {id del pago: {movimiento_id, fecha, importe}}."""
    fechas = [p.fecha for p in s.scalars(select(PagoPrevisto)) if p.fecha <= date.today() + timedelta(days=DIAS_MARGEN)]
    if not fechas:
        return {}
    movs = prevision.movimientos_tuyos(s, min(fechas) - timedelta(days=DIAS_MARGEN), date.today() + timedelta(days=1))
    return {pago_id: {"movimiento_id": m.id, "fecha": m.fecha.isoformat(), "importe": round(-m.importe, 2)}
            for pago_id, m in prevision.emparejar_pagos(s, movs, DIAS_MARGEN).items()}


@router.post("/pagos/conciliar")
def conciliar_pagos(s: Session = SesionDB):
    """Marca como pagados los pagos previstos pendientes que ya aparecen cargados en el banco."""
    vistos = vistos_en_banco(s)
    marcados = 0
    for p in s.scalars(select(PagoPrevisto).where(~PagoPrevisto.pagado)):
        if p.id in vistos:
            p.pagado, marcados = True, marcados + 1
    s.commit()
    if marcados:
        sync.guardar_instantanea(s)  # lo pagado de la obra nueva cuenta en el patrimonio
    return {"marcados": marcados}


def avisos(s: Session) -> list[dict]:
    """Pagos previstos que ya aparecen en el banco sin marcar (info) y los vencidos hace más de una semana
    que ni se han marcado ni se ven en el banco (aviso)."""
    hoy = date.today()
    pendientes = s.scalars(select(PagoPrevisto).where(~PagoPrevisto.pagado).order_by(PagoPrevisto.fecha)).all()
    if not pendientes:
        return []
    vistos = vistos_en_banco(s)
    hay_banco = s.scalar(select(Movimiento.id).limit(1)) is not None
    lista = []
    for p in pendientes:
        if p.id in vistos:
            cuando = date.fromisoformat(vistos[p.id]["fecha"])
            lista.append({"nivel": "info", "ir": "/plan",
                          "texto": f"«{p.concepto}» ya aparece cargado en el banco el {cuando:%d/%m}: márcalo como pagado."})
        elif (hoy - p.fecha).days > DIAS_VENCIDO:
            lista.append({"nivel": "aviso", "ir": "/plan",
                          "texto": f"El pago «{p.concepto}» venció el {p.fecha:%d/%m} y "
                                   + ("no aparece en el banco." if hay_banco else "sigue sin marcar como pagado.")})
    return lista
