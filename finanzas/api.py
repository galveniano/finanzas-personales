"""API JSON que consume el frontal (carpeta frontend/)."""
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from finanzas import auth, config, db, patrimonio, sync
from finanzas.fechas import iso_utc
from finanzas.fiscal import alquiler, autonomo, nomina as calc_nomina
from finanzas.hipoteca import cuota_mensual, intereses_anio, saldo_pendiente
from finanzas.importers import aeat, sabadell
from finanzas.integrations import enablebanking
from finanzas.models import (
    DocumentoDrive, Activo, CambioRenta, Categoria, Cliente, ContratoAlquiler, Cuenta, Declaracion, Deuda, Factura, GastoAutonomo,
    GastoInmueble, Instantanea, InversionPrivada, Movimiento, Nomina, Objetivo, PagoPrevisto, Valoracion,
)

router = APIRouter(prefix="/api", dependencies=[Depends(auth.requiere_sesion)])
SesionDB = Depends(db.get_session)
CERO = Decimal("0")
# Parte tuya de cada cuenta (participacion vacía = 100 %): las cuentas que no son tuyas pesan 0
PARTE = func.coalesce(Cuenta.participacion, 100) / 100


def n(valor) -> float | None:
    return None if valor is None else float(valor)


def f(valor: date | None) -> str | None:
    return valor.isoformat() if valor else None


def _obtener(s: Session, modelo, id_: int):
    obj = s.get(modelo, id_)
    if obj is None:
        raise HTTPException(404, f"No existe {modelo.__name__} {id_}")
    return obj


# --- Resumen (panel) --------------------------------------------------------

def _gasto_por_mes(s: Session, meses: int = 6) -> list[dict]:
    from finanzas import prevision
    desde = (date.today().replace(day=1) - timedelta(days=31 * (meses - 1))).replace(day=1)
    movs = prevision.movimientos_tuyos(s, desde)
    traspasos = prevision.ids_traspaso(movs)
    por_mes: dict[str, dict] = defaultdict(lambda: {"ingresos": 0.0, "gastos": 0.0})
    for m in movs:
        if m.tipo == "transferencia" or m.id in traspasos:
            continue
        clave = m.fecha.strftime("%Y-%m")
        if m.tuyo >= 0:
            por_mes[clave]["ingresos"] += m.tuyo
        else:
            por_mes[clave]["gastos"] += -m.tuyo
    return [{"mes": k, "ingresos": round(v["ingresos"], 2), "gastos": round(v["gastos"], 2)}
            for k, v in sorted(por_mes.items())]


def _gasto_por_categoria(s: Session, dias: int = 30) -> list[dict]:
    from finanzas import prevision
    movs = prevision.movimientos_tuyos(s, date.today() - timedelta(days=dias))
    traspasos = prevision.ids_traspaso(movs)
    por_cat: dict[str, float] = defaultdict(float)
    for m in movs:
        if m.importe < 0 and m.tipo != "transferencia" and m.id not in traspasos:
            por_cat[m.categoria or "Sin categoría"] += -m.tuyo
    return sorted(({"categoria": c, "importe": round(t, 2)} for c, t in por_cat.items()), key=lambda x: -x["importe"])


@router.get("/resumen")
def resumen(s: Session = SesionDB):
    from finanzas import avisos, hacienda, prevision
    hoy = date.today()
    prev_completa = prevision.calcular(s)
    pendiente = hacienda.pendiente(s, prev_completa)
    p = patrimonio.calcular(s, hoy, pendiente)
    facturas, gastos = s.scalars(select(Factura)).all(), s.scalars(select(GastoAutonomo)).all()
    # El trimestre que toca pagar: el anterior mientras dura su plazo (hasta el 20, o el 30 de enero), si no el actual
    anio_t, t = hoy.year, autonomo.trimestre_de(hoy)
    if hoy.month in (1, 4, 7, 10) and hoy.day <= (30 if hoy.month == 1 else 20):
        anio_t, t = (hoy.year - 1, 4) if t == 1 else (hoy.year, t - 1)
    m303 = autonomo.calcular_303(anio_t, t, facturas, gastos)
    presentadas = _presentadas(s, anio_t)
    m130 = autonomo.calcular_130(anio_t, t, facturas, gastos, _presentados_130(presentadas))
    d303, d130 = presentadas.get(("303", t)), presentadas.get(("130", t))
    # Si hay previsión, lo no presentado sale de ella, igual que en Autónomo y Previsión
    prev = prev_completa if prevision.leer(s).get("clientes") or prevision.leer(s).get("nomina") else None
    p_t = (prev or {}).get("trimestres", {}).get(f"{anio_t}-{t}")
    renta = next((a for a in (prev or {}).get("anios", []) if a["anio"] == hoy.year), None)
    sync.rellenar_vehiculos(s)
    historico = s.scalars(select(Instantanea).order_by(Instantanea.fecha)).all()
    proximos = s.scalars(select(PagoPrevisto).where(~PagoPrevisto.pagado).order_by(PagoPrevisto.fecha).limit(6))
    return {
        "fecha": f(hoy),
        "neto": n(p.neto), "activos": n(p.total_activos), "pasivos": n(p.total_pasivos),
        "grupos": [{"grupo": g, "importe": n(v)} for g, v in p.por_grupo().items()],
        "lineas_activo": [{"nombre": l.nombre, "grupo": l.grupo, "importe": n(l.importe), "detalle": l.detalle}
                          for l in p.activos],
        "lineas_pasivo": [{"nombre": l.nombre, "grupo": l.grupo, "importe": n(l.importe), "detalle": l.detalle}
                          for l in p.pasivos],
        "historico": [{"fecha": f(i.fecha), "neto": n(i.neto), "liquidez": n(i.liquidez),
                       "inversiones": n(i.inversiones), "inmuebles": n(i.inmuebles), "vehiculos": n(i.vehiculos),
                       "deudas": n(i.deudas)}
                      for i in historico],
        "flujo_mensual": _gasto_por_mes(s),
        "gasto_categorias": _gasto_por_categoria(s),
        "proximos_pagos": [{"id": pp.id, "concepto": pp.concepto, "fecha": f(pp.fecha), "importe": n(pp.importe)}
                           for pp in proximos],
        "fiscal": {
            "trimestre": t, "anio": anio_t,
            "iva": {"resultado": n(d303.importe) if d303 else p_t["iva"] if p_t else n(m303.resultado),
                    "presentado": bool(d303), "previsto": bool(p_t and not d303),
                    "repercutido": n(m303.iva_repercutido),
                    "soportado": n(m303.iva_soportado_deducible), "plazo": m303.plazo},
            "irpf": {"resultado": n(d130.importe) if d130 else p_t["irpf"] if p_t else n(m130.resultado),
                     "presentado": bool(d130), "previsto": bool(p_t and not d130),
                     "exento": False if d130 else p_t["exento_130"] if p_t else m130.exento,
                     "notas": [] if d130 or p_t else m130.notas, "plazo": m130.plazo},
            "renta": {"anio": renta["anio"], "resultado": renta["resultado"], "cuota": renta["cuota"],
                      "neto_mes": renta["ingresos"]["total"]["neto_mes"],
                      "bruto_mes": renta["ingresos"]["total"]["bruto_mes"]} if renta else None,
        },
        "sync": sync.estado(s),
        "liquidez": n(p.por_grupo().get("Liquidez", CERO)),
        "hacienda_pendiente": pendiente,
        "disponible": round(float(p.por_grupo().get("Liquidez", CERO)) - pendiente["total"], 2),
        "avisos": avisos.calcular(s, hacienda.revision_reta(s, prev_completa)),
    }


# --- Cuentas y movimientos --------------------------------------------------

class CuentaIn(BaseModel):
    nombre: str
    entidad: str = ""
    tipo: str = "corriente"
    iban: str = ""
    saldo: Decimal = CERO


def _cuenta(c: Cuenta) -> dict:
    return {"id": c.id, "nombre": c.nombre, "entidad": c.entidad, "tipo": c.tipo, "iban": c.iban,
            "origen": c.origen, "saldo": n(c.saldo), "saldo_fecha": f(c.saldo_fecha),
            "participacion": n(c.parte * 100), "saldo_tuyo": n((c.saldo * c.parte).quantize(Decimal("0.01"))),
            "ultima_sincronizacion": iso_utc(c.ultima_sincronizacion)}


@router.get("/indexa")
def detalle_indexa(s: Session = SesionDB):
    """Posiciones y rentabilidad de cada cuenta de Indexa (de la última sincronización)."""
    import json
    cuentas = s.scalars(select(Cuenta).where(Cuenta.origen == "indexa", Cuenta.activa).order_by(Cuenta.nombre))
    return [{"cuenta_id": c.id, "nombre": c.nombre, "numero": c.id_externo, "fecha": f(c.saldo_fecha),
             **json.loads(c.detalle or "{}")} for c in cuentas]


@router.get("/cuentas")
def listar_cuentas(s: Session = SesionDB):
    return [_cuenta(c) for c in s.scalars(select(Cuenta).where(Cuenta.activa).order_by(Cuenta.tipo, Cuenta.nombre))]


@router.post("/cuentas")
def crear_cuenta(datos: CuentaIn, s: Session = SesionDB):
    c = Cuenta(**datos.model_dump(), saldo_fecha=date.today() if datos.saldo else None)
    s.add(c)
    s.commit()
    return _cuenta(c)


@router.post("/cuentas/{cuenta_id}/importar")
async def importar_extracto(cuenta_id: int, fichero: UploadFile = File(...), s: Session = SesionDB):
    cuenta = _obtener(s, Cuenta, cuenta_id)
    try:
        r = sabadell.importar(s, cuenta, fichero.filename or "extracto.csv", await fichero.read())
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"leidos": r.leidos, "nuevos": r.nuevos, "duplicados": r.duplicados}


@router.get("/categorias")
def listar_categorias(s: Session = SesionDB):
    return [{"id": c.id, "nombre": c.nombre, "tipo": c.tipo, "ambito": c.ambito}
            for c in s.scalars(select(Categoria).order_by(Categoria.nombre))]


