"""Casillas e importes de lo presentado a Hacienda (datos inventados, en 2011 para no mezclarse con otros tests)."""
from decimal import Decimal as D

from finanzas import db, declaraciones
from finanzas.models import Declaracion


def _decl(casillas, **extra):
    return Declaracion(modelo="130", ejercicio=2011, periodo="1T", casillas=casillas, **extra)


def test_casillas_sin_declaracion_ni_json():
    assert declaraciones.casillas(None) == {}
    assert declaraciones.casillas(_decl(None)) == {}
    assert declaraciones.casillas(_decl("")) == {}


def test_casillas_json_valido():
    assert declaraciones.casillas(_decl('{"ingresos": 1000.5, "gastos": 50}')) == {"ingresos": 1000.5, "gastos": 50}


def test_casillas_json_roto():
    assert declaraciones.casillas(_decl("{no es json")) == {}


def test_importe_presentado_suma_complementarias():
    db.init_db()
    s = db.SessionLocal()
    original, complementaria = _decl(None, importe=D("300"), justificante="a"), _decl(None, importe=D("50.25"), justificante="b")
    try:
        s.add_all([original, complementaria])
        s.commit()
        assert declaraciones.presentada(s, "130", 2011, "1T")
        assert declaraciones.importe_presentado(s, "130", 2011, "1T") == 350.25
        assert not declaraciones.presentada(s, "130", 2011, "2T")
        assert declaraciones.importe_presentado(s, "130", 2011, "2T") is None
    finally:
        s.delete(original)
        s.delete(complementaria)
        s.commit()
        s.close()
