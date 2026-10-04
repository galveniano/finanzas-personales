"""Previsión de ingresos e impuestos con supuestos inventados."""
import pytest
from fastapi.testclient import TestClient

from finanzas.main import app

SUPUESTOS = {"nomina": {"empresa": "Empresa ejemplo", "bruto_anual": 40000, "variable_pct": 5, "mes_variable": 3, "pagas": 14},
             "clientes": [{"nombre": "Cliente A", "tarifa_hora": 30, "horas_dia": 8, "dias_mes": 20, "iva": 21, "retencion": 15},
                          {"nombre": "Cliente B", "tarifa_hora": 25, "horas_dia": 8, "dias_mes": 20, "iva": 0, "retencion": 0}],
             "gastos_autonomo_mes": 300, "gasto_habitual_mes": 2000, "meses_sin_facturar": [8]}


@pytest.fixture(autouse=True)
def sin_supuestos_al_acabar():
    """La base de datos de los tests es compartida: no dejar supuestos que cambien Autónomo en otros tests."""
    yield
    with TestClient(app) as c:
        c.put("/api/prevision/supuestos", json={})


def test_prevision_meses_e_impuestos():
    with TestClient(app) as c:
        assert c.put("/api/prevision/supuestos", json=SUPUESTOS).status_code == 200
        d = c.get("/api/prevision?meses=12").json()
        assert len(d["meses"]) == 12 and d["supuestos"]["clientes"][1]["nombre"] == "Cliente B"
        meses = {m["mes"][5:]: m for m in d["meses"]}
        normal = next(m for k, m in meses.items() if k not in ("08",))
        # 30·8·20 = 4800 con IVA 21 % y retención 15 %, más 25·8·20 = 4000 sin nada
        assert normal["facturado"] == 8800 and normal["cobros"] == 8800 + 1008 - 720
        assert meses["08"]["facturado"] == 0  # agosto sin facturar
        assert meses["06"]["nomina"] > meses["05"]["nomina"]  # paga extra
        # El 303 y el 130 se pagan en enero, abril, julio y octubre
        trimestrales = [k for k, m in meses.items() if any("(303)" in i["concepto"] for i in m["impuestos"])]
        assert sorted(trimestrales) == ["01", "04", "07", "10"]
        assert any(i["concepto"].startswith("Renta") for i in meses["06"]["impuestos"])
        r = d["anios"][0]
        assert r["cuota"] > 0 and r["retenciones_nomina"] > 0 and r["pagos_130"] > 0
        assert abs(d["meses"][-1]["liquidez"] - d["liquidez_hoy"] - sum(m["neto"] for m in d["meses"])) < 0.05


def test_sin_130_si_casi_todo_lleva_retencion():
    with TestClient(app) as c:
        solo_retenido = {**SUPUESTOS, "clientes": SUPUESTOS["clientes"][:1], "meses_sin_facturar": []}
        c.put("/api/prevision/supuestos", json=solo_retenido)
        d = c.get("/api/prevision").json()
        assert not any("(130)" in i["concepto"] and not i["presentado"] for m in d["meses"] for i in m["impuestos"])
        assert c.put("/api/prevision/supuestos", json={**SUPUESTOS, "nomina": {**SUPUESTOS["nomina"], "pagas": 13}}).status_code == 400


def test_dias_del_ultimo_mes_facturado():
    with TestClient(app) as c:
        c.post("/api/autonomo/facturas", json={"numero": "P-1", "cliente": "Zeta Ejemplo SL", "fecha": "2019-01-31",
                                               "base": 4500, "tipo_iva": 21, "tipo_retencion": 15})
        sup = {**SUPUESTOS, "clientes": [{"nombre": "Zeta Ejemplo", "tarifa_hora": 30, "horas_dia": 10, "dias_mes": None,
                                          "iva": 21, "retencion": 15}]}
        assert c.put("/api/prevision/supuestos", json=sup).status_code == 200
        [cli] = c.get("/api/prevision").json()["clientes"]
        assert cli["dias_mes"] == 15 and "2019-01" in cli["origen_dias"]


def test_autonomo_usa_la_prevision_en_lo_no_presentado():
    from datetime import date
    with TestClient(app) as c:
        c.put("/api/prevision/supuestos", json=SUPUESTOS)
        anio = date.today().year
        trimestres = c.get(f"/api/autonomo?anio={anio}").json()["trimestres"]
        no_presentados = [t for t in trimestres if t["iva_fuente"] != "presentado"]
        assert no_presentados and all(t["iva_fuente"] == "previsto" and t["base_prevista"] is not None for t in no_presentados)