@router.get("/movimientos")
def listar_movimientos(cuenta_id: int | None = None, categoria_id: int | None = None, q: str = "",
                       limite: int = 300, solo_tuyas: bool = False, s: Session = SesionDB):
    consulta = select(Movimiento).order_by(Movimiento.fecha.desc(), Movimiento.id.desc()).limit(limite)
    if cuenta_id:
        consulta = consulta.where(Movimiento.cuenta_id == cuenta_id)
    elif solo_tuyas:  # sin elegir cuenta, fuera las que no son tuyas
        consulta = consulta.join(Cuenta, Movimiento.cuenta_id == Cuenta.id).where(PARTE > 0)
    if categoria_id == 0:
        consulta = consulta.where(Movimiento.categoria_id.is_(None))
    elif categoria_id:
        consulta = consulta.where(Movimiento.categoria_id == categoria_id)
    if q:
        consulta = consulta.where(Movimiento.concepto.ilike(f"%{q}%"))
    return [{"id": m.id, "cuenta_id": m.cuenta_id, "cuenta": m.cuenta.nombre, "fecha": f(m.fecha),
             "concepto": m.concepto, "importe": n(m.importe), "saldo": n(m.saldo),
             "categoria_id": m.categoria_id} for m in s.scalars(consulta)]


class CuentaPatch(BaseModel):
    nombre: str | None = None
    participacion: Decimal | None = None


@router.patch("/cuentas/{cuenta_id}")
def actualizar_cuenta(cuenta_id: int, datos: CuentaPatch, s: Session = SesionDB):
    c = _obtener(s, Cuenta, cuenta_id)
    if datos.nombre is not None and datos.nombre.strip():
        c.nombre = datos.nombre.strip()[:120]
    if datos.participacion is not None:
        if not 0 <= datos.participacion <= 100:
            raise HTTPException(400, "La parte tuya tiene que estar entre 0 y 100 %")
        c.participacion = datos.participacion
    s.commit()
    from finanzas import sync
    sync.guardar_instantanea(s)  # el patrimonio cambia
    return _cuenta(c)


class MovimientoPatch(BaseModel):
    categoria_id: int | None = None


@router.patch("/movimientos/{mov_id}")
def actualizar_movimiento(mov_id: int, datos: MovimientoPatch, s: Session = SesionDB):
    """Al cambiar la categoría se aprende la regla para los siguientes y se dice cuántos anteriores parecidos hay."""
    from finanzas import categorizar
    m = _obtener(s, Movimiento, mov_id)
    m.categoria_id = datos.categoria_id
    s.commit()
    return {"ok": True, **categorizar.aprender(s, m)}


@router.post("/movimientos/{mov_id}/aplicar-a-parecidos")
def aplicar_a_parecidos(mov_id: int, s: Session = SesionDB):
    from finanzas import categorizar
    m = _obtener(s, Movimiento, mov_id)
    parecidos = categorizar.parecidos(s, m)
    for x in parecidos:
        x.categoria_id = m.categoria_id
    s.commit()
    return {"ok": True, "cambiados": len(parecidos)}


@router.delete("/cuentas/{cuenta_id}")
def borrar_cuenta(cuenta_id: int, s: Session = SesionDB):
    """Las cuentas manuales o de extractos se borran con sus movimientos; las que vienen del banco o de
    Indexa solo se ocultan (volverían en la siguiente sincronización)."""
    c = _obtener(s, Cuenta, cuenta_id)
    if c.origen in ("enable_banking", "indexa"):
        c.activa = False
        oculta = True
    else:
        for m in s.scalars(select(Movimiento).where(Movimiento.cuenta_id == c.id)):
            s.delete(m)
        s.delete(c)
        oculta = False
    s.commit()
    sync.guardar_instantanea(s)
    return {"ok": True, "oculta": oculta}


# --- Sincronización ---------------------------------------------------------

@router.get("/sync")
def estado_sync(s: Session = SesionDB):
    return sync.estado(s)


@router.post("/sync")
def sincronizar_todo(s: Session = SesionDB):
    return {"resultados": sync.sincronizar_todo(s), "estado": sync.estado(s)}


@router.post("/sync/indexa")
def sincronizar_indexa(s: Session = SesionDB):
    r = sync.sincronizar_indexa(s)
    sync.guardar_instantanea(s)
    return r


@router.post("/sync/sabadell")
def sincronizar_sabadell(s: Session = SesionDB):
    r = sync.sincronizar_sabadell(s)
    sync.guardar_instantanea(s)
    return r


COOKIE_ESTADO_BANCO = "finanzas_banco_estado"


@router.post("/sync/sabadell/conectar")
def conectar_sabadell(response: Response):
    estado = enablebanking.nuevo_estado()
    try:
        url = enablebanking.iniciar_autorizacion(estado=estado)
    except enablebanking.EnableBankingError as e:
        raise HTTPException(400, str(e))
    # A la vuelta del banco se comprueba que el state es este: así nadie puede colarte otra conexión
    response.set_cookie(COOKIE_ESTADO_BANCO, estado, max_age=1800, httponly=True, secure=config.EN_VERCEL,
                        samesite="lax", path="/")
    return {"url": url}


class CodigoIn(BaseModel):
    codigo: str


@router.post("/sync/sabadell/completar")
def completar_sabadell(datos: CodigoIn, request: Request, s: Session = SesionDB):
    estado = enablebanking.extraer_estado(datos.codigo)
    if estado is not None and estado != request.cookies.get(COOKIE_ESTADO_BANCO):
        raise HTTPException(400, "Esa dirección no corresponde a la conexión que has empezado. Vuelve a pulsar Conectar.")
    try:
        con = enablebanking.completar_autorizacion(s, enablebanking.extraer_code(datos.codigo))
    except enablebanking.EnableBankingError as e:
        raise HTTPException(400, str(e))
    r = sync.sincronizar_sabadell(s)
    sync.guardar_instantanea(s)
    return {"valida_hasta": con.valida_hasta.date().isoformat() if con.valida_hasta else None, "sync": r}


# --- Autónomo ---------------------------------------------------------------

class FacturaIn(BaseModel):
    numero: str
    cliente: str
    fecha: date
    concepto: str = ""
    base: Decimal
    tipo_iva: Decimal = Decimal("21")
    tipo_retencion: Decimal = Decimal("15")
    fecha_cobro: date | None = None


class GastoAutonomoIn(BaseModel):
    fecha: date
    proveedor: str = ""
    concepto: str = ""
    categoria: str = "otros"
    base: Decimal
    tipo_iva: Decimal = Decimal("21")
    deducible_pct: Decimal = Decimal("100")


@dataclass
class Presentada:
    """Un 303 o 130 de un trimestre. Con complementarias, lo pagado es la suma de todas y las casillas
    (acumuladas) las de la última."""
    importe: Decimal
    casillas: str | None


def _presentadas(s: Session, anio: int) -> dict[tuple[str, int], Presentada]:
    """Los 303 y 130 presentados del año, por (modelo, trimestre)."""
    decl = s.scalars(select(Declaracion).where(
        Declaracion.ejercicio == anio, Declaracion.modelo.in_(("303", "130")),
        Declaracion.periodo.in_(("1T", "2T", "3T", "4T"))).order_by(Declaracion.id)).all()
    res: dict[tuple[str, int], Presentada] = {}
    for d in decl:
        clave = (d.modelo, int(d.periodo[0]))
        previa = res.get(clave)
        res[clave] = Presentada((previa.importe if previa else CERO) + d.importe, d.casillas or (previa and previa.casillas))
    return res


def _casillas(d: Declaracion | Presentada | None) -> dict:
    try:
        return json.loads(d.casillas) if d and d.casillas else {}
    except ValueError:
        return {}


def _presentados_130(presentadas: dict[tuple[str, int], Declaracion]) -> dict[int, tuple]:
    """Los 130 presentados por trimestre, con su importe y casillas, para que la estimación parta de ellos."""
    return {t: (d.importe, _casillas(d)) for (mod, t), d in presentadas.items() if mod == "130"}


def _autonomo_por_anio(s: Session, facturas, gastos, previsto: dict) -> list[dict]:
    """Facturado y ganado neto (menos gastos e IRPF de la actividad) de cada año con facturas.
    El año en curso, si hay previsión, se completa con lo previsto."""
    from finanzas import prevision
    cfg = prevision.resolver_clientes(s, prevision.leer(s))
    rentas = {d.ejercicio: _casillas(d) for d in s.scalars(select(Declaracion).where(Declaracion.modelo == "100")
                                                           .order_by(Declaracion.id))}
    anios = sorted({x.fecha.year for x in facturas} | {int(k[:4]) for k in previsto}
                   | {a for a, c in rentas.items() if c.get("ingresos_actividad")})
    filas = []
    for anio in anios:
        facturado = float(sum((x.base for x in facturas if x.fecha.year == anio), CERO))
        gasto = float(sum((g.base * g.deducible_pct / 100 for g in gastos if g.fecha.year == anio), CERO))
        prev = [v for k, v in previsto.items() if k.startswith(f"{anio}-")]
        es_previsto = bool(prev) and anio >= date.today().year
        if es_previsto:
            facturado = max(facturado, sum(v["base"] for v in prev))
            gasto = max(gasto, float(cfg.get("gastos_autonomo_mes", 0)) * 12)
        renta = rentas.get(anio, {})
        if not es_previsto and renta.get("ingresos_actividad"):
            # Año con la renta presentada: lo declarado manda
            facturado, gasto = renta["ingresos_actividad"], renta.get("gastos_actividad", gasto)
        rendimiento = max(facturado - gasto, 0.0)
        if renta.get("cuota") and renta.get("base_general"):
            irpf = rendimiento * renta["cuota"] / renta["base_general"]  # tipo medio real de ese año
        else:
            irpf = prevision.irpf_de_la_actividad(cfg, rendimiento)
        filas.append({"anio": anio, "facturado": round(facturado, 2), "gastos": round(gasto, 2),
                      "irpf": round(irpf, 2), "neto": round(facturado - gasto - irpf, 2), "previsto": es_previsto})
    return filas


