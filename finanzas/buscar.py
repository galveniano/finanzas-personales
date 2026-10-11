"""Lo transversal de la app: búsqueda global (paleta Ctrl+K), historial de sincronizaciones y estado de la app."""
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from finanzas import auth, config, db
from finanzas.fechas import iso_utc
from finanzas.integrations import enablebanking
from finanzas.models import (Activo, Categoria, Cliente, ConexionBancaria, Cuenta, Declaracion, Factura, Movimiento,
                             Objetivo, PagoPrevisto, RegistroSync)

router = APIRouter(prefix="/api", dependencies=[Depends(auth.requiere_sesion)])
SesionDB = Depends(db.get_session)
POR_GRUPO = 8
FUENTES_SYNC = ("sabadell", "indexa")
TIPO_ACTIVO = {"inmueble": "Inmueble", "inmueble_en_construccion": "Obra nueva", "vehiculo": "Vehículo", "otro": "Bien"}


# --- Búsqueda global ---------------------------------------------------------------

def _item(texto: str, detalle: str, ir: str, importe=None) -> dict:
    return {"texto": texto, "detalle": detalle, "ir": ir, "importe": None if importe is None else float(importe)}


def _dia(d: date | None) -> str:
    return f"{d:%d/%m/%Y}" if d else ""


def _grupo(nombre: str, resultados: list[dict]) -> dict:
    return {"nombre": nombre, "resultados": resultados[:POR_GRUPO]}


def _declaraciones(s: Session, palabras: list[str]) -> list[dict]:
    from finanzas.api import NOMBRE_MODELO
    encontradas = []
    for d in s.scalars(select(Declaracion).order_by(Declaracion.ejercicio.desc(), Declaracion.periodo.desc())):
        nombre = NOMBRE_MODELO.get(d.modelo, f"Modelo {d.modelo}")
        texto = f"{d.modelo} {nombre} {d.periodo} {d.ejercicio}".lower()
        if all(p in texto for p in palabras):
            encontradas.append(_item(f"Modelo {d.modelo} · {d.periodo} {d.ejercicio}",
                                     f"{nombre} · presentado el {_dia(d.fecha_presentacion) or '—'}",
                                     "/impuestos?ver=presentadas", d.importe))
            if len(encontradas) == POR_GRUPO:
                break
    return encontradas


@router.get("/buscar")
def buscar(q: str = "", s: Session = SesionDB):
    """Hasta 8 resultados por grupo para la paleta de comandos. Menos de dos letras: nada."""
    q = " ".join(q.split())
    if len(q) < 2:
        return {"q": q, "grupos": []}
    patron = f"%{q}%"
    limite = POR_GRUPO
    grupos = []

    movimientos = s.execute(select(Movimiento, Cuenta.nombre).join(Cuenta, Movimiento.cuenta_id == Cuenta.id)
                            .where(Movimiento.concepto.ilike(patron))
                            .order_by(Movimiento.fecha.desc(), Movimiento.id.desc()).limit(limite)).all()
    if movimientos:
        grupos.append(_grupo("Movimientos", [_item(m.concepto, f"{_dia(m.fecha)} · {cuenta}", f"/cuentas?q={q}", m.importe)
                                             for m, cuenta in movimientos]))

    facturas = s.execute(select(Factura, Cliente.nombre).join(Cliente, Factura.cliente_id == Cliente.id)
                         .where(or_(Factura.numero.ilike(patron), Cliente.nombre.ilike(patron), Factura.concepto.ilike(patron)))
                         .order_by(Factura.fecha.desc()).limit(limite)).all()
    if facturas:
        grupos.append(_grupo("Facturas", [_item(f"Factura {f.numero} · {cliente}",
                                                f"{_dia(f.fecha)}{' · cobrada' if f.fecha_cobro else ' · pendiente de cobro'}",
                                                "/ingresos", f.total_a_cobrar) for f, cliente in facturas]))

    clientes = s.scalars(select(Cliente).where(Cliente.nombre.ilike(patron)).order_by(Cliente.nombre).limit(limite)).all()
    if clientes:
        grupos.append(_grupo("Clientes", [_item(c.nombre, c.nif or "Cliente", "/ingresos") for c in clientes]))

    bienes = s.scalars(select(Activo).where(Activo.nombre.ilike(patron)).order_by(Activo.nombre).limit(limite)).all()
    if bienes:
        grupos.append(_grupo("Bienes", [_item(a.nombre, TIPO_ACTIVO.get(a.tipo, "Bien"), "/inmuebles") for a in bienes]))

    objetivos = s.scalars(select(Objetivo).where(Objetivo.nombre.ilike(patron)).order_by(Objetivo.nombre).limit(limite)).all()
    pagos = s.scalars(select(PagoPrevisto).where(PagoPrevisto.concepto.ilike(patron))
                      .order_by(PagoPrevisto.fecha.desc()).limit(limite)).all()
    plan = ([_item(o.nombre, f"Objetivo · {_dia(o.fecha_objetivo) or 'sin fecha'}", "/plan", o.importe_objetivo) for o in objetivos]
            + [_item(p.concepto, f"Pago {'hecho' if p.pagado else 'previsto'} · {_dia(p.fecha)}", "/plan", p.importe) for p in pagos])
    if plan:
        grupos.append(_grupo("Plan", plan))

    declaraciones = _declaraciones(s, q.lower().split())
    if declaraciones:
        grupos.append(_grupo("Hacienda", declaraciones))

    categorias = s.scalars(select(Categoria).where(Categoria.nombre.ilike(patron)).order_by(Categoria.nombre).limit(limite)).all()
    if categorias:
        grupos.append(_grupo("Categorías", [_item(c.nombre, f"Categoría de {c.tipo}", f"/cuentas?categoria={c.id}")
                                            for c in categorias]))
    return {"q": q, "grupos": grupos}


