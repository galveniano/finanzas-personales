"""Análisis de gastos y suscripciones sin duplicados (datos inventados, en 2015 para no mezclarse con otros tests)."""
from datetime import date
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from finanzas import db, gastos
from finanzas.main import app
from finanzas.models import Categoria, Cuenta, Movimiento

HOY = date(2015, 6, 15)


@pytest.fixture(scope="module")
def s():
    with TestClient(app):
        sesion = _preparar()
        yield sesion
        sesion.close()


def _preparar():
    s = db.SessionLocal()
    mia = Cuenta(nombre="Ejemplo mía", participacion=100)
    compartida = Cuenta(nombre="Ejemplo compartida", participacion=50)
    ajena = Cuenta(nombre="Ejemplo de otra persona", participacion=0)
    s.add_all([mia, compartida, ajena])
    s.flush()
    super_ = s.scalar(select(Categoria).where(Categoria.nombre == "Supermercado"))
    movs = [
        # Streamflix conocido como Netflix: en la mía con un concepto y en la compartida con otro
        (mia, "2015-02-03", "COMPRA TARJ. 1234XXXX NETFLIX.COM", "-12.99"),
        (mia, "2015-03-03", "COMPRA TARJ. 1234XXXX NETFLIX.COM", "-12.99"),
        (compartida, "2015-04-03", "NETFLIX INTERNATIONAL BV", "-25.98"),  # tu parte: 12,99
        (compartida, "2015-05-03", "NETFLIX INTERNATIONAL BV", "-27.98"),  # sube a 13,99
        (mia, "2015-05-04", "NETFLIX.COM", "-13.99"),  # mismo mes en otra cuenta: cobro doble
        (mia, "2015-01-07", "SPOTIFY P1234", "-10.99"),
        (mia, "2015-02-07", "SPOTIFY P1234", "-10.99"),
        (mia, "2015-03-07", "SPOTIFY P1234", "-11.99"),
        (mia, "2015-04-07", "SPOTIFY P1234", "-11.99"),
        (mia, "2015-05-07", "SPOTIFY P1234", "-11.99"),
        # Recibo que nadie conoce, siempre igual
        (mia, "2015-03-01", "RECIBO GIMNASIO BARRIO EJEMPLO", "-30"),
        (mia, "2015-04-01", "RECIBO GIMNASIO BARRIO EJEMPLO", "-30"),
        (mia, "2015-05-01", "RECIBO GIMNASIO BARRIO EJEMPLO", "-30"),
        (mia, "2015-06-01", "RECIBO GIMNASIO BARRIO EJEMPLO", "-30"),
        # Uno que dejó de cobrarse
        (mia, "2015-01-10", "CUOTA CLUB VIEJO EJEMPLO", "-9"),
        (mia, "2015-02-10", "CUOTA CLUB VIEJO EJEMPLO", "-9"),
        # Anual conocido (un solo cargo hace meses)
        (mia, "2015-01-20", "AMAZON PRIME*EJEMPLO", "-49.90"),
        # Compras sueltas: no son suscripción
        *[(mia, f"2015-0{m}-{d:02d}", f"MERCADONA EJEMPLO {d}", "-40") for m in (3, 4, 5) for d in (5, 12, 19)],
        (mia, "2015-04-22", "CENA UNICA EJEMPLO", "-300"),
        # Traspaso entre tus cuentas y la cuenta ajena: no son gasto
        (mia, "2015-04-10", "ENVIO A OTRA CUENTA", "-500"),
        (compartida, "2015-04-11", "RECIBIDO DE OTRA CUENTA", "500"),
        (ajena, "2015-04-03", "NETFLIX.COM", "-12.99"),
        (ajena, "2015-04-05", "GASTO DE OTRA PERSONA", "-1000"),
        (mia, "2015-04-28", "NOMINA EJEMPLO", "2000"),
    ]
    for n, (cuenta, f, concepto, importe) in enumerate(movs):
        s.add(Movimiento(cuenta_id=cuenta.id, fecha=date.fromisoformat(f), concepto=concepto, importe=D(importe),
                         huella=f"gastos-ej-{n}", categoria_id=super_.id if super_ and "MERCADONA" in concepto else None))
    s.commit()
    return s


def test_suscripciones_una_vez_cada_una(s):
    subs = {x["nombre"]: x for x in gastos.suscripciones(s, HOY)}
    netflix = [x for x in subs.values() if x["clave"] == "netflix"]
    assert len(netflix) == 1  # en dos cuentas y con conceptos distintos, sale una vez
    n = netflix[0]
    assert n["tipo"] == "suscripcion" and n["icono"] == "netflix" and n["periodicidad"] == "mensual"
    assert n["cobro_doble"] and set(n["cuentas"]) == {"Ejemplo mía", "Ejemplo compartida"}
    assert n["subida"] is None  # en mayo no sube: se cobra dos veces
    assert subs["Spotify"]["subida"] == {"antes": 10.99, "ahora": 11.99} and subs["Spotify"]["mes"] == 11.99
    gym = subs["Gimnasio Barrio Ejemplo"]
    assert gym["mes"] == 30 and gym["anual"] == 360 and gym["activa"] and gym["tipo"] == "recibo"
    assert gym["proximo"] == "2015-07-01"
    assert not subs["Cuota Club Viejo Ejemplo"]["activa"]
    prime = subs["Amazon Prime"]
    assert prime["periodicidad"] == "anual" and prime["mes"] == round(49.90 / 12, 2)
    assert not any("Mercadona" in k or "Cena" in k or "Otra Persona" in k for k in subs)


def test_analisis_sin_traspasos_ni_cuentas_ajenas(s):
    d = gastos.analisis(s, 3, HOY)
    assert d["desde"] == "2015-03-01" and [m["mes"] for m in d["por_mes"]] == ["2015-03", "2015-04", "2015-05"]
    abril = d["por_mes"][1]
    # Abril: gimnasio 30 + Netflix (tu parte) 12,99 + Spotify 11,99 + súper 120 + cena 300; sin el traspaso ni la cuenta ajena
    assert abril["gastos"] == round(30 + 12.99 + 11.99 + 120 + 300, 2) and abril["ingresos"] == 2000
    assert d["mayores"][0]["importe"] == 300
    nombres = [x["nombre"] for x in d["sitios"]]
    assert nombres.count("Netflix") == 1
    sup = next(c for c in d["categorias"] if c["categoria"] == "Supermercado")
    assert sup["mes"] == 120 and sup["sitios"][0]["veces"] == 9  # el número de ticket no separa el sitio
    assert abs(sum(c["peso"] for c in d["categorias"]) - 100) < 0.5
    assert d["fijo_mes"] > 0 and d["suscripciones_mes"] > 0


def test_endpoint():
    with TestClient(app) as c:
        r = c.get("/api/gastos?meses=6")
        assert r.status_code == 200 and {"categorias", "suscripciones", "recibos"} <= r.json().keys()
