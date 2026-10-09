"""Bienes: préstamos y otras deudas, cuadro de amortización y simulador de amortización anticipada, escriturar la
obra nueva, cobros del alquiler cruzados con el banco, y los avisos de hipotecas y contratos."""
import json
import statistics
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas import auth, db, prevision, sync
from finanzas.api import _obtener, _pct_texto, f, n
from finanzas.avisos import _eur
from finanzas.fechas import MESES, sumar_meses
from finanzas.fiscal import alquiler
from finanzas.hipoteca import CENT, cuadro_desde, cuadro_vigente, cuota_mensual, intereses_anio, saldo_pendiente
from finanzas.models import Activo, CambioRenta, ContratoAlquiler, Cuenta, Deuda, GastoInmueble, PagoPrevisto, Valoracion
from finanzas.prevision import MovTuyo, movimientos_tuyos

router = APIRouter(prefix="/api", dependencies=[Depends(auth.requiere_sesion)])
SesionDB = Depends(db.get_session)
CERO = Decimal("0")
TIPOS_DEUDA = ("hipoteca", "prestamo", "otro")
CATEGORIA_ALQUILER = "Alquiler cobrado"
CATEGORIA_CUOTA = "Cuota hipoteca"
DIA_AVISO_ALQUILER = 10  # pasado este día, si no ha llegado el alquiler, se avisa
TOLERANCIA_CUOTA = Decimal("5")  # diferencia entre lo que cobra el banco y la cuota calculada que ya merece aviso


# --- Deudas: lo que devuelve cada una ----------------------------------------------

def deuda_dict(d: Deuda, hoy: date, anio: int) -> dict:
    """La deuda como la ve el frontal: cuota y pendiente de hoy, intereses del año y cuándo acaba."""
    vigente = cuadro_vigente(d)
    pendientes = [c for c in vigente if c.fecha > hoy]
    cuota = pendientes[0].cuota if pendientes else cuota_mensual(d.capital_inicial, d.tipo_interes_anual, d.plazo_meses)
    return {
        "id": d.id, "nombre": d.nombre, "entidad": d.entidad, "tipo": d.tipo, "activo_id": d.activo_id,
        "capital_inicial": n(d.capital_inicial), "tipo_interes_anual": n(d.tipo_interes_anual),
        "plazo_meses": d.plazo_meses, "fecha_inicio": f(d.fecha_inicio),
        "saldo_pendiente_manual": n(d.saldo_pendiente_manual), "saldo_fecha": f(d.saldo_fecha),
        "cuota": n(cuota), "pendiente": n(saldo_pendiente(d, hoy)), "intereses_anio": n(intereses_anio(d, anio, vigente)),
        "futura": bool(d.fecha_inicio and d.fecha_inicio > hoy),
        "fin": f(vigente[-1].fecha) if vigente else None, "cuotas_restantes": len(pendientes),
        "intereses_restantes": n(sum((c.intereses for c in pendientes), CERO)),
    }


@router.get("/deudas")
def listar_deudas(s: Session = SesionDB):
    """Todas las deudas (hipotecas, préstamos y otras) con el bien al que van ligadas, si lo hay."""
    hoy = date.today()
    nombres = {a.id: a.nombre for a in s.scalars(select(Activo))}
    return [{**deuda_dict(d, hoy, hoy.year), "activo": nombres.get(d.activo_id)}
            for d in s.scalars(select(Deuda).order_by(Deuda.tipo, Deuda.nombre))]


class PrestamoIn(BaseModel):
    nombre: str
    entidad: str = ""
    tipo: str = "prestamo"  # prestamo | otro (las hipotecas se crean desde su inmueble)
    capital_inicial: Decimal
    tipo_interes_anual: Decimal = CERO
    fecha_inicio: date
    plazo_meses: int
    saldo_pendiente_manual: Decimal | None = None
    saldo_fecha: date | None = None  # a qué día es ese pendiente (vacío: hoy)
    activo_id: int | None = None  # para ligarlo a un coche u otro bien


