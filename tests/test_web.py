import io

from fastapi.testclient import TestClient

from finanzas.main import app


def test_flujo_completo_api():
    with TestClient(app) as c:
        for ruta in ("/resumen", "/cuentas", "/categorias", "/movimientos", "/autonomo", "/nominas",
                     "/inmuebles", "/planificacion", "/sync", "/app/estado", "/sync/historial", "/buscar?q=ab"):
            assert c.get(f"/api{ruta}").status_code == 200, ruta

        cuenta = c.post("/api/cuentas", json={"nombre": "Cuenta Sabadell", "entidad": "Banco Sabadell"}).json()
        r = c.post(f"/api/cuentas/{cuenta['id']}/importar", files={"fichero": ("e.csv", io.BytesIO(
            "Fecha;Concepto;Importe;Saldo\n01/10/2026;ALQUILER PISO;650,00;1800,50\n".encode()), "text/csv")})
        assert r.json()["nuevos"] == 1
        cuentas = {x["id"]: x for x in c.get("/api/cuentas").json()}
        assert cuentas[cuenta["id"]]["saldo"] == 1800.5  # el extracto fija el saldo

        mov = c.get("/api/movimientos?q=ALQUILER PISO").json()["movimientos"][0]
        assert c.patch(f"/api/movimientos/{mov['id']}", json={"categoria_id": 1}).status_code == 200

        c.post("/api/autonomo/facturas", json={"numero": "1", "cliente": "Aciturri", "fecha": "2026-08-01",
                                               "base": 7360, "tipo_iva": 21, "tipo_retencion": 15})
        c.post("/api/autonomo/facturas", json={"numero": "61", "cliente": "Trustportal", "fecha": "2026-08-01",
                                               "base": 6304.56, "tipo_iva": 0, "tipo_retencion": 0})
        a = c.get("/api/autonomo?anio=2026").json()
        t3 = a["trimestres"][2]
        assert t3["iva_resultado"] == 1545.6
        assert t3["retenciones_acumuladas"] == 1104.0
        assert {x["cliente"] for x in a["por_cliente"]} == {"Aciturri", "Trustportal"}

        piso = c.post("/api/inmuebles", json={"nombre": "Piso alquilado", "uso": "alquiler", "precio_compra": 150000,
                                              "valor_catastral": 80000, "valor_catastral_construccion": 40000}).json()
        c.post(f"/api/inmuebles/{piso['id']}/hipotecas", json={"capital_inicial": 120000, "tipo_interes_anual": 2.5,
                                                                 "fecha_inicio": "2020-01-15", "plazo_meses": 300})
        c.post(f"/api/inmuebles/{piso['id']}/contratos", json={"fecha_inicio": "2021-01-01", "renta_mensual": 600})
        fichas = c.get("/api/inmuebles?anio=2026").json()["inmuebles"]
        contrato = next(i for i in fichas if i["nombre"] == "Piso alquilado")["contratos"][0]["id"]
        c.post(f"/api/contratos/{contrato}/rentas", json={"desde": "2026-01-01", "renta_mensual": 650})
        fichas = c.get("/api/inmuebles?anio=2026").json()["inmuebles"]
        ficha = next(i for i in fichas if i["nombre"] == "Piso alquilado")
        assert ficha["contratos"][0]["renta_actual"] == 650
        assert ficha["rendimiento"]["ingresos"] == 7800

        obra = c.post("/api/inmuebles", json={"nombre": "Casa obra nueva", "tipo": "inmueble_en_construccion"}).json()
        c.post("/api/pagos", json={"concepto": "Reserva", "fecha": "2026-01-10", "importe": 6000,
                                   "activo_id": obra["id"], "pagado": True})
        c.post("/api/objetivos", json={"nombre": "Boda", "tipo": "boda", "fecha_objetivo": "2030-09-01",
                                       "importe_objetivo": 20000})
        plan = c.get("/api/planificacion").json()
        assert plan["objetivos"][0]["ahorro_mensual"] > 0

        res = c.get("/api/resumen").json()
        nombres = {l["nombre"] for l in res["lineas_activo"]}
        assert {"Piso alquilado", "Casa obra nueva", "Cuenta Sabadell"} <= nombres

        assert c.post("/api/sync").status_code == 200
        assert len(c.get("/api/resumen").json()["historico"]) == 1  # foto diaria del patrimonio


def test_errores_legibles():
    with TestClient(app) as c:
        r = c.post("/api/sync/sabadell/conectar")
        assert r.status_code == 400 and "Enable Banking" in r.json()["detail"]
        assert c.post("/api/cuentas/999/importar", files={"fichero": ("e.csv", b"x")}).status_code == 404
