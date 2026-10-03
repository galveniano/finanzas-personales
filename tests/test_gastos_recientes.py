"""Gasto medio por categoría y suscripciones detectadas en los movimientos (datos inventados)."""
from datetime import date, timedelta
from decimal import Decimal as D

from fastapi.testclient import TestClient

from finanzas import db
from finanzas.main import app
from finanzas.models import Cuenta, Movimiento


def _mes_atras(n: int, dia: int) -> date:
    d = date.today().replace(day=1)
    for _ in range(n):
        d = (d - timedelta(days=1)).replace(day=1)
    return d.replace(day=dia)


def test_suscripciones_y_media():
    with TestClient(app) as c:
        s = db.SessionLocal()
        cuenta = Cuenta(nombre="Cuenta gastos ejemplo")
        s.add(cuenta)
        s.flush()
        movs = []
        for i in (1, 2, 3):
            movs += [("STREAMFLIX.COM 1234", "-12.99", 5), ("GIMNASIO EJEMPLO CUOTA", "-30", 2)]
            movs += [(f"COMPRA SUPER EJEMPLO {k}", "-50", 3 + k) for k in range(4)]  # varias al mes: no es cuota
        movs += [("CENA UNICA", "-80", 10)]
        for n, (concepto, importe, dia) in enumerate(movs):
            mes = 1 + (n // 6) % 3
            s.add(Movimiento(cuenta_id=cuenta.id, fecha=_mes_atras(mes, dia), concepto=concepto, importe=D(importe),
                             huella=f"gasto-ej-{n}"))
        s.commit()
        s.close()
        d = c.get("/api/gastos/recientes").json()
        subs = {x["concepto"].split()[0]: x for x in d["suscripciones"]}
        assert subs["STREAMFLIX.COM"]["mes"] == 12.99 and subs["STREAMFLIX.COM"]["anual"] == 155.88
        assert "GIMNASIO" in subs and "COMPRA" not in subs and "CENA" not in subs
        assert d["gastos_mes"] > 0 and d["categorias"]