def _comprobar_deuda(s: Session, plazo_meses: int | None, capital: Decimal | None, activo_id: int | None) -> None:
    if plazo_meses is not None and plazo_meses <= 0:
        raise HTTPException(400, "El plazo tiene que ser de al menos un mes")
    if capital is not None and capital <= 0:
        raise HTTPException(400, "El capital tiene que ser mayor que cero")
    if activo_id is not None:
        _obtener(s, Activo, activo_id)


@router.post("/deudas")
def crear_prestamo(datos: PrestamoIn, s: Session = SesionDB):
    if datos.tipo not in ("prestamo", "otro"):
        raise HTTPException(400, "El tipo tiene que ser préstamo u otra deuda")
    _comprobar_deuda(s, datos.plazo_meses, datos.capital_inicial, datos.activo_id)
    valores = datos.model_dump()
    valores["saldo_fecha"] = (valores["saldo_fecha"] or date.today()) if valores["saldo_pendiente_manual"] is not None else None
    d = Deuda(**valores)
    s.add(d)
    s.commit()
    sync.guardar_instantanea(s)
    return {"id": d.id}


class DeudaPatch(BaseModel):
    nombre: str | None = None
    entidad: str | None = None
    capital_inicial: Decimal | None = None
    tipo_interes_anual: Decimal | None = None
    fecha_inicio: date | None = None
    plazo_meses: int | None = None
    # Estos tres admiten null para quitarlos (el resto, null = no tocar)
    saldo_pendiente_manual: Decimal | None = None
    saldo_fecha: date | None = None
    activo_id: int | None = None


ANULABLES = {"saldo_pendiente_manual", "saldo_fecha", "activo_id"}


@router.patch("/deudas/{deuda_id}")
def actualizar_deuda(deuda_id: int, datos: DeudaPatch, s: Session = SesionDB):
    d = _obtener(s, Deuda, deuda_id)
    cambios = datos.model_dump(exclude_unset=True)
    _comprobar_deuda(s, cambios.get("plazo_meses"), cambios.get("capital_inicial"), cambios.get("activo_id"))
    for campo, valor in cambios.items():
        if valor is not None or campo in ANULABLES:
            setattr(d, campo, valor)
    if d.saldo_pendiente_manual is None:
        d.saldo_fecha = None
    elif ("saldo_pendiente_manual" in cambios and not cambios.get("saldo_fecha")) or d.saldo_fecha is None:
        d.saldo_fecha = date.today()  # un pendiente nuevo sin fecha es el de hoy
    s.commit()
    sync.guardar_instantanea(s)
    return {"ok": True}


# --- Cuadro de amortización y amortización anticipada -------------------------------

def _agrupar_por_anio(cuotas) -> list[dict]:
    anios: dict[int, dict] = {}
    for c in cuotas:
        a = anios.setdefault(c.fecha.year, {"anio": c.fecha.year, "cuotas": 0, "intereses": CERO, "amortizado": CERO})
        a["cuotas"] += 1
        a["intereses"] += c.intereses
        a["amortizado"] += c.amortizado
        a["pendiente_fin"] = c.pendiente
    return [{**a, "intereses": n(a["intereses"]), "amortizado": n(a["amortizado"]), "pendiente_fin": n(a["pendiente_fin"])}
            for a in anios.values()]


def _pendientes(d: Deuda, hoy: date):
    if d.fecha_inicio and d.fecha_inicio > hoy:
        raise HTTPException(400, f"{d.nombre} aún no ha empezado: empieza el {d.fecha_inicio:%d/%m/%Y}")
    pendientes = [c for c in cuadro_vigente(d) if c.fecha > hoy]
    if not pendientes:
        raise HTTPException(400, f"{d.nombre} no tiene cuotas por pagar: revisa la fecha de firma y el plazo")
    return pendientes


