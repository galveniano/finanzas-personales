"""Sincronización automática de Sabadell (Enable Banking) e Indexa, y foto diaria del patrimonio."""
import logging
import threading
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from finanzas import config, db, patrimonio
from finanzas.fechas import iso_utc, sumar_meses
from finanzas.integrations import enablebanking, indexa
from finanzas.models import Activo, Instantanea, RegistroSync

log = logging.getLogger("finanzas.sync")
_cerrojo = threading.Lock()


def _registrar(session: Session, fuente: str, ok: bool, mensaje: str) -> dict:
    session.add(RegistroSync(fuente=fuente, ok=ok, mensaje=mensaje))
    session.commit()
    return {"fuente": fuente, "ok": ok, "mensaje": mensaje}


def sincronizar_sabadell(session: Session, cliente=None) -> dict:
    try:
        r = enablebanking.sincronizar(session, cliente)
        return _registrar(session, "sabadell", True,
                          f"{r['cuentas']} cuentas, {r['movimientos_nuevos']} movimientos nuevos"
                          + (". Sigue trayendo el histórico: vuelve a sincronizar" if r.get("historico_pendiente") else ""))
    except Exception as e:  # el error se guarda y se enseña en la app
        session.rollback()
        return _registrar(session, "sabadell", False, str(e))


def sincronizar_indexa(session: Session, cliente=None) -> dict:
    try:
        cuentas = indexa.sincronizar(session, cliente)
        return _registrar(session, "indexa", True, f"{len(cuentas)} cuentas actualizadas")
    except Exception as e:
        session.rollback()
        return _registrar(session, "indexa", False, str(e))


def guardar_instantanea(session: Session, fecha: date | None = None) -> Instantanea:
    fecha = fecha or date.today()
    pendiente = None
    if fecha == date.today():  # lo que debes a Hacienda también es deuda (como en Inicio)
        try:
            from finanzas import hacienda
            pendiente = hacienda.pendiente(session)
        except Exception:
            session.rollback()
            log.exception("No se ha podido estimar lo pendiente con Hacienda")
    p = patrimonio.calcular(session, fecha, pendiente)
    grupos = p.por_grupo()
    foto = session.scalar(select(Instantanea).where(Instantanea.fecha == fecha)) or Instantanea(fecha=fecha)
    foto.liquidez = grupos.get("Liquidez", 0)
    foto.inversiones = grupos.get("Inversiones", 0)
    foto.inmuebles = grupos.get("Inmuebles", 0)
    foto.vehiculos = grupos.get("Vehículos", 0)
    foto.otros = grupos.get("Otros", 0)
    foto.deudas = p.total_pasivos
    session.add(foto)
    session.commit()
    return foto


def rellenar_vehiculos(session: Session) -> None:
    """Las fotos de antes no guardaban el coche: se calcula su valor a esa fecha (se deprecia solo).
    Se llama en cada /resumen, así que primero mira barato si queda alguna por rellenar."""
    if not session.scalar(select(exists().where(Instantanea.vehiculos.is_(None)))):
        return
    fotos = session.scalars(select(Instantanea).where(Instantanea.vehiculos.is_(None))).all()
    coches = session.scalars(select(Activo).where(Activo.tipo == "vehiculo")).all()
    for foto in fotos:
        foto.vehiculos = sum((patrimonio.valor_activo(a, foto.fecha)[0] for a in coches
                              if not a.fecha_compra or a.fecha_compra <= foto.fecha), Decimal(0))
    session.commit()


def muestrear(fotos: list, hoy: date | None = None) -> list:
    """Aligera una lista de fotos ordenadas por fecha (cualquier cosa con `.fecha`): un punto por día en los
    últimos 3 meses, uno por semana hasta un año y uno por mes más atrás, quedándose con el último de cada
    tramo (así el cierre de cada año sigue estando). Con años de fotos diarias el frontal recibiría miles."""
    hoy = hoy or date.today()
    hace_3_meses, hace_1_anio = sumar_meses(hoy, -3), sumar_meses(hoy, -12)
    elegidas: dict[tuple, object] = {}
    for foto in fotos:
        f = foto.fecha
        if f >= hace_3_meses:
            clave = ("dia", f)
        elif f >= hace_1_anio:  # con el mes en la clave, una semana a caballo de dos meses no se traga el cierre
            clave = ("semana", f.year, f.month, f.isocalendar()[1])
        else:
            clave = ("mes", f.year, f.month)
        elegidas[clave] = foto  # los tramos van seguidos en el tiempo: el orden del dict es el cronológico
    return list(elegidas.values())


def historico(session: Session, hoy: date | None = None) -> list[Instantanea]:
    """Fotos del patrimonio para la gráfica de Inicio, ya aligeradas y con el coche rellenado en las antiguas."""
    rellenar_vehiculos(session)
    return muestrear(session.scalars(select(Instantanea).order_by(Instantanea.fecha)).all(), hoy)


def sincronizar_todo(session: Session) -> list[dict]:
    """Sincroniza lo que esté configurado. Nunca lanza: devuelve el resultado de cada fuente."""
    with _cerrojo:
        resultados = []
        if config.INDEXA_TOKEN:
            resultados.append(sincronizar_indexa(session))
        if enablebanking.configurado() and enablebanking.conexion_activa(session):
            resultados.append(sincronizar_sabadell(session))
        guardar_instantanea(session)
        return resultados


def estado(session: Session) -> dict:
    def ultimo(fuente):
        r = session.scalar(select(RegistroSync).where(RegistroSync.fuente == fuente)
                           .order_by(RegistroSync.id.desc()).limit(1))
        return None if r is None else {"fecha": iso_utc(r.fecha), "ok": r.ok,
                                       "mensaje": r.mensaje}

    con = enablebanking.conexion_activa(session)
    return {
        "sabadell": {
            "configurado": enablebanking.configurado(),
            "conectado": con is not None,
            "valida_hasta": con.valida_hasta.date().isoformat() if con and con.valida_hasta else None,
            "ultima": ultimo("sabadell"),
            "url_vuelta": config.ENABLE_BANKING_REDIRECT_URL,
            # Con la app publicada (https), el banco vuelve directamente a /sabadell/vuelta y se completa solo
            "vuelta_automatica": not config.ENABLE_BANKING_REDIRECT_URL.startswith("https://localhost"),
        },
        "indexa": {"configurado": bool(config.INDEXA_TOKEN), "ultima": ultimo("indexa")},
        "cada_horas": config.SYNC_HORAS,
        "en_vercel": config.EN_VERCEL,
    }


class Programador:
    """Hilo que sincroniza al arrancar y luego cada SYNC_HORAS mientras la app esté abierta."""

    def __init__(self, horas: float):
        self.horas = horas
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, daemon=True, name="sync")

    def arrancar(self):
        if self.horas > 0:
            self._hilo.start()

    def parar(self):
        self._parar.set()

    def _bucle(self):
        while not self._parar.is_set():
            try:
                with db.SessionLocal() as s:
                    for r in sincronizar_todo(s):
                        log.info("sync %s: %s", r["fuente"], r["mensaje"])
            except Exception:
                log.exception("Fallo en la sincronización automática")
            self._parar.wait(self.horas * 3600)
