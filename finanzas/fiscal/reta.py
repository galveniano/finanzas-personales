"""Cuota de autónomos por ingresos reales (desde 2023) y devolución por pluriactividad.

Cada año la Seguridad Social compara la base por la que cotizaste con la que te tocaba según tu
rendimiento neto real (el que declaras en la renta) y regulariza: si cotizaste por debajo de la base
mínima de tu tramo te cobra la diferencia; si cotizaste por encima de la máxima, te devuelve.
Además, si trabajas a la vez por cuenta ajena (pluriactividad) y entre los dos regímenes cotizas más
de un tope, devuelve de oficio la mitad del exceso. Todo esto es una estimación orientativa.
"""
from dataclasses import asdict, dataclass

# Tramos de rendimiento neto mensual (hasta) con su base mínima y máxima. 2025 y 2026 tienen la misma
# tabla (Orden PJC/297/2026). Antes de 2025 las bases eran otras: no se estima.
TRAMOS = [
    (670.00, 653.59, 718.94), (900.00, 718.95, 900.00), (1166.70, 849.67, 1166.70),
    (1300.00, 950.98, 1300.00), (1500.00, 960.78, 1500.00), (1700.00, 960.78, 1700.00),
    (1850.00, 1143.79, 1850.00), (2030.00, 1209.15, 2030.00), (2330.00, 1274.51, 2330.00),
    (2760.00, 1356.21, 2760.00), (3190.00, 1437.91, 3190.00), (3620.00, 1519.61, 3620.00),
    (4050.00, 1601.31, 4050.00), (6000.00, 1732.03, 5101.20), (float("inf"), 1928.10, 5101.20),
]
TABLAS = {2025: TRAMOS, 2026: TRAMOS}
# Tipo total de cotización (contingencias comunes 28,3 %, profesionales, cese, formación y MEI)
TIPO = {2025: 31.40, 2026: 31.50}
TIPO_CONTINGENCIAS_COMUNES = 28.30
# Régimen general: contingencias comunes de empresa (23,60 %) y trabajador (4,70 %)
TIPO_CC_GENERAL = 28.30
BASE_MAXIMA_GENERAL = {2025: 4909.50, 2026: 5101.20}
# Tope de cotización por contingencias comunes entre los dos regímenes para la devolución por pluriactividad
TOPE_PLURIACTIVIDAD = {2025: 16672.66, 2026: 17323.68}
GASTOS_GENERICOS = 0.07  # el rendimiento para cotizar se reduce un 7 % (3 % si eres societario)


@dataclass
class Regularizacion:
    anio: int
    rendimiento_neto: float  # el de la renta (o el previsto), antes de restar la cuota
    cuota_pagada: float
    rendimiento_computable_mes: float
    tramo: int
    base_minima: float
    base_maxima: float
    cuota_minima_anual: float
    cuota_maxima_anual: float
    a_pagar: float  # lo que reclamaría la Seguridad Social (estimado)
    a_devolver: float  # lo que devolvería por cotizar de más en tu tramo
    devolucion_pluriactividad: float
    fuente: str
    tipo: float  # tipo total de cotización del año, en %
    base_cotizada_mes: float  # la base mensual a la que equivale la cuota que pagas (cuota / 12 / tipo)

    def a_dict(self) -> dict:
        return asdict(self)


def anio_tabla(anio: int) -> int | None:
    """El año cuya tabla se usa: el suyo si la tiene; para los años posteriores a la última tabla, esa última
    (hasta que se actualice); para los anteriores a 2025 ninguno (las bases eran otras: no se estima)."""
    if anio in TABLAS:
        return anio
    ultimo = max(TABLAS)
    return ultimo if anio > ultimo else None


def tramo(rendimiento_mes: float, anio: int) -> tuple[int, float, float]:
    for i, (hasta, minima, maxima) in enumerate(TABLAS[anio], start=1):
        if rendimiento_mes <= hasta:
            return i, minima, maxima
    raise AssertionError("inalcanzable")


def devolucion_pluriactividad(anio: int, cuota_reta: float, bruto_nomina: float) -> float:
    """La mitad de lo que las contingencias comunes de los dos regímenes superan el tope, como mucho la mitad
    de lo cotizado por contingencias comunes como autónomo."""
    anio = anio_tabla(anio)
    if anio is None or not cuota_reta or not bruto_nomina:
        return 0.0
    base_general = min(bruto_nomina / 12, BASE_MAXIMA_GENERAL[anio]) * 12
    cc_general = base_general * TIPO_CC_GENERAL / 100
    cc_reta = cuota_reta * TIPO_CONTINGENCIAS_COMUNES / TIPO[anio]
    exceso = cc_general + cc_reta - TOPE_PLURIACTIVIDAD[anio]
    return round(max(min(exceso * 0.5, cc_reta * 0.5), 0.0), 2)


def regularizar(anio: int, rendimiento_neto: float, cuota_pagada: float, bruto_nomina: float = 0.0,
                fuente: str = "") -> Regularizacion | None:
    """Compara lo cotizado con lo que toca. El rendimiento para cotizar es el neto de la actividad más la
    propia cuota (que en la renta resta como gasto), menos el 7 %."""
    tabla = anio_tabla(anio)
    if tabla is None:
        return None
    if tabla != anio:
        fuente = f"{fuente} (tramos de {tabla}, pendientes de actualizar)".strip()
    computable = (rendimiento_neto + cuota_pagada) * (1 - GASTOS_GENERICOS) / 12
    t, minima, maxima = tramo(computable, tabla)
    tipo = TIPO[tabla] / 100
    cuota_min, cuota_max = minima * 12 * tipo, maxima * 12 * tipo
    return Regularizacion(
        anio=anio, rendimiento_neto=round(rendimiento_neto, 2), cuota_pagada=round(cuota_pagada, 2),
        rendimiento_computable_mes=round(computable, 2), tramo=t, base_minima=minima, base_maxima=maxima,
        cuota_minima_anual=round(cuota_min, 2), cuota_maxima_anual=round(cuota_max, 2),
        a_pagar=round(max(cuota_min - cuota_pagada, 0.0), 2), a_devolver=round(max(cuota_pagada - cuota_max, 0.0), 2),
        devolucion_pluriactividad=devolucion_pluriactividad(anio, cuota_pagada, bruto_nomina), fuente=fuente,
        tipo=TIPO[tabla], base_cotizada_mes=round(cuota_pagada / 12 / tipo, 2))