@router.get("/autonomo")
def ver_autonomo(anio: int | None = None, s: Session = SesionDB):
    """Lo presentado en Hacienda manda; las facturas sirven para estimar lo que aún no se ha presentado."""
    anio = anio or date.today().year
    facturas = s.scalars(select(Factura).order_by(Factura.fecha.desc())).all()
    gastos = s.scalars(select(GastoAutonomo).order_by(GastoAutonomo.fecha.desc())).all()
    hay_facturas = any(x.fecha.year == anio for x in facturas)
    presentadas = _presentadas(s, anio)
    # Lo no presentado se estima con la previsión (sueldo, tarifas y días del último mes) si está configurada
    from finanzas import prevision
    previsto = prevision.calcular(s)["trimestres"] if prevision.leer(s).get("clientes") else {}
    trimestres, ingresos_declarados, ultimo_130 = [], None, None
    for t in range(1, 5):
        m303 = autonomo.calcular_303(anio, t, facturas, gastos)
        m130 = autonomo.calcular_130(anio, t, facturas, gastos, _presentados_130(presentadas))
        d303, d130 = presentadas.get(("303", t)), presentadas.get(("130", t))
        p = previsto.get(f"{anio}-{t}")
        c130 = _casillas(d130)
        if "ingresos" in c130:
            ingresos_declarados, ultimo_130 = c130["ingresos"], t
        trimestres.append({
            "trimestre": t, "plazo": m303.plazo,
            "base": n(m303.base_repercutida), "iva_repercutido": n(m303.iva_repercutido),
            "iva_soportado": n(m303.iva_soportado_deducible),
            "iva_resultado": n(d303.importe) if d303 else p["iva"] if p else n(m303.resultado),
            "iva_fuente": "presentado" if d303 else "previsto" if p else "estimado",
            "iva_estimado": n(m303.resultado) if hay_facturas else None,
            "ingresos_acumulados": c130.get("ingresos"),
            "rendimiento_acumulado": c130.get("rendimiento", n(m130.rendimiento_neto)),
            "retenciones_acumuladas": c130.get("retenciones", n(m130.retenciones_acumuladas)),
            "irpf_resultado": n(d130.importe) if d130 else p["irpf"] if p else n(m130.resultado),
            "irpf_fuente": "presentado" if d130 else "previsto" if p else "estimado",
            "base_prevista": p["base"] if p and not d303 else None,
            "irpf_estimado": n(m130.resultado) if hay_facturas else None,
            "exento_130": False if d130 else p["exento_130"] if p else m130.exento,
            "notas": [] if d130 or p else m130.notas,
        })
    pagado = {m: n(sum((d.importe for (mod, _), d in presentadas.items() if mod == m), CERO)) for m in ("303", "130")}
    por_anio = _autonomo_por_anio(s, facturas, gastos, previsto)
    del_anio = [x for x in facturas if x.fecha.year == anio]
    return {
        "anio": anio, "trimestres": trimestres,
        "ingresos_declarados": ingresos_declarados, "ultimo_130": ultimo_130, "por_anio": por_anio,
        "pagado_iva": pagado["303"], "pagado_irpf": pagado["130"],
        "total_facturado": n(sum((x.base for x in del_anio), CERO)),
        "por_cliente": [{"cliente": c, "base": n(b)} for c, b in sorted(
            {x.cliente.nombre: sum((y.base for y in del_anio if y.cliente_id == x.cliente_id), CERO)
             for x in del_anio}.items(), key=lambda kv: -kv[1])],
        "facturas": [{"id": x.id, "numero": x.numero, "cliente": x.cliente.nombre, "fecha": f(x.fecha),
                      "concepto": x.concepto, "base": n(x.base), "tipo_iva": n(x.tipo_iva),
                      "tipo_retencion": n(x.tipo_retencion), "cuota_iva": n(x.cuota_iva),
                      "retencion": n(x.retencion), "total": n(x.total_a_cobrar), "fecha_cobro": f(x.fecha_cobro)}
                     for x in del_anio],
        "gastos": [{"id": g.id, "fecha": f(g.fecha), "proveedor": g.proveedor, "concepto": g.concepto,
                    "categoria": g.categoria, "base": n(g.base), "tipo_iva": n(g.tipo_iva),
                    "cuota_iva": n(g.cuota_iva), "deducible_pct": n(g.deducible_pct)}
                   for g in gastos if g.fecha.year == anio],
        "clientes": [c.nombre for c in s.scalars(select(Cliente).order_by(Cliente.nombre))],
    }


@router.post("/autonomo/facturas")
def crear_factura(datos: FacturaIn, s: Session = SesionDB):
    nombre = datos.cliente.strip()
    cli = s.scalar(select(Cliente).where(Cliente.nombre == nombre))
    if cli is None:
        cli = Cliente(nombre=nombre)
        s.add(cli)
        s.flush()
    valores = datos.model_dump(exclude={"cliente"})
    s.add(Factura(cliente_id=cli.id, **valores))
    s.commit()
    return {"ok": True}


@router.post("/autonomo/gastos")
def crear_gasto_autonomo(datos: GastoAutonomoIn, s: Session = SesionDB):
    s.add(GastoAutonomo(**datos.model_dump()))
    s.commit()
    return {"ok": True}


@router.delete("/autonomo/{tipo}/{item_id}")
def borrar_autonomo(tipo: str, item_id: int, s: Session = SesionDB):
    modelo = {"facturas": Factura, "gastos": GastoAutonomo}.get(tipo)
    if modelo is None:
        raise HTTPException(404)
    s.delete(_obtener(s, modelo, item_id))
    s.commit()
    return {"ok": True}


# --- Nóminas ----------------------------------------------------------------

class NominaIn(BaseModel):
    empresa: str = "Indra"
    fecha: date
    bruto: Decimal
    retencion_irpf: Decimal
    seguridad_social: Decimal
    neto: Decimal


def _nominas_banco(s: Session) -> list[Movimiento]:
    """Ingresos categorizados como Nómina en tus cuentas (los dos últimos años)."""
    return s.scalars(
        select(Movimiento).join(Cuenta, Movimiento.cuenta_id == Cuenta.id)
        .join(Categoria, Movimiento.categoria_id == Categoria.id)
        .where(Categoria.nombre == "Nómina", Movimiento.importe > 0, PARTE > 0,
               Movimiento.fecha >= date.today() - timedelta(days=730))
        .order_by(Movimiento.fecha.desc())).all()


@router.get("/nominas")
def listar_nominas(anio: int | None = None, s: Session = SesionDB):
    """Las nóminas registradas mandan; si no hay, se sacan de los ingresos de nómina del banco
    (solo se ve el neto: bruto, IRPF y Seguridad Social se estiman a partir de él)."""
    anio = anio or date.today().year
    nominas = s.scalars(select(Nomina).order_by(Nomina.fecha.desc())).all()
    del_anio = [x for x in nominas if x.fecha.year == anio]
    totales = {k: n(sum((getattr(x, k) for x in del_anio), CERO))
               for k in ("bruto", "retencion_irpf", "seguridad_social", "neto")}
    hace_un_anio = date.today() - timedelta(days=365)
    ultimos = [x for x in nominas if x.fecha > hace_un_anio]
    bruto_12 = n(sum((x.bruto for x in ultimos), CERO)) if ultimos else None

    banco = _nominas_banco(s)
    estimado, fuente = None, "nominas" if del_anio else "ninguna"
    recientes = [m for m in banco if m.fecha > hace_un_anio]
    if recientes:
        meses = len({(m.fecha.year, m.fecha.month) for m in recientes})
        neto_medio = float(sum((m.importe for m in recientes), CERO)) / meses
        # Media de lo cobrado (con extras incluidas) como si fueran 12 pagas iguales
        c = calc_nomina.bruto_para_neto(neto_medio, pagas=12)
        estimado = {"neto_medio_mes": round(neto_medio, 2), "meses": meses, "bruto_anual": c.bruto_anual,
                    "irpf_anual": c.irpf_anual, "ss_anual": c.ss_anual, "tipo_irpf": c.tipo_irpf}
        bruto_12 = bruto_12 if ultimos else c.bruto_anual
        cobrado = sum((m.importe for m in banco if m.fecha.year == anio), CERO)
        if not del_anio and cobrado:
            parte = float(cobrado) / c.neto_anual
            totales = {"bruto": round(c.bruto_anual * parte, 2), "retencion_irpf": round(c.irpf_anual * parte, 2),
                       "seguridad_social": round(c.ss_anual * parte, 2), "neto": n(cobrado)}
            fuente = "banco"
    return {"anio": anio, "totales": totales, "fuente": fuente, "bruto_12_meses": bruto_12, "estimado_banco": estimado,
            "banco": [{"id": m.id, "fecha": f(m.fecha), "concepto": m.concepto, "importe": n(m.importe),
                       "cuenta": m.cuenta.nombre} for m in banco],
            "nominas": [{"id": x.id, "empresa": x.empresa, "fecha": f(x.fecha), "bruto": n(x.bruto),
                         "retencion_irpf": n(x.retencion_irpf), "seguridad_social": n(x.seguridad_social),
                         "neto": n(x.neto)} for x in nominas]}


@router.get("/nominas/calculo")
def calcular_nomina(bruto_anual: float | None = None, neto_mes: float | None = None, pagas: int = 14,
                    hijos: int = 0, temporal: bool = False):
    """De bruto anual a neto de cada mes, o el bruto que hace falta para un neto mensual."""
    try:
        if neto_mes is not None:
            return calc_nomina.bruto_para_neto(neto_mes, pagas, hijos, temporal).a_dict()
        if bruto_anual is None:
            raise HTTPException(400, "Indica el bruto anual o el neto mensual")
        return calc_nomina.calcular(bruto_anual, pagas, hijos, temporal).a_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/nominas")
def crear_nomina(datos: NominaIn, s: Session = SesionDB):
    s.add(Nomina(**datos.model_dump()))
    s.commit()
    return {"ok": True}


@router.delete("/nominas/{nomina_id}")
def borrar_nomina(nomina_id: int, s: Session = SesionDB):
    s.delete(_obtener(s, Nomina, nomina_id))
    s.commit()
    return {"ok": True}


# --- Inmuebles --------------------------------------------------------------

class ActivoIn(BaseModel):
    nombre: str
    tipo: str = "inmueble"
    uso: str = "otro"
    fecha_compra: date | None = None
    precio_compra: Decimal = CERO
    gastos_compra: Decimal = CERO
    valor_catastral: Decimal = CERO
    valor_catastral_construccion: Decimal = CERO
    porcentaje_propiedad: Decimal = Decimal("100")


