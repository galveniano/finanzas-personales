from datetime import date
from decimal import Decimal as D

from finanzas.fiscal import alquiler, autonomo
from finanzas.hipoteca import cuota_mensual
from finanzas.models import Activo, CambioRenta, ContratoAlquiler, Factura, GastoAutonomo, GastoInmueble


def fac(fecha, base, ret="15"):
    return Factura(numero="x", cliente_id=1, fecha=fecha, base=D(base), tipo_iva=D("21"), tipo_retencion=D(ret))


def gasto(fecha, base, iva="21", pct="100"):
    return GastoAutonomo(fecha=fecha, base=D(base), tipo_iva=D(iva), deducible_pct=D(pct))


def test_303_trimestre():
    facturas = [fac(date(2026, 1, 15), "1000"), fac(date(2026, 4, 1), "5000")]
    gastos = [gasto(date(2026, 2, 1), "100"), gasto(date(2026, 3, 1), "100", pct="50")]
    m = autonomo.calcular_303(2026, 1, facturas, gastos)
    assert m.iva_repercutido == D("210.00")
    assert m.iva_soportado_deducible == D("31.50")
    assert m.resultado == D("178.50")


def test_130_acumulado_resta_pagos_previos():
    facturas = [fac(date(2026, 1, 15), "10000", ret="0"), fac(date(2026, 5, 1), "10000", ret="0")]
    gastos = [gasto(date(2026, 1, 20), "2000", iva="0")]
    t1 = autonomo.calcular_130(2026, 1, facturas, gastos)
    assert t1.resultado == D("1520.00")  # 20 % de 8000 − 5 % de difícil justificación (7600)
    t2 = autonomo.calcular_130(2026, 2, facturas, gastos)
    assert t2.pagos_anteriores == D("1520.00")
    assert t2.resultado == D("1900.00")  # 20 % de 18000 − 900 (17100) − 1520


def test_130_con_retencion_y_exencion_70():
    facturas = [fac(date(2025, 6, 1), "5000"), fac(date(2026, 2, 1), "5000")]
    m = autonomo.calcular_130(2026, 1, facturas, [])
    assert m.resultado == D("200.00")  # 20 % de 4750 (5000 − 5 %) = 950 − 750 de retenciones
    assert m.exento  # en 2025 el 100 % de lo facturado llevaba retención


def test_cuota_hipoteca():
    assert cuota_mensual(D("100000"), D("3"), 300) == D("474.21")


def test_rendimiento_alquiler():
    piso = Activo(nombre="Piso", precio_compra=D("150000"), gastos_compra=D("15000"),
                  valor_catastral=D("80000"), valor_catastral_construccion=D("40000"),
                  porcentaje_propiedad=D("100"))
    contrato = ContratoAlquiler(activo_id=1, fecha_inicio=date(2022, 1, 1), renta_mensual=D("800"),
                                reduccion_pct=D("60"))
    gastos = [GastoInmueble(activo_id=1, fecha=date(2026, 3, 1), tipo="ibi", importe=D("400")),
              GastoInmueble(activo_id=1, fecha=date(2026, 12, 31), tipo="intereses", importe=D("2000"))]
    r = alquiler.calcular_rendimiento(piso, [contrato], gastos, 2026)
    assert r.ingresos == D("9600")
    assert r.amortizacion == D("2475.00")  # 3 % de 165000 × 50 %
    assert r.rendimiento_neto == D("4725.00")
    assert r.rendimiento_reducido == D("1890.00")


def test_rendimiento_con_subida_de_renta():
    piso = Activo(nombre="Piso", precio_compra=D("0"), gastos_compra=D("0"), valor_catastral=D("0"),
                  valor_catastral_construccion=D("0"), porcentaje_propiedad=D("100"))
    contrato = ContratoAlquiler(activo_id=1, fecha_inicio=date(2022, 6, 1), renta_mensual=D("600"),
                                reduccion_pct=D("60"))
    contrato.cambios_renta = [CambioRenta(desde=date(2026, 7, 1), renta_mensual=D("650"))]
    r = alquiler.calcular_rendimiento(piso, [contrato], [], 2026)
    assert r.ingresos == D("7500")  # 6 × 600 + 6 × 650
    assert contrato.renta_en(date(2026, 10, 3)) == D("650")