@router.get("/deudas/{deuda_id}/cuadro")
def cuadro_deuda(deuda_id: int, s: Session = SesionDB):
    """Las cuotas que quedan desde hoy, agrupadas por año, según el cuadro vigente."""
    d = _obtener(s, Deuda, deuda_id)
    hoy = date.today()
    pendientes = _pendientes(d, hoy)
    return {"anios": _agrupar_por_anio(pendientes),
            "resumen": {"cuotas_restantes": len(pendientes), "cuota": n(pendientes[0].cuota),
                        "pendiente": n(saldo_pendiente(d, hoy)),
                        "intereses_restantes": n(sum((c.intereses for c in pendientes), CERO)),
                        "fin": f(pendientes[-1].fecha), "desde_saldo_real": d.saldo_pendiente_manual is not None}}


def _cuenta_indexa(s: Session) -> tuple[str, float] | None:
    """Nombre y rentabilidad esperada (%) de la primera cuenta de Indexa que la tenga en su detalle."""
    for c in s.scalars(select(Cuenta).where(Cuenta.origen == "indexa", Cuenta.activa).order_by(Cuenta.id)):
        try:
            esperada = json.loads(c.detalle or "{}").get("rentabilidad_esperada")
        except ValueError:
            esperada = None
        if esperada is not None:
            return c.nombre, float(esperada)
    return None


def _tipo_marginal(s: Session, anio: int) -> float | None:
    """Tipo marginal de la renta del año según la previsión, si está configurada."""
    if not prevision.tiene_supuestos(prevision.leer(s)):
        return None
    r = next((a for a in prevision.calcular(s)["anios"] if a["anio"] == anio), None)
    return r.get("tipo_marginal") if r else None


def _fiscal(s: Session, d: Deuda, ahorro: Decimal, hoy: date) -> dict:
    """Si el piso está alquilado los intereses son gasto deducible: ahorrarlos sube lo que tributa el alquiler."""
    a = d.activo
    if not (a and a.tipo == "inmueble" and a.uso == "alquiler"):
        return {"deducible": False, "tipo_marginal": None, "tipo_efectivo": None, "ahorro_neto": n(ahorro),
                "nota": "Al no ser un piso alquilado, los intereses no se deducen en la renta: el ahorro es íntegro "
                        "(por una vivienda habitual comprada después de 2013 ya no hay deducción)."}
    marginal = _tipo_marginal(s, hoy.year)
    vigentes = [c for c in s.scalars(select(ContratoAlquiler).where(ContratoAlquiler.activo_id == a.id)) if c.vigente(hoy)]
    reduccion = float(vigentes[0].reduccion_pct) if vigentes else 0.0
    if marginal is None:
        return {"deducible": True, "tipo_marginal": None, "tipo_efectivo": None, "ahorro_neto": n(ahorro),
                "nota": "Los intereses del piso alquilado se deducen en la renta, así que el ahorro real es menor. "
                        "Pon tu sueldo y tarifas en Ingresos para estimarlo con tu tipo marginal."}
    efectivo = round(marginal * (1 - reduccion / 100), 2)
    neto = (ahorro * Decimal(str(1 - efectivo / 100))).quantize(CENT)
    return {"deducible": True, "tipo_marginal": marginal, "tipo_efectivo": efectivo, "ahorro_neto": n(neto),
            "nota": f"Los intereses del piso alquilado se deducen en la renta: con tu tipo marginal del {_pct_texto(marginal)} % "
                    f"y la reducción del {_pct_texto(reduccion)} % del alquiler, cada euro de intereses te costaba de verdad "
                    f"{_pct_texto(100 - efectivo)} céntimos. Ahorro real estimado: {_eur(neto)}."}


