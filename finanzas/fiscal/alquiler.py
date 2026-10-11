"""Rendimiento del capital inmobiliario del piso alquilado (IRPF), estimación anual."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable

from finanzas.hipoteca import intereses_anio
from finanzas.models import Activo, ContratoAlquiler, Deuda, GastoInmueble

CERO = Decimal("0")
CENT = Decimal("0.01")
AMORTIZACION_PCT = Decimal("3")

# Tipos de gasto del piso (clave guardada → cómo se llama en la app)
TIPOS_GASTO = {"ibi": "IBI", "comunidad": "Comunidad", "seguro": "Seguro", "reparacion": "Reparación",
               "intereses": "Intereses hipoteca", "suministros": "Suministros", "gestion": "Gestión", "otros": "Otros"}
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


FECHA_LEY_VIVIENDA = date(2023, 5, 26)


def reduccion_por_defecto(fecha_inicio: date) -> Decimal:
    """Reducción del rendimiento del alquiler de vivienda: 60 % en contratos anteriores al 26/05/2023 y 50 %
    en los posteriores (puede ser más en zonas tensionadas, que en Murcia no hay)."""
    return Decimal("60") if fecha_inicio < FECHA_LEY_VIVIENDA else Decimal("50")


def amortizacion_acumulada(activo: Activo, contratos: Iterable[ContratoAlquiler], hasta: date) -> Decimal:
    """Lo amortizado mientras el piso estuvo alquilado: al venderlo, baja el valor de adquisición."""
    base = base_amortizacion(activo)
    meses = 0
    for c in contratos:
        fin = min(c.fecha_fin or hasta, hasta)
        if fin > c.fecha_inicio:
            meses += (fin.year - c.fecha_inicio.year) * 12 + fin.month - c.fecha_inicio.month
    return (base * AMORTIZACION_PCT / 100 * meses / 12).quantize(CENT)


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


def rendimiento_del_anio(activo: Activo, contratos: Iterable[ContratoAlquiler], gastos: Iterable[GastoInmueble],
                         deudas: Iterable[Deuda], anio: int) -> RendimientoAlquiler:
    """Rendimiento del año con los gastos apuntados. Si no hay intereses de ese año apuntados, se añaden
    los de cada hipoteca según su cuadro de amortización."""
    gastos = list(gastos)
    if not any(g.tipo == "intereses" and g.fecha.year == anio for g in gastos):
        for d in deudas:
            gastos.append(GastoInmueble(activo_id=activo.id, fecha=date(anio, 12, 31), tipo="intereses",
                                        importe=intereses_anio(d, anio)))
    return calcular_rendimiento(activo, contratos, gastos, anio)