def test_facturado_y_neto_por_anio():
    from datetime import date
    with TestClient(app) as c:
        c.post("/api/autonomo/facturas", json={"numero": "Y-1", "cliente": "Cliente Anual SL", "fecha": "2018-05-10",
                                               "base": 10000, "tipo_iva": 21, "tipo_retencion": 15})
        c.put("/api/prevision/supuestos", json=SUPUESTOS)
        filas = {f["anio"]: f for f in c.get(f"/api/autonomo?anio={date.today().year}").json()["por_anio"]}
        assert filas[2018]["facturado"] == 10000 and 0 < filas[2018]["neto"] < 10000 and not filas[2018]["previsto"]
        actual = filas[date.today().year]
        assert actual["previsto"] and actual["facturado"] >= 8800 * 11


def test_bruto_y_neto_por_fuente():
    with TestClient(app) as c:
        c.put("/api/prevision/supuestos", json=SUPUESTOS)
        r = c.get("/api/prevision").json()["anios"][-1]
        ing = r["ingresos"]
        fuentes = {x["fuente"]: x for x in ing["fuentes"]}
        assert fuentes["Nómina"]["bruto_anual"] == 42000  # 40.000 + 5 % de variable
        # Cada cliente sale aparte, con los gastos de autónomo repartidos (300 al mes en total)
        clientes = [x for x in ing["fuentes"] if x["cliente"]]
        assert {x["fuente"] for x in clientes} >= {"Cliente A", "Cliente B"}
        assert abs(sum(x["gastos_anual"] for x in clientes) - 3600) < 0.05
        # El IRPF repartido entre fuentes suma la cuota de la renta
        assert abs(sum(x["irpf_anual"] for x in ing["fuentes"]) - r["cuota"]) < 0.05
        assert ing["total"]["neto_mes"] < ing["total"]["bruto_mes"]
        assert all(abs(x["neto_anual"] - (x["bruto_anual"] - x["gastos_anual"] - x["irpf_anual"])) < 0.05
                   for x in ing["fuentes"])


def test_cuota_de_autonomos_del_banco():
    import io
    from datetime import date, timedelta
    mes_pasado = date.today().replace(day=1) - timedelta(days=1)
    with TestClient(app) as c:
        cuenta = c.post("/api/cuentas", json={"nombre": "Cuenta cuota", "entidad": "Banco ejemplo"}).json()
        csv = f"Fecha;Concepto;Importe;Saldo\n{mes_pasado:%d/%m/%Y};TGSS COTIZACION 0521;-310,00;1000,00\n"
        c.post(f"/api/cuentas/{cuenta['id']}/importar", files={"fichero": ("e.csv", io.BytesIO(csv.encode()), "text/csv")})
        c.put("/api/prevision/supuestos", json={**SUPUESTOS, "gastos_autonomo_mes": 0})
        d = c.get("/api/prevision").json()
        assert d["gastos_autonomo_mes"] == 310 and "banco" in d["origen_gastos_autonomo"]
        c.put("/api/prevision/supuestos", json=SUPUESTOS)
        assert c.get("/api/prevision").json()["gastos_autonomo_mes"] == 300  # lo puesto a mano manda


def test_nominas_subidas_mandan_en_su_mes():
    from datetime import date
    with TestClient(app) as c:
        c.put("/api/prevision/supuestos", json=SUPUESTOS)
        antes = c.get("/api/prevision").json()["anios"][0]
        anio = antes["anio"]
        r = c.post("/api/nominas", json={"empresa": "Empresa ejemplo", "fecha": f"{anio}-01-28", "bruto": 3000,
                                          "retencion_irpf": 2000, "seguridad_social": 190, "neto": 810})
        assert r.status_code == 200
        despues = c.get("/api/prevision").json()["anios"][0]
        assert despues["retenciones_nomina"] > antes["retenciones_nomina"] + 1000  # 2.000 reales frente a ~800 previstos
        nid = next(x["id"] for x in c.get("/api/nominas").json()["nominas"] if x["fecha"] == f"{anio}-01-28")
        c.delete(f"/api/nominas/{nid}")


def test_dias_planificados_mandan_en_ese_mes():
    with TestClient(app) as c:
        c.put("/api/prevision/supuestos", json=SUPUESTOS)
        mes = next(m["mes"] for m in c.get("/api/prevision").json()["meses"] if not m["mes"].endswith("-08"))
        assert c.put("/api/prevision/dias", json={"cliente": "Cliente A", "mes": mes, "dias": 10}).status_code == 200
        c.put("/api/prevision/supuestos", json=SUPUESTOS)  # guardar supuestos no borra lo planificado
        fila = next(m for m in c.get("/api/prevision").json()["meses"] if m["mes"] == mes)
        assert fila["facturado"] == 30 * 8 * 10 + 4000  # Cliente A 10 días, Cliente B sus 20
        c.put("/api/prevision/dias", json={"cliente": "Cliente A", "mes": mes, "dias": None})
        fila = next(m for m in c.get("/api/prevision").json()["meses"] if m["mes"] == mes)
        assert fila["facturado"] == 8800  # vuelve a los 20 días
        assert c.put("/api/prevision/dias", json={"cliente": "Cliente A", "mes": "nov-2026", "dias": 3}).status_code == 400
