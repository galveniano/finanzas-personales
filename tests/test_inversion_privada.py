from datetime import date

from fastapi.testclient import TestClient

from finanzas.main import app


def test_inversion_privada():
    """Fondo con 10.000 € comprometidos: dos llamadas pagadas y tres previstas (datos de ejemplo)."""
    with TestClient(app) as c:
        antes = c.get("/api/resumen").json()["neto"]
        r = c.post("/api/inversiones", json={
            "nombre": "Fondo de prueba", "gestora": "Plataforma", "compromiso": 10000, "fecha_compromiso": "2025-07-01",
            "nav": 2650, "llamadas": [
                {"fecha": "2025-07-15", "importe": 1500, "pagado": True},
                {"fecha": "2026-05-15", "importe": 1500, "pagado": True},
                {"fecha": "2099-05-15", "importe": 2500},
                {"fecha": "2099-11-15", "importe": 2500},
            ]}).json()
        assert r["desembolsado"] == 3000 and r["pendiente"] == 7000 and r["sin_calendario"] == 2000
        assert r["pct_desembolsado"] == 30 and r["tvpi"] == 0.88 and r["resultado"] == -350
        assert r["proxima_llamada"] == {"fecha": "2099-05-15", "importe": 2500}
        assert r["nav_fecha"] == date.today().isoformat()

        # Suma el NAV al patrimonio y las llamadas salen en la planificación
        assert round(c.get("/api/resumen").json()["neto"] - antes, 2) == 2650
        pagos = [p for p in c.get("/api/planificacion").json()["pagos"] if p["inversion"] == "Fondo de prueba"]
        assert len(pagos) == 4 and sum(not p["pagado"] for p in pagos) == 2

        # Se paga una llamada, se añade la que faltaba, se actualiza el NAV y llega una distribución
        c.patch(f"/api/pagos/{pagos[2]['id']}", json={"pagado": True})
        c.post(f"/api/inversiones/{r['id']}/llamadas", json={"fecha": "2099-12-01", "importe": 2000})
        r = c.patch(f"/api/inversiones/{r['id']}", json={"nav": 5000, "distribuido": 1000}).json()
        assert r["desembolsado"] == 5500 and r["sin_calendario"] == 0 and r["tvpi"] == 1.09
        assert c.get("/api/inversiones").json()["totales"]["nav"] >= 5000

        assert c.delete(f"/api/inversiones/{r['id']}").status_code == 200
        assert not [p for p in c.get("/api/planificacion").json()["pagos"] if p["inversion"] == "Fondo de prueba"]