class ValoracionIn(BaseModel):
    fecha: date
    valor: Decimal


class HipotecaIn(BaseModel):
    nombre: str = "Hipoteca"
    entidad: str = "Banco Sabadell"
    capital_inicial: Decimal
    tipo_interes_anual: Decimal
    fecha_inicio: date
    plazo_meses: int
    saldo_pendiente_manual: Decimal | None = None


class ContratoIn(BaseModel):
    inquilino: str = ""
    fecha_inicio: date
    fecha_fin: date | None = None
    renta_mensual: Decimal
    # Vacío: 60 % si el contrato es anterior al 26/05/2023 y 50 % si es posterior
    reduccion_pct: Decimal | None = None


class RentaIn(BaseModel):
    desde: date
    renta_mensual: Decimal


class GastoInmuebleIn(BaseModel):
    fecha: date
    tipo: str
    importe: Decimal
    concepto: str = ""


def _pct(parte: Decimal, total: Decimal) -> float | None:
    return round(float(parte / total * 100), 2) if total > 0 else None


def _rentabilidad(a: Activo, contratos, gastos, deudas, valor: Decimal, hoy: date) -> dict | None:
    """Rentabilidad del alquiler con la renta de hoy y los gastos de los últimos 12 meses.
    Bruta y neta sobre lo que costó (precio + gastos de compra); también sobre el dinero que pusiste tú."""
    vigentes = [c for c in contratos if c.fecha_inicio <= hoy and (not c.fecha_fin or c.fecha_fin >= hoy)]
    if a.tipo != "inmueble" or not vigentes:
        return None
    renta = sum((c.renta_en(hoy) for c in vigentes), CERO) * 12
    coste = a.precio_compra + a.gastos_compra
    gastos_anio = sum((g.importe for g in gastos if g.tipo != "intereses" and g.fecha > hoy - timedelta(days=365)), CERO)
    intereses = sum((intereses_anio(d, hoy.year) for d in deudas), CERO)
    cuotas = sum((cuota_mensual(d.capital_inicial, d.tipo_interes_anual, d.plazo_meses) * 12
                  for d in deudas if saldo_pendiente(d, hoy) > 0), CERO)
    aportado = coste - sum((d.capital_inicial for d in deudas), CERO)
    neto = renta - gastos_anio
    return {"renta_anual": n(renta), "gastos_anuales": n(gastos_anio), "intereses_anuales": n(intereses),
            "cuotas_anuales": n(cuotas), "coste": n(coste), "aportado": n(aportado),
            "bruta": _pct(renta, coste), "neta": _pct(neto, coste), "neta_sobre_valor": _pct(neto, valor),
            "sobre_aportado": _pct(neto - intereses, aportado), "flujo_caja_anual": n(neto - cuotas)}


@router.get("/inmuebles")
def listar_inmuebles(anio: int | None = None, s: Session = SesionDB):
    anio = anio or date.today().year
    hoy = date.today()
    fichas = []
    for a in s.scalars(select(Activo).order_by(Activo.nombre)):
        deudas = s.scalars(select(Deuda).where(Deuda.activo_id == a.id)).all()
        contratos = s.scalars(select(ContratoAlquiler).where(ContratoAlquiler.activo_id == a.id)).all()
        gastos = s.scalars(select(GastoInmueble).where(GastoInmueble.activo_id == a.id)
                           .order_by(GastoInmueble.fecha.desc())).all()
        pagos = s.scalars(select(PagoPrevisto).where(PagoPrevisto.activo_id == a.id).order_by(PagoPrevisto.fecha)).all()
        rend = None
        if contratos:
            gastos_calc = list(gastos)
            if not any(g.tipo == "intereses" and g.fecha.year == anio for g in gastos):
                for d in deudas:
                    gastos_calc.append(GastoInmueble(activo_id=a.id, fecha=date(anio, 12, 31),
                                                     tipo="intereses", importe=intereses_anio(d, anio)))
            r = alquiler.calcular_rendimiento(a, contratos, gastos_calc, anio)
            rend = {"anio": anio, "ingresos": n(r.ingresos), "gastos_limitados": n(r.gastos_limitados_aplicables),
                    "gastos_otros": n(r.gastos_otros), "amortizacion": n(r.amortizacion),
                    "rendimiento_neto": n(r.rendimiento_neto), "reduccion_pct": n(r.reduccion_pct),
                    "reduccion": n(r.reduccion), "rendimiento_reducido": n(r.rendimiento_reducido), "notas": r.notas}
        if a.tipo == "inmueble_en_construccion":
            valor, detalle = sum((p.importe for p in pagos if p.pagado), CERO), "pagado a la promotora"
        else:
            valor, detalle = patrimonio.valor_activo(a, hoy)
        deuda_total = sum((saldo_pendiente(d, hoy) for d in deudas), CERO)
        fichas.append({
            "rentabilidad": _rentabilidad(a, contratos, gastos, deudas, valor, hoy), "notas": a.notas,
            "id": a.id, "nombre": a.nombre, "tipo": a.tipo, "uso": a.uso, "fecha_compra": f(a.fecha_compra),
            "precio_compra": n(a.precio_compra), "gastos_compra": n(a.gastos_compra),
            "valor_catastral": n(a.valor_catastral), "valor_catastral_construccion": n(a.valor_catastral_construccion),
            "porcentaje_propiedad": n(a.porcentaje_propiedad),
            "valor": n(valor), "valor_detalle": detalle, "deuda": n(deuda_total), "equity": n(valor - deuda_total),
            "valoraciones": [{"id": v.id, "fecha": f(v.fecha), "valor": n(v.valor)} for v in a.valoraciones],
            "hipotecas": [{"id": d.id, "nombre": d.nombre, "entidad": d.entidad, "capital_inicial": n(d.capital_inicial),
                           "tipo_interes_anual": n(d.tipo_interes_anual), "plazo_meses": d.plazo_meses,
                           "fecha_inicio": f(d.fecha_inicio),
                           "cuota": n(cuota_mensual(d.capital_inicial, d.tipo_interes_anual, d.plazo_meses)),
                           "pendiente": n(saldo_pendiente(d, hoy)), "intereses_anio": n(intereses_anio(d, anio)),
                           "futura": bool(d.fecha_inicio and d.fecha_inicio > hoy)}
                          for d in deudas],
            "contratos": [{"id": c.id, "inquilino": c.inquilino, "fecha_inicio": f(c.fecha_inicio),
                           "fecha_fin": f(c.fecha_fin), "renta_inicial": n(c.renta_mensual),
                           "renta_actual": n(c.renta_en(hoy)), "reduccion_pct": n(c.reduccion_pct),
                           "cambios": [{"desde": f(x.desde), "renta": n(x.renta_mensual)} for x in c.cambios_renta]}
                          for c in contratos],
            "gastos": [{"id": g.id, "fecha": f(g.fecha), "tipo": g.tipo, "importe": n(g.importe), "concepto": g.concepto}
                       for g in gastos],
            "pagos": [{"id": p.id, "concepto": p.concepto, "fecha": f(p.fecha), "importe": n(p.importe),
                       "pagado": p.pagado} for p in pagos],
            "rendimiento": rend,
        })
    return {"anio": anio, "inmuebles": fichas}


@router.post("/inmuebles")
def crear_inmueble(datos: ActivoIn, s: Session = SesionDB):
    a = Activo(**datos.model_dump())
    s.add(a)
    s.commit()
    return {"id": a.id}


@router.post("/inmuebles/{activo_id}/valoraciones")
def crear_valoracion(activo_id: int, datos: ValoracionIn, s: Session = SesionDB):
    _obtener(s, Activo, activo_id)
    s.add(Valoracion(activo_id=activo_id, **datos.model_dump()))
    s.commit()
    return {"ok": True}


@router.post("/inmuebles/{activo_id}/hipotecas")
def crear_hipoteca(activo_id: int, datos: HipotecaIn, s: Session = SesionDB):
    _obtener(s, Activo, activo_id)
    s.add(Deuda(activo_id=activo_id, tipo="hipoteca", saldo_fecha=date.today() if datos.saldo_pendiente_manual else None,
                **datos.model_dump()))
    s.commit()
    return {"ok": True}


@router.delete("/deudas/{deuda_id}")
def borrar_deuda(deuda_id: int, s: Session = SesionDB):
    s.delete(_obtener(s, Deuda, deuda_id))
    s.commit()
    return {"ok": True}


@router.post("/inmuebles/{activo_id}/contratos")
def crear_contrato(activo_id: int, datos: ContratoIn, s: Session = SesionDB):
    _obtener(s, Activo, activo_id)
    valores = datos.model_dump()
    if valores["reduccion_pct"] is None:
        valores["reduccion_pct"] = alquiler.reduccion_por_defecto(datos.fecha_inicio)
    s.add(ContratoAlquiler(activo_id=activo_id, **valores))
    s.commit()
    return {"ok": True}


@router.post("/contratos/{contrato_id}/rentas")
def actualizar_renta(contrato_id: int, datos: RentaIn, s: Session = SesionDB):
    _obtener(s, ContratoAlquiler, contrato_id)
    s.add(CambioRenta(contrato_id=contrato_id, **datos.model_dump()))
    s.commit()
    return {"ok": True}


@router.post("/inmuebles/{activo_id}/gastos")
def crear_gasto_inmueble(activo_id: int, datos: GastoInmuebleIn, s: Session = SesionDB):
    _obtener(s, Activo, activo_id)
    s.add(GastoInmueble(activo_id=activo_id, **datos.model_dump()))
    s.commit()
    return {"ok": True}


@router.get("/prevision")
def ver_prevision(meses: int = 12, s: Session = SesionDB):
    from finanzas import prevision
    return prevision.calcular(s, max(1, min(meses, 24)))


class ClientePrevision(BaseModel):
    nombre: str
    tarifa_hora: float
    horas_dia: float = 8
    dias_mes: float | None = None  # vacío: los del último mes facturado
    iva: float = 21
    retencion: float = 15


class NominaPrevision(BaseModel):
    empresa: str = ""
    bruto_anual: float
    variable_pct: float = 0
    mes_variable: int = 3
    pagas: int = 14