@router.get("/deudas/{deuda_id}/simular")
def simular_amortizacion(deuda_id: int, importe: float, modo: str = "plazo", s: Session = SesionDB):
    """Qué pasa si amortizas `importe` hoy: reduciendo plazo (misma cuota) o reduciendo cuota (mismo fin)."""
    if modo not in ("plazo", "cuota"):
        raise HTTPException(400, "El modo tiene que ser plazo o cuota")
    d = _obtener(s, Deuda, deuda_id)
    hoy = date.today()
    pendientes = _pendientes(d, hoy)
    saldo = saldo_pendiente(d, hoy)
    imp = Decimal(str(importe)).quantize(CENT)
    if imp <= 0 or imp > saldo:
        raise HTTPException(400, f"Pon un importe entre 1 y {_eur(saldo)} (lo que queda por pagar)")
    cuota_actual = pendientes[0].cuota
    simulado = cuadro_desde(d, saldo - imp, hoy, cuota=cuota_actual if modo == "plazo" else None)
    intereses_sin = sum((c.intereses for c in pendientes), CERO)
    intereses_con = sum((c.intereses for c in simulado), CERO)
    ahorro = intereses_sin - intereses_con
    fiscal = _fiscal(s, d, ahorro, hoy)
    comparativa = None
    if indexa := _cuenta_indexa(s):
        nombre, esperada = indexa
        anios = len(pendientes) / 12
        rendiria = round(float(imp) * ((1 + esperada / 100) ** anios - 1), 2)
        rendiria_neto = round(rendiria - prevision.escala_ahorro(rendiria), 2)
        comparativa = {"cuenta": nombre, "rentabilidad_esperada": esperada, "meses": len(pendientes),
                       "rendiria": rendiria, "rendiria_neto": rendiria_neto,
                       "mejor": "invertir" if rendiria_neto > float(fiscal["ahorro_neto"]) else "amortizar"}
    return {
        "importe": n(imp), "modo": modo, "pendiente_hoy": n(saldo), "cuota_actual": n(cuota_actual),
        "cuotas_restantes": len(pendientes), "intereses_restantes": n(intereses_sin), "intereses_con": n(intereses_con),
        "ahorro_intereses": n(ahorro), "meses_menos": len(pendientes) - len(simulado),
        "nueva_cuota": n(simulado[0].cuota) if simulado else 0.0,
        "fin_actual": f(pendientes[-1].fecha), "nuevo_fin": f(simulado[-1].fecha) if simulado else f(hoy),
        "comparativa": comparativa, "fiscal": fiscal,
        "notas": ["Estimación con el tipo de interés actual durante todo el plazo y sin la comisión por amortización "
                  "anticipada, si tu hipoteca la tiene.",
                  "Lo que rendiría en Indexa es a la rentabilidad esperada de tu cartera, descontando el IRPF del ahorro "
                  "al venderlo; no es una rentabilidad garantizada."] if comparativa else
                 ["Estimación con el tipo de interés actual durante todo el plazo y sin la comisión por amortización "
                  "anticipada, si tu hipoteca la tiene."],
    }


# --- Escriturar la obra nueva -------------------------------------------------------

class EscriturarIn(BaseModel):
    fecha: date
    precio_total: Decimal | None = None  # vacío: la suma de lo pagado a la promotora


@router.post("/inmuebles/{activo_id}/escriturar")
def escriturar(activo_id: int, datos: EscriturarIn, s: Session = SesionDB):
    """La obra nueva pasa a ser tu vivienda: se marcan pagados los plazos hasta la fecha, el precio es lo pagado
    (o el que digas), los gastos de escritura son los pagos «Escritura…» y la hipoteca prevista empieza ese día."""
    a = _obtener(s, Activo, activo_id)
    if a.tipo != "inmueble_en_construccion":
        raise HTTPException(400, "Solo se escritura una obra nueva en construcción")
    pagos = s.scalars(select(PagoPrevisto).where(PagoPrevisto.activo_id == a.id)).all()
    marcados = 0
    for p in pagos:
        if not p.pagado and p.fecha <= datos.fecha:
            p.pagado, marcados = True, marcados + 1
    pagados = [p for p in pagos if p.pagado]
    escritura = sum((p.importe for p in pagados if p.concepto.startswith("Escritura")), CERO)
    precio = datos.precio_total or sum((p.importe for p in pagados if not p.concepto.startswith("Escritura")), CERO)
    a.tipo, a.uso, a.fecha_compra, a.precio_compra, a.gastos_compra = "inmueble", "vivienda_habitual", datos.fecha, precio, escritura
    hipotecas = 0
    for d in s.scalars(select(Deuda).where(Deuda.activo_id == a.id)):
        if d.fecha_inicio is None or d.fecha_inicio > datos.fecha:
            d.fecha_inicio, hipotecas = datos.fecha, hipotecas + 1
    s.commit()
    sync.guardar_instantanea(s)
    return {"ok": True, "precio_compra": n(precio), "gastos_compra": n(escritura), "pagos_marcados": marcados,
            "hipotecas_actualizadas": hipotecas}


