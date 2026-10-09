"""Patrimonio neto: lo que tienes menos lo que debes, a una fecha."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas.hipoteca import saldo_pendiente
from finanzas.models import Activo, Cuenta, Deuda, InversionPrivada, PagoPrevisto

CERO = Decimal("0")
# Grupo de cada tipo de deuda en el patrimonio
GRUPO_DEUDA = {"hipoteca": "Hipoteca", "prestamo": "Préstamo", "otro": "Otra deuda"}


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


# Depreciación anual típica de un coche de más de 3 años en el mercado de segunda mano
DEPRECIACION_COCHE = Decimal("0.09")


def valor_activo(activo: Activo, a_fecha: date) -> tuple[Decimal, str]:
    """Última valoración anterior a la fecha; si no hay, precio de compra.
    Para obra nueva sin entregar, lo ya pagado a la promotora."""
    vals = [v for v in activo.valoraciones if v.fecha <= a_fecha]
    if vals:
        v = vals[-1]
        valor, detalle, desde = v.valor, f"valoración {v.fecha:%d/%m/%Y}", v.fecha
    else:
        valor, detalle, desde = activo.precio_compra, "precio de compra", activo.fecha_compra
    if activo.tipo == "vehiculo" and desde and a_fecha > desde:
        # Un coche pierde valor solo: se estima desde la última cifra conocida
        anios = Decimal((a_fecha - desde).days) / Decimal("365.25")
        valor = (valor * (1 - DEPRECIACION_COCHE) ** anios).quantize(Decimal("1"))
        detalle = f"estimado (−{DEPRECIACION_COCHE * 100:.0f} %/año desde {detalle})"
    return (valor * activo.porcentaje_propiedad / 100), detalle


def liquidez(session: Session) -> Decimal:
    """Lo que tienes en cuentas corrientes y de ahorro activas, contando solo tu parte."""
    return sum((c.saldo * c.parte for c in session.scalars(select(Cuenta).where(
        Cuenta.activa, Cuenta.tipo.in_(["corriente", "ahorro"])))), CERO)


def calcular(session: Session, a_fecha: date | None = None, hacienda: dict | None = None) -> Patrimonio:
    """`hacienda`: lo que debes a Hacienda y aún no has pagado (finanzas.hacienda.pendiente), como pasivo."""
    a_fecha = a_fecha or date.today()
    p = Patrimonio(a_fecha)
    if hacienda and hacienda.get("total"):
        p.pasivos.append(Linea("Hacienda (IVA, 130 y renta pendientes)", "Impuestos",
                               Decimal(str(hacienda["total"])), "estimado"))

    for c in session.scalars(select(Cuenta).where(Cuenta.activa)):
        if c.parte == 0:  # se ve en Cuentas pero no es tuya
            continue
        saldo = (c.saldo * c.parte).quantize(Decimal("0.01"))
        detalle = c.entidad + (f" · tu parte, {c.parte * 100:.0f} %" if c.parte < 1 else "")
        grupo = "Inversiones" if c.tipo == "inversion" else "Liquidez"
        if c.tipo == "tarjeta":
            if saldo < 0:
                p.pasivos.append(Linea(c.nombre, "Tarjetas", -saldo))
            continue
        p.activos.append(Linea(c.nombre, grupo, saldo, detalle))

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
        grupo = "Inmuebles" if a.tipo.startswith("inmueble") else "Vehículos" if a.tipo == "vehiculo" else "Otros"
        p.activos.append(Linea(a.nombre, grupo, valor, detalle))

    for inv in session.scalars(select(InversionPrivada)):
        detalle = f"NAV a {inv.nav_fecha:%d/%m/%Y}" if inv.nav_fecha else "NAV"
        p.activos.append(Linea(inv.nombre, "Inversiones", inv.nav, f"{inv.gestora} · {detalle}".lstrip(" ·")))

    for d in session.scalars(select(Deuda)):
        if d.fecha_inicio and d.fecha_inicio > a_fecha:
            continue  # hipoteca prevista, aún sin firmar
        p.pasivos.append(Linea(d.nombre, GRUPO_DEUDA.get(d.tipo, d.tipo.capitalize()), saldo_pendiente(d, a_fecha), d.entidad))

    return p