class SupuestosPrevision(BaseModel):
    nomina: NominaPrevision | None = None
    clientes: list[ClientePrevision] = []
    gastos_autonomo_mes: float = 0
    gasto_habitual_mes: float | None = None
    meses_sin_facturar: list[int] = []
    # Días que planificas trabajar para un cliente en un mes concreto: {"Cliente": {"2026-11": 18}}
    dias_planificados: dict[str, dict[str, float]] | None = None


class DiasPlanificados(BaseModel):
    cliente: str
    mes: str  # AAAA-MM
    dias: float | None = None  # vacío: quitar lo planificado


@router.put("/prevision/supuestos")
def guardar_supuestos(datos: SupuestosPrevision, s: Session = SesionDB):
    from finanzas import prevision
    if datos.nomina and datos.nomina.pagas not in (12, 14):
        raise HTTPException(400, "Las pagas tienen que ser 12 o 14")
    nuevos = datos.model_dump()
    if nuevos["dias_planificados"] is None:  # el formulario de supuestos no los manda: se conservan
        nuevos["dias_planificados"] = prevision.leer(s).get("dias_planificados") or {}
    prevision.guardar(s, nuevos)
    return {"ok": True}


@router.put("/prevision/dias")
def planificar_dias(datos: DiasPlanificados, s: Session = SesionDB):
    """Guarda los días que vas a trabajar para un cliente en un mes; la previsión los usa en vez de la media."""
    from finanzas import prevision
    try:
        date.fromisoformat(f"{datos.mes}-01")
    except ValueError:
        raise HTTPException(400, "El mes tiene que ser AAAA-MM")
    cfg = prevision.leer(s)
    planes = cfg.get("dias_planificados") or {}
    del_cliente = planes.setdefault(datos.cliente, {})
    if datos.dias is None:
        del_cliente.pop(datos.mes, None)
    else:
        del_cliente[datos.mes] = max(0.0, min(datos.dias, 31.0))
    prevision.guardar(s, {**cfg, "dias_planificados": {k: v for k, v in planes.items() if v}})
    return {"ok": True}


@router.post("/importar/datos")
async def importar_datos(fichero: UploadFile = File(...), s: Session = SesionDB):
    """Fichero JSON con inmuebles, coches e inversiones privadas (ver importers/datos_json.py)."""
    from finanzas.importers import datos_json
    try:
        datos = json.loads(await fichero.read())
        return {"mensajes": datos_json.importar(s, datos)}
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise HTTPException(400, f"No se ha podido importar: {e}")


# --- Planificación ----------------------------------------------------------

class ObjetivoIn(BaseModel):
    nombre: str
    tipo: str = "otro"
    fecha_objetivo: date | None = None
    importe_objetivo: Decimal = CERO
    ahorrado: Decimal = CERO


class ObjetivoPatch(BaseModel):
    nombre: str | None = None
    tipo: str | None = None
    fecha_objetivo: date | None = None
    importe_objetivo: Decimal | None = None
    ahorrado: Decimal | None = None


class PagoIn(BaseModel):
    concepto: str
    fecha: date
    importe: Decimal
    objetivo_id: int | None = None
    activo_id: int | None = None
    inversion_id: int | None = None
    pagado: bool = False


class PagoPatch(BaseModel):
    pagado: bool


def _meses_hasta(d: date) -> int:
    hoy = date.today()
    return max(1, (d.year - hoy.year) * 12 + d.month - hoy.month)


@router.get("/planificacion")
def ver_planificacion(s: Session = SesionDB):
    hoy = date.today()
    objetivos = s.scalars(select(Objetivo).order_by(Objetivo.fecha_objetivo)).all()
    pagos = s.scalars(select(PagoPrevisto).order_by(PagoPrevisto.fecha)).all()
    activos = {a.id: a.nombre for a in s.scalars(select(Activo))}
    inversiones = {i.id: i.nombre for i in s.scalars(select(InversionPrivada))}
    nombres_obj = {o.id: o.nombre for o in objetivos}
    pendiente_12m = sum((p.importe for p in pagos if not p.pagado and p.fecha <= hoy + timedelta(days=365)), CERO)
    # Lo que pagará una hipoteca prevista no sale de tu bolsillo
    financiado = sum((d.capital_inicial for d in s.scalars(select(Deuda).where(
        Deuda.fecha_inicio > hoy, Deuda.fecha_inicio <= hoy + timedelta(days=365)))), CERO)
    pendiente_12m = max(pendiente_12m - financiado, CERO)
    liquidez = sum((c.saldo * c.parte for c in s.scalars(select(Cuenta).where(Cuenta.activa, Cuenta.tipo.in_(
        ["corriente", "ahorro"])))), CERO)
    return {
        "liquidez": n(liquidez), "pendiente_12_meses": n(pendiente_12m), "financiado_hipoteca": n(financiado),
        "objetivos": [{
            "id": o.id, "nombre": o.nombre, "tipo": o.tipo, "fecha_objetivo": f(o.fecha_objetivo),
            "importe_objetivo": n(o.importe_objetivo), "ahorrado": n(o.ahorrado),
            "ahorro_mensual": n(max(CERO, (o.importe_objetivo - o.ahorrado) / _meses_hasta(o.fecha_objetivo)).quantize(
                Decimal("0.01"))) if o.fecha_objetivo and o.fecha_objetivo > hoy else None,
        } for o in objetivos],
        "pagos": [{"id": p.id, "concepto": p.concepto, "fecha": f(p.fecha), "importe": n(p.importe),
                   "pagado": p.pagado, "objetivo": nombres_obj.get(p.objetivo_id), "inmueble": activos.get(p.activo_id),
                   "inversion": inversiones.get(p.inversion_id)}
                  for p in pagos],
        "inmuebles": [{"id": k, "nombre": v} for k, v in activos.items()],
    }


@router.post("/objetivos")
def crear_objetivo(datos: ObjetivoIn, s: Session = SesionDB):
    s.add(Objetivo(**datos.model_dump()))
    s.commit()
    return {"ok": True}


