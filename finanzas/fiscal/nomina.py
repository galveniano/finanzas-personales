"""Calculadora de nómina: de bruto anual a neto de cada mes, y al revés.

Seguridad Social del trabajador y retención de IRPF según el procedimiento general del
Reglamento del IRPF (arts. 80 a 86). Es una estimación: la empresa puede aplicar un tipo de
retención distinto (por ejemplo, si se lo pides más alto), y como también eres autónomo la renta
final no coincide con lo retenido en la nómina.

Parámetros de 2026 (Orden de cotización 2026; escala y reducciones vigentes del RIRPF).
"""
from dataclasses import asdict, dataclass

# --- Seguridad Social 2026 (parte del trabajador) ---------------------------
BASE_MAXIMA_MES = 5101.20
BASE_MINIMA_MES = 1381.20  # grupo 7; para sueldos normales no influye
SS_TRABAJADOR = {
    "contingencias_comunes": 4.70,
    "desempleo": 1.55,  # 1,60 % con contrato temporal
    "formacion": 0.10,
    "mei": 0.15,
}
DESEMPLEO_TEMPORAL = 1.60
# Cotización de solidaridad: tramos sobre la base máxima (mensual) y parte del trabajador
SOLIDARIDAD = [(BASE_MAXIMA_MES * 1.10, 0.19), (BASE_MAXIMA_MES * 1.50, 0.21), (float("inf"), 0.24)]

# --- Retenciones de IRPF ----------------------------------------------------
ESCALA_RETENCION = [(12450, 19), (20200, 24), (35200, 30), (60000, 37), (300000, 45), (float("inf"), 47)]
OTROS_GASTOS = 2000.0
MINIMO_PERSONAL = 5550.0
MINIMO_HIJOS = [2400.0, 2700.0, 4000.0, 4500.0]  # 1º, 2º, 3º y siguientes
# Límite por debajo del cual no se retiene (situación 3, la general), según número de hijos
LIMITE_SIN_RETENCION = {0: 15876.0, 1: 16342.0, 2: 16867.0}


def _escala(base: float) -> float:
    cuota, desde = 0.0, 0.0
    for hasta, tipo in ESCALA_RETENCION:
        if base <= desde:
            break
        cuota += (min(base, hasta) - desde) * tipo / 100
        desde = hasta
    return cuota


def _reduccion_trabajo(rendimiento_neto: float) -> float:
    if rendimiento_neto <= 14852:
        return 7302.0
    if rendimiento_neto <= 17673.52:
        return 7302 - 1.75 * (rendimiento_neto - 14852)
    if rendimiento_neto <= 19747.5:
        return 2364.34 - 1.14 * (rendimiento_neto - 17673.52)
    return 0.0


def seguridad_social_mes(base_mes: float, temporal: bool = False) -> float:
    base = min(max(base_mes, BASE_MINIMA_MES), BASE_MAXIMA_MES)
    tipos = dict(SS_TRABAJADOR, desempleo=DESEMPLEO_TEMPORAL if temporal else SS_TRABAJADOR["desempleo"])
    cuota = base * sum(tipos.values()) / 100
    # Solidaridad: solo sobre lo que supera la base máxima
    exceso, desde = base_mes - BASE_MAXIMA_MES, BASE_MAXIMA_MES
    for hasta, tipo in SOLIDARIDAD:
        if exceso <= 0:
            break
        tramo = min(base_mes, hasta) - desde
        if tramo > 0:
            cuota += tramo * tipo / 100
        desde = hasta
    return round(cuota, 2)


def tipo_retencion(bruto_anual: float, ss_anual: float, hijos: int = 0) -> float:
    """Tipo de retención en %, redondeado a dos decimales como hace el algoritmo de la AEAT."""
    limite = LIMITE_SIN_RETENCION[min(hijos, 2)]
    if bruto_anual <= limite:
        return 0.0
    rendimiento_neto = max(bruto_anual - ss_anual, 0)
    base = max(rendimiento_neto - OTROS_GASTOS - _reduccion_trabajo(rendimiento_neto - OTROS_GASTOS), 0)
    minimo = MINIMO_PERSONAL + sum(MINIMO_HIJOS[min(i, 3)] for i in range(hijos))
    cuota = max(_escala(base) - _escala(minimo), 0)
    # La retención no puede superar el 43 % de lo que exceda del límite exento
    cuota = min(cuota, (bruto_anual - limite) * 0.43)
    return round(cuota / bruto_anual * 100, 2)


@dataclass
class Mes:
    mes: int
    bruto: float
    seguridad_social: float
    irpf: float
    neto: float
    paga_extra: bool


@dataclass
class CalculoNomina:
    bruto_anual: float
    pagas: int
    tipo_irpf: float
    ss_anual: float
    irpf_anual: float
    neto_anual: float
    neto_mes: float  # neto de un mes normal
    neto_paga_extra: float | None
    meses: list[Mes]

    def a_dict(self) -> dict:
        return asdict(self)


def calcular(bruto_anual: float, pagas: int = 14, hijos: int = 0, temporal: bool = False,
             tipo_irpf: float | None = None) -> CalculoNomina:
    """Neto de cada mes. Con 14 pagas, las extras se cobran en junio y diciembre; su Seguridad Social
    ya va prorrateada en los 12 meses, así que en la paga extra solo se descuenta IRPF."""
    if pagas not in (12, 14):
        raise ValueError("Las pagas tienen que ser 12 o 14")
    ss_mes = seguridad_social_mes(bruto_anual / 12, temporal)
    ss_anual = round(ss_mes * 12, 2)
    tipo = tipo_retencion(bruto_anual, ss_anual, hijos) if tipo_irpf is None else tipo_irpf
    paga = bruto_anual / pagas
    meses = []
    for m in range(1, 13):
        for extra in ([False, True] if pagas == 14 and m in (6, 12) else [False]):
            bruto = round(paga, 2)
            ss = 0.0 if extra else ss_mes
            irpf = round(bruto * tipo / 100, 2)
            meses.append(Mes(m, bruto, ss, irpf, round(bruto - ss - irpf, 2), extra))
    normal = next(x for x in meses if not x.paga_extra)
    extra = next((x for x in meses if x.paga_extra), None)
    irpf_anual = round(sum(x.irpf for x in meses), 2)
    return CalculoNomina(
        bruto_anual=round(bruto_anual, 2), pagas=pagas, tipo_irpf=tipo, ss_anual=ss_anual,
        irpf_anual=irpf_anual, neto_anual=round(sum(x.neto for x in meses), 2), neto_mes=normal.neto,
        neto_paga_extra=extra.neto if extra else None, meses=meses,
    )


def bruto_para_neto(neto_mes: float, pagas: int = 14, hijos: int = 0, temporal: bool = False) -> CalculoNomina:
    """Busca el bruto anual que deja ese neto en un mes normal (búsqueda binaria)."""
    bajo, alto = neto_mes * 12, neto_mes * 40
    for _ in range(60):
        medio = (bajo + alto) / 2
        if calcular(medio, pagas, hijos, temporal).neto_mes < neto_mes:
            bajo = medio
        else:
            alto = medio
    return calcular(round(alto, 2), pagas, hijos, temporal)
