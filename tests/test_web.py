import io

from fastapi.testclient import TestClient

from finanzas.main import app


def test_flujo_completo():
    with TestClient(app) as c:
        for ruta in ("/", "/cuentas", "/autonomo", "/nominas", "/inmuebles", "/planificacion"):
            assert c.get(ruta).status_code == 200, ruta
        c.post("/cuentas", data={"nombre": "Cuenta Sabadell", "saldo": "1.000,50"})
        r = c.post("/cuentas/1/importar", files={"fichero": ("e.csv", io.BytesIO(
            "Fecha;Concepto;Importe;Saldo\n01/10/2026;ALQUILER PISO;800,00;1800,50\n".encode()), "text/csv")})
        assert "1 movimientos nuevos" in r.text
        c.post("/autonomo/facturas", data={"numero": "2026-001", "cliente": "Aciturri", "fecha": "2026-10-01",
                                           "base": "4000", "tipo_iva": "21", "tipo_retencion": "15"})
        assert "840,00 €" in c.get("/autonomo?anio=2026").text
        c.post("/inmuebles", data={"nombre": "Piso alquilado", "uso": "alquiler", "precio_compra": "150000",
                                   "valor_catastral": "80000", "valor_catastral_construccion": "40000"})
        c.post("/inmuebles/1/hipoteca", data={"capital_inicial": "120000", "tipo_interes_anual": "2.5",
                                              "fecha_inicio": "2020-01-15", "plazo_meses": "300"})
        c.post("/inmuebles/1/contrato", data={"fecha_inicio": "2021-01-01", "renta_mensual": "800"})
        c.post("/contratos/1/renta", data={"desde": "2026-01-01", "renta_mensual": "650"})
        assert "650,00 € desde 01/01/2026" in c.get("/inmuebles").text
        c.post("/inmuebles", data={"nombre": "Casa obra nueva", "tipo": "inmueble_en_construccion",
                                   "uso": "vivienda_habitual"})
        c.post("/pagos", data={"concepto": "Reserva", "fecha": "2026-01-10", "importe": "6000", "activo_id": "2",
                               "pagado": "1"})
        c.post("/objetivos", data={"nombre": "Boda", "tipo": "boda", "fecha_objetivo": "2027-09-01",
                                   "importe_objetivo": "20000"})
        panel = c.get("/").text
        assert "Piso alquilado" in panel and "Casa obra nueva" in panel
        assert "Rendimiento a declarar" in c.get("/inmuebles").text
        assert "al mes para llegar" in c.get("/planificacion").text