@router.patch("/objetivos/{objetivo_id}")
def actualizar_objetivo(objetivo_id: int, datos: ObjetivoPatch, s: Session = SesionDB):
    o = _obtener(s, Objetivo, objetivo_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        if valor is not None or campo == "fecha_objetivo":
            setattr(o, campo, valor)
    s.commit()
    return {"ok": True}


@router.delete("/objetivos/{objetivo_id}")
def borrar_objetivo(objetivo_id: int, s: Session = SesionDB):
    o = _obtener(s, Objetivo, objetivo_id)
    for p in s.scalars(select(PagoPrevisto).where(PagoPrevisto.objetivo_id == objetivo_id)):
        p.objetivo_id = None  # los pagos se quedan, sin objetivo
    s.delete(o)
    s.commit()
    return {"ok": True}


@router.post("/pagos")
def crear_pago(datos: PagoIn, s: Session = SesionDB):
    s.add(PagoPrevisto(**datos.model_dump()))
    s.commit()
    return {"ok": True}


@router.patch("/pagos/{pago_id}")
def actualizar_pago(pago_id: int, datos: PagoPatch, s: Session = SesionDB):
    _obtener(s, PagoPrevisto, pago_id).pagado = datos.pagado
    s.commit()
    return {"ok": True}


@router.delete("/pagos/{pago_id}")
def borrar_pago(pago_id: int, s: Session = SesionDB):
    s.delete(_obtener(s, PagoPrevisto, pago_id))
    s.commit()
    return {"ok": True}


# --- Inversión privada (private equity) -----------------------------------------

def _inversion(s: Session, inv: InversionPrivada) -> dict:
    llamadas = s.scalars(select(PagoPrevisto).where(PagoPrevisto.inversion_id == inv.id)
                         .order_by(PagoPrevisto.fecha)).all()
    desembolsado = sum((p.importe for p in llamadas if p.pagado), CERO)
    previsto = sum((p.importe for p in llamadas if not p.pagado), CERO)
    proxima = next((p for p in llamadas if not p.pagado), None)
    return {
        "id": inv.id, "nombre": inv.nombre, "gestora": inv.gestora, "compromiso": n(inv.compromiso),
        "fecha_compromiso": f(inv.fecha_compromiso), "nav": n(inv.nav), "nav_fecha": f(inv.nav_fecha),
        "distribuido": n(inv.distribuido), "desembolsado": n(desembolsado),
        "pendiente": n(max(inv.compromiso - desembolsado, CERO)),
        "sin_calendario": n(max(inv.compromiso - desembolsado - previsto, CERO)),
        "pct_desembolsado": n((desembolsado / inv.compromiso * 100).quantize(Decimal("0.01"))) if inv.compromiso else None,
        # TVPI: (valor actual + lo ya devuelto) / lo desembolsado
        "tvpi": n(((inv.nav + inv.distribuido) / desembolsado).quantize(Decimal("0.01"))) if desembolsado else None,
        "resultado": n(inv.nav + inv.distribuido - desembolsado),
        "proxima_llamada": {"fecha": f(proxima.fecha), "importe": n(proxima.importe)} if proxima else None,
        "llamadas": [{"id": p.id, "fecha": f(p.fecha), "importe": n(p.importe), "pagado": p.pagado} for p in llamadas],
        "notas": inv.notas,
    }


@router.get("/inversiones")
def listar_inversiones(s: Session = SesionDB):
    datos = [_inversion(s, i) for i in s.scalars(select(InversionPrivada).order_by(InversionPrivada.id))]
    total = {k: round(sum(d[k] or 0 for d in datos), 2) for k in ("compromiso", "desembolsado", "pendiente", "nav", "distribuido")}
    return {"inversiones": datos, "totales": total}


class LlamadaIn(BaseModel):
    fecha: date
    importe: Decimal
    pagado: bool = False


class InversionIn(BaseModel):
    nombre: str
    gestora: str = ""
    compromiso: Decimal
    fecha_compromiso: date | None = None
    nav: Decimal = Decimal("0")
    nav_fecha: date | None = None
    distribuido: Decimal = Decimal("0")
    notas: str = ""
    llamadas: list[LlamadaIn] = []


def _concepto_llamada(inv: InversionPrivada) -> str:
    return f"Llamada de capital {inv.nombre}"[:160]


@router.post("/inversiones")
def crear_inversion(datos: InversionIn, s: Session = SesionDB):
    inv = InversionPrivada(**datos.model_dump(exclude={"llamadas"}))
    inv.nav_fecha = inv.nav_fecha or date.today()
    s.add(inv)
    s.flush()
    for ll in datos.llamadas:
        s.add(PagoPrevisto(concepto=_concepto_llamada(inv), inversion_id=inv.id, **ll.model_dump()))
    s.commit()
    return _inversion(s, inv)


class InversionPatch(BaseModel):
    nombre: str | None = None
    gestora: str | None = None
    compromiso: Decimal | None = None
    nav: Decimal | None = None
    nav_fecha: date | None = None
    distribuido: Decimal | None = None
    notas: str | None = None


@router.patch("/inversiones/{inversion_id}")
def actualizar_inversion(inversion_id: int, datos: InversionPatch, s: Session = SesionDB):
    inv = _obtener(s, InversionPrivada, inversion_id)
    cambios = datos.model_dump(exclude_none=True)
    if "nav" in cambios and "nav_fecha" not in cambios:
        cambios["nav_fecha"] = date.today()
    for k, v in cambios.items():
        setattr(inv, k, v)
    s.commit()
    return _inversion(s, inv)


@router.post("/inversiones/{inversion_id}/llamadas")
def crear_llamada(inversion_id: int, datos: LlamadaIn, s: Session = SesionDB):
    inv = _obtener(s, InversionPrivada, inversion_id)
    s.add(PagoPrevisto(concepto=_concepto_llamada(inv), inversion_id=inv.id, **datos.model_dump()))
    s.commit()
    return _inversion(s, inv)


@router.delete("/inversiones/{inversion_id}")
def borrar_inversion(inversion_id: int, s: Session = SesionDB):
    inv = _obtener(s, InversionPrivada, inversion_id)
    for p in s.scalars(select(PagoPrevisto).where(PagoPrevisto.inversion_id == inv.id)):
        s.delete(p)
    s.flush()  # primero las llamadas, por la clave foránea
    s.delete(inv)
    s.commit()
    return {"ok": True}


@router.get("/config")
def ver_config():
    return {"ccaa": config.CCAA, "banco": config.BANCO,
            "redirect_url": config.ENABLE_BANKING_REDIRECT_URL}


# --- Hacienda: modelos presentados ------------------------------------------

NOMBRE_MODELO = {"303": "IVA trimestral", "130": "IRPF pago fraccionado", "100": "Renta",
                 "390": "Resumen anual IVA", "347": "Operaciones con terceros", "349": "Operaciones intracomunitarias"}


def _estimado(s: Session, d: Declaracion, cache: dict) -> float | None:
    """Lo que la app calcula para ese modelo y trimestre, para compararlo con lo presentado."""
    if d.modelo not in ("303", "130") or not d.periodo.endswith("T"):
        return None
    if "f" not in cache:
        cache["f"] = s.scalars(select(Factura)).all()
        cache["g"] = s.scalars(select(GastoAutonomo)).all()
    if not any(x.fecha.year == d.ejercicio for x in cache["f"]):
        return None
    t = int(d.periodo[0])
    if d.modelo == "303":
        return n(autonomo.calcular_303(d.ejercicio, t, cache["f"], cache["g"]).resultado)
    previos = _presentados_130(_presentadas(s, d.ejercicio))
    return n(autonomo.calcular_130(d.ejercicio, t, cache["f"], cache["g"], previos).resultado)


def _declaracion(d: Declaracion, estimado: float | None) -> dict:
    return {"id": d.id, "modelo": d.modelo, "nombre": NOMBRE_MODELO.get(d.modelo, f"Modelo {d.modelo}"),
            "ejercicio": d.ejercicio, "periodo": d.periodo, "resultado": d.resultado, "importe": n(d.importe),
            "fecha_presentacion": f(d.fecha_presentacion), "justificante": d.justificante, "csv": d.csv,
            "tiene_pdf": bool(d.nombre_fichero), "estimado": estimado, "notas": d.notas}


@router.get("/declaraciones")
def ver_declaraciones(s: Session = SesionDB):
    decl = s.scalars(select(Declaracion).order_by(Declaracion.ejercicio.desc(), Declaracion.periodo.desc(),
                                                  Declaracion.modelo)).all()
    cache: dict = {}
    lista = [_declaracion(d, _estimado(s, d, cache)) for d in decl]
    por_anio: dict[int, dict] = {}
    for d in decl:
        a = por_anio.setdefault(d.ejercicio, {"ejercicio": d.ejercicio, "pagado": 0.0, "devuelto": 0.0})
        if d.importe > 0:
            a["pagado"] += float(d.importe)
        elif d.resultado == "devolver":
            a["devuelto"] -= float(d.importe)
    return {"declaraciones": lista, "por_anio": sorted(por_anio.values(), key=lambda x: -x["ejercicio"])}


def _guardar_txt(s: Session, contenido: bytes, nombre: str) -> str:
    """Declaración en .txt (formato de presentación). Si ya hay un justificante PDF de ese periodo, manda el PDF."""
    from finanzas.importers import aeat_txt
    t = aeat_txt.leer(contenido)
    existentes = s.scalars(select(Declaracion).where(
        Declaracion.modelo == t.modelo, Declaracion.ejercicio == t.ejercicio, Declaracion.periodo == t.periodo)).all()
    texto = f"Modelo {t.modelo} {t.periodo} {t.ejercicio}"
    if any(d.justificante for d in existentes):
        return texto + " (ya estaba con su justificante PDF)"
    d = existentes[0] if existentes else Declaracion(modelo=t.modelo, ejercicio=t.ejercicio, periodo=t.periodo,
                                                     justificante="")
    d.resultado, d.importe, d.nombre_fichero = t.resultado, t.importe, nombre[:200]
    if t.casillas:
        d.casillas = json.dumps({k: float(v) for k, v in t.casillas.items()})
    d.notas = "Importado del fichero .txt" + ("" if t.exacto else ": revisa el importe")
    s.add(d)
    s.commit()
    return texto + (" (actualizado)" if existentes else "") + ("" if t.exacto else ", revisa el importe")


def _guardar_pdf(s: Session, contenido: bytes, nombre: str) -> str:
    j = aeat.leer_pdf(contenido)
    d = s.scalar(select(Declaracion).where(
        Declaracion.modelo == j.modelo, Declaracion.ejercicio == j.ejercicio,
        Declaracion.periodo == j.periodo, Declaracion.justificante == j.justificante))
    # Si ese periodo venía de un .txt, el justificante lo sustituye
    d = d or s.scalar(select(Declaracion).where(
        Declaracion.modelo == j.modelo, Declaracion.ejercicio == j.ejercicio,
        Declaracion.periodo == j.periodo, Declaracion.justificante == ""))
    nueva = d is None
    d = d or Declaracion(modelo=j.modelo, ejercicio=j.ejercicio, periodo=j.periodo)
    d.justificante, d.resultado, d.importe, d.fecha_presentacion, d.csv = (
        j.justificante, j.resultado, j.importe, j.fecha_presentacion, j.csv)
    d.nombre_fichero, d.pdf = nombre[:200], contenido
    if j.casillas:
        d.casillas = json.dumps(j.casillas)
    if (d.notas or "").startswith("Importado del fichero .txt"):
        d.notas = ""
    s.add(d)
    s.commit()
    return f"Modelo {j.modelo} {j.periodo} {j.ejercicio}" + ("" if nueva else " (actualizado)")


@router.post("/declaraciones/pdf")
async def subir_declaraciones(ficheros: list[UploadFile] = File(...), s: Session = SesionDB):
    """Justificantes PDF de la sede o ficheros .txt de la declaración, varios a la vez."""
    resultados = []
    for fichero in ficheros:
        contenido = await fichero.read()
        nombre = fichero.filename or "declaracion"
        es_txt = nombre.lower().endswith(".txt") or contenido.lstrip()[:2] == b"<T"
        try:
            mensaje = _guardar_txt(s, contenido, nombre) if es_txt else _guardar_pdf(s, contenido, nombre)
            resultados.append({"fichero": nombre, "ok": True, "mensaje": mensaje})
        except aeat.ErrorAEAT as e:
            s.rollback()
            resultados.append({"fichero": nombre, "ok": False, "mensaje": str(e)})
    return {"resultados": resultados}


class DeclaracionIn(BaseModel):
    modelo: str
    ejercicio: int
    periodo: str
    resultado: str = "ingresar"
    importe: Decimal
    fecha_presentacion: date | None = None
    notas: str = ""


@router.post("/declaraciones")
def crear_declaracion(datos: DeclaracionIn, s: Session = SesionDB):
    v = datos.model_dump()
    if v["resultado"] in ("devolver", "compensar"):
        v["importe"] = -abs(v["importe"])
    s.add(Declaracion(**v))
    try:
        s.commit()
    except IntegrityError:
        s.rollback()
        raise HTTPException(409, "Ya tienes esa declaración apuntada")
    return {"ok": True}


@router.delete("/declaraciones/{declaracion_id}")
def borrar_declaracion(declaracion_id: int, s: Session = SesionDB):
    s.delete(_obtener(s, Declaracion, declaracion_id))
    s.commit()
    return {"ok": True}


@router.get("/declaraciones/{declaracion_id}/pdf")
def pdf_declaracion(declaracion_id: int, s: Session = SesionDB):
    d = _obtener(s, Declaracion, declaracion_id)
    if not d.pdf:
        raise HTTPException(404, "Esta declaración no tiene PDF")
    return Response(d.pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{d.modelo}-{d.periodo}-{d.ejercicio}.pdf"'})


# --- Google Drive y asistente --------------------------------------------------

class ImportarDriveIn(BaseModel):
    access_token: str
    desde: str = "2024-01-01"


@router.post("/drive/importar")
def importar_drive(datos: ImportarDriveIn, s: Session = SesionDB):
    from finanzas.integrations import drive
    try:
        return drive.importar(s, datos.access_token, datos.desde)
    except drive.ErrorDrive as e:
        raise HTTPException(400, str(e))


@router.get("/drive/documentos")
def listar_documentos_drive(s: Session = SesionDB):
    import json
    orden = {"pendiente": 0, "error": 1, "importado": 2, "ignorado": 3}
    docs = sorted(s.scalars(select(DocumentoDrive)), key=lambda d: (orden.get(d.estado, 9), d.nombre))
    from finanzas import ia
    return {"ia": ia.disponible(s), "google_client_id": config.GOOGLE_CLIENT_ID or None,
            "documentos": [{"id": d.id, "nombre": d.nombre, "enlace": d.enlace, "tipo": d.tipo, "estado": d.estado,
                            "mensaje": d.mensaje, "datos": json.loads(d.datos or "{}"),
                            "revisado": iso_utc(d.revisado)} for d in docs]}


class GastoDriveIn(BaseModel):
    deducible_pct: Decimal = Decimal("100")
    categoria: str | None = None


@router.post("/drive/documentos/{doc_id}/gasto")
def gasto_desde_drive(doc_id: int, datos: GastoDriveIn, s: Session = SesionDB):
    from finanzas.integrations import drive
    doc = _obtener(s, DocumentoDrive, doc_id)
    if doc.gasto_id:
        raise HTTPException(409, "Ya está apuntado como gasto")
    drive.crear_gasto(s, doc, datos.deducible_pct, datos.categoria)
    return {"ok": True}


@router.post("/drive/documentos/{doc_id}/ignorar")
def ignorar_documento_drive(doc_id: int, s: Session = SesionDB):
    doc = _obtener(s, DocumentoDrive, doc_id)
    doc.estado, doc.mensaje = "ignorado", "Descartado a mano"
    s.commit()
    return {"ok": True}


class MensajeIn(BaseModel):
    role: str
    content: str


class AsistenteIn(BaseModel):
    mensajes: list[MensajeIn]


@router.post("/asistente")
def preguntar_asistente(datos: AsistenteIn, s: Session = SesionDB):
    from finanzas import asistente, ia
    if not datos.mensajes or datos.mensajes[-1].role != "user":
        raise HTTPException(400, "Falta la pregunta")
    try:
        return asistente.responder(s, [m.model_dump() for m in datos.mensajes])
    except ia.ErrorIA as e:
        raise HTTPException(400, str(e))


@router.get("/asistente/estado")
def estado_asistente(s: Session = SesionDB):
    from finanzas import ia
    cfg = ia.configuracion(s)
    return {"disponible": cfg.lista, "proveedor": cfg.proveedor,
            "proveedor_nombre": ia.PROVEEDORES[cfg.proveedor]["nombre"], "modelo": cfg.modelo}


# --- Ajustes del asistente (IA) -------------------------------------------------

def _ajustes_ia(s: Session) -> dict:
    from finanzas import ajustes, ia
    cfg = ia.configuracion(s)
    proveedores = {}
    for p, info in ia.PROVEEDORES.items():
        en_app = ajustes.leer(s, f"{p}_api_key")
        clave = en_app or ia._clave_entorno(p)
        proveedores[p] = {"nombre": info["nombre"], "modelo_defecto": info["modelo"],
                          "modelo": ajustes.leer(s, f"{p}_modelo"), "clave": ajustes.oculto(clave),
                          "origen_clave": "app" if en_app else ("entorno" if clave else None)}
    return {"proveedor": cfg.proveedor, "modelo": cfg.modelo, "disponible": cfg.lista, "proveedores": proveedores}


@router.get("/ajustes/ia")
def ver_ajustes_ia(s: Session = SesionDB):
    return _ajustes_ia(s)


class AjustesIAIn(BaseModel):
    proveedor: str
    clave: str | None = None  # None = no tocar; "" = borrar la guardada en la app
    modelo: str | None = None


@router.put("/ajustes/ia")
def guardar_ajustes_ia(datos: AjustesIAIn, s: Session = SesionDB):
    from finanzas import ajustes, ia
    if datos.proveedor not in ia.PROVEEDORES:
        raise HTTPException(400, "Proveedor desconocido")
    ajustes.guardar(s, "ia_proveedor", datos.proveedor)
    if datos.clave is not None:
        ajustes.guardar(s, f"{datos.proveedor}_api_key", datos.clave.strip(), secreto=True)
    if datos.modelo is not None:
        ajustes.guardar(s, f"{datos.proveedor}_modelo", datos.modelo.strip()[:80])
    return _ajustes_ia(s)


@router.post("/ajustes/ia/probar")
def probar_ajustes_ia(s: Session = SesionDB):
    from finanzas import ia
    cfg = ia.configuracion(s)
    try:
        respuesta = ia.probar(cfg)
    except ia.ErrorIA as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "proveedor": ia.PROVEEDORES[cfg.proveedor]["nombre"], "modelo": cfg.modelo,
            "respuesta": respuesta[:200]}


# --- Inmuebles: editar, borrar, gastos de escritura y vender o seguir alquilando ----------

class ActivoPatch(BaseModel):
    nombre: str | None = None
    uso: str | None = None
    fecha_compra: date | None = None
    precio_compra: Decimal | None = None
    gastos_compra: Decimal | None = None
    valor_catastral: Decimal | None = None
    valor_catastral_construccion: Decimal | None = None
    porcentaje_propiedad: Decimal | None = None
    notas: str | None = None


@router.patch("/inmuebles/{activo_id}")
def actualizar_inmueble(activo_id: int, datos: ActivoPatch, s: Session = SesionDB):
    a = _obtener(s, Activo, activo_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        if valor is not None or campo == "fecha_compra":
            setattr(a, campo, valor)
    s.commit()
    sync.guardar_instantanea(s)
    return {"ok": True}


@router.delete("/inmuebles/{activo_id}")
def borrar_inmueble(activo_id: int, s: Session = SesionDB):
    """Borra el bien con sus hipotecas, contratos, gastos y valoraciones. Sus pagos previstos se quedan, sin bien."""
    a = _obtener(s, Activo, activo_id)
    for modelo in (Deuda, GastoInmueble, Valoracion):
        for x in s.scalars(select(modelo).where(modelo.activo_id == a.id)):
            s.delete(x)
    for c in s.scalars(select(ContratoAlquiler).where(ContratoAlquiler.activo_id == a.id)):
        for cambio in c.cambios_renta:
            s.delete(cambio)
        s.delete(c)
    for p in s.scalars(select(PagoPrevisto).where(PagoPrevisto.activo_id == a.id)):
        p.activo_id = None
    s.flush()
    s.delete(a)
    s.commit()
    sync.guardar_instantanea(s)
    return {"ok": True}


@router.delete("/valoraciones/{valoracion_id}")
def borrar_valoracion(valoracion_id: int, s: Session = SesionDB):
    s.delete(_obtener(s, Valoracion, valoracion_id))
    s.commit()
    return {"ok": True}


@router.delete("/gastos-inmueble/{gasto_id}")
def borrar_gasto_inmueble(gasto_id: int, s: Session = SesionDB):
    s.delete(_obtener(s, GastoInmueble, gasto_id))
    s.commit()
    return {"ok": True}


class ContratoPatch(BaseModel):
    inquilino: str | None = None
    fecha_fin: date | None = None
    renta_mensual: Decimal | None = None
    reduccion_pct: Decimal | None = None


@router.patch("/contratos/{contrato_id}")
def actualizar_contrato(contrato_id: int, datos: ContratoPatch, s: Session = SesionDB):
    c = _obtener(s, ContratoAlquiler, contrato_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        if valor is not None or campo == "fecha_fin":
            setattr(c, campo, valor)
    s.commit()
    return {"ok": True}


@router.delete("/contratos/{contrato_id}")
def borrar_contrato(contrato_id: int, s: Session = SesionDB):
    c = _obtener(s, ContratoAlquiler, contrato_id)
    for cambio in c.cambios_renta:
        s.delete(cambio)
    s.delete(c)
    s.commit()
    return {"ok": True}


AJD_MURCIA_PCT = Decimal("1.5")  # actos jurídicos documentados en la compra de obra nueva (Región de Murcia)
NOTARIA_REGISTRO = Decimal("1200")  # notaría, registro y gestoría, aproximado


class EscrituraIn(BaseModel):
    fecha: date
    precio: Decimal | None = None  # sin IVA; vacío: el precio de compra del bien


@router.post("/inmuebles/{activo_id}/gastos-escritura")
def gastos_escritura(activo_id: int, datos: EscrituraIn, s: Session = SesionDB):
    """Añade como pago previsto los gastos de la escritura de la casa nueva: AJD más notaría y registro."""
    a = _obtener(s, Activo, activo_id)
    precio = datos.precio or a.precio_compra
    if not precio:
        raise HTTPException(400, "Pon el precio de la vivienda (sin IVA)")
    importe = (precio * AJD_MURCIA_PCT / 100 + NOTARIA_REGISTRO).quantize(Decimal("1"))
    s.add(PagoPrevisto(concepto=f"Escritura {a.nombre}: AJD 1,5 % y notaría (estimado)"[:160], fecha=datos.fecha,
                       importe=importe, activo_id=a.id))
    s.commit()
    return {"ok": True, "importe": n(importe)}


@router.get("/inmuebles/{activo_id}/vender")
def vender_o_alquilar(activo_id: int, precio: float | None = None, gastos_venta_pct: float = 3.0,
                      s: Session = SesionDB):
    """Compara vender el piso (lo que te quedaría en mano tras impuestos e hipoteca) con seguir alquilándolo."""
    from finanzas import prevision
    a = _obtener(s, Activo, activo_id)
    hoy = date.today()
    valor, detalle = patrimonio.valor_activo(a, hoy)
    venta = Decimal(str(precio)) if precio else valor
    gastos_venta = (venta * Decimal(str(gastos_venta_pct)) / 100).quantize(Decimal("0.01"))
    contratos = s.scalars(select(ContratoAlquiler).where(ContratoAlquiler.activo_id == a.id)).all()
    amortizado = alquiler.amortizacion_acumulada(a, contratos, hoy)
    adquisicion = (a.precio_compra + a.gastos_compra) * a.porcentaje_propiedad / 100 - amortizado
    ganancia = venta - gastos_venta - adquisicion
    irpf = Decimal(str(round(prevision.escala_ahorro(float(max(ganancia, CERO))), 2)))
    deudas = s.scalars(select(Deuda).where(Deuda.activo_id == a.id)).all()
    hipoteca = sum((saldo_pendiente(d, hoy) for d in deudas), CERO)
    en_mano = venta - gastos_venta - irpf - hipoteca
    gastos = s.scalars(select(GastoInmueble).where(GastoInmueble.activo_id == a.id)).all()
    rent = _rentabilidad(a, contratos, gastos, deudas, valor, hoy)
    prev = prevision.calcular(s)
    renta_actual = next((r for r in prev["anios"] if r["anio"] == hoy.year), None)
    marginal = (renta_actual or {}).get("tipo_marginal", 45.0) / 100
    rend = alquiler.calcular_rendimiento(a, contratos, gastos, hoy.year).rendimiento_reducido if contratos else CERO
    flujo = Decimal(str(rent["flujo_caja_anual"])) if rent else CERO
    flujo_tras_irpf = flujo - rend * Decimal(str(marginal))
    return {
        "precio_venta": n(venta), "valor_detalle": "el precio que has puesto" if precio else detalle,
        "gastos_venta": n(gastos_venta), "amortizacion_acumulada": n(amortizado),
        "valor_adquisicion": n(adquisicion), "ganancia": n(ganancia), "irpf_ganancia": n(irpf),
        "hipoteca_pendiente": n(hipoteca), "en_mano": n(en_mano),
        "alquiler_flujo_anual": n(flujo), "alquiler_irpf_anual": n((rend * Decimal(str(marginal))).quantize(Decimal("0.01"))),
        "alquiler_flujo_tras_irpf": n(flujo_tras_irpf.quantize(Decimal("0.01"))),
        "rentabilidad_sobre_en_mano": round(float(flujo_tras_irpf / en_mano * 100), 2) if en_mano > 0 else None,
        "notas": ["Falta la plusvalía municipal, que depende del valor catastral del suelo y de los años.",
                  "La ganancia tributa en la base del ahorro (19 % a 30 %); si compras tu vivienda habitual "
                  "no hay exención por reinversión porque este piso no es tu vivienda."],
    }


# --- Autónomo: editar una factura ------------------------------------------------

@router.put("/autonomo/facturas/{factura_id}")
def actualizar_factura(factura_id: int, datos: FacturaIn, s: Session = SesionDB):
    x = _obtener(s, Factura, factura_id)
    nombre = datos.cliente.strip()
    cli = s.scalar(select(Cliente).where(Cliente.nombre == nombre))
    if cli is None:
        cli = Cliente(nombre=nombre)
        s.add(cli)
        s.flush()
    for campo, valor in datos.model_dump(exclude={"cliente"}).items():
        setattr(x, campo, valor)
    x.cliente_id = cli.id
    s.commit()
    return {"ok": True}


# --- Hacienda: lo pendiente, la hucha, la cuota de autónomos y el ahorro fiscal -----------

@router.get("/hacienda")
def ver_hacienda(s: Session = SesionDB):
    from finanzas import avisos, hacienda, prevision
    prev = prevision.calcular(s)
    pend = hacienda.pendiente(s, prev)
    hoy = date.today()
    renta = next((r for r in prev["anios"] if r["anio"] == hoy.year), None)
    return {
        "pendiente": pend, "hucha": hacienda.hucha(s, pend, prev), "cuota_autonomos": hacienda.revision_reta(s, prev),
        "renta": {k: renta[k] for k in ("anio", "base", "base_liquidable", "base_ahorro", "imputacion_inmuebles",
                                        "reduccion_pensiones", "cuota", "resultado", "tipo_medio", "tipo_marginal")}
        if renta else None,
        "supuestos": {k: prev["supuestos"].get(k) for k in ("aportacion_pensiones_anio", "aportacion_ppes_anio",
                                                             "fraccionar_renta", "rentas_ahorro_anio",
                                                             "imputacion_inmuebles_anio")},
        "origen": {"rentas_ahorro_anio": prev["origen_rentas_ahorro_anio"],
                   "imputacion_inmuebles_anio": prev["origen_imputacion_inmuebles_anio"],
                   "valor_rentas_ahorro": prev["rentas_ahorro_anio"],
                   "valor_imputacion": prev["imputacion_inmuebles_anio"]},
        "plazos": [{"fecha": f(p["fecha"]), "titulo": p["titulo"], "detalle": p["detalle"]}
                   for p in avisos.plazos(hoy, hoy + timedelta(days=365))],
        "cuentas": [{"id": c.id, "nombre": c.nombre} for c in s.scalars(
            select(Cuenta).where(Cuenta.activa, Cuenta.tipo.in_(["corriente", "ahorro"])).order_by(Cuenta.nombre))],
    }


class HuchaIn(BaseModel):
    cuenta_id: int | None = None


@router.put("/hacienda/hucha")
def elegir_hucha(datos: HuchaIn, s: Session = SesionDB):
    from finanzas import ajustes, hacienda
    if datos.cuenta_id is not None:
        _obtener(s, Cuenta, datos.cuenta_id)
    ajustes.guardar(s, hacienda.CLAVE_HUCHA, str(datos.cuenta_id or ""))
    return {"ok": True}


class SupuestosRentaIn(BaseModel):
    aportacion_pensiones_anio: float = 0
    aportacion_ppes_anio: float = 0
    fraccionar_renta: bool = False
    rentas_ahorro_anio: float | None = None
    imputacion_inmuebles_anio: float | None = None


@router.put("/hacienda/supuestos")
def guardar_supuestos_renta(datos: SupuestosRentaIn, s: Session = SesionDB):
    """Lo de la renta que la app no ve en tus cuentas; se guarda con el resto de supuestos de la previsión."""
    from finanzas import prevision
    prevision.guardar(s, {**prevision.leer(s), **datos.model_dump()})
    return {"ok": True}


@router.get("/hacienda/ahorro")
def simular_ahorro(pensiones: float = 0, ppes: float = 0, gastos: float = 0, s: Session = SesionDB):
    """Cuánto baja la renta de este año aportando a pensiones o apuntando más gastos de la actividad."""
    from finanzas import prevision
    prev = prevision.calcular(s)
    hoy = date.today()
    r = next((a for a in prev["anios_todos"] if a["anio"] == hoy.year), None)
    if r is None:
        raise HTTPException(400, "Falta la previsión de este año")
    cfg = prevision.resolver_clientes(s, prevision.leer(s))
    e = r["entradas"]
    base = {"pensiones": 0, "ppes": 0, "gastos_actividad": 0}
    con = {"pensiones": max(pensiones, 0), "ppes": max(ppes, 0), "gastos_actividad": max(gastos, 0)}
    args = (cfg, e["nomina"], e["facturado"], e["retenciones"], e["pagos_130"], e["alquiler"], e["imputacion_app"])
    sin, simulada = prevision._renta(*args, extra=base), prevision._renta(*args, extra=con)
    return {"anio": hoy.year, "cuota_sin": sin["cuota"], "cuota_con": simulada["cuota"],
            "ahorro": round(sin["cuota"] - simulada["cuota"], 2), "tipo_marginal": sin["tipo_marginal"],
            "reduccion_aplicada": simulada["reduccion_pensiones"],
            "limites": {"pensiones": prevision.LIMITE_PENSIONES, "ppes": prevision.LIMITE_PPES,
                        "pct_rendimientos": prevision.LIMITE_PENSIONES_PCT * 100}}


# --- Copia de seguridad y calendario ---------------------------------------------

@router.get("/exportar")
def exportar(pdfs: bool = False, s: Session = SesionDB):
    """Todos tus datos en JSON. Las claves de API guardadas no salen; los PDF de Hacienda, solo si los pides."""
    import base64
    from finanzas import ajustes as aj, avisos
    from finanzas.models import Ajuste
    tablas = {}
    for tabla in db.Base.metadata.sorted_tables:
        filas = []
        for fila in s.execute(tabla.select()).mappings():
            d = {}
            for k, v in fila.items():
                if isinstance(v, bytes):
                    v = base64.b64encode(v).decode() if pdfs else None
                elif isinstance(v, Decimal):
                    v = float(v)
                elif hasattr(v, "isoformat"):
                    v = v.isoformat()
                d[k] = v
            if tabla.name == Ajuste.__tablename__ and str(d.get("valor", "")).startswith(aj.PREFIJO):
                continue  # secretos cifrados
            filas.append(d)
        tablas[tabla.name] = filas
    aj.guardar(s, avisos.CLAVE_ULTIMA_COPIA, date.today().isoformat())
    nombre = f"finanzas-{date.today().isoformat()}.json"
    return Response(json.dumps({"version": 1, "fecha": date.today().isoformat(), "tablas": tablas}, ensure_ascii=False),
                    media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/exportar/movimientos.xlsx")
def exportar_movimientos(s: Session = SesionDB):
    import io
    from openpyxl import Workbook
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Movimientos"
    hoja.append(["Fecha", "Cuenta", "Concepto", "Importe", "Tu parte", "Categoría", "Saldo"])
    filas = s.execute(select(Movimiento.fecha, Cuenta.nombre, Movimiento.concepto, Movimiento.importe,
                             Movimiento.importe * PARTE, Categoria.nombre, Movimiento.saldo)
                      .join(Cuenta, Movimiento.cuenta_id == Cuenta.id)
                      .join(Categoria, Movimiento.categoria_id == Categoria.id, isouter=True)
                      .order_by(Movimiento.fecha.desc(), Movimiento.id.desc()))
    for fecha, cuenta, concepto, importe, tuyo, cat, saldo in filas:
        hoja.append([fecha, cuenta, concepto, float(importe), round(float(tuyo), 2), cat or "",
                     float(saldo) if saldo is not None else None])
    for col, ancho in zip("ABCDEFG", (12, 22, 60, 12, 12, 22, 12)):
        hoja.column_dimensions[col].width = ancho
    salida = io.BytesIO()
    libro.save(salida)
    return Response(salida.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="movimientos-{date.today().isoformat()}.xlsx"'})


@router.post("/exportar/hecha")
def copia_hecha(s: Session = SesionDB):
    """El frontal avisa de que ha guardado la copia en tu Google Drive."""
    from finanzas import ajustes as aj, avisos
    aj.guardar(s, avisos.CLAVE_ULTIMA_COPIA, date.today().isoformat())
    return {"ok": True}


@router.get("/calendario/enlace")
def enlace_calendario():
    """Dirección secreta para suscribirte desde Google Calendar a los plazos de Hacienda."""
    from finanzas import calendario
    return {"ruta": f"/calendario/{calendario.token()}.ics"}
