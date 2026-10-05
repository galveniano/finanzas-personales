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


def test_renta_resultado_y_casillas():
    from finanzas.importers import aeat as aeat_mod
    portada = ("INFORMACIÓN DE LA PRESENTACIÓN DE LA DECLARACIÓN\nModelo 100 Ejercicio 2019\n"
               "Presentación realizada el: 10-06-2020 a las 10:00:00\nExpediente/Referencia (nº registro asignado): 2019ABC\n"
               "Número de justificante: 1001234567890\nDOMICILIACIÓN DEL IMPORTE A INGRESAR\n")
    cuerpo = ("Rendimiento neto [(18)-(19)-(20)-(21)]\n30.000,00 0022\nSuma de gastos fiscalmente deducibles.\n5.000,00 0218\n"
              "Cuota resultante de la autoliquidación [(587)-(588)]\n12.000,00 0595\nPagos fraccionados\n6.000,00 0604\n"
              "Resultado de la declaración\n-250,50 0670\n")
    j = aeat_mod.interpretar([portada, cuerpo])
    assert (j.modelo, j.ejercicio, j.periodo) == ("100", 2019, "0A")
    assert j.importe == aeat_mod.Decimal("-250.50") and j.resultado == "devolver"
    assert j.casillas["rendimiento_trabajo"] == 30000 and j.casillas["gastos_actividad"] == 5000
    assert j.casillas["cuota"] == 12000 and j.casillas["pagos_130"] == 6000


INGRESO_FRACCIONADO = """Resultado a ingresar o devolver
: 1.000,00
Declaración a Ingresar. Datos del ingreso
 Fraccionamiento del pago en dos plazos
Importe del primer plazo (60% del resultado de la declaración)
: 600,00
Forma de pago
: DOMICILIACIÓN DEL IMPORTE A INGRESAR
El importe de la domiciliación se cargará el día
: 30/06/{a}
Declaración a Ingresar. Datos del ingreso del segundo plazo
 Importe del segundo plazo (40% del resultado de la declaración)
: 400,00
Forma de pago
: DOMICILIACIÓN DEL IMPORTE A INGRESAR
El importe de la domiciliación se cargará el día
: 05/11/{a}
"""


def test_renta_fraccionada_lee_los_dos_plazos():
    from finanzas.importers.aeat import plazos_renta
    assert plazos_renta(INGRESO_FRACCIONADO.format(a=2026)) == [
        {"plazo": 1, "importe": 600.0, "fecha": "2026-06-30"}, {"plazo": 2, "importe": 400.0, "fecha": "2026-11-05"}]
    unico = "Resultado a ingresar o devolver\n: 250,00\nEl importe de la domiciliación se cargará el día\n: 30/06/2026\n"
    assert plazos_renta(unico) == [{"plazo": 1, "importe": 250.0, "fecha": "2026-06-30"}]
    assert plazos_renta("Resultado a ingresar o devolver\n: -80,00\n") == []


def test_segundo_plazo_de_la_renta_en_la_prevision():
    """Una renta presentada a dos plazos: el segundo sale en la previsión, en lo que debes y en los avisos."""
    import json
    from datetime import date
    from finanzas import db
    from finanzas.importers.aeat import plazos_renta
    from finanzas.models import Declaracion
    hoy = date.today()
    anio_cargo = hoy.year if hoy < date(hoy.year, 11, 5) else hoy.year + 1
    s = db.SessionLocal()
    d = Declaracion(modelo="100", ejercicio=anio_cargo - 1, periodo="0A", justificante="100000000ejemplo",
                    resultado="ingresar", importe=Decimal("1000"),
                    casillas=json.dumps({"resultado": 1000.0, "plazos": plazos_renta(INGRESO_FRACCIONADO.format(a=anio_cargo))}))
    s.add(d)
    s.commit()
    did = d.id
    s.close()
    try:
        with TestClient(app) as c:
            meses = {m["mes"]: m for m in c.get("/api/prevision?meses=14").json()["meses"]}
            nov = meses[f"{anio_cargo}-11"]["impuestos"]
            assert {"concepto": f"Renta {anio_cargo - 1} (2.º plazo)", "importe": 400.0, "presentado": True,
                    "tipo": "renta", "vence": f"{anio_cargo}-11-05"} in nov
            from finanzas import hacienda
            s = db.SessionLocal()
            assert any("2.º plazo" in x["concepto"] and x["importe"] == 400 for x in hacienda.pendiente(s)["lineas"])
            s.close()
    finally:
        s = db.SessionLocal()
        s.delete(s.get(Declaracion, did))
        s.commit()
        s.close()
