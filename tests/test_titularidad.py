from datetime import date
from decimal import Decimal as D

from fastapi.testclient import TestClient

from finanzas import db
from finanzas.main import app
from finanzas.models import Cuenta, Movimiento


def test_cuentas_compartidas_y_ajenas():
    with TestClient(app) as c:
        antes = c.get("/api/resumen").json()
        with db.SessionLocal() as s:
            mia = Cuenta(nombre="Pareja prueba", saldo=D("1000"))
            ajena = Cuenta(nombre="Madre prueba", saldo=D("5000"))
            s.add_all([mia, ajena])
            s.flush()
            hoy = date.today()
            s.add_all([Movimiento(cuenta_id=mia.id, fecha=hoy, concepto="SUPER PAREJA", importe=D("-100"), huella="t1"),
                       Movimiento(cuenta_id=ajena.id, fecha=hoy, concepto="SUPER MADRE", importe=D("-80"), huella="t2")])
            s.commit()
            ids = mia.id, ajena.id

        assert c.patch(f"/api/cuentas/{ids[0]}", json={"participacion": 50}).json()["saldo_tuyo"] == 500
        assert c.patch(f"/api/cuentas/{ids[1]}", json={"participacion": 0}).json()["saldo_tuyo"] == 0
        assert c.patch(f"/api/cuentas/{ids[1]}", json={"participacion": 120}).status_code == 400

        despues = c.get("/api/resumen").json()
        assert round(despues["neto"] - antes["neto"], 2) == 500  # solo tu mitad; la de tu madre no cuenta
        assert not any(l["nombre"] == "Madre prueba" for l in despues["lineas_activo"])

        conceptos = {m["concepto"] for m in c.get("/api/movimientos?solo_tuyas=true").json()["movimientos"]}
        assert "SUPER PAREJA" in conceptos and "SUPER MADRE" not in conceptos
        # Eligiendo la cuenta sí se ven
        assert [m["concepto"] for m in c.get(f"/api/movimientos?cuenta_id={ids[1]}").json()["movimientos"]] == ["SUPER MADRE"]
        # Y siguen apareciendo en Cuentas
        assert {"Pareja prueba", "Madre prueba"} <= {x["nombre"] for x in c.get("/api/cuentas").json()}
