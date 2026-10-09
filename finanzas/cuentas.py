"""Cuentas y movimientos, segunda parte: movimientos apuntados a mano, categorización en lote, categorías y
reglas, y los avisos de esta sección. Lo de siempre (listar cuentas y movimientos, importar extractos,
titularidad) sigue en api.py."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, joinedload

from finanzas import api, auth, categorizar, db, sync
from finanzas.api import _obtener
from finanzas.models import Categoria, Cuenta, Movimiento, ReglaCategoria

router = APIRouter(prefix="/api", dependencies=[Depends(auth.requiere_sesion)])
SesionDB = Depends(db.get_session)

TIPOS_CATEGORIA = ("gasto", "ingreso", "transferencia")
AMBITOS = ("personal", "autonomo", "piso", "nomina")
DIAS_SALDO_VIEJO = 60
MINIMO_SIN_CATEGORIA = 5


# --- Movimientos a mano -----------------------------------------------------

class MovimientoIn(BaseModel):
    cuenta_id: int
    fecha: date
    concepto: str
    importe: Decimal  # negativo si sale de la cuenta
    categoria_id: int | None = None  # vacío: se categoriza con las reglas
    nota: str = ""


class MovimientoPut(BaseModel):
    fecha: date
    concepto: str
    importe: Decimal
    categoria_id: int | None = None
    nota: str = ""


def _cuenta_manual(s: Session, cuenta_id: int) -> Cuenta:
    c = _obtener(s, Cuenta, cuenta_id)
    if c.origen not in api.ORIGENES_MANUALES:
        raise HTTPException(400, "Los movimientos de una cuenta sincronizada los trae el banco: "
                                 "solo puedes apuntarlos a mano en cuentas manuales o de extracto.")
    return c


def _movimiento_manual(s: Session, mov_id: int) -> Movimiento:
    m = _obtener(s, Movimiento, mov_id)
    if not api.es_manual(m):
        raise HTTPException(400, "Este movimiento viene del banco o de un extracto: solo puedes cambiarle la categoría y la nota.")
    return m


def _concepto(texto: str) -> str:
    texto = texto.strip()[:300]
    if not texto:
        raise HTTPException(400, "Escribe un concepto")
    return texto


def _categoria_valida(s: Session, categoria_id: int | None) -> None:
    if categoria_id is not None:
        _obtener(s, Categoria, categoria_id)


def _mover_saldo(c: Cuenta, diferencia: Decimal, fecha: date | None = None) -> None:
    """El saldo de la cuenta sigue a sus movimientos; la fecha del saldo no retrocede."""
    c.saldo = (c.saldo or Decimal("0")) + diferencia
    if fecha and (c.saldo_fecha is None or fecha > c.saldo_fecha):
        c.saldo_fecha = fecha


@router.post("/movimientos")
def crear_movimiento(datos: MovimientoIn, s: Session = SesionDB):
    c = _cuenta_manual(s, datos.cuenta_id)
    concepto = _concepto(datos.concepto)
    _categoria_valida(s, datos.categoria_id)
    categoria_id = datos.categoria_id if datos.categoria_id is not None else categorizar.categorizar(s, concepto)
    m = Movimiento(cuenta_id=c.id, fecha=datos.fecha, concepto=concepto, importe=datos.importe,
                   categoria_id=categoria_id, nota=datos.nota.strip()[:500], huella=f"manual:{uuid.uuid4().hex}")
    s.add(m)
    _mover_saldo(c, datos.importe, datos.fecha)
    s.commit()
    sync.guardar_instantanea(s)
    return api._movimiento(m)


@router.put("/movimientos/{mov_id}")
def editar_movimiento(mov_id: int, datos: MovimientoPut, s: Session = SesionDB):
    m = _movimiento_manual(s, mov_id)
    concepto = _concepto(datos.concepto)
    _categoria_valida(s, datos.categoria_id)
    _mover_saldo(m.cuenta, datos.importe - m.importe, datos.fecha)
    m.fecha, m.concepto, m.importe = datos.fecha, concepto, datos.importe
    m.categoria_id, m.nota = datos.categoria_id, datos.nota.strip()[:500]
    s.commit()
    sync.guardar_instantanea(s)
    return api._movimiento(m)


@router.delete("/movimientos/{mov_id}")
def borrar_movimiento(mov_id: int, s: Session = SesionDB):
    m = _movimiento_manual(s, mov_id)
    _mover_saldo(m.cuenta, -m.importe)
    s.delete(m)
    s.commit()
    sync.guardar_instantanea(s)
    return {"ok": True}


class CategoriaLote(BaseModel):
    ids: list[int]
    categoria_id: int | None = None


@router.patch("/movimientos/categoria")
def categorizar_en_lote(datos: CategoriaLote, s: Session = SesionDB):
    """La misma categoría a varios movimientos de golpe (sin aprender reglas: eso es para el cambio de uno)."""
    _categoria_valida(s, datos.categoria_id)
    movs = s.scalars(select(Movimiento).where(Movimiento.id.in_(datos.ids))).all()
    for m in movs:
        m.categoria_id = datos.categoria_id
    s.commit()
    return {"ok": True, "cambiados": len(movs)}


# --- Categorías y reglas ----------------------------------------------------

class CategoriaIn(BaseModel):
    nombre: str
    tipo: str = "gasto"
    ambito: str = "personal"


class CategoriaPatch(BaseModel):
    nombre: str | None = None
    tipo: str | None = None
    ambito: str | None = None


def _nombre_libre(s: Session, nombre: str, salvo: int | None = None) -> str:
    nombre = nombre.strip()[:80]
    if not nombre:
        raise HTTPException(400, "Ponle un nombre a la categoría")
    otra = s.scalar(select(Categoria.id).where(func.lower(Categoria.nombre) == nombre.lower(), Categoria.id != (salvo or 0)))
    if otra:
        raise HTTPException(400, f"Ya hay una categoría que se llama «{nombre}»")
    return nombre


def _tipo_y_ambito(tipo: str | None, ambito: str | None) -> None:
    if tipo is not None and tipo not in TIPOS_CATEGORIA:
        raise HTTPException(400, "El tipo tiene que ser gasto, ingreso o transferencia")
    if ambito is not None and ambito not in AMBITOS:
        raise HTTPException(400, "El ámbito tiene que ser personal, autónomo, piso o nómina")


def _no_de_serie(c: Categoria, accion: str) -> None:
    if c.nombre in categorizar.NOMBRES_DE_SERIE:
        raise HTTPException(400, f"«{c.nombre}» es una categoría de serie: la app la busca por ese nombre, así que no se puede {accion}.")


@router.post("/categorias")
def crear_categoria(datos: CategoriaIn, s: Session = SesionDB):
    _tipo_y_ambito(datos.tipo, datos.ambito)
    c = Categoria(nombre=_nombre_libre(s, datos.nombre), tipo=datos.tipo, ambito=datos.ambito)
    s.add(c)
    s.commit()
    return api._categoria(c)


@router.patch("/categorias/{categoria_id}")
def actualizar_categoria(categoria_id: int, datos: CategoriaPatch, s: Session = SesionDB):
    c = _obtener(s, Categoria, categoria_id)
    _tipo_y_ambito(datos.tipo, datos.ambito)
    if datos.nombre is not None and datos.nombre.strip() != c.nombre:
        _no_de_serie(c, "renombrar")
        c.nombre = _nombre_libre(s, datos.nombre, salvo=c.id)
    if datos.tipo is not None:
        c.tipo = datos.tipo
    if datos.ambito is not None:
        c.ambito = datos.ambito
    s.commit()
    return api._categoria(c)


@router.delete("/categorias/{categoria_id}")
def borrar_categoria(categoria_id: int, s: Session = SesionDB):
    """Sus movimientos se quedan sin categoría y sus reglas desaparecen."""
    c = _obtener(s, Categoria, categoria_id)
    _no_de_serie(c, "borrar")
    r = s.execute(update(Movimiento).where(Movimiento.categoria_id == c.id).values(categoria_id=None))
    s.execute(delete(ReglaCategoria).where(ReglaCategoria.categoria_id == c.id))
    s.delete(c)
    s.commit()
    return {"ok": True, "movimientos": r.rowcount}


def _regla(r: ReglaCategoria) -> dict:
    return {"id": r.id, "patron": r.patron, "categoria_id": r.categoria_id, "categoria": r.categoria.nombre,
            "aprendida": bool(r.aprendida)}


@router.get("/categorias/reglas")
def listar_reglas(s: Session = SesionDB):
    """Primero las aprendidas (las más nuevas antes), luego las de serie por categoría."""
    reglas = s.scalars(select(ReglaCategoria).options(joinedload(ReglaCategoria.categoria))).all()
    return [_regla(r) for r in sorted(reglas, key=lambda r: (0, -r.id, "") if r.aprendida else (1, 0, r.categoria.nombre))]


@router.delete("/categorias/reglas/{regla_id}")
def borrar_regla(regla_id: int, s: Session = SesionDB):
    r = _obtener(s, ReglaCategoria, regla_id)
    if not r.aprendida:
        raise HTTPException(400, "Las reglas de serie no se borran; si una categoriza mal, corrige el movimiento y la app aprende la tuya.")
    s.delete(r)
    s.commit()
    return {"ok": True}


# --- Avisos -----------------------------------------------------------------

def avisos(s: Session) -> list[dict]:
    """Saldos manuales viejos y movimientos del mes sin categoría (los enseña Inicio)."""
    hoy = date.today()
    lista = []
    viejas = s.scalars(select(Cuenta).where(Cuenta.activa, api.PARTE > 0, Cuenta.origen.in_(api.ORIGENES_MANUALES),
                                            Cuenta.saldo_fecha < hoy - timedelta(days=DIAS_SALDO_VIEJO))
                       .order_by(Cuenta.nombre))
    for c in viejas:
        lista.append({"nivel": "aviso", "texto": f"El saldo de {c.nombre} es del {c.saldo_fecha:%d/%m}: actualízalo.",
                      "ir": "/cuentas"})
    sin_categoria = s.scalar(select(func.count()).select_from(Movimiento).join(Cuenta, Movimiento.cuenta_id == Cuenta.id)
                             .where(Cuenta.activa, api.PARTE > 0, Movimiento.categoria_id.is_(None),
                                    Movimiento.fecha >= hoy.replace(day=1)))
    if sin_categoria >= MINIMO_SIN_CATEGORIA:
        lista.append({"nivel": "info", "texto": f"Tienes {sin_categoria} movimientos de este mes sin categoría.",
                      "ir": "/cuentas?categoria=0"})
    return lista
