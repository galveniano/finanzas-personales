from datetime import date
from decimal import Decimal as D

from finanzas.fiscal import autonomo
from finanzas.models import Factura


def _factura(fecha, base, ret):
    return Factura(fecha=fecha, base=D(base), tipo_iva=D(21), tipo_retencion=D(ret))


def test_130_parte_de_lo_presentado():
    facturas = [_factura(date(2019, 2, 1), 9000, 0), _factura(date(2019, 5, 1), 5000, 15)]
    # Sin presentados: 20 % de 13.300 (14.000 − 5 %) − 750 de retención − 1.710 estimados en el 1T
    assert autonomo.calcular_130(2019, 2, facturas, []).resultado == D("200.00")
    # Con el 1T presentado (declaró 10.000 de ingresos y pagó 2.000), se parte de ahí
    # (sus casillas ya llevan restado el 5 % de difícil justificación: 500 de 10.000)
    previos = {1: (D("2000"), {"ingresos": 10000, "gastos": 500, "retenciones": 0})}
    m = autonomo.calcular_130(2019, 2, facturas, [], previos)
    assert m.ingresos_acumulados == D("15000") and m.pagos_anteriores == D("2000")
    assert m.gastos_acumulados == D("0.00")
    assert m.resultado == D("100.00")  # 20 % de 14.250 (15.000 − 5 %) = 2.850 − 750 − 2.000


def test_130_nunca_suma_retenciones_negativas():
    facturas = [_factura(date(2019, 8, 1), 10000, -15)]
    assert autonomo.calcular_130(2019, 3, facturas, []).resultado == D("400.00")
