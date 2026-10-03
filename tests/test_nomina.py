import pytest
from fastapi.testclient import TestClient

from finanzas.fiscal.nomina import bruto_para_neto, calcular, seguridad_social_mes, tipo_retencion
from finanzas.main import app


def test_seguridad_social_con_tope():
    assert seguridad_social_mes(2000) == 130.0  # 6,50 %
    assert seguridad_social_mes(5101.20) == seguridad_social_mes(5101.20)
    # Por encima de la base máxima solo suma la cotización de solidaridad (céntimos)
    assert 331.58 < seguridad_social_mes(6000) < 334


def test_sin_retencion_por_debajo_del_limite():
    assert tipo_retencion(15000, 975) == 0


def test_neto_14_pagas():
    c = calcular(35000, pagas=14)
    assert len(c.meses) == 14 and c.neto_paga_extra > c.neto_mes  # la extra no paga Seguridad Social
    assert 17 < c.tipo_irpf < 19.5
    assert c.neto_anual == pytest.approx(35000 - c.ss_anual - c.irpf_anual, abs=0.05)


def test_hijos_bajan_la_retencion():
    assert tipo_retencion(35000, 2275, hijos=2) < tipo_retencion(35000, 2275)


def test_bruto_para_neto():
    c = bruto_para_neto(2000, pagas=12)
    assert abs(c.neto_mes - 2000) < 0.05


def test_api():
    with TestClient(app) as c:
        assert c.get("/api/nominas/calculo?bruto_anual=30000&pagas=12").json()["pagas"] == 12
        assert c.get("/api/nominas/calculo?pagas=13&bruto_anual=1").status_code == 400
        assert abs(c.get("/api/nominas/calculo?neto_mes=1800").json()["neto_mes"] - 1800) < 0.05
