"""Categorización de movimientos por reglas de texto y categorías iniciales."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas.models import Categoria, Movimiento, ReglaCategoria

# Categorías que el resto de la app busca por su nombre (nóminas del banco, previsión, gastos, traspasos…):
# se pueden usar, pero ni renombrar ni borrar.
NOMBRES_DE_SERIE = ("Nómina", "Cobro de facturas", "Alquiler cobrado", "Cuota hipoteca", "Cuota autónomos", "Impuestos",
                    "Inversión (Indexa)", "Traspaso entre cuentas")

CATEGORIAS_INICIALES = [
    # (nombre, tipo, ámbito, patrones)
    ("Nómina", "ingreso", "nomina", ["nomina", "nómina", "indra"]),
    ("Cobro de facturas", "ingreso", "autonomo", ["aciturri", "trustportal"]),
    ("Alquiler cobrado", "ingreso", "piso", []),
    ("Cuota hipoteca", "gasto", "piso", ["prestamo", "préstamo", "hipoteca"]),
    ("Cuota autónomos", "gasto", "autonomo", ["tgss", "seguridad social", "cotizacion autonom", "cuota autonom"]),
    ("Impuestos", "gasto", "personal", ["aeat", "agencia tributaria", "hacienda"]),
    ("Supermercado", "gasto", "personal", ["mercadona", "carrefour", "lidl", "dia retail", "supermercados dia",
                                           "eroski", "alcampo"]),
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


# Reglas de versiones anteriores que atrapaban de más: «reta» cogía «retail» y «dia » cogía «media »
REGLAS_CAMBIADAS = {"reta": ["cotizacion autonom", "cuota autonom"], "dia ": ["dia retail", "supermercados dia"]}


def actualizar_reglas(session: Session) -> None:
    """Cambia en una base de datos ya creada las reglas de serie demasiado amplias."""
    for viejo, nuevos in REGLAS_CAMBIADAS.items():
        reglas = session.scalars(select(ReglaCategoria).where(ReglaCategoria.patron == viejo,
                                                              ReglaCategoria.aprendida.isnot(True))).all()
        for r in reglas:
            for patron in nuevos:
                if not session.scalar(select(ReglaCategoria.id).where(ReglaCategoria.patron == patron)):
                    session.add(ReglaCategoria(patron=patron, categoria_id=r.categoria_id))
            session.delete(r)
    session.commit()


def _reglas(session: Session) -> list[ReglaCategoria]:
    # Primero las aprendidas (las más nuevas antes) y luego las de serie
    return sorted(session.scalars(select(ReglaCategoria)),
                  key=lambda r: (0, -r.id) if r.aprendida else (1, r.id))


def categorizar(session: Session, concepto: str, reglas: list[ReglaCategoria] | None = None) -> int | None:
    """Las reglas aprendidas se guardaron como `patron_de` del concepto, así que se buscan en el patrón del
    concepto nuevo («netflix com»); las de serie, en el texto en minúsculas como siempre."""
    texto = concepto.lower()
    patron = None
    for regla in reglas if reglas is not None else _reglas(session):
        if regla.aprendida:
            if patron is None:
                patron = patron_de(concepto)
            if regla.patron.lower() in patron:
                return regla.categoria_id
        elif regla.patron.lower() in texto:
            return regla.categoria_id
    return None


def patron_de(concepto: str) -> str:
    """Lo que identifica un concepto sin fechas, importes ni números de operación, en minúsculas:
    «COMPRA TARJ. 5402 NETFLIX.COM 12/09» → «netflix com»."""
    texto = re.sub(r"[\d/.,:*#-]+", " ", (concepto or "").lower())
    texto = re.sub(r"\b(compra|tarj|tarjeta|pago|recibo|adeudo|cargo|en|de|a|sepa|contactless|transferencia|"
                   r"bizum|traspaso)\b", " ", texto)
    return " ".join(texto.split())[:60]


def aprender(session: Session, mov: Movimiento) -> dict:
    """Al poner tú una categoría a un movimiento, se crea (o corrige) la regla para los siguientes.
    Devuelve el patrón y cuántos movimientos anteriores parecidos tienen otra categoría."""
    patron = patron_de(mov.concepto)
    if len(patron) < 3:
        return {"patron": None, "parecidos": 0}
    regla = session.scalar(select(ReglaCategoria).where(ReglaCategoria.patron == patron, ReglaCategoria.aprendida))
    if mov.categoria_id is None:  # «Sin categoría»: la regla aprendida de ese patrón deja de valer
        if regla is not None:
            session.delete(regla)
            session.commit()
        return {"patron": None, "parecidos": 0}
    if regla is None:
        regla = ReglaCategoria(patron=patron, aprendida=True, categoria_id=mov.categoria_id)
        session.add(regla)
    regla.categoria_id = mov.categoria_id
    session.commit()
    return {"patron": patron, "parecidos": len(parecidos(session, mov))}


def parecidos(session: Session, mov: Movimiento) -> list[Movimiento]:
    """Movimientos con el mismo patrón y otra categoría (ninguno si el concepto no tiene letras)."""
    patron = patron_de(mov.concepto)
    if not patron:
        return []
    candidatos = session.scalars(select(Movimiento).where(Movimiento.id != mov.id,
                                                          Movimiento.concepto.ilike(f"%{patron.split()[0]}%")))
    return [m for m in candidatos if patron_de(m.concepto) == patron and m.categoria_id != mov.categoria_id]
