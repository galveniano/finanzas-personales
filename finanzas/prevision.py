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
                             GastoInmueble, Movimiento, Nomina, PagoPrevisto)

CLAVE = "prevision"
SS_TRABAJADOR_PCT = sum(calc_nomina.SS_TRABAJADOR.values())
GASTOS_DIFICIL_JUSTIFICACION = (0.05, 2000.0)  # estimación directa simplificada: 5 %, máximo 2.000 €
LIMITE_REDUCCION_TRABAJO = 6500.0  # con más rentas que no sean del trabajo no hay reducción

VACIO = {"nomina": None, "clientes": [], "gastos_autonomo_mes": 0, "gasto_habitual_mes": None,
         "meses_sin_facturar": [], "dias_planificados": {}}


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

    @property
    def neto(self) -> float:
        return round(self.nomina + self.cobros + self.alquiler - self.gastos - self.pagos_previstos
                     - sum(i["importe"] for i in self.impuestos), 2)


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
    return round(min(max(c["cuota"] / calculada, 0.85), 1.1), 4) if calculada > 0 else 1.0


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


def gasto_habitual(s: Session) -> float | None:
    """Media de lo que sale de tus cuentas en los últimos 3 meses completos (sin traspasos ni impuestos)."""
    fin = date.today().replace(day=1)
    inicio = (fin - timedelta(days=85)).replace(day=1)
    parte = func.coalesce(Cuenta.participacion, 100) / 100
    total = s.scalar(
        select(func.sum(Movimiento.importe * parte)).join(Cuenta, Movimiento.cuenta_id == Cuenta.id)
        .join(Categoria, Movimiento.categoria_id == Categoria.id, isouter=True)
        .where(Movimiento.fecha >= inicio, Movimiento.fecha < fin, Movimiento.importe < 0, parte > 0,
               (Categoria.tipo.is_(None)) | (Categoria.tipo != "transferencia"),
               (Categoria.nombre.is_(None)) | (Categoria.nombre != "Impuestos")))
    meses = (fin.year - inicio.year) * 12 + fin.month - inicio.month
    return round(-float(total) / meses, 2) if total else None


def _renta(cfg: dict, nom: dict, facturado: float, retenciones: float, pagos_130: float, alquiler_tributa: float) -> dict:
    gastos_act = float(cfg.get("gastos_autonomo_mes", 0)) * 12
    previo = max(facturado - gastos_act, 0.0)
    pct, tope = GASTOS_DIFICIL_JUSTIFICACION
    actividad = previo - min(previo * pct, tope)
    trabajo = max(nom["bruto"] - nom["ss"] - calc_nomina.OTROS_GASTOS, 0.0)
    if actividad + alquiler_tributa <= LIMITE_REDUCCION_TRABAJO:
        trabajo = max(trabajo - calc_nomina._reduccion_trabajo(trabajo), 0.0)
    base = trabajo + actividad + alquiler_tributa
    cuota = max(_escala(base) - _escala(calc_nomina.MINIMO_PERSONAL), 0.0) * float(cfg.get("factor_renta", 1.0))
    pagado = nom["irpf"] + retenciones + pagos_130
    return {"rendimiento_trabajo": round(trabajo, 2), "rendimiento_actividad": round(actividad, 2),
            "rendimiento_alquiler": round(alquiler_tributa, 2), "base": round(base, 2), "cuota": round(cuota, 2),
            "retenciones_nomina": round(nom["irpf"], 2), "retenciones_facturas": round(retenciones, 2),
            "pagos_130": round(pagos_130, 2), "resultado": round(cuota - pagado, 2),
            "tipo_medio": round(cuota / base * 100, 2) if base else 0.0}


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
    d = s.scalar(select(Declaracion).where(Declaracion.modelo == modelo, Declaracion.ejercicio == anio,
                                           Declaracion.periodo == f"{trimestre}T").order_by(Declaracion.id.desc()))
    return float(d.importe) if d else None


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


