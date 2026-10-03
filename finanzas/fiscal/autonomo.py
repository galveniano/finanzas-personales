"""Estimaciones trimestrales del autónomo: modelo 303 (IVA) y modelo 130 (pago fraccionado IRPF).

Son estimaciones orientativas en estimación directa simplificada. No sustituyen la
presentación real ni el criterio de un asesor.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable

from finanzas.models import Factura, GastoAutonomo

CERO = Decimal("0")
CENT = Decimal("0.01")


def trimestre_de(d: date) -> int:
    return (d.month - 1) // 3 + 1


def limites_trimestre(anio: int, trimestre: int) -> tuple[date, date]:
    inicio = date(anio, 3 * (trimestre - 1) + 1, 1)
    fin_mes = 3 * trimestre
    fin = date(anio + 1, 1, 1) if fin_mes == 12 else date(anio, fin_mes + 1, 1)
    return inicio, fin  # [inicio, fin)


def plazo_presentacion(anio: int, trimestre: int) -> str:
    return {
        1: f"1-20 abril {anio}",
        2: f"1-20 julio {anio}",
        3: f"1-20 octubre {anio}",
        4: f"1-30 enero {anio + 1}",
    }[trimestre]


@dataclass
class Modelo303:
    anio: int
    trimestre: int
    base_repercutida: Decimal = CERO
    iva_repercutido: Decimal = CERO
    base_soportada: Decimal = CERO
    iva_soportado_deducible: Decimal = CERO

    @property
    def resultado(self) -> Decimal:
        return self.iva_repercutido - self.iva_soportado_deducible

    @property
    def plazo(self) -> str:
        return plazo_presentacion(self.anio, self.trimestre)


@dataclass
class Modelo130:
    anio: int
    trimestre: int
    ingresos_acumulados: Decimal = CERO
    gastos_acumulados: Decimal = CERO
    retenciones_acumuladas: Decimal = CERO
    pagos_anteriores: Decimal = CERO
    porcentaje_con_retencion_anio_anterior: Decimal | None = None
    notas: list[str] = field(default_factory=list)

    @property
    def rendimiento_neto(self) -> Decimal:
        return self.ingresos_acumulados - self.gastos_acumulados

    @property
    def resultado(self) -> Decimal:
        bruto = (self.rendimiento_neto * Decimal("0.20")).quantize(CENT)
        return max(CERO, bruto - self.retenciones_acumuladas - self.pagos_anteriores)

    @property
    def exento(self) -> bool:
        """No hay obligación de presentar el 130 si en el año anterior al menos el 70 %
        de los ingresos de la actividad profesional tuvo retención."""
        p = self.porcentaje_con_retencion_anio_anterior
        return p is not None and p >= 70

    @property
    def plazo(self) -> str:
        return plazo_presentacion(self.anio, self.trimestre)


def _en_rango(d: date, inicio: date, fin: date) -> bool:
    return inicio <= d < fin


def calcular_303(
    anio: int, trimestre: int, facturas: Iterable[Factura], gastos: Iterable[GastoAutonomo]
) -> Modelo303:
    inicio, fin = limites_trimestre(anio, trimestre)
    m = Modelo303(anio, trimestre)
    for f in facturas:
        if _en_rango(f.fecha, inicio, fin):
            m.base_repercutida += f.base
            m.iva_repercutido += f.cuota_iva
    for g in gastos:
        if _en_rango(g.fecha, inicio, fin) and g.tipo_iva > 0:
            m.base_soportada += g.base
            m.iva_soportado_deducible += (g.cuota_iva * g.deducible_pct / 100).quantize(CENT)
    return m


def porcentaje_con_retencion(facturas: Iterable[Factura], anio: int) -> Decimal | None:
    total = con_ret = CERO
    for f in facturas:
        if f.fecha.year == anio:
            total += f.base
            if f.tipo_retencion > 0:
                con_ret += f.base
    if total == 0:
        return None
    return (con_ret * 100 / total).quantize(CENT)


def calcular_130(
    anio: int, trimestre: int, facturas: Iterable[Factura], gastos: Iterable[GastoAutonomo],
    presentados: dict[int, tuple[Decimal, dict]] | None = None,
) -> Modelo130:
    """El 130 es acumulativo: desde el 1 de enero hasta el final del trimestre,
    restando las retenciones de las facturas y lo ya ingresado en trimestres anteriores.

    `presentados` son los 130 ya presentados por trimestre (importe y casillas). Lo ingresado en
    Hacienda cuenta como pago anterior, y las casillas acumuladas del último presentado sirven de
    punto de partida: solo se suman las facturas posteriores."""
    facturas = list(facturas)
    gastos = list(gastos)
    presentados = presentados or {}
    pagos_previos = CERO
    base = (CERO, CERO, CERO)  # ingresos, gastos y retenciones acumulados ya declarados
    desde = date(anio, 1, 1)
    m = Modelo130(anio, trimestre)
    for t in range(1, trimestre + 1):
        _, fin = limites_trimestre(anio, t)
        m = Modelo130(anio, t, ingresos_acumulados=base[0], gastos_acumulados=base[1],
                      retenciones_acumuladas=base[2], pagos_anteriores=pagos_previos)
        for f in facturas:
            if _en_rango(f.fecha, desde, fin):
                m.ingresos_acumulados += f.base
                m.retenciones_acumuladas += abs(f.retencion)
        for g in gastos:
            if _en_rango(g.fecha, desde, fin):
                m.gastos_acumulados += (g.base * g.deducible_pct / 100).quantize(CENT)
        if t in presentados and t < trimestre:
            importe, casillas = presentados[t]
            pagos_previos += importe
            if "ingresos" in casillas:
                base = tuple(Decimal(str(casillas.get(k, 0))) for k in ("ingresos", "gastos", "retenciones"))
                desde = fin
        else:
            pagos_previos += m.resultado
    m.porcentaje_con_retencion_anio_anterior = porcentaje_con_retencion(facturas, anio - 1)
    if m.exento:
        m.notas.append(
            "En el año anterior más del 70 % de tus ingresos llevaba retención: "
            "no estás obligado a presentar el 130."
        )
    elif m.porcentaje_con_retencion_anio_anterior is None:
        m.notas.append(
            "No hay facturas del año anterior para comprobar la exención del 70 %."
        )
    return m
