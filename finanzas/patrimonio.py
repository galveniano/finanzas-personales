"""Patrimonio neto: lo que tienes menos lo que debes, a una fecha."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas.hipoteca import saldo_pendiente
from finanzas.models import Activo, Cuenta, Deuda, InversionPrivada, PagoPrevisto

CERO = Decimal("0")


@dataclass
class Linea:
    nombre: str
    grupo: str
    importe: Decimal
    detalle: str = ""


@dataclass
class Patrimonio:
    fecha: date
    activos: list[Linea] = field(default_factory=list)
    pasivos: list[Linea] = field(default_factory=list)

    @property
    def total_activos(self) -> Decimal:
        return sum((l.importe for l in self.activos), CERO)

    @property
    def total_pasivos(self) -> Decimal:
        return sum((l.importe for l in self.pasivos), CERO)

    @property
    def neto(self) -> Decimal:
        return self.total_activos - self.total_pasivos

    def por_grupo(self) -> dict[str, Decimal]:
        grupos: dict[str, Decimal] = {}
        for l in self.activos:
            grupos[l.grupo] = grupos.get(l.grupo, CERO) + l.importe
        return grupos


def valor_activo(activo: Activo, a_fecha: date) -> tuple[Decimal, str]:
    """Última valoración anterior a la fecha; si no hay, precio de compra.
    Para obra nueva sin entregar, lo ya pagado a la promotora."""
    vals = [v for v in activo.valoraciones if v.fecha <= a_fecha]
    if vals:
        v = vals[-1]
        valor, detalle = v.valor, f"valoración {v.fecha:%d/%m/%Y}"
    else:
        valor, detalle = activo.precio_compra, "precio de compra"
    return (valor * activo.porcentaje_propiedad / 100), detalle


def calcular(session: Session, a_fecha: date | None = None) -> Patrimonio:
    a_fecha = a_fecha or date.today()
    p = Patrimonio(a_fecha)

    for c in session.scalars(select(Cuenta).where(Cuenta.activa)):
        grupo = "Inversiones" if c.tipo == "inversion" else "Liquidez"
        if c.tipo == "tarjeta":
            if c.saldo < 0:
                p.pasivos.append(Linea(c.nombre, "Tarjetas", -c.saldo))
            continue
        p.activos.append(Linea(c.nombre, grupo, c.saldo, c.entidad))

    for a in session.scalars(select(Activo)):
        if a.tipo == "inmueble_en_construccion":
            pagado = sum(
                (pp.importe for pp in session.scalars(
                    select(PagoPrevisto).where(PagoPrevisto.activo_id == a.id, PagoPrevisto.pagado)
                )),
                CERO,
            )
            p.activos.append(Linea(a.nombre, "Inmuebles", pagado, "pagado a la promotora"))
            continue
        valor, detalle = valor_activo(a, a_fecha)
        p.activos.append(Linea(a.nombre, "Inmuebles" if a.tipo.startswith("inmueble") else "Otros",
                               valor, detalle))

    for inv in session.scalars(select(InversionPrivada)):
        detalle = f"NAV a {inv.nav_fecha:%d/%m/%Y}" if inv.nav_fecha else "NAV"
        p.activos.append(Linea(inv.nombre, "Inversiones", inv.nav, f"{inv.gestora} · {detalle}".lstrip(" ·")))

    for d in session.scalars(select(Deuda)):
        p.pasivos.append(Linea(d.nombre, d.tipo.capitalize(), saldo_pendiente(d, a_fecha), d.entidad))

    return p
