from decimal import Decimal

from fastapi.testclient import TestClient

from finanzas.importers.aeat import interpretar
from finanzas.main import app

PORTADA = """INFORMACIÓN DE LA PRESENTACIÓN DE LA DECLARACIÓN
Modelo 303
Presentación realizada el: 28-01-2025 a las 14:25:57
Expediente/Referencia (nº registro asignado): 202430300000000N
Código Seguro de Verificación: ABCDEFGH12345678
Número de justificante: 3030000000001
En calidad de: Titular
INGRESAR
NRC: 3030000000001XXXXXXX IMPORTE: 2.114,72
"""


def test_justificante_303():
    j = interpretar([PORTADA, "Ejercicio Período\n2024 4T\n"])
    assert (j.modelo, j.ejercicio, j.periodo, j.resultado) == ("303", 2024, "4T", "ingresar")
    assert j.importe == Decimal("2114.72") and j.csv == "ABCDEFGH12345678"
    assert j.fecha_presentacion.isoformat() == "2025-01-28"


def test_renta_a_devolver_sin_periodo():
    portada = PORTADA.replace("Modelo 303", "Modelo 100").replace("INGRESAR", "DEVOLVER") \
        .replace("202430300000000N", "202510000000000X").replace("2.114,72", "845,10")
    j = interpretar([portada])
    assert (j.modelo, j.ejercicio, j.periodo, j.resultado) == ("100", 2025, "0A", "devolver")
    assert j.importe == Decimal("-845.10")


def test_declaraciones_api():
    with TestClient(app) as c:
        r = c.post("/api/declaraciones/pdf", files=[("ficheros", ("x.pdf", b"no es un pdf", "application/pdf"))])
        assert r.json()["resultados"][0]["ok"] is False
        assert c.post("/api/declaraciones", json={"modelo": "130", "ejercicio": 2025, "periodo": "2T",
                                                  "importe": 300}).status_code == 200
        assert c.post("/api/declaraciones", json={"modelo": "100", "ejercicio": 2024, "periodo": "0A",
                                                  "resultado": "devolver", "importe": 500}).status_code == 200
        d = c.get("/api/declaraciones").json()
        anios = {a["ejercicio"]: a for a in d["por_anio"]}
        assert anios[2025]["pagado"] == 300 and anios[2024]["devuelto"] == 500
