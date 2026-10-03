"""Categorización de movimientos por reglas de texto y categorías iniciales."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas.models import Categoria, ReglaCategoria

CATEGORIAS_INICIALES = [
    # (nombre, tipo, ámbito, patrones)
    ("Nómina", "ingreso", "nomina", ["nomina", "nómina", "indra"]),
    ("Cobro de facturas", "ingreso", "autonomo", ["aciturri", "trustportal"]),
    ("Alquiler cobrado", "ingreso", "piso", []),
    ("Cuota hipoteca", "gasto", "piso", ["prestamo", "préstamo", "hipoteca"]),
    ("Cuota autónomos", "gasto", "autonomo", ["tgss", "seguridad social", "reta"]),
    ("Impuestos", "gasto", "personal", ["aeat", "agencia tributaria", "hacienda"]),
    ("Supermercado", "gasto", "personal", ["mercadona", "carrefour", "lidl", "dia ", "eroski", "alcampo"]),
    ("Restaurantes", "gasto", "personal", ["restaurante", "bar ", "glovo", "just eat", "uber eats"]),
    ("Transporte", "gasto", "personal", ["repsol", "cepsa", "galp", "renfe", "uber", "cabify", "parking"]),
    ("Suministros", "gasto", "personal", ["iberdrola", "endesa", "naturgy", "movistar", "vodafone", "orange"]),
    ("Compras", "gasto", "personal", ["amazon", "el corte ingles", "zara"]),
    ("Ocio y suscripciones", "gasto", "personal", ["netflix", "spotify", "hbo", "disney"]),
    ("Viajes", "gasto", "personal", ["booking", "airbnb", "ryanair", "iberia", "vueling"]),
    ("Inversión (Indexa)", "transferencia", "personal", ["indexa"]),
    ("Traspaso entre cuentas", "transferencia", "personal", ["traspaso"]),
    ("Otros", "gasto", "personal", []),
]


def sembrar_categorias(session: Session) -> None:
    if session.scalar(select(Categoria.id).limit(1)) is not None:
        return
    for nombre, tipo, ambito, patrones in CATEGORIAS_INICIALES:
        cat = Categoria(nombre=nombre, tipo=tipo, ambito=ambito)
        session.add(cat)
        session.flush()
        for p in patrones:
            session.add(ReglaCategoria(patron=p, categoria_id=cat.id))
    session.commit()


def categorizar(session: Session, concepto: str) -> int | None:
    texto = concepto.lower()
    for regla in session.scalars(select(ReglaCategoria).order_by(ReglaCategoria.id)):
        if regla.patron.lower() in texto:
            return regla.categoria_id
    return None
