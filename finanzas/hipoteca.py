"""Cuadro de amortización francés (cuota constante)."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from finanzas.models import Deuda

CENT = Decimal("0.01")


@dataclass
class Cuota:
    numero: int
    fecha: date
    cuota: Decimal
    intereses: Decimal
    amortizado: Decimal
    pendiente: Decimal


def _sumar_meses(d: date, meses: int) -> date:
    m = d.month - 1 + meses
    anio, mes = d.year + m // 12, m % 12 + 1
    dia = min(d.day, 28)
    return date(anio, mes, dia)


def cuota_mensual(capital: Decimal, interes_anual: Decimal, plazo_meses: int) -> Decimal:
    if plazo_meses <= 0:
        return Decimal("0")
    i = interes_anual / 100 / 12
    if i == 0:
        return (capital / plazo_meses).quantize(CENT)
    return (capital * i / (1 - (1 + i) ** -plazo_meses)).quantize(CENT)


def cuadro_amortizacion(deuda: Deuda) -> list[Cuota]:
    if not deuda.fecha_inicio or deuda.plazo_meses <= 0:
        return []
    i = deuda.tipo_interes_anual / 100 / 12
    cuota = cuota_mensual(deuda.capital_inicial, deuda.tipo_interes_anual, deuda.plazo_meses)
    pendiente = deuda.capital_inicial
    filas = []
    for n in range(1, deuda.plazo_meses + 1):
        intereses = (pendiente * i).quantize(CENT)
        amortizado = min(cuota - intereses, pendiente)
        if n == deuda.plazo_meses:
            amortizado = pendiente
        pendiente -= amortizado
        filas.append(Cuota(n, _sumar_meses(deuda.fecha_inicio, n), amortizado + intereses,
                           intereses, amortizado, pendiente))
    return filas


def saldo_pendiente(deuda: Deuda, a_fecha: date) -> Decimal:
    cuadro = cuadro_amortizacion(deuda)
    if deuda.saldo_pendiente_manual is not None:
        # El saldo real que diste en una fecha; desde ahí sigue bajando con cada cuota del cuadro
        pendiente = deuda.saldo_pendiente_manual
        if deuda.saldo_fecha:
            i = deuda.tipo_interes_anual / 100 / 12
            for c in cuadro:
                if deuda.saldo_fecha < c.fecha <= a_fecha and pendiente > 0:
                    pendiente -= min(c.cuota - (pendiente * i).quantize(CENT), pendiente)
        return pendiente
    if not cuadro:
        return deuda.capital_inicial
    pendiente = deuda.capital_inicial
    for c in cuadro:
        if c.fecha > a_fecha:
            break
        pendiente = c.pendiente
    return pendiente


def intereses_anio(deuda: Deuda, anio: int) -> Decimal:
    return sum((c.intereses for c in cuadro_amortizacion(deuda) if c.fecha.year == anio), Decimal("0"))