def calcular(s: Session, meses: int = 12) -> dict:
    supuestos = leer(s)
    cfg = resolver_clientes(s, supuestos)
    hoy = date.today()
    inicio = hoy.replace(day=1)
    ventana = _meses(inicio, meses)
    anios = sorted({d.year for d in ventana})
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
    tabla: dict[str, Mes] = {}
    trimestres: dict[str, dict] = {}
    resumen_anios = []
    for anio in anios:
        nom = _nomina_con_reales(s, anio, _nomina_anual(cfg.get("nomina")))
        acumulado = {"base": 0.0, "ret": 0.0, "pagos130": 0.0}
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
            facturado_anio, ret_anio = facturado_anio + base, ret_anio + ret
            acumulado["base"] += base - gastos_act_mes
            acumulado["ret"] += ret
            if d.month % 3 == 0:  # fin de trimestre: 303 y 130 se pagan el mes siguiente
                t = d.month // 3
                pago = _meses(d, 2)[1]
                del_trimestre = [tabla[x.strftime("%Y-%m")] for x in _meses(date(anio, d.month - 2, 1), 3)]
                iva_t = sum(x.iva for x in del_trimestre)
                p130 = 0.0 if _exento_130(cfg) else max(
                    0.2 * acumulado["base"] - acumulado["ret"] - acumulado["pagos130"], 0.0)
                real_303, real_130 = _presentado(s, "303", anio, t), _presentado(s, "130", anio, t)
                iva_t = real_303 if real_303 is not None else iva_t
                p130 = real_130 if real_130 is not None else p130
                acumulado["pagos130"] += p130
                casillas = _casillas_130(s, anio, t)
                if "ingresos" in casillas:  # lo declarado en el 130 manda sobre lo calculado
                    acumulado["base"] = float(casillas["ingresos"]) - float(casillas.get("gastos", 0))
                    acumulado["ret"] = float(casillas.get("retenciones", acumulado["ret"]))
                trimestres[f"{anio}-{t}"] = {
                    "base": round(sum(x.facturado for x in del_trimestre), 2),
                    "iva": round(iva_t, 2), "irpf": round(p130, 2), "exento_130": _exento_130(cfg)}
                destino = tabla.setdefault(pago.strftime("%Y-%m"), Mes(pago.strftime("%Y-%m")))
                for concepto, importe, real in ((f"IVA {t}T (303)", iva_t, real_303), (f"IRPF {t}T (130)", p130, real_130)):
                    if importe:
                        destino.impuestos.append({"concepto": concepto, "importe": round(importe, 2),
                                                  "presentado": real is not None})
        _, alquiler_tributa = _alquiler(s, anio)
        r = _renta(cfg, nom, facturado_anio, ret_anio, acumulado["pagos130"], alquiler_tributa)
        r["anio"] = anio
        alquiler_bruto = sum(tabla[x.strftime("%Y-%m")].alquiler for x in _meses(date(anio, 1, 1), 12))
        r["ingresos"] = _ingresos(nom, facturado_anio, gastos_act_mes * 12, alquiler_bruto,
                                  *_gastos_alquiler(s, anio), r, por_cliente)
        resumen_anios.append(r)
        junio = tabla.setdefault(f"{anio + 1}-06", Mes(f"{anio + 1}-06"))
        if r["resultado"]:
            junio.impuestos.append({"concepto": f"Renta {anio}" + (" (a pagar)" if r["resultado"] > 0 else " (a devolver)"),
                                    "importe": r["resultado"], "presentado": False})

    liquidez = float(sum((c.saldo * c.parte for c in s.scalars(select(Cuenta).where(
        Cuenta.activa, Cuenta.tipo.in_(["corriente", "ahorro"])))), Decimal(0)))
    filas, saldo = [], liquidez
    for d in ventana:
        m = tabla[d.strftime("%Y-%m")]
        saldo += m.neto
        filas.append({"mes": m.clave, "nomina": m.nomina, "facturado": m.facturado, "cobros": m.cobros, "iva": m.iva,
                      "retenciones": m.retenciones, "alquiler": m.alquiler, "gastos": m.gastos,
                      "pagos_previstos": m.pagos_previstos, "impuestos": m.impuestos,
                      "total_impuestos": round(sum(i["importe"] for i in m.impuestos), 2),
                      "neto": m.neto, "liquidez": round(saldo, 2)})
    return {"supuestos": supuestos, "clientes": cfg["clientes"],
            "gastos_autonomo_mes": cfg["gastos_autonomo_mes"], "origen_gastos_autonomo": cfg["origen_gastos_autonomo"],
            "renta_presentada": ultima_renta(s), "trimestres": trimestres, "gasto_habitual_banco": gasto_habitual(s), "liquidez_hoy": round(liquidez, 2),
            "meses": filas, "anios": [a for a in resumen_anios if a["anio"] in {d.year for d in ventana}]}


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
    parte = func.coalesce(Cuenta.participacion, 100) / 100
    filas = s.execute(
        select(Movimiento.fecha, Movimiento.concepto, Movimiento.importe * parte, Categoria.nombre, Categoria.tipo)
        .join(Cuenta, Movimiento.cuenta_id == Cuenta.id)
        .join(Categoria, Movimiento.categoria_id == Categoria.id, isouter=True)
        .where(Movimiento.fecha >= inicio, Movimiento.fecha < fin, parte > 0)).all()
    ingresos = gastos = 0.0
    por_cat: dict[str, float] = {}
    for _f, _c, importe, cat, tipo in filas:
        if tipo == "transferencia":
            continue
        v = float(importe)
        if v >= 0:
            ingresos += v
        else:
            gastos -= v
            por_cat[cat or "Sin categoría"] = por_cat.get(cat or "Sin categoría", 0.0) - v
    n = meses
    categorias = sorted(({"categoria": k, "mes": round(v / n, 2)} for k, v in por_cat.items()), key=lambda x: -x["mes"])

    # Suscripciones: mismo patrón en al menos 2 meses distintos de los últimos 4, importes parecidos
    desde = inicio - timedelta(days=31)
    cargos = s.execute(
        select(Movimiento.fecha, Movimiento.concepto, Movimiento.importe * parte, Categoria.tipo)
        .join(Cuenta, Movimiento.cuenta_id == Cuenta.id)
        .join(Categoria, Movimiento.categoria_id == Categoria.id, isouter=True)
        .where(Movimiento.fecha >= desde, Movimiento.importe < 0, parte > 0)).all()
    grupos: dict[str, list] = {}
    for fecha_m, concepto, importe, tipo in cargos:
        if tipo == "transferencia" or not _patron(concepto):
            continue
        grupos.setdefault(_patron(concepto), []).append((fecha_m, concepto, -float(importe)))
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
