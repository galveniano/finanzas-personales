"""API JSON que consume el frontal (carpeta frontend/)."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from finanzas import auth, config, db, patrimonio, sync
from finanzas.fiscal import alquiler, autonomo, nomina as calc_nomina
from finanzas.hipoteca import cuota_mensual, intereses_anio, saldo_pendiente
from finanzas.importers import aeat, sabadell
from finanzas.integrations import enablebanking
from finanzas.models import (
    Activo, CambioRenta, Categoria, Cliente, ContratoAlquiler, Cuenta, Declaracion, Deuda, Factura, GastoAutonomo,
    GastoInmueble, Instantanea, Movimiento, Nomina, Objetivo, PagoPrevisto, Valoracion,
)

router = APIRouter(prefix="/api", dependencies=[Depends(auth.requiere_sesion)])
SesionDB = Depends(db.get_session)
CERO = Decimal("0")


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
    desde = (date.today().replace(day=1) - timedelta(days=31 * (meses - 1))).replace(day=1)
    filas = s.execute(
        select(Movimiento.fecha, Movimiento.importe, Categoria.nombre, Categoria.tipo)
        .join(Categoria, Movimiento.categoria_id == Categoria.id, isouter=True)
        .where(Movimiento.fecha >= desde)
    ).all()
    por_mes: dict[str, dict] = defaultdict(lambda: {"ingresos": CERO, "gastos": CERO})
    for fecha, importe, _cat, tipo in filas:
        if tipo == "transferencia":
            continue
        clave = fecha.strftime("%Y-%m")
        if importe >= 0:
            por_mes[clave]["ingresos"] += importe
        else:
            por_mes[clave]["gastos"] += -importe
    return [{"mes": k, "ingresos": n(v["ingresos"]), "gastos": n(v["gastos"])} for k, v in sorted(por_mes.items())]


def _gasto_por_categoria(s: Session, dias: int = 30) -> list[dict]:
    desde = date.today() - timedelta(days=dias)
    nombre = func.coalesce(Categoria.nombre, "Sin categoría")
    filas = s.execute(
        select(nombre, func.sum(Movimiento.importe))
        .join(Categoria, Movimiento.categoria_id == Categoria.id, isouter=True)
        .where(Movimiento.fecha >= desde, Movimiento.importe < 0,
               (Categoria.tipo.is_(None)) | (Categoria.tipo != "transferencia"))
        .group_by(nombre)
    ).all()
    return sorted(({"categoria": c, "importe": -float(t)} for c, t in filas), key=lambda x: -x["importe"])


@router.get("/resumen")
def resumen(s: Session = SesionDB):
    hoy = date.today()
    p = patrimonio.calcular(s, hoy)
    facturas, gastos = s.scalars(select(Factura)).all(), s.scalars(select(GastoAutonomo)).all()
    t = autonomo.trimestre_de(hoy)
    m303 = autonomo.calcular_303(hoy.year, t, facturas, gastos)
    m130 = autonomo.calcular_130(hoy.year, t, facturas, gastos)
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
                       "inversiones": n(i.inversiones), "inmuebles": n(i.inmuebles), "deudas": n(i.deudas)}
                      for i in historico],
        "flujo_mensual": _gasto_por_mes(s),
        "gasto_categorias": _gasto_por_categoria(s),
        "proximos_pagos": [{"id": pp.id, "concepto": pp.concepto, "fecha": f(pp.fecha), "importe": n(pp.importe)}
                           for pp in proximos],
        "fiscal": {
            "trimestre": t, "anio": hoy.year,
            "iva": {"resultado": n(m303.resultado), "repercutido": n(m303.iva_repercutido),
                    "soportado": n(m303.iva_soportado_deducible), "plazo": m303.plazo},
            "irpf": {"resultado": n(m130.resultado), "exento": m130.exento, "notas": m130.notas, "plazo": m130.plazo},
        },
        "sync": sync.estado(s),
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
            "ultima_sincronizacion": c.ultima_sincronizacion.isoformat(timespec="minutes")
            if c.ultima_sincronizacion else None}


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
                       limite: int = 300, s: Session = SesionDB):
    consulta = select(Movimiento).order_by(Movimiento.fecha.desc(), Movimiento.id.desc()).limit(limite)
    if cuenta_id:
        consulta = consulta.where(Movimiento.cuenta_id == cuenta_id)
    if categoria_id == 0:
        consulta = consulta.where(Movimiento.categoria_id.is_(None))
    elif categoria_id:
        consulta = consulta.where(Movimiento.categoria_id == categoria_id)
    if q:
        consulta = consulta.where(Movimiento.concepto.ilike(f"%{q}%"))
    return [{"id": m.id, "cuenta_id": m.cuenta_id, "cuenta": m.cuenta.nombre, "fecha": f(m.fecha),
             "concepto": m.concepto, "importe": n(m.importe), "saldo": n(m.saldo),
             "categoria_id": m.categoria_id} for m in s.scalars(consulta)]


class MovimientoPatch(BaseModel):
    categoria_id: int | None = None


@router.patch("/movimientos/{mov_id}")
def actualizar_movimiento(mov_id: int, datos: MovimientoPatch, s: Session = SesionDB):
    m = _obtener(s, Movimiento, mov_id)
    m.categoria_id = datos.categoria_id
    s.commit()
    return {"ok": True}


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


@router.post("/sync/sabadell/conectar")
def conectar_sabadell():
    try:
        return {"url": enablebanking.iniciar_autorizacion()}
    except enablebanking.EnableBankingError as e:
        raise HTTPException(400, str(e))


class CodigoIn(BaseModel):
    codigo: str


@router.post("/sync/sabadell/completar")
def completar_sabadell(datos: CodigoIn, s: Session = SesionDB):
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


@router.get("/autonomo")
def ver_autonomo(anio: int | None = None, s: Session = SesionDB):
    anio = anio or date.today().year
    facturas = s.scalars(select(Factura).order_by(Factura.fecha.desc())).all()
    gastos = s.scalars(select(GastoAutonomo).order_by(GastoAutonomo.fecha.desc())).all()
    trimestres = []
    for t in range(1, 5):
        m303 = autonomo.calcular_303(anio, t, facturas, gastos)
        m130 = autonomo.calcular_130(anio, t, facturas, gastos)
        trimestres.append({
            "trimestre": t, "plazo": m303.plazo,
            "base": n(m303.base_repercutida), "iva_repercutido": n(m303.iva_repercutido),
            "iva_soportado": n(m303.iva_soportado_deducible), "iva_resultado": n(m303.resultado),
            "rendimiento_acumulado": n(m130.rendimiento_neto), "retenciones_acumuladas": n(m130.retenciones_acumuladas),
            "irpf_resultado": n(m130.resultado), "exento_130": m130.exento, "notas": m130.notas,
        })
    del_anio = [x for x in facturas if x.fecha.year == anio]
    return {
        "anio": anio, "trimestres": trimestres,
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


@router.get("/nominas")
def listar_nominas(anio: int | None = None, s: Session = SesionDB):
    anio = anio or date.today().year
    nominas = s.scalars(select(Nomina).order_by(Nomina.fecha.desc())).all()
    del_anio = [x for x in nominas if x.fecha.year == anio]
    totales = {k: n(sum((getattr(x, k) for x in del_anio), CERO))
               for k in ("bruto", "retencion_irpf", "seguridad_social", "neto")}
    hace_un_anio = date.today() - timedelta(days=365)
    ultimos = [x for x in nominas if x.fecha > hace_un_anio]
    return {"anio": anio, "totales": totales,
            "bruto_12_meses": n(sum((x.bruto for x in ultimos), CERO)) if ultimos else None,
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
    reduccion_pct: Decimal = Decimal("60")


class RentaIn(BaseModel):
    desde: date
    renta_mensual: Decimal


class GastoInmuebleIn(BaseModel):
    fecha: date
    tipo: str
    importe: Decimal
    concepto: str = ""


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
            "id": a.id, "nombre": a.nombre, "tipo": a.tipo, "uso": a.uso, "fecha_compra": f(a.fecha_compra),
            "precio_compra": n(a.precio_compra), "gastos_compra": n(a.gastos_compra),
            "valor_catastral": n(a.valor_catastral), "valor_catastral_construccion": n(a.valor_catastral_construccion),
            "porcentaje_propiedad": n(a.porcentaje_propiedad),
            "valor": n(valor), "valor_detalle": detalle, "deuda": n(deuda_total), "equity": n(valor - deuda_total),
            "valoraciones": [{"fecha": f(v.fecha), "valor": n(v.valor)} for v in a.valoraciones],
            "hipotecas": [{"id": d.id, "nombre": d.nombre, "entidad": d.entidad, "capital_inicial": n(d.capital_inicial),
                           "tipo_interes_anual": n(d.tipo_interes_anual), "plazo_meses": d.plazo_meses,
                           "fecha_inicio": f(d.fecha_inicio),
                           "cuota": n(cuota_mensual(d.capital_inicial, d.tipo_interes_anual, d.plazo_meses)),
                           "pendiente": n(saldo_pendiente(d, hoy)), "intereses_anio": n(intereses_anio(d, anio))}
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


@router.post("/inmuebles/{activo_id}/contratos")
def crear_contrato(activo_id: int, datos: ContratoIn, s: Session = SesionDB):
    _obtener(s, Activo, activo_id)
    s.add(ContratoAlquiler(activo_id=activo_id, **datos.model_dump()))
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


# --- Planificación ----------------------------------------------------------

class ObjetivoIn(BaseModel):
    nombre: str
    tipo: str = "otro"
    fecha_objetivo: date | None = None
    importe_objetivo: Decimal = CERO
    ahorrado: Decimal = CERO


class ObjetivoPatch(BaseModel):
    ahorrado: Decimal


class PagoIn(BaseModel):
    concepto: str
    fecha: date
    importe: Decimal
    objetivo_id: int | None = None
    activo_id: int | None = None
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
    nombres_obj = {o.id: o.nombre for o in objetivos}
    pendiente_12m = sum((p.importe for p in pagos if not p.pagado and p.fecha <= hoy + timedelta(days=365)), CERO)
    liquidez = sum((c.saldo for c in s.scalars(select(Cuenta).where(Cuenta.activa, Cuenta.tipo.in_(
        ["corriente", "ahorro"])))), CERO)
    return {
        "liquidez": n(liquidez), "pendiente_12_meses": n(pendiente_12m),
        "objetivos": [{
            "id": o.id, "nombre": o.nombre, "tipo": o.tipo, "fecha_objetivo": f(o.fecha_objetivo),
            "importe_objetivo": n(o.importe_objetivo), "ahorrado": n(o.ahorrado),
            "ahorro_mensual": n(max(CERO, (o.importe_objetivo - o.ahorrado) / _meses_hasta(o.fecha_objetivo)).quantize(
                Decimal("0.01"))) if o.fecha_objetivo and o.fecha_objetivo > hoy else None,
        } for o in objetivos],
        "pagos": [{"id": p.id, "concepto": p.concepto, "fecha": f(p.fecha), "importe": n(p.importe),
                   "pagado": p.pagado, "objetivo": nombres_obj.get(p.objetivo_id), "inmueble": activos.get(p.activo_id)}
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
    _obtener(s, Objetivo, objetivo_id).ahorrado = datos.ahorrado
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
    calc = autonomo.calcular_303 if d.modelo == "303" else autonomo.calcular_130
    return n(calc(d.ejercicio, t, cache["f"], cache["g"]).resultado)


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


@router.post("/declaraciones/pdf")
async def subir_declaraciones(ficheros: list[UploadFile] = File(...), s: Session = SesionDB):
    resultados = []
    for fichero in ficheros:
        contenido = await fichero.read()
        try:
            j = aeat.leer_pdf(contenido)
        except aeat.ErrorAEAT as e:
            resultados.append({"fichero": fichero.filename, "ok": False, "mensaje": str(e)})
            continue
        d = s.scalar(select(Declaracion).where(
            Declaracion.modelo == j.modelo, Declaracion.ejercicio == j.ejercicio,
            Declaracion.periodo == j.periodo, Declaracion.justificante == j.justificante))
        nueva = d is None
        d = d or Declaracion(modelo=j.modelo, ejercicio=j.ejercicio, periodo=j.periodo, justificante=j.justificante)
        d.resultado, d.importe, d.fecha_presentacion, d.csv = j.resultado, j.importe, j.fecha_presentacion, j.csv
        d.nombre_fichero, d.pdf = (fichero.filename or "justificante.pdf")[:200], contenido
        s.add(d)
        s.commit()
        resultados.append({"fichero": fichero.filename, "ok": True,
                           "mensaje": f"Modelo {j.modelo} {j.periodo} {j.ejercicio}" + ("" if nueva else " (actualizado)")})
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
