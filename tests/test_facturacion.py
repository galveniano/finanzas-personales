"""Emitir facturas desde los días trabajados (datos inventados)."""
from fastapi.testclient import TestClient

from finanzas.facturacion import siguiente_numero
from finanzas.main import app


def test_siguiente_numero_respeta_tu_formato():
    assert siguiente_numero(None, None, 2026) == "2026-001"
    assert siguiente_numero("2026-014", 2026, 2026) == "2026-015"
    assert siguiente_numero("F/7", 2026, 2026) == "F/8"
    assert siguiente_numero("045/2026", 2026, 2026) == "046/2026"
    # Nuevo año: si el número lleva el año, se cambia y el contador vuelve a 1
    assert siguiente_numero("2025-045", 2025, 2026) == "2026-001"
    assert siguiente_numero("A-099", 2025, 2026) == "A-100"


def test_dias_no_disponibles_y_documento():
    with TestClient(app) as c:
        r = c.put("/api/facturacion/dias", json={"dias": ["2031-08-03", "2031-08-04"], "tipo": "vacaciones"})
        assert r.status_code == 200
        c.put("/api/facturacion/dias", json={"dias": ["2031-08-05"], "tipo": "no_disponible"})
        c.put("/api/facturacion/dias", json={"dias": ["2031-08-04"], "tipo": None})
        dias = c.get("/api/facturacion").json()["dias_no_disponibles"]
        assert dias["2031-08-03"] == "vacaciones" and dias["2031-08-05"] == "no_disponible" and "2031-08-04" not in dias

        c.put("/api/facturacion/emisor", json={"nombre": "Ana Ejemplo", "nif": "00000000T", "iban": "ES00 0000 0000"})
        c.put("/api/facturacion/clientes/Cliente UK Test", json={"nif": "GB000", "direccion": "1 Test St\nLondon",
                                                                 "idioma": "en"})
        numero = c.get("/api/facturacion/siguiente-numero?anio=2031").json()["numero"]
        r = c.post("/api/autonomo/facturas", json={
            "numero": numero, "cliente": "Cliente UK Test", "fecha": "2031-08-31", "concepto": "Consulting <August>",
            "base": 520, "tipo_iva": 0, "tipo_retencion": 0,
            "detalle": {"horas": 16, "precio_hora": 32.5, "dias": ["2031-08-01", "2031-08-06"]}})
        assert r.status_code == 200, r.text
        fid = r.json()["id"]
        # El número ya está usado: no se repite
        assert c.post("/api/autonomo/facturas", json={"numero": numero, "cliente": "X", "fecha": "2031-09-01",
                                                      "base": 1}).status_code == 400
        assert c.get("/api/facturacion/siguiente-numero?anio=2031").json()["numero"] != numero

        html = c.get(f"/api/autonomo/facturas/{fid}/documento").text
        assert "Invoice" in html and "Ana Ejemplo" in html and "1 Test St<br>London" in html
        assert "€520.00" in html and "Reverse charge" in html and "ES00 0000 0000" in html
        assert "Consulting &lt;August&gt;" in html and "August 1, 6, 2031" in html

        # Editar sin detalle lo conserva; si la base deja de cuadrar, el documento va sin horas
        f = {"numero": numero, "cliente": "Cliente UK Test", "fecha": "2031-08-31", "concepto": "Consulting",
             "base": 600, "tipo_iva": 0, "tipo_retencion": 0}
        assert c.put(f"/api/autonomo/facturas/{fid}", json=f).status_code == 200
        html = c.get(f"/api/autonomo/facturas/{fid}/documento").text
        assert "€600.00" in html and "Hours" not in html
        c.delete(f"/api/autonomo/facturas/{fid}")


def test_documento_espanol_con_iva_y_retencion():
    with TestClient(app) as c:
        r = c.post("/api/autonomo/facturas", json={
            "numero": "T-2031-ES", "cliente": "Cliente ES Test", "fecha": "2031-10-31", "concepto": "Consultoría",
            "base": 6400, "tipo_iva": 21, "tipo_retencion": 15,
            "detalle": {"horas": 160, "precio_hora": 40, "dias": []}})
        fid = r.json()["id"]
        html = c.get(f"/api/autonomo/facturas/{fid}/documento").text
        assert "Factura" in html and "6.400,00 €" in html and "1.344,00 €" in html and "-960,00 €" in html
        assert "6.784,00 €" in html and "31/10/2031" in html and "art. 69" not in html
        c.delete(f"/api/autonomo/facturas/{fid}")
