"""Previsión de los próximos meses: nómina, facturación como autónomo, alquiler, impuestos y liquidez.

Los supuestos (sueldo, tarifas por hora, días al mes...) se guardan en ajustes como JSON y se editan
desde la app. Se simula el año natural completo para que los modelos 303 y 130 acumulen bien, y la
renta del año se estima con la escala general (estatal + autonómica) para el pago o la devolución de junio.
Es una estimación: no sustituye al borrador de la renta.
"""
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finanzas import ajustes
from finanzas.fiscal import alquiler, nomina as calc_nomina
from finanzas.hipoteca import cuadro_amortizacion, intereses_anio
from finanzas.models import (Activo, Categoria, Cliente, ContratoAlquiler, Cuenta, Declaracion, Deuda, Factura,
                             GastoInmueble, Movimiento, Nomina, Objetivo, PagoPrevisto)

CLAVE = "prevision"
SS_TRABAJADOR_PCT = sum(calc_nomina.SS_TRABAJADOR.values())
GASTOS_DIFICIL_JUSTIFICACION = (0.05, 2000.0)  # estimación directa simplificada: 5 %, máximo 2.000 €
LIMITE_REDUCCION_TRABAJO = 6500.0  # con más rentas que no sean del trabajo no hay reducción
# Base del ahorro (intereses, dividendos, ventas de fondos): escala desde 2025
ESCALA_AHORRO = [(6000, 19), (50000, 21), (200000, 23), (300000, 27), (float("inf"), 30)]
# Planes de pensiones: individual 1.500 €; de empleo simplificado para autónomos, 4.250 € más;
# en total no más del 30 % de los rendimientos del trabajo y de la actividad
LIMITE_PENSIONES, LIMITE_PPES, LIMITE_PENSIONES_PCT = 1500.0, 4250.0, 0.30
IMPUTACION_PCT = 0.011  # 1,1 % del valor catastral (revisado después de 1994) de inmuebles que no alquilas

VACIO = {"nomina": None, "clientes": [], "gastos_autonomo_mes": 0, "gasto_habitual_mes": None,
         "meses_sin_facturar": [], "dias_planificados": {},
         # Renta: base del ahorro e imputación de inmuebles al año (vacío: los de la última renta),
         # aportaciones a pensiones y si fraccionas el pago (60 % junio, 40 % noviembre)
         "rentas_ahorro_anio": None, "imputacion_inmuebles_anio": None, "aportacion_pensiones_anio": 0,
         "aportacion_ppes_anio": 0, "fraccionar_renta": False}


def leer(s: Session) -> dict:
    try:
        datos = json.loads(ajustes.leer(s, CLAVE, "") or "{}")
    except ValueError:
        datos = {}
    return {**VACIO, **datos}


def guardar(s: Session, datos: dict) -> None:
    ajustes.guardar(s, CLAVE, json.dumps({k: datos.get(k, v) for k, v in VACIO.items()}))


@dataclass
class Mes:
    clave: str
    nomina: float = 0.0
    facturado: float = 0.0
    cobros: float = 0.0  # base + IVA - retención
    iva: float = 0.0
    retenciones: float = 0.0
    alquiler: float = 0.0
    gastos: float = 0.0
    pagos_previstos: float = 0.0
    impuestos: list[dict] = field(default_factory=list)
    objetivos: list[dict] = field(default_factory=list)
    ya: dict | None = None  # lo que ya ha pasado este mes (solo el mes en curso)

    @property
    def neto(self) -> float:
        return round(self.nomina + self.cobros + self.alquiler - self.gastos - self.pagos_previstos
                     - sum(i["importe"] for i in self.impuestos) - sum(o["importe"] for o in self.objetivos), 2)