# --- Sincronización: historial y desconectar ---------------------------------------------

@router.post("/sync/sabadell/desconectar")
def desconectar_sabadell(s: Session = SesionDB):
    """Da de baja la conexión con el banco. Las cuentas y sus movimientos se quedan, pero dejan de sincronizarse
    hasta que vuelvas a conectar."""
    activas = s.scalars(select(ConexionBancaria).where(ConexionBancaria.activa)).all()
    for con in activas:
        con.activa = False
    s.commit()
    return {"ok": True, "desconectadas": len(activas)}


@router.get("/sync/historial")
def historial_sync(s: Session = SesionDB):
    """Las últimas 10 sincronizaciones de cada fuente, la más reciente primero."""
    def ultimas(fuente: str) -> list[dict]:
        filas = s.scalars(select(RegistroSync).where(RegistroSync.fuente == fuente)
                          .order_by(RegistroSync.id.desc()).limit(10))
        return [{"fecha": iso_utc(r.fecha), "ok": r.ok, "mensaje": r.mensaje} for r in filas]
    return {fuente: ultimas(fuente) for fuente in FUENTES_SYNC}


# --- Estado de la app -----------------------------------------------------------------

def version() -> str | None:
    """Hash corto de git si el despliegue dejó finanzas/version.txt; si no, nada."""
    ruta = Path(__file__).with_name("version.txt")
    try:
        return ruta.read_text(encoding="utf-8").strip()[:12] or None
    except OSError:
        return None


def _base_de_datos() -> dict:
    if db.engine is None:
        return {"tipo": "Sin configurar", "detalle": db.ERROR_CONFIG}
    url = db.engine.url
    if url.get_backend_name() == "sqlite":
        return {"tipo": "SQLite", "detalle": url.database or ""}
    return {"tipo": "Postgres", "detalle": url.host or ""}


def _sincronizacion() -> dict:
    if config.EN_VERCEL:
        return {"modo": "cron", "cada_horas": 0, "texto": "Tarea programada de Vercel cada día a las 6:00 (UTC) y el botón Sincronizar"}
    if config.SYNC_HORAS > 0:
        return {"modo": "programada", "cada_horas": config.SYNC_HORAS,
                "texto": f"Al arrancar y cada {config.SYNC_HORAS:g} horas mientras la app está abierta"}
    return {"modo": "manual", "cada_horas": 0, "texto": "Solo a mano, con el botón Sincronizar (SYNC_HORAS=0)"}


@router.get("/app/estado")
def estado_app(request: Request, s: Session = SesionDB):
    from finanzas import ajustes, avisos
    copia = ajustes.leer(s, avisos.CLAVE_ULTIMA_COPIA)  # «AAAA-MM-DD» o «AAAA-MM-DD drive»
    fecha_copia, _, destino = copia.partition(" ")
    dias = None
    if fecha_copia:
        try:
            dias = (date.today() - date.fromisoformat(fecha_copia[:10])).days
        except ValueError:
            fecha_copia = ""
    return {
        "base_datos": _base_de_datos(),
        "ccaa": config.CCAA,
        "banco": {"nombre": config.BANCO, "configurado": enablebanking.configurado(),
                  "conectado": enablebanking.conexion_activa(s) is not None},
        "indexa_configurado": bool(config.INDEXA_TOKEN),
        "ultima_copia": {"fecha": fecha_copia, "destino": destino or "descarga", "hace_dias": dias} if fecha_copia else None,
        "sincronizacion": _sincronizacion(),
        "sesion": {"requerida": config.AUTH_REQUERIDA,
                   "email": auth.email_de_sesion(request) if config.AUTH_REQUERIDA else None},
        "version": version(),
        "en_vercel": config.EN_VERCEL,
    }
