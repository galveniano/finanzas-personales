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
