"""Carga de datos en bloque desde un fichero JSON: inmuebles, coches y sus hipotecas, contratos, gastos y
pagos, e inversiones privadas con sus llamadas de capital. Lo que ya existe (mismo nombre) no se duplica.

    {"activos": [{"nombre": "Piso", "tipo": "inmueble", "uso": "alquiler", "precio_compra": 100000,
                  "valoraciones": [...], "hipotecas": [...], "contratos": [...], "gastos": [...], "pagos": [...]}],
     "inversiones": [{"nombre": "Fondo", "compromiso": 20000, "llamadas": [...]}]}
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas.models import (Activo, ContratoAlquiler, Deuda, GastoInmueble, InversionPrivada, PagoPrevisto,
                             Valoracion)

TIPOS_ACTIVO = {"inmueble", "inmueble_en_construccion", "vehiculo", "otro"}


class ErrorDatos(ValueError):
    pass


def _fecha(v) -> date | None:
    try:
        return date.fromisoformat(v) if v else None
    except (TypeError, ValueError):
        raise ErrorDatos(f"Fecha no válida: {v!r} (usa AAAA-MM-DD)")


def _dinero(v, defecto="0") -> Decimal:
    try:
        return Decimal(str(v if v is not None else defecto))
    except ArithmeticError:
        raise ErrorDatos(f"Importe no válido: {v!r}")


def _pago(x: dict, **claves) -> PagoPrevisto:
    return PagoPrevisto(concepto=str(x.get("concepto", ""))[:160], fecha=_fecha(x.get("fecha")) or date.today(),
                        importe=_dinero(x.get("importe")), pagado=bool(x.get("pagado")), **claves)


def _activo(s: Session, x: dict) -> str:
    nombre = str(x.get("nombre", "")).strip()[:120]
    if not nombre:
        raise ErrorDatos("Falta el nombre de un inmueble o coche")
    if s.scalar(select(Activo).where(Activo.nombre == nombre)):
        return f"{nombre}: ya existía, no se ha tocado"
    tipo = x.get("tipo", "inmueble")
    if tipo not in TIPOS_ACTIVO:
        raise ErrorDatos(f"{nombre}: tipo {tipo!r} no válido")
    a = Activo(nombre=nombre, tipo=tipo, uso=x.get("uso", "otro"), fecha_compra=_fecha(x.get("fecha_compra")),
               precio_compra=_dinero(x.get("precio_compra")), gastos_compra=_dinero(x.get("gastos_compra")),
               valor_catastral=_dinero(x.get("valor_catastral")),
               valor_catastral_construccion=_dinero(x.get("valor_catastral_construccion")),
               porcentaje_propiedad=_dinero(x.get("porcentaje_propiedad"), "100"), notas=str(x.get("notas", "")))
    s.add(a)
    s.flush()
    for v in x.get("valoraciones", []):
        s.add(Valoracion(activo_id=a.id, fecha=_fecha(v.get("fecha")) or date.today(), valor=_dinero(v.get("valor"))))
    for h in x.get("hipotecas", []):
        manual = h.get("saldo_pendiente_manual")
        s.add(Deuda(activo_id=a.id, tipo="hipoteca", nombre=str(h.get("nombre", f"Hipoteca {nombre}"))[:120],
                    entidad=str(h.get("entidad", ""))[:80], capital_inicial=_dinero(h.get("capital_inicial")),
                    tipo_interes_anual=_dinero(h.get("tipo_interes_anual")), fecha_inicio=_fecha(h.get("fecha_inicio")),
                    plazo_meses=int(h.get("plazo_meses", 0)),
                    saldo_pendiente_manual=None if manual is None else _dinero(manual),
                    saldo_fecha=_fecha(h.get("saldo_fecha")) or (date.today() if manual is not None else None)))
    for c in x.get("contratos", []):
        s.add(ContratoAlquiler(activo_id=a.id, inquilino=str(c.get("inquilino", ""))[:120],
                               fecha_inicio=_fecha(c.get("fecha_inicio")) or date.today(),
                               fecha_fin=_fecha(c.get("fecha_fin")), renta_mensual=_dinero(c.get("renta_mensual")),
                               reduccion_pct=_dinero(c.get("reduccion_pct"), "60")))
    for g in x.get("gastos", []):
        s.add(GastoInmueble(activo_id=a.id, fecha=_fecha(g.get("fecha")) or date.today(), tipo=g.get("tipo", "otros"),
                            importe=_dinero(g.get("importe")), concepto=str(g.get("concepto", ""))))
    for p in x.get("pagos", []):
        s.add(_pago(p, activo_id=a.id))
    return f"{nombre}: añadido"


def _inversion(s: Session, x: dict) -> str:
    nombre = str(x.get("nombre", "")).strip()[:120]
    if not nombre:
        raise ErrorDatos("Falta el nombre de una inversión")
    if s.scalar(select(InversionPrivada).where(InversionPrivada.nombre == nombre)):
        return f"{nombre}: ya existía, no se ha tocado"
    inv = InversionPrivada(nombre=nombre, gestora=str(x.get("gestora", ""))[:120], compromiso=_dinero(x.get("compromiso")),
                           fecha_compromiso=_fecha(x.get("fecha_compromiso")), nav=_dinero(x.get("nav")),
                           nav_fecha=_fecha(x.get("nav_fecha")), distribuido=_dinero(x.get("distribuido")),
                           notas=str(x.get("notas", "")))
    s.add(inv)
    s.flush()
    for p in x.get("llamadas", []):
        s.add(_pago(p, inversion_id=inv.id))
    return f"{nombre}: añadido"


def importar(s: Session, datos: dict) -> list[str]:
    """Todo o nada: si algo falla no se guarda nada."""
    if not isinstance(datos, dict):
        raise ErrorDatos("El fichero debe ser un objeto JSON con 'activos' y/o 'inversiones'")
    try:
        mensajes = [_activo(s, x) for x in datos.get("activos", [])]
        mensajes += [_inversion(s, x) for x in datos.get("inversiones", [])]
        s.commit()
        return mensajes
    except Exception:
        s.rollback()
        raise