# --- Contratos, gastos y valoraciones -----------------------------------------------

@router.delete("/rentas/{cambio_id}")
def borrar_cambio_renta(cambio_id: int, s: Session = SesionDB):
    s.delete(_obtener(s, CambioRenta, cambio_id))
    s.commit()
    return {"ok": True}


class GastoInmueblePatch(BaseModel):
    fecha: date | None = None
    tipo: str | None = None
    importe: Decimal | None = None
    concepto: str | None = None


@router.patch("/gastos-inmueble/{gasto_id}")
def actualizar_gasto_inmueble(gasto_id: int, datos: GastoInmueblePatch, s: Session = SesionDB):
    g = _obtener(s, GastoInmueble, gasto_id)
    if datos.tipo is not None and datos.tipo not in alquiler.TIPOS_GASTO:
        raise HTTPException(400, "Tipo de gasto desconocido")
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        if valor is not None:
            setattr(g, campo, valor)
    s.commit()
    return {"ok": True}


class ValoracionPatch(BaseModel):
    fecha: date | None = None
    valor: Decimal | None = None


@router.patch("/valoraciones/{valoracion_id}")
def actualizar_valoracion(valoracion_id: int, datos: ValoracionPatch, s: Session = SesionDB):
    v = _obtener(s, Valoracion, valoracion_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        if valor is not None:
            setattr(v, campo, valor)
    s.commit()
    sync.guardar_instantanea(s)
    return {"ok": True}


# --- ¿Ha pagado el inquilino? --------------------------------------------------------

def ingresos_recientes(s: Session, hoy: date, meses: int = 3) -> list[MovTuyo]:
    """Entradas en tus cuentas desde el primer día de hace `meses` meses (para cruzar los cobros del alquiler)."""
    desde = sumar_meses(hoy.replace(day=1), -(meses - 1))
    return [m for m in movimientos_tuyos(s, desde) if m.importe > 0]


def cobros_alquiler(c: ContratoAlquiler, ingresos: list[MovTuyo], hoy: date, meses: int = 3) -> list[dict]:
    """Mes a mes (los últimos `meses`), si ha llegado el alquiler: un ingreso del importe de la renta (±1 €) o de
    categoría «Alquiler cobrado» en ese mes. `cuadra` dice si el importe coincide con la renta."""
    filas = []
    for k in range(meses - 1, -1, -1):
        mes = sumar_meses(hoy.replace(day=1), -k)
        if mes < c.fecha_inicio.replace(day=1) or (c.fecha_fin and mes > c.fecha_fin):
            continue
        renta = float(c.renta_en(mes))
        del_mes = [m for m in ingresos if (m.fecha.year, m.fecha.month) == (mes.year, mes.month)]
        por_importe = [m for m in del_mes if abs(m.importe - renta) <= 1]
        por_categoria = [m for m in del_mes if m.categoria == CATEGORIA_ALQUILER]
        m = min(por_importe or por_categoria, key=lambda x: x.fecha, default=None)
        filas.append({"mes": mes.strftime("%Y-%m"), "renta": renta, "fecha": f(m.fecha) if m else None,
                      "importe": round(m.importe, 2) if m else None, "cuadra": bool(m and abs(m.importe - renta) <= 1)})
    return filas


# --- Avisos -------------------------------------------------------------------------

def _aniversario(inicio: date, hoy: date) -> date:
    """El próximo aniversario del contrato (hoy incluido); si empezó un 29 de febrero, el 1 de marzo."""
    for anio in (hoy.year, hoy.year + 1):
        try:
            d = inicio.replace(year=anio)
        except ValueError:
            d = date(anio, 3, 1)
        if d >= hoy:
            return d
    return d


def _avisos_contratos(s: Session, hoy: date, movs: list[MovTuyo]) -> list[dict]:
    lista = []
    ingresos = [m for m in movs if m.importe > 0]
    hay_banco_este_mes = any(m.fecha >= hoy.replace(day=1) for m in movs)
    for c in s.scalars(select(ContratoAlquiler)):
        if not c.vigente(hoy):
            continue
        quien = c.inquilino or c.activo.nombre
        if hoy.day > DIA_AVISO_ALQUILER and hay_banco_este_mes:
            actual = next((x for x in cobros_alquiler(c, ingresos, hoy, 1)), None)
            if actual and not actual["fecha"]:
                lista.append({"nivel": "aviso", "texto": f"El alquiler de {MESES[hoy.month - 1]} aún no ha llegado"
                              f"{f' ({quien})' if c.inquilino else ''}.", "ir": "/inmuebles"})
        aniversario = _aniversario(c.fecha_inicio, hoy)
        ultimo = max([c.fecha_inicio] + [x.desde for x in c.cambios_renta])
        if (aniversario - hoy).days <= 30 and sumar_meses(ultimo, 12) <= aniversario:
            anios = aniversario.year - c.fecha_inicio.year
            lista.append({"nivel": "info", "texto": f"El contrato de {quien} cumple {anios} {'año' if anios == 1 else 'años'} "
                          f"el {aniversario:%d/%m}: puedes actualizar la renta.", "ir": "/inmuebles"})
        if c.fecha_fin and (c.fecha_fin - hoy).days <= 60:
            lista.append({"nivel": "aviso", "texto": f"El contrato de {quien} termina el {c.fecha_fin:%d/%m/%Y}.",
                          "ir": "/inmuebles"})
    return lista


def _avisos_deudas(s: Session, hoy: date, movs: list[MovTuyo]) -> list[dict]:
    """Si lo que cobra el banco (categoría «Cuota hipoteca») no cuadra con la cuota calculada."""
    cargos = sorted((m for m in movs if m.importe < 0 and m.categoria == CATEGORIA_CUOTA), key=lambda m: m.fecha, reverse=True)
    if len(cargos) < 2:
        return []
    activas = [(d, cuota) for d in s.scalars(select(Deuda)) if d.fecha_inicio and d.fecha_inicio <= hoy
               and (cuota := next((c.cuota for c in cuadro_vigente(d) if c.fecha > hoy), None))]
    lista = []
    for d, cuota in activas:
        # Con varias deudas, a cada una le tocan los cargos que se parecen a su cuota
        suyos = cargos if len(activas) == 1 else [m for m in cargos if abs(Decimal(str(-m.importe)) - cuota) <= cuota / 4]
        if len(suyos) < 2:
            continue
        real = Decimal(str(statistics.median(-m.importe for m in suyos[:3]))).quantize(CENT)
        if abs(real - cuota) > TOLERANCIA_CUOTA:
            que = "Tu hipoteca" if d.tipo == "hipoteca" else "Tu préstamo"
            nombre = "" if d.nombre.lower() in ("hipoteca", "préstamo", "prestamo") else f" {d.nombre}"
            lista.append({"nivel": "aviso", "texto": f"{que}{nombre} cobra {_eur(real)} y la app supone {_eur(cuota)}: "
                          "actualiza el tipo o el pendiente.", "ir": "/inmuebles"})
    return lista


def avisos(s: Session) -> list[dict]:
    """Avisos de Bienes: alquiler que no llega, contratos que cumplen años o terminan y cuotas que no cuadran."""
    hoy = date.today()
    movs = movimientos_tuyos(s, min(sumar_meses(hoy.replace(day=1), -2), hoy - timedelta(days=120)))
    return _avisos_contratos(s, hoy, movs) + _avisos_deudas(s, hoy, movs)
