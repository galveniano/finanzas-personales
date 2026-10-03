"""Carga en bloque, rentabilidad del alquiler, coche que se deprecia e hipoteca con saldo real (datos inventados)."""
import json
from datetime import date, timedelta

from fastapi.testclient import TestClient

from finanzas.main import app

HOY = date.today()
DATOS = {
    "activos": [
        {"nombre": "Piso ejemplo", "tipo": "inmueble", "uso": "alquiler", "fecha_compra": "2019-05-01",
         "precio_compra": 80000, "gastos_compra": 0,
         "hipotecas": [{"nombre": "Hipoteca ejemplo", "capital_inicial": 50000, "tipo_interes_anual": 2,
                        "fecha_inicio": "2019-05-01", "plazo_meses": 240, "saldo_pendiente_manual": 30000,
                        "saldo_fecha": (HOY - timedelta(days=70)).isoformat()}],
         "contratos": [{"fecha_inicio": "2022-01-01", "renta_mensual": 500}],
         "gastos": [{"fecha": HOY.isoformat(), "tipo": "comunidad", "importe": 400},
                    {"fecha": HOY.isoformat(), "tipo": "intereses", "importe": 999}]},
        {"nombre": "Casa ejemplo", "tipo": "inmueble_en_construccion", "precio_compra": 200000,
         "pagos": [{"concepto": "Entregas", "fecha": "2025-01-01", "importe": 30000, "pagado": True},
                   {"concepto": "Llave", "fecha": "2027-06-01", "importe": 170000}]},
        {"nombre": "Coche ejemplo", "tipo": "vehiculo", "fecha_compra": (HOY - timedelta(days=730)).isoformat(),
         "precio_compra": 20000},
    ],
    "inversiones": [{"nombre": "Fondo ejemplo", "compromiso": 10000, "nav": 3000,
                     "llamadas": [{"concepto": "Llamada 1", "fecha": "2025-03-01", "importe": 3000, "pagado": True}]}],
}


def subir(c, datos):
    return c.post("/api/importar/datos", files={"fichero": ("datos.json", json.dumps(datos).encode(), "application/json")})


def test_importar_bienes_y_rentabilidad():
    with TestClient(app) as c:
        r = subir(c, DATOS)
        assert r.status_code == 200 and all("añadido" in m for m in r.json()["mensajes"])
        assert all("ya existía" in m for m in subir(c, DATOS).json()["mensajes"])  # no duplica

        fichas = {i["nombre"]: i for i in c.get("/api/inmuebles").json()["inmuebles"]}
        piso = fichas["Piso ejemplo"]
        ren = piso["rentabilidad"]
        assert ren["renta_anual"] == 6000 and ren["gastos_anuales"] == 400  # los intereses no cuentan como gasto
        assert ren["bruta"] == 7.5 and ren["neta"] == 7.0 and ren["aportado"] == 30000
        # El saldo real dado hace ~2 meses ha seguido bajando con las cuotas
        assert 29000 < piso["deuda"] < 30000
        assert fichas["Casa ejemplo"]["valor"] == 30000 and fichas["Casa ejemplo"]["rentabilidad"] is None

        coche = fichas["Coche ejemplo"]
        assert 16000 < coche["valor"] < 17000 and "estimado" in coche["valor_detalle"]
        grupos = {g["grupo"]: g["importe"] for g in c.get("/api/resumen").json()["grupos"]}
        assert grupos["Vehículos"] == coche["valor"]
        assert any(i["nombre"] == "Fondo ejemplo" for i in c.get("/api/inversiones").json()["inversiones"])


def test_importar_rechaza_basura_sin_guardar_nada():
    with TestClient(app) as c:
        malo = {"activos": [{"nombre": "Bien A", "tipo": "inmueble"}, {"nombre": "Bien B", "fecha_compra": "ayer"}]}
        assert subir(c, malo).status_code == 400
        assert not any(i["nombre"] == "Bien A" for i in c.get("/api/inmuebles").json()["inmuebles"])
        assert c.post("/api/importar/datos", files={"fichero": ("x.json", b"no es json", "application/json")}).status_code == 400


def test_hipoteca_prevista_no_es_deuda_y_entra_en_la_prevision():
    from datetime import date
    with TestClient(app) as c:
        obra = c.post("/api/inmuebles", json={"nombre": "Obra de prueba", "tipo": "inmueble_en_construccion"}).json()
        futuro = date(date.today().year + 1, date.today().month, 1).isoformat()
        c.post(f"/api/inmuebles/{obra['id']}/hipotecas", json={"nombre": "Hipoteca prevista", "entidad": "Banco ejemplo",
               "capital_inicial": 100000, "tipo_interes_anual": 3, "fecha_inicio": futuro, "plazo_meses": 240})
        ficha = next(i for i in c.get("/api/inmuebles").json()["inmuebles"] if i["nombre"] == "Obra de prueba")
        [h] = ficha["hipotecas"]
        assert h["futura"] and h["pendiente"] == 0 and ficha["deuda"] == 0
        assert "Hipoteca prevista" not in {l["nombre"] for l in c.get("/api/resumen").json()["lineas_pasivo"]}
        c.put("/api/prevision/supuestos", json={"nomina": {"bruto_anual": 30000, "pagas": 12}})
        meses = c.get("/api/prevision?meses=24").json()["meses"]
        assert any(m["pagos_previstos"] >= h["cuota"] - 0.01 for m in meses)
        c.put("/api/prevision/supuestos", json={})
        assert c.delete(f"/api/deudas/{h['id']}").status_code == 200
        ficha = next(i for i in c.get("/api/inmuebles").json()["inmuebles"] if i["nombre"] == "Obra de prueba")
        assert ficha["hipotecas"] == []


def test_reimportar_corrige_el_inmueble():
    datos = {"activos": [{"nombre": "Piso corregible", "tipo": "inmueble", "uso": "alquiler", "precio_compra": 70000,
                          "contratos": [{"fecha_inicio": "2023-01-01", "renta_mensual": 500}],
                          "gastos": [{"fecha": "2019-01-01", "tipo": "comunidad", "importe": 300}]}]}
    with TestClient(app) as c:
        subir(c, datos)
        datos["activos"][0].update({
            "precio_compra": 75000, "gastos_compra": 2000, "fecha_compra": "2018-03-01", "valor_catastral": 40000,
            "valor_catastral_construccion": 30000,
            "contratos": [{"fecha_inicio": "2018-03-01", "renta_mensual": 450,
                           "cambios": [{"desde": "2019-03-01", "renta_mensual": 500}]}],
            "gastos": [{"fecha": "2019-01-01", "tipo": "comunidad", "importe": 360},
                       {"fecha": "2019-01-01", "tipo": "ibi", "importe": 200}]})
        assert "actualizado" in subir(c, datos).json()["mensajes"][0]
        subir(c, datos)  # dos veces no duplica
        piso = next(i for i in c.get("/api/inmuebles?anio=2019").json()["inmuebles"] if i["nombre"] == "Piso corregible")
        assert piso["precio_compra"] == 75000 and piso["valor_catastral_construccion"] == 30000
        [contrato] = piso["contratos"]
        assert contrato["fecha_inicio"] == "2018-03-01" and contrato["renta_actual"] == 500 and len(contrato["cambios"]) == 1
        assert piso["rendimiento"]["ingresos"] == 450 * 2 + 500 * 10
