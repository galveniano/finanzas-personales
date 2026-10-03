"""Rendimiento del capital inmobiliario del piso alquilado (IRPF), estimación anual."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable

from finanzas.models import Activo, ContratoAlquiler, GastoInmueble

CERO = Decimal("0")
CENT = Decimal("0.01")
AMORTIZACION_PCT = Decimal("3")

# Intereses y gastos de reparación/conservación no pueden generar rendimiento negativo
# (el exceso se arrastra 4 años). El resto sí se deduce sin ese límite.
TIPOS_LIMITADOS = {"intereses", "reparacion"}


@dataclass
class RendimientoAlquiler:
    anio: int
    ingresos: Decimal = CERO
    gastos_limitados: Decimal = CERO
    gastos_otros: Decimal = CERO
    amortizacion: Decimal = CERO
    reduccion_pct: Decimal = CERO
    notas: list[str] = field(default_factory=list)

    @property
    def gastos_limitados_aplicables(self) -> Decimal:
        return min(self.gastos_limitados, self.ingresos)

    @property
    def rendimiento_neto(self) -> Decimal:
        return self.ingresos - self.gastos_limitados_aplicables - self.gastos_otros - self.amortizacion

    @property
    def reduccion(self) -> Decimal:
        if self.rendimiento_neto <= 0:
            return CERO
        return (self.rendimiento_neto * self.reduccion_pct / 100).quantize(CENT)

    @property
    def rendimiento_reducido(self) -> Decimal:
        return self.rendimiento_neto - self.reduccion


def meses_alquilado(contrato: ContratoAlquiler, anio: int) -> list[date]:
    """Primer día de cada mes del año en que el contrato estaba vigente."""
    inicio = contrato.fecha_inicio.replace(day=1)
    return [
        d for d in (date(anio, mes, 1) for mes in range(1, 13))
        if d >= inicio and (contrato.fecha_fin is None or d <= contrato.fecha_fin)
    ]


def base_amortizacion(activo: Activo) -> Decimal:
    """3 % sobre el mayor entre coste de adquisición y valor catastral, solo la parte
    de construcción (se excluye el suelo, usando la proporción del catastro)."""
    if activo.valor_catastral <= 0 or activo.valor_catastral_construccion <= 0:
        return CERO
    proporcion = activo.valor_catastral_construccion / activo.valor_catastral
    coste = activo.precio_compra + activo.gastos_compra
    base = max(coste, activo.valor_catastral) * proporcion
    return (base * activo.porcentaje_propiedad / 100).quantize(CENT)


def calcular_rendimiento(
    activo: Activo,
    contratos: Iterable[ContratoAlquiler],
    gastos: Iterable[GastoInmueble],
    anio: int,
) -> RendimientoAlquiler:
    r = RendimientoAlquiler(anio)
    meses_total = 0
    for c in contratos:
        meses = meses_alquilado(c, anio)
        meses_total += len(meses)
        r.ingresos += sum((c.renta_en(m) for m in meses), CERO)
        r.reduccion_pct = c.reduccion_pct
    for g in gastos:
        if g.fecha.year != anio:
            continue
        if g.tipo in TIPOS_LIMITADOS:
            r.gastos_limitados += g.importe
        else:
            r.gastos_otros += g.importe
    base = base_amortizacion(activo)
    r.amortizacion = (base * AMORTIZACION_PCT / 100 * min(meses_total, 12) / 12).quantize(CENT)
    if base == 0:
        r.notas.append("Falta el valor catastral (total y construcción) para calcular la amortización.")
    if r.gastos_limitados > r.ingresos:
        r.notas.append(
            f"Intereses y reparaciones superan los ingresos: {r.gastos_limitados - r.ingresos} € "
            "se pueden compensar en los 4 años siguientes."
        )
    return r
