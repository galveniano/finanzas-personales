"""La nómina se saca de los ingresos categorizados como Nómina en el banco (datos inventados)."""
from datetime import date, timedelta
from decimal import Decimal as D

from fastapi.testclient import TestClient

from finanzas import db
from finanzas.main import app
from finanzas.models import Categoria, Cuenta, Movimiento


def test_nomina_desde_el_banco():
    with TestClient(app) as c:
        s = db.SessionLocal()
        nomina = s.query(Categoria).filter_by(nombre="Nómina").one()
        mia = Cuenta(nombre="Cuenta nómina ejemplo")
        ajena = Cuenta(nombre="Cuenta ajena ejemplo", participacion=D("0"))
        s.add_all([mia, ajena])
        s.flush()
        hoy = date.today()
        for i in range(3):
            s.add(Movimiento(cuenta_id=mia.id, fecha=hoy - timedelta(days=31 * i + 1), concepto=f"NOMINA EJEMPLO {i}",
                             importe=D("1800"), categoria_id=nomina.id, huella=f"nom-ej-{i}"))
        s.add(Movimiento(cuenta_id=ajena.id, fecha=hoy - timedelta(days=2), concepto="NOMINA DE OTRA PERSONA",
                         importe=D("1500"), categoria_id=nomina.id, huella="nom-ajena"))
        s.commit()
        s.close()

        d = c.get("/api/nominas").json()
        conceptos = {m["concepto"] for m in d["banco"]}
        assert {"NOMINA EJEMPLO 0", "NOMINA EJEMPLO 2"} <= conceptos and "NOMINA DE OTRA PERSONA" not in conceptos
        e = d["estimado_banco"]
        assert e["bruto_anual"] > e["neto_medio_mes"] * 12 and e["irpf_anual"] > 0 and e["ss_anual"] > 0
        assert d["bruto_12_meses"] is not None