def _meses(desde: date, n: int) -> list[date]:
    return [date(desde.year + (desde.month - 1 + i) // 12, (desde.month - 1 + i) % 12 + 1, 1) for i in range(n)]


def _nomina_anual(cfg: dict | None) -> dict:
    """Neto de cada mes del año (con las extras) y totales para la renta."""
    if not cfg or not cfg.get("bruto_anual"):
        return {"meses": {m: 0.0 for m in range(1, 13)}, "bruto": 0.0, "ss": 0.0, "irpf": 0.0}
    bruto = float(cfg["bruto_anual"])
    c = calc_nomina.calcular(bruto, int(cfg.get("pagas", 14)))
    meses = {m: sum(x.neto for x in c.meses if x.mes == m) for m in range(1, 13)}
    variable = bruto * float(cfg.get("variable_pct", 0)) / 100
    ss_var = irpf_var = 0.0
    if variable:
        ss_var, irpf_var = variable * SS_TRABAJADOR_PCT / 100, variable * c.tipo_irpf / 100
        mes_var = int(cfg.get("mes_variable", 3))
        meses[mes_var] += variable - ss_var - irpf_var
    return {"meses": meses, "bruto": bruto + variable, "ss": c.ss_anual + ss_var, "irpf": c.irpf_anual + irpf_var}


def _por_cliente(cfg: dict, d: date) -> list[tuple[str, float, float, float]]:
    """Nombre, base, IVA y retención previstos de cada cliente en un mes. Los días planificados para ese
    mes mandan; si no, los meses sin facturar dan 0 y el resto usa los días al mes del cliente."""
    clave, planes = d.strftime("%Y-%m"), cfg.get("dias_planificados") or {}
    filas = []
    for c in cfg.get("clientes", []):
        plan = (planes.get(c.get("nombre")) or {}).get(clave)
        if plan is None and d.month in cfg.get("meses_sin_facturar", []):
            dias = 0.0
        else:
            dias = float(plan if plan is not None else c.get("dias_mes", 20))
        b = float(c.get("tarifa_hora", 0)) * float(c.get("horas_dia", 8)) * dias
        filas.append((c.get("nombre", ""), b, b * float(c.get("iva", 0)) / 100, b * float(c.get("retencion", 0)) / 100))
    return filas


def _facturacion(cfg: dict, d: date) -> tuple[float, float, float]:
    """Base, IVA y retención de lo facturado en un mes."""
    filas = _por_cliente(cfg, d)
    return tuple(round(sum(f[i] for f in filas), 2) for i in (1, 2, 3))


def _exento_130(cfg: dict) -> bool:
    """Sin 130 si al menos el 70 % de lo facturado lleva retención."""
    bases = [(float(c.get("tarifa_hora", 0)) * float(c.get("horas_dia", 8)) * float(c.get("dias_mes", 20)),
              float(c.get("retencion", 0))) for c in cfg.get("clientes", [])]
    total = sum(b for b, _ in bases)
    return bool(total) and sum(b for b, r in bases if r > 0) / total >= 0.7


def _palabra(nombre: str) -> str:
    return nombre.split()[0].lower() if nombre and nombre.split() else ""


def _dias_ultimo_mes(s: Session, c: dict) -> tuple[float, str] | None:
    """Días trabajados al mes para ese cliente: media de sus últimos 3 meses facturados (lo facturado / tarifa × horas)."""
    precio_dia = float(c.get("tarifa_hora", 0)) * float(c.get("horas_dia", 8))
    palabra = _palabra(c.get("nombre") or "")
    if not precio_dia or not palabra:
        return None
    facturas = s.scalars(select(Factura).join(Cliente).where(func.lower(Cliente.nombre).contains(palabra))
                         .order_by(Factura.fecha.desc())).all()
    if not facturas:
        return None
    meses = sorted({f.fecha.strftime("%Y-%m") for f in facturas}, reverse=True)[:3]
    base = sum(float(f.base) for f in facturas if f.fecha.strftime("%Y-%m") in meses)
    texto = f"facturado en {meses[0]}" if len(meses) == 1 else f"media de {meses[-1]} a {meses[0]}"
    return round(base / precio_dia / len(meses), 1), texto


PATRON_CUOTA_AUTONOMO = ("tgss", "seguridad social", "cotizacion autonomo", "cuota autonomo")


def cuota_autonomo_banco(s: Session) -> float | None:
    """Media mensual de la cuota de autónomos cargada en el banco en los últimos 3 meses completos."""
    fin = date.today().replace(day=1)
    inicio = (fin - timedelta(days=85)).replace(day=1)
    movs = s.scalars(select(Movimiento).where(Movimiento.fecha >= inicio, Movimiento.fecha < fin,
                                              Movimiento.importe < 0)).all()
    cargos = [m for m in movs if any(p in (m.concepto or "").lower() for p in PATRON_CUOTA_AUTONOMO)]
    if not cargos:
        return None
    meses = len({m.fecha.strftime("%Y-%m") for m in cargos})
    return round(-float(sum((m.importe for m in cargos), Decimal(0))) / meses, 2)


def resolver_clientes(s: Session, cfg: dict) -> dict:
    """Si no pones días al mes, se usan los del último mes facturado (y si no hay facturas, 20).
    Si no pones gastos de autónomo, se usa la cuota de autónomos que veas cargada en el banco."""
    clientes = []
    for c in cfg.get("clientes", []):
        c = dict(c)
        if c.get("dias_mes") in (None, ""):
            ultimo = _dias_ultimo_mes(s, c)
            c["dias_mes"], c["origen_dias"] = (ultimo[0], ultimo[1]) if ultimo else (20, "por defecto")
        else:
            c["origen_dias"] = "a mano"
        clientes.append(c)
    resuelto = {**cfg, "clientes": clientes, "origen_gastos_autonomo": "a mano", "factor_renta": factor_renta(s)}
    # Lo que la app no ve (las otras viviendas, intereses y ventas de fondos) sale de la última renta si no lo pones
    casillas = (ultima_renta(s) or {}).get("casillas", {})
    for clave, casilla in (("rentas_ahorro_anio", "base_ahorro"), ("imputacion_inmuebles_anio", "imputacion_inmuebles")):
        if cfg.get(clave) in (None, ""):
            resuelto[clave] = float(casillas.get(casilla) or 0)
            resuelto[f"origen_{clave}"] = "última renta" if casillas.get(casilla) else "sin datos"
        else:
            resuelto[clave], resuelto[f"origen_{clave}"] = float(cfg[clave]), "a mano"
    if not float(cfg.get("gastos_autonomo_mes") or 0):
        cuota, origen = cuota_autonomo_banco(s), "cuota de autónomos del banco"
        if not cuota and (ultima := ultima_renta(s)) and ultima["casillas"].get("gastos_actividad"):
            cuota = round(ultima["casillas"]["gastos_actividad"] / 12, 2)
            origen = f"gastos de la actividad en la renta {ultima['anio']}"
        resuelto["gastos_autonomo_mes"] = cuota or 0
        resuelto["origen_gastos_autonomo"] = origen if cuota else "sin datos"
    return resuelto


def factor_renta(s: Session) -> float:
    """Ajuste de la escala con la última renta presentada: su cuota real entre la que calcula la app con
    la misma base (recoge la escala autonómica exacta y las deducciones). Entre 0,85 y 1,1."""
    ultima = ultima_renta(s)
    c = (ultima or {}).get("casillas", {})
    if not c.get("base_general") or not c.get("cuota"):
        return 1.0
    calculada = _escala(c["base_general"]) - _escala(calc_nomina.MINIMO_PERSONAL)
    cuota_general = c["cuota"] - escala_ahorro(c.get("base_ahorro") or 0.0)  # la cuota de la renta incluye el ahorro
    return round(min(max(cuota_general / calculada, 0.85), 1.1), 4) if calculada > 0 else 1.0


def escala_ahorro(base: float) -> float:
    cuota, desde = 0.0, 0.0
    for hasta, tipo in ESCALA_AHORRO:
        if base <= desde:
            break
        cuota += (min(base, hasta) - desde) * tipo / 100
        desde = hasta
    return cuota


def imputacion_activos(s: Session, anio: int) -> float:
    """Imputación de rentas de los inmuebles que tienes en la app y no son tu casa ni están alquilados ese año."""
    total = 0.0
    for a in s.scalars(select(Activo).where(Activo.tipo == "inmueble", Activo.uso != "vivienda_habitual")):
        if not a.valor_catastral:
            continue
        contratos = s.scalars(select(ContratoAlquiler).where(ContratoAlquiler.activo_id == a.id)).all()
        if any(alquiler.meses_alquilado(c, anio) for c in contratos):
            continue
        total += float(a.valor_catastral) * IMPUTACION_PCT * float(a.porcentaje_propiedad) / 100
    return round(total, 2)


def ultima_renta(s: Session) -> dict | None:
    """La última renta (modelo 100) presentada con sus casillas leídas del PDF."""
    d = s.scalar(select(Declaracion).where(Declaracion.modelo == "100").order_by(Declaracion.ejercicio.desc(),
                                                                                  Declaracion.id.desc()))
    if not d:
        return None
    try:
        casillas = json.loads(d.casillas) if d.casillas else {}
    except ValueError:
        casillas = {}
    return {"anio": d.ejercicio, "resultado": float(d.importe), "casillas": casillas}


def _nomina_con_reales(s: Session, anio: int, prevista: dict) -> dict:
    """Las nóminas que hayas subido mandan en sus meses (bruto, Seguridad Social, IRPF retenido y neto);
    el resto del año sigue la previsión."""
    reales = [x for x in s.scalars(select(Nomina)).all() if x.fecha.year == anio]
    if not reales:
        return prevista
    meses = dict(prevista["meses"])
    cubiertos = {x.fecha.month for x in reales}
    neto_previsto = sum(prevista["meses"].values()) or 1.0
    resto = sum(v for m, v in prevista["meses"].items() if m not in cubiertos) / neto_previsto
    for m in cubiertos:
        meses[m] = sum(float(x.neto) for x in reales if x.fecha.month == m)
    return {"meses": meses,
            "bruto": sum(float(x.bruto) for x in reales) + prevista["bruto"] * resto,
            "ss": sum(float(x.seguridad_social) for x in reales) + prevista["ss"] * resto,
            "irpf": sum(float(x.retencion_irpf) for x in reales) + prevista["irpf"] * resto,
            "reales": len(cubiertos)}


def _escala(base: float) -> float:
    return calc_nomina._escala(max(base, 0.0))


def _alquiler(s: Session, anio: int) -> tuple[float, float]:
    """Renta mensual de hoy y rendimiento reducido del año (lo que tributa) de todos los pisos alquilados."""
    hoy, renta_mes, tributa = date.today(), 0.0, 0.0
    for a in s.scalars(select(Activo).where(Activo.tipo == "inmueble")):
        contratos = s.scalars(select(ContratoAlquiler).where(ContratoAlquiler.activo_id == a.id)).all()
        if not contratos:
            continue
        renta_mes += float(sum((c.renta_en(hoy) for c in contratos
                                if c.fecha_inicio <= hoy and (not c.fecha_fin or c.fecha_fin >= hoy)), Decimal(0)))
        gastos = list(s.scalars(select(GastoInmueble).where(GastoInmueble.activo_id == a.id)))
        if not any(g.tipo == "intereses" and g.fecha.year == anio for g in gastos):
            for d in s.scalars(select(Deuda).where(Deuda.activo_id == a.id)):
                gastos.append(GastoInmueble(fecha=date(anio, 12, 31), tipo="intereses", importe=intereses_anio(d, anio)))
        tributa += float(alquiler.calcular_rendimiento(a, contratos, gastos, anio).rendimiento_reducido)
    return renta_mes, tributa


@dataclass
class MovTuyo:
    id: int
    fecha: date
    cuenta_id: int
    importe: float  # lo que mueve la cuenta
    tuyo: float  # tu parte (importe × participación)
    concepto: str
    categoria: str | None
    tipo: str | None


def movimientos_tuyos(s: Session, desde: date, hasta: date | None = None) -> list[MovTuyo]:
    """Movimientos de las cuentas que son (en parte) tuyas, con tu parte del importe."""
    parte = func.coalesce(Cuenta.participacion, 100) / 100
    consulta = (select(Movimiento.id, Movimiento.fecha, Movimiento.cuenta_id, Movimiento.importe,
                       Movimiento.importe * parte, Movimiento.concepto, Categoria.nombre, Categoria.tipo)
                .join(Cuenta, Movimiento.cuenta_id == Cuenta.id)
                .join(Categoria, Movimiento.categoria_id == Categoria.id, isouter=True)
                .where(Movimiento.fecha >= desde, parte > 0))
    if hasta:
        consulta = consulta.where(Movimiento.fecha < hasta)
    return [MovTuyo(i, f, c, float(imp), float(t), con or "", cat, tipo)
            for i, f, c, imp, t, con, cat, tipo in s.execute(consulta)]


def ids_traspaso(movs: list[MovTuyo], dias: int = 3) -> set[int]:
    """Traspasos entre tus cuentas aunque el concepto no diga «traspaso»: una salida y una entrada del mismo
    importe en dos cuentas tuyas con como mucho 3 días de diferencia. No son gasto ni ingreso."""
    entradas = sorted((m for m in movs if m.importe > 0 and m.tipo != "transferencia"), key=lambda m: m.fecha)
    usados: set[int] = set()
    for sal in sorted((m for m in movs if m.importe < 0 and m.tipo != "transferencia"), key=lambda m: m.fecha):
        for ent in entradas:
            if (ent.id not in usados and ent.cuenta_id != sal.cuenta_id and abs(ent.importe + sal.importe) < 0.005
                    and abs((ent.fecha - sal.fecha).days) <= dias):
                usados |= {ent.id, sal.id}
                break
    return usados


def ids_pagos_previstos(s: Session, movs: list[MovTuyo], dias: int = 20) -> set[int]:
    """Cargos que son un pago previsto (plazos de la casa, llamadas de capital...): ya van aparte en la
    previsión, así que no cuentan como gasto habitual."""
    pagos = [(p.fecha, float(p.importe)) for p in s.scalars(select(PagoPrevisto)) if p.importe > 0]
    ids = set()
    for m in movs:
        if m.importe < 0 and any(abs(-m.importe - imp) <= max(imp * 0.01, 1) and abs((m.fecha - f).days) <= dias
                                 for f, imp in pagos):
            ids.add(m.id)
    return ids


def es_gasto_corriente(m: MovTuyo, excluidos: set[int]) -> bool:
    return (m.importe < 0 and m.id not in excluidos and m.tipo != "transferencia"
            and m.categoria != "Impuestos")


def gasto_habitual(s: Session) -> float | None:
    """Lo que sale de tus cuentas en un mes normal: la mediana de los últimos 3 meses completos, sin traspasos
    entre tus cuentas, impuestos ni pagos previstos (que la previsión ya resta aparte)."""
    fin = date.today().replace(day=1)
    inicio = (fin - timedelta(days=85)).replace(day=1)
    movs = movimientos_tuyos(s, inicio, fin)
    if not movs:
        return None
    excluidos = ids_traspaso(movs) | ids_pagos_previstos(s, movs)
    por_mes = {m.fecha.strftime("%Y-%m"): 0.0 for m in movs}  # solo los meses de los que hay movimientos
    for m in movs:
        if es_gasto_corriente(m, excluidos):
            por_mes[m.fecha.strftime("%Y-%m")] -= m.tuyo
    totales = sorted(por_mes.values())
    mediana = totales[len(totales) // 2] if len(totales) % 2 else (totales[len(totales) // 2 - 1] + totales[len(totales) // 2]) / 2
    return round(mediana, 2) if mediana else None


def ya_este_mes(s: Session) -> dict[str, float]:
    """Lo que ya ha pasado este mes en tus cuentas, para no contarlo otra vez en la previsión
    (el saldo de hoy ya lo incluye)."""
    hoy = date.today()
    movs = movimientos_tuyos(s, hoy.replace(day=1), hoy + timedelta(days=1))
    excluidos = ids_traspaso(movs) | ids_pagos_previstos(s, movs)
    ya = {"nomina": 0.0, "cobros": 0.0, "alquiler": 0.0, "gastos": 0.0, "impuestos": 0.0}
    claves = {"Nómina": "nomina", "Cobro de facturas": "cobros", "Alquiler cobrado": "alquiler"}
    for m in movs:
        if m.id in excluidos:
            continue
        if m.importe > 0 and m.categoria in claves:
            ya[claves[m.categoria]] += m.tuyo
        elif m.importe < 0 and m.categoria == "Impuestos":
            ya["impuestos"] -= m.tuyo
        elif es_gasto_corriente(m, excluidos):
            ya["gastos"] -= m.tuyo
    return {k: round(v, 2) for k, v in ya.items()}


def _renta(cfg: dict, nom: dict, facturado: float, retenciones: float, pagos_130: float, alquiler_tributa: float,
           imputacion_app: float = 0.0, extra: dict | None = None) -> dict:
    """Renta del año. `extra` simula aportaciones a pensiones o gastos de la actividad de más."""
    extra = extra or {}
    gastos_act = float(cfg.get("gastos_autonomo_mes", 0)) * 12 + float(extra.get("gastos_actividad", 0))
    previo = max(facturado - gastos_act, 0.0)
    pct, tope = GASTOS_DIFICIL_JUSTIFICACION
    actividad = previo - min(previo * pct, tope)
    trabajo = max(nom["bruto"] - nom["ss"] - calc_nomina.OTROS_GASTOS, 0.0)
    imputacion = float(cfg.get("imputacion_inmuebles_anio") or 0) + imputacion_app
    if actividad + alquiler_tributa + imputacion <= LIMITE_REDUCCION_TRABAJO:
        trabajo = max(trabajo - calc_nomina._reduccion_trabajo(trabajo), 0.0)
    base = trabajo + actividad + alquiler_tributa + imputacion
    pensiones = (min(float(extra.get("pensiones", cfg.get("aportacion_pensiones_anio") or 0)), LIMITE_PENSIONES)
                 + min(float(extra.get("ppes", cfg.get("aportacion_ppes_anio") or 0)), LIMITE_PPES))
    pensiones = min(pensiones, (trabajo + actividad) * LIMITE_PENSIONES_PCT)
    liquidable = max(base - pensiones, 0.0)
    factor = float(cfg.get("factor_renta", 1.0))
    cuota_general = max(_escala(liquidable) - _escala(calc_nomina.MINIMO_PERSONAL), 0.0) * factor
    base_ahorro = float(cfg.get("rentas_ahorro_anio") or 0)
    cuota_ahorro = escala_ahorro(base_ahorro)
    cuota = cuota_general + cuota_ahorro
    pagado = nom["irpf"] + retenciones + pagos_130
    # Tipo marginal: lo que pagarías por 100 € más de base general
    marginal = (max(_escala(liquidable + 100) - _escala(calc_nomina.MINIMO_PERSONAL), 0.0) * factor - cuota_general)
    return {"rendimiento_trabajo": round(trabajo, 2), "rendimiento_actividad": round(actividad, 2),
            "rendimiento_alquiler": round(alquiler_tributa, 2), "imputacion_inmuebles": round(imputacion, 2),
            "reduccion_pensiones": round(pensiones, 2), "base": round(base, 2), "base_liquidable": round(liquidable, 2),
            "base_ahorro": round(base_ahorro, 2), "cuota_ahorro": round(cuota_ahorro, 2), "cuota": round(cuota, 2),
            "retenciones_nomina": round(nom["irpf"], 2), "retenciones_facturas": round(retenciones, 2),
            "pagos_130": round(pagos_130, 2), "resultado": round(cuota - pagado, 2),
            "tipo_medio": round(cuota / (base + base_ahorro) * 100, 2) if base + base_ahorro else 0.0,
            "tipo_marginal": round(marginal, 2)}


def irpf_de_la_actividad(cfg: dict, actividad: float) -> float:
    """IRPF que se lleva la actividad al tipo medio de la renta: la cuota con nómina y actividad,
    repartida según lo que pesa cada una en la base."""
    nom = _nomina_anual(cfg.get("nomina"))
    trabajo = max(nom["bruto"] - nom["ss"] - calc_nomina.OTROS_GASTOS, 0.0)
    base = trabajo + max(actividad, 0.0)
    if not base:
        return 0.0
    cuota = max(_escala(base) - _escala(calc_nomina.MINIMO_PERSONAL), 0.0) * float(cfg.get("factor_renta", 1.0))
    return cuota * max(actividad, 0.0) / base


def _presentado(s: Session, modelo: str, anio: int, trimestre: int) -> float | None:
    """Lo ingresado por ese modelo y trimestre; con complementarias, la suma de todas."""
    decl = s.scalars(select(Declaracion).where(Declaracion.modelo == modelo, Declaracion.ejercicio == anio,
                                               Declaracion.periodo == f"{trimestre}T")).all()
    return float(sum((d.importe for d in decl), Decimal(0))) if decl else None


def _casillas_130(s: Session, anio: int, trimestre: int) -> dict:
    d = s.scalar(select(Declaracion).where(Declaracion.modelo == "130", Declaracion.ejercicio == anio,
                                           Declaracion.periodo == f"{trimestre}T").order_by(Declaracion.id.desc()))
    try:
        return json.loads(d.casillas) if d and d.casillas else {}
    except ValueError:
        return {}


def _facturado_por_mes(s: Session, cfg: dict) -> dict[str, dict]:
    """Base, IVA y retención de las facturas emitidas por mes, y la base de cada cliente
    (con el nombre que tenga en los supuestos si coincide la primera palabra)."""
    nombres = {_palabra(c.get("nombre", "")): c.get("nombre", "") for c in cfg.get("clientes", [])}
    meses: dict[str, dict] = {}
    for x in s.scalars(select(Factura)).all():
        fila = meses.setdefault(x.fecha.strftime("%Y-%m"), {"base": 0.0, "iva": 0.0, "ret": 0.0, "clientes": {}})
        fila["base"] += float(x.base)
        fila["iva"] += float(x.cuota_iva)
        fila["ret"] += abs(float(x.retencion))
        cliente = x.cliente.nombre if x.cliente else "Otros"
        cliente = next((v for k, v in nombres.items() if k and k in cliente.lower()), cliente)
        fila["clientes"][cliente] = fila["clientes"].get(cliente, 0.0) + float(x.base)
    return meses


def _gastos_alquiler(s: Session, anio: int) -> tuple[float, float]:
    """Gastos del año de los pisos alquilados (sin intereses) e intereses de sus hipotecas.
    Si el año aún no tiene gastos apuntados, se repiten los del último año que los tenga."""
    gastos = intereses = 0.0
    for a in s.scalars(select(Activo).where(Activo.tipo == "inmueble")):
        if not s.scalar(select(ContratoAlquiler.id).where(ContratoAlquiler.activo_id == a.id).limit(1)):
            continue
        lista = [g for g in s.scalars(select(GastoInmueble).where(GastoInmueble.activo_id == a.id))
                 if g.tipo != "intereses"]
        anios = sorted({g.fecha.year for g in lista if g.fecha.year <= anio})
        if anios:
            gastos += float(sum((g.importe for g in lista if g.fecha.year == anios[-1]), Decimal(0)))
        for d in s.scalars(select(Deuda).where(Deuda.activo_id == a.id)):
            intereses += float(intereses_anio(d, anio))
    return gastos, intereses


def _autonomo_por_cliente(facturado: float, gastos: float, irpf: float, por_cliente: dict[str, float]) -> list[dict]:
    """La parte de autónomo de cada cliente: gastos e IRPF repartidos según lo que factura cada uno."""
    clientes = {n: b for n, b in por_cliente.items() if b}
    if not clientes or not facturado:
        return [{"fuente": "Autónomo", "bruto": facturado, "gastos": gastos, "irpf": irpf}]
    return [{"fuente": n, "bruto": b, "gastos": gastos * b / facturado, "irpf": irpf * b / facturado, "cliente": True}
            for n, b in sorted(clientes.items(), key=lambda kv: -kv[1])]


def _ingresos(nom: dict, facturado: float, gastos_act: float, alquiler_bruto: float, gastos_alq: float,
              intereses: float, r: dict, por_cliente: dict[str, float] | None = None) -> dict:
    """Bruto y neto de cada fuente al mes. El IRPF de la renta se reparte al tipo medio entre las fuentes."""
    # Cada fuente paga el tipo medio de la renta sobre lo que aporta a la base
    base = r["base"] or 1.0
    irpf_trabajo = r["cuota"] * r["rendimiento_trabajo"] / base
    irpf_act = r["cuota"] * r["rendimiento_actividad"] / base
    irpf_alq = max(r["cuota"] - irpf_trabajo - irpf_act, 0.0)
    fuentes = [
        {"fuente": "Nómina", "bruto": nom["bruto"], "gastos": nom["ss"], "irpf": irpf_trabajo},
        *_autonomo_por_cliente(facturado, gastos_act, irpf_act, por_cliente or {}),
        {"fuente": "Alquiler", "bruto": alquiler_bruto, "gastos": gastos_alq + intereses, "irpf": irpf_alq},
    ]
    filas = []
    for f_ in fuentes:
        neto = f_["bruto"] - f_["gastos"] - f_["irpf"]
        filas.append({"fuente": f_["fuente"], "cliente": f_.get("cliente", False), "bruto_anual": round(f_["bruto"], 2), "neto_anual": round(neto, 2),
                      "gastos_anual": round(f_["gastos"], 2), "irpf_anual": round(f_["irpf"], 2),
                      "bruto_mes": round(f_["bruto"] / 12, 2), "neto_mes": round(neto / 12, 2)})
    total = {k: round(sum(x[k] for x in filas), 2) for k in ("bruto_anual", "neto_anual", "gastos_anual", "irpf_anual",
                                                               "bruto_mes", "neto_mes")}
    return {"fuentes": filas, "total": total}


def _renta_presentada(s: Session, anio: int) -> bool:
    return s.scalar(select(Declaracion.id).where(Declaracion.modelo == "100", Declaracion.ejercicio == anio)
                    .limit(1)) is not None


def _rendimiento_130(previo: float) -> float:
    """Rendimiento del 130 a partir del acumulado antes de los gastos de difícil justificación (5 %, máx. 2.000 €)."""
    pct, tope = GASTOS_DIFICIL_JUSTIFICACION
    return previo - min(max(previo, 0.0) * pct, tope)


def _previo_de_casillas(rendimiento: float) -> float:
    """El rendimiento de un 130 presentado ya lleva restado el 5 %: se deshace para seguir acumulando."""
    pct, tope = GASTOS_DIFICIL_JUSTIFICACION
    if rendimiento <= 0:
        return rendimiento
    sin_tope = rendimiento / (1 - pct)
    return sin_tope if sin_tope * pct <= tope else rendimiento + tope


def calcular(s: Session, meses: int = 12) -> dict:
    supuestos = leer(s)
    cfg = resolver_clientes(s, supuestos)
    hoy = date.today()
    inicio = hoy.replace(day=1)
    ventana = _meses(inicio, meses)
    anios = sorted({d.year for d in ventana})
    # La renta del año pasado se paga en junio: mientras no esté presentada también se simula
    if not _renta_presentada(s, hoy.year - 1) and hoy.month <= 7:
        anios.insert(0, hoy.year - 1)
    habitual = cfg.get("gasto_habitual_mes")
    habitual = float(habitual) if habitual is not None else (gasto_habitual(s) or 0.0)
    renta_mes, _ = _alquiler(s, hoy.year)
    pagos = s.scalars(select(PagoPrevisto).where(~PagoPrevisto.pagado)).all()
    gastos_act_mes = float(cfg.get("gastos_autonomo_mes", 0))

    reales = _facturado_por_mes(s, cfg)
    # Las hipotecas que aún no han empezado (la de la casa nueva) no están en el gasto del banco: sus cuotas se suman
    cuotas_futuras: dict[str, float] = {}
    for deuda in s.scalars(select(Deuda).where(Deuda.fecha_inicio > hoy)):
        # El mes en que se firma, el banco pone el capital (paga la entrega); luego vienen las cuotas
        firma = deuda.fecha_inicio.strftime("%Y-%m")
        cuotas_futuras[firma] = cuotas_futuras.get(firma, 0.0) - float(deuda.capital_inicial)
        for c in cuadro_amortizacion(deuda):
            cuotas_futuras[c.fecha.strftime("%Y-%m")] = cuotas_futuras.get(c.fecha.strftime("%Y-%m"), 0.0) + float(c.cuota)
    # Objetivos con fecha (boda, viajes...): el dinero sale ese mes, salvo que ya tengan sus pagos previstos
    con_pagos = {p.objetivo_id for p in s.scalars(select(PagoPrevisto)) if p.objetivo_id}
    objetivos: dict[str, list[dict]] = {}
    colchon = 0.0
    for o in s.scalars(select(Objetivo)):
        if o.tipo == "colchon":
            colchon += float(o.importe_objetivo)
        elif o.fecha_objetivo and o.fecha_objetivo >= inicio and o.id not in con_pagos and o.importe_objetivo:
            objetivos.setdefault(o.fecha_objetivo.strftime("%Y-%m"), []).append(
                {"concepto": o.nombre, "importe": float(o.importe_objetivo)})
    tabla: dict[str, Mes] = {}
    trimestres: dict[str, dict] = {}
    resumen_anios = []
    for anio in anios:
        nom = _nomina_con_reales(s, anio, _nomina_anual(cfg.get("nomina")))
        acumulado = {"previo": 0.0, "ret": 0.0, "pagos130": 0.0}
        facturado_anio = ret_anio = 0.0
        por_cliente: dict[str, float] = {}
        for d in _meses(date(anio, 1, 1), 12):
            m = tabla.setdefault(d.strftime("%Y-%m"), Mes(d.strftime("%Y-%m")))
            # Los meses ya cerrados con facturas usan lo facturado de verdad; el resto, las tarifas
            real = reales.get(d.strftime("%Y-%m")) if d < inicio else None
            if real:
                base, iva, ret = round(real["base"], 2), round(real["iva"], 2), round(real["ret"], 2)
                del_mes = real["clientes"]
            else:
                base, iva, ret = _facturacion(cfg, d)
                del_mes = {n: b for n, b, _, _ in _por_cliente(cfg, d)}
            for nombre_cli, b in del_mes.items():
                por_cliente[nombre_cli] = por_cliente.get(nombre_cli, 0.0) + b
            m.nomina, m.facturado, m.iva, m.retenciones = round(nom["meses"][d.month], 2), base, iva, ret
            m.cobros, m.alquiler = round(base + iva - ret, 2), round(renta_mes, 2)
            m.gastos = round(habitual, 2)
            m.pagos_previstos = round(float(sum((p.importe for p in pagos if p.fecha.strftime("%Y-%m") == m.clave),
                                                Decimal(0))) + cuotas_futuras.get(m.clave, 0.0), 2)
            m.objetivos = objetivos.get(m.clave, [])
            facturado_anio, ret_anio = facturado_anio + base, ret_anio + ret
            acumulado["previo"] += base - gastos_act_mes
            acumulado["ret"] += ret
            if d.month % 3 == 0:  # fin de trimestre: 303 y 130 se pagan el mes siguiente
                t = d.month // 3
                pago = _meses(d, 2)[1]
                del_trimestre = [tabla[x.strftime("%Y-%m")] for x in _meses(date(anio, d.month - 2, 1), 3)]
                iva_t = sum(x.iva for x in del_trimestre)
                p130 = 0.0 if _exento_130(cfg) else max(
                    0.2 * _rendimiento_130(acumulado["previo"]) - acumulado["ret"] - acumulado["pagos130"], 0.0)
                real_303, real_130 = _presentado(s, "303", anio, t), _presentado(s, "130", anio, t)
                iva_t = real_303 if real_303 is not None else iva_t
                p130 = real_130 if real_130 is not None else p130
                acumulado["pagos130"] += p130
                casillas = _casillas_130(s, anio, t)
                if "ingresos" in casillas:  # lo declarado en el 130 manda sobre lo calculado
                    acumulado["previo"] = _previo_de_casillas(float(casillas["ingresos"]) - float(casillas.get("gastos", 0)))
                    acumulado["ret"] = float(casillas.get("retenciones", acumulado["ret"]))
                trimestres[f"{anio}-{t}"] = {
                    "base": round(sum(x.facturado for x in del_trimestre), 2),
                    "iva": round(iva_t, 2), "irpf": round(p130, 2), "exento_130": _exento_130(cfg),
                    "presentado_303": real_303 is not None, "presentado_130": real_130 is not None}
                destino = tabla.setdefault(pago.strftime("%Y-%m"), Mes(pago.strftime("%Y-%m")))
                vence = date(pago.year, pago.month, 30 if pago.month == 1 else 20).isoformat()
                for concepto, importe, real in ((f"IVA {t}T (303)", iva_t, real_303), (f"IRPF {t}T (130)", p130, real_130)):
                    if importe:
                        destino.impuestos.append({"concepto": concepto, "importe": round(importe, 2),
                                                  "presentado": real is not None, "tipo": "trimestre", "vence": vence})
        _, alquiler_tributa = _alquiler(s, anio)
        imputacion_app = imputacion_activos(s, anio)
        r = _renta(cfg, nom, facturado_anio, ret_anio, acumulado["pagos130"], alquiler_tributa, imputacion_app)
        r["anio"] = anio
        # Lo que entra en la renta, para simular cambios (ahorro fiscal) sin repetir la previsión
        r["entradas"] = {"nomina": {k: round(nom[k], 2) for k in ("bruto", "ss", "irpf")},
                         "facturado": round(facturado_anio, 2), "retenciones": round(ret_anio, 2),
                         "pagos_130": round(acumulado["pagos130"], 2), "alquiler": round(alquiler_tributa, 2),
                         "imputacion_app": imputacion_app}
        alquiler_bruto = sum(tabla[x.strftime("%Y-%m")].alquiler for x in _meses(date(anio, 1, 1), 12))
        r["ingresos"] = _ingresos(nom, facturado_anio, gastos_act_mes * 12, alquiler_bruto,
                                  *_gastos_alquiler(s, anio), r, por_cliente)
        resumen_anios.append(r)
        if r["resultado"] > 0 and cfg.get("fraccionar_renta"):
            # Fraccionada: el 60 % en junio y el 40 % a primeros de noviembre
            for mes, dia, parte, texto in (("06", 30, 0.6, "1.er plazo"), ("11", 5, 0.4, "2.º plazo")):
                destino = tabla.setdefault(f"{anio + 1}-{mes}", Mes(f"{anio + 1}-{mes}"))
                destino.impuestos.append({"concepto": f"Renta {anio} ({texto})", "importe": round(r["resultado"] * parte, 2),
                                          "presentado": False, "tipo": "renta", "vence": f"{anio + 1}-{mes}-{dia:02d}"})
        elif r["resultado"]:
            junio = tabla.setdefault(f"{anio + 1}-06", Mes(f"{anio + 1}-06"))
            junio.impuestos.append({"concepto": f"Renta {anio}" + (" (a pagar)" if r["resultado"] > 0 else " (a devolver)"),
                                    "importe": r["resultado"], "presentado": False, "tipo": "renta",
                                    "vence": f"{anio + 1}-06-30"})

    for clave, linea in (_regularizacion_reta(s, supuestos, cfg, resumen_anios) + _tributos_locales(s, inicio)):
        if clave >= inicio.strftime("%Y-%m"):
            tabla.setdefault(clave, Mes(clave)).impuestos.append(linea)

    # Este mes ya ha pasado en parte y el saldo de hoy lo incluye: solo cuenta lo que falta
    ya = ya_este_mes(s)
    actual = tabla[inicio.strftime("%Y-%m")]
    actual.ya = ya
    actual.nomina = round(max(actual.nomina - ya["nomina"], 0.0), 2)
    actual.cobros = round(max(actual.cobros - ya["cobros"], 0.0), 2)
    actual.alquiler = round(max(actual.alquiler - ya["alquiler"], 0.0), 2)
    actual.gastos = round(max(actual.gastos - ya["gastos"], 0.0), 2)
    pendientes = sum(i["importe"] for i in actual.impuestos if i["importe"] > 0)
    if ya["impuestos"] and pendientes:
        actual.impuestos.append({"concepto": "Ya pagado este mes", "importe": -round(min(ya["impuestos"], pendientes), 2),
                                 "presentado": True, "tipo": "ajuste", "vence": None})

    liquidez = float(sum((c.saldo * c.parte for c in s.scalars(select(Cuenta).where(
        Cuenta.activa, Cuenta.tipo.in_(["corriente", "ahorro"])))), Decimal(0)))
    filas, saldo = [], liquidez
    for d in ventana:
        m = tabla[d.strftime("%Y-%m")]
        saldo += m.neto
        filas.append({"mes": m.clave, "nomina": m.nomina, "facturado": m.facturado, "cobros": m.cobros, "iva": m.iva,
                      "retenciones": m.retenciones, "alquiler": m.alquiler, "gastos": m.gastos,
                      "pagos_previstos": m.pagos_previstos, "impuestos": m.impuestos,
                      "objetivos": m.objetivos, "total_objetivos": round(sum(o["importe"] for o in m.objetivos), 2),
                      "total_impuestos": round(sum(i["importe"] for i in m.impuestos), 2),
                      "neto": m.neto, "liquidez": round(saldo, 2), "ya_este_mes": m.ya,
                      "bajo_colchon": bool(colchon) and saldo < colchon})
    return {"supuestos": supuestos, "clientes": cfg["clientes"],
            "gastos_autonomo_mes": cfg["gastos_autonomo_mes"], "origen_gastos_autonomo": cfg["origen_gastos_autonomo"],
            "rentas_ahorro_anio": cfg["rentas_ahorro_anio"], "origen_rentas_ahorro_anio": cfg["origen_rentas_ahorro_anio"],
            "imputacion_inmuebles_anio": cfg["imputacion_inmuebles_anio"],
            "origen_imputacion_inmuebles_anio": cfg["origen_imputacion_inmuebles_anio"],
            "renta_presentada": ultima_renta(s), "trimestres": trimestres, "gasto_habitual_banco": gasto_habitual(s),
            "liquidez_hoy": round(liquidez, 2), "colchon": round(colchon, 2),
            "meses": filas, "anios": [a for a in resumen_anios if a["anio"] in {d.year for d in ventana}],
            "anios_todos": resumen_anios}


# --- Seguridad Social y tributos locales en la previsión ------------------------

MES_REGULARIZACION_RETA = 11  # aproximado: la Seguridad Social regulariza cuando Hacienda le pasa la renta


def _regularizacion_reta(s: Session, supuestos: dict, cfg: dict, resumen_anios: list[dict]) -> list[tuple[str, dict]]:
    """Lo que la Seguridad Social reclamaría o devolvería de la cuota de autónomos de cada año (con la
    devolución por pluriactividad ya restada). Se pone en noviembre del año siguiente: la fecha real
    depende de cuándo lo resuelva, así que es aproximada."""
    from finanzas import hacienda  # hacienda importa este módulo
    prev = {"supuestos": supuestos, "anios_todos": resumen_anios, "gastos_autonomo_mes": cfg.get("gastos_autonomo_mes")}
    lineas = []
    for r in hacienda.revision_reta(s, prev):
        neto = round(r["a_pagar"] - r["a_devolver"] - r["devolucion_pluriactividad"], 2)
        if abs(neto) < 1:
            continue
        clave = f"{r['anio'] + 1}-{MES_REGULARIZACION_RETA:02d}"
        lineas.append((clave, {"concepto": f"Cuota de autónomos {r['anio']} ({'a pagar' if neto > 0 else 'a devolver'})",
                               "importe": neto, "presentado": False, "tipo": "reta", "vence": None}))
    return lineas


PATRON_TRIBUTO_LOCAL = ("ibi", "i.b.i", "bienes inmuebles", "ivtm", "vehiculo", "vehículo", "circulacion",
                        "circulación", "basura", "ayuntamiento", "ayto", "region de murcia", "región de murcia",
                        "atrm", "recaudacion", "recaudación", "tasa ")


def _tributos_locales(s: Session, inicio: date) -> list[tuple[str, dict]]:
    """IBI, impuesto de circulación, basuras...: los cargos en «Impuestos» de los últimos 12 meses que no son
    de Hacienda se repiten el mismo mes del año siguiente. No están en el gasto habitual (que quita los
    impuestos), así que sin esto no saldrían en la previsión."""
    desde = date(inicio.year - 1, inicio.month, 1)
    lineas = []
    for m in movimientos_tuyos(s, desde, inicio):
        concepto = (m.concepto or "").lower()
        if m.importe >= 0 or m.categoria != "Impuestos" or not any(p in concepto for p in PATRON_TRIBUTO_LOCAL):
            continue
        cuando = date(m.fecha.year + 1, m.fecha.month, min(m.fecha.day, 28))
        lineas.append((cuando.strftime("%Y-%m"), {"concepto": f"{(m.concepto or 'Tributo').strip()[:40]} (como el año pasado)",
                                                  "importe": round(-m.tuyo, 2), "presentado": False, "tipo": "local",
                                                  "vence": cuando.isoformat()}))
    return lineas


# --- Gastos de los últimos meses y suscripciones ------------------------------

def _patron(concepto: str) -> str:
    """Concepto sin números ni fechas, para reconocer el mismo cargo mes a mes."""
    import re
    texto = re.sub(r"[\d/.,:*#-]+", " ", (concepto or "").upper())
    texto = re.sub(r"\b(COMPRA|TARJ|TARJETA|PAGO|RECIBO|ADEUDO|CARGO|EN|DE|A|SEPA|CONTACTLESS)\b", " ", texto)
    return " ".join(texto.split())[:40]


def gastos_recientes(s: Session, meses: int = 3) -> dict:
    """Media mensual de ingresos, gastos y ahorro de los últimos meses completos, por categoría,
    y cargos que se repiten cada mes con un importe parecido (suscripciones, recibos)."""
    fin = date.today().replace(day=1)
    inicio = _meses(fin, 1)[0]
    for _ in range(meses):
        inicio = (inicio - timedelta(days=1)).replace(day=1)
    movs = movimientos_tuyos(s, inicio, fin)
    traspasos = ids_traspaso(movs)
    ingresos = gastos = 0.0
    por_cat: dict[str, float] = {}
    for m in movs:
        if m.tipo == "transferencia" or m.id in traspasos:
            continue
        if m.tuyo >= 0:
            ingresos += m.tuyo
        else:
            gastos -= m.tuyo
            por_cat[m.categoria or "Sin categoría"] = por_cat.get(m.categoria or "Sin categoría", 0.0) - m.tuyo
    n = meses
    categorias = sorted(({"categoria": k, "mes": round(v / n, 2)} for k, v in por_cat.items()), key=lambda x: -x["mes"])

    # Suscripciones: mismo patrón en al menos 2 meses distintos de los últimos 4, importes parecidos
    desde = inicio - timedelta(days=31)
    previos = movimientos_tuyos(s, desde)
    traspasos = ids_traspaso(previos)
    grupos: dict[str, list] = {}
    for m in previos:
        if m.importe >= 0 or m.tipo == "transferencia" or m.id in traspasos or not _patron(m.concepto):
            continue
        grupos.setdefault(_patron(m.concepto), []).append((m.fecha, m.concepto, -m.tuyo))
    subs = []
    for patron, lista in grupos.items():
        meses_vistos = {f.strftime("%Y-%m") for f, _, _ in lista}
        if len(meses_vistos) < 2 or len(lista) > len(meses_vistos) + 1:  # varias veces al mes: no es una cuota
            continue
        importes = sorted(i for _, _, i in lista)
        mediana = importes[len(importes) // 2]
        if mediana <= 0 or any(abs(i - mediana) / mediana > 0.2 for i in importes):
            continue
        ultimo = max(lista)
        subs.append({"concepto": ultimo[1], "mes": round(mediana, 2), "anual": round(mediana * 12, 2),
                     "ultimo_cargo": ultimo[0].isoformat(), "veces": len(lista)})
    subs.sort(key=lambda x: -x["mes"])
    return {"desde": inicio.isoformat(), "meses": n, "ingresos_mes": round(ingresos / n, 2),
            "gastos_mes": round(gastos / n, 2), "ahorro_mes": round((ingresos - gastos) / n, 2),
            "tasa_ahorro": round((ingresos - gastos) / ingresos * 100, 1) if ingresos else None,
            "categorias": categorias, "suscripciones": subs,
            "suscripciones_mes": round(sum(x["mes"] for x in subs), 2)}
