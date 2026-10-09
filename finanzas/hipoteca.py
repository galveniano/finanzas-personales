"""Cuadro de amortización francés (cuota constante).

Dos cuadros: el teórico (desde el capital de la firma) y el vigente, que a partir del saldo real que diste
en una fecha sigue con ese saldo y el tipo actual, como hace el banco al revisar un tipo variable."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from finanzas.fechas import sumar_meses
from finanzas.models import Deuda

CENT = Decimal("0.01")
CERO = Decimal("0")


@dataclass
class Cuota:
    numero: int
    fecha: date
    cuota: Decimal
    intereses: Decimal
    amortizado: Decimal
    pendiente: Decimal


def cuota_mensual(capital: Decimal, interes_anual: Decimal, plazo_meses: int) -> Decimal:
    if plazo_meses <= 0:
        return CERO
    i = interes_anual / 100 / 12
    if i == 0:
        return (capital / plazo_meses).quantize(CENT)
    return (capital * i / (1 - (1 + i) ** -plazo_meses)).quantize(CENT)


def _fechas_cuotas(deuda: Deuda) -> list[tuple[int, date]]:
    """Número y fecha de cada cuota del plazo: una al mes desde la firma."""
    if not deuda.fecha_inicio or deuda.plazo_meses <= 0:
        return []
    return [(k, sumar_meses(deuda.fecha_inicio, k)) for k in range(1, deuda.plazo_meses + 1)]


def _amortizar(fechas: list[tuple[int, date]], saldo: Decimal, cuota: Decimal, interes_anual: Decimal) -> list[Cuota]:
    """Paga `cuota` en cada fecha desde `saldo`: la última cuota salda lo que quede, y si se acaba antes, se para."""
    i = interes_anual / 100 / 12
    pendiente = saldo
    filas = []
    for k, (numero, fecha) in enumerate(fechas):
        if pendiente <= 0:
            break
        intereses = (pendiente * i).quantize(CENT)
        amortizado = pendiente if k == len(fechas) - 1 else min(cuota - intereses, pendiente)
        pendiente -= amortizado
        filas.append(Cuota(numero, fecha, amortizado + intereses, intereses, amortizado, pendiente))
    return filas


def cuadro_amortizacion(deuda: Deuda) -> list[Cuota]:
    """Cuadro teórico: desde el capital de la firma, con su tipo y su plazo."""
    cuota = cuota_mensual(deuda.capital_inicial, deuda.tipo_interes_anual, deuda.plazo_meses)
    return _amortizar(_fechas_cuotas(deuda), deuda.capital_inicial, cuota, deuda.tipo_interes_anual)


def cuadro_desde(deuda: Deuda, saldo: Decimal, desde: date, cuota: Decimal | None = None) -> list[Cuota]:
    """Cuadro desde un saldo en una fecha: las cuotas que quedan del plazo (las posteriores a `desde`) con el tipo
    actual. Sin `cuota` se recalcula para acabar en la fecha prevista (lo que hace el banco al revisar el tipo);
    con `cuota` se mantiene esa y el préstamo acaba antes o después."""
    fechas = [(k, fecha) for k, fecha in _fechas_cuotas(deuda) if fecha > desde]
    if cuota is None:
        cuota = cuota_mensual(saldo, deuda.tipo_interes_anual, len(fechas))
    return _amortizar(fechas, saldo, cuota, deuda.tipo_interes_anual)


def _fecha_saldo_real(deuda: Deuda) -> date | None:
    """Fecha del saldo real que diste (si no la diste, vale desde hoy)."""
    if deuda.saldo_pendiente_manual is None:
        return None
    return deuda.saldo_fecha or date.today()


def cuadro_vigente(deuda: Deuda) -> list[Cuota]:
    """El cuadro que vale hoy: el teórico hasta la fecha del saldo real y, desde ahí, el que sale de ese saldo."""
    teorico = cuadro_amortizacion(deuda)
    desde = _fecha_saldo_real(deuda)
    if desde is None:
        return teorico
    return [c for c in teorico if c.fecha <= desde] + cuadro_desde(deuda, deuda.saldo_pendiente_manual, desde)


def _pendiente_en(cuadro: list[Cuota], inicial: Decimal, a_fecha: date) -> Decimal:
    pendiente = inicial
    for c in cuadro:
        if c.fecha > a_fecha:
            break
        pendiente = c.pendiente
    return pendiente


def saldo_pendiente(deuda: Deuda, a_fecha: date) -> Decimal:
    if deuda.fecha_inicio and deuda.fecha_inicio > a_fecha:
        return CERO  # aún no firmada: es una simulación, no una deuda
    desde = _fecha_saldo_real(deuda)
    if desde is not None and a_fecha >= desde:
        # El saldo real que diste en esa fecha; desde ahí sigue bajando con cada cuota
        saldo = deuda.saldo_pendiente_manual
        return _pendiente_en(cuadro_desde(deuda, saldo, desde), saldo, a_fecha)
    return _pendiente_en(cuadro_amortizacion(deuda), deuda.capital_inicial, a_fecha)


def cuotas_pendientes(deuda: Deuda, desde: date) -> list[Cuota]:
    """Las cuotas del cuadro vigente que quedan por pagar después de `desde`."""
    return [c for c in cuadro_vigente(deuda) if c.fecha > desde]


def intereses_anio(deuda: Deuda, anio: int, cuadro: list[Cuota] | None = None) -> Decimal:
    """Intereses de un año según el cuadro vigente (desde el saldo real, si lo diste)."""
    cuadro = cuadro_vigente(deuda) if cuadro is None else cuadro
    return sum((c.intereses for c in cuadro if c.fecha.year == anio), CERO)
