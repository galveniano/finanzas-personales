"""Lo que debes a Hacienda y a la Seguridad Social y aún no has pagado, y la hucha para pagarlo.

El IVA que cobras en las facturas no es tuyo: lo guardas hasta el 303. Igual pasa con el 130 del
trimestre en curso y con la renta, que se va generando mes a mes y se paga en junio del año siguiente.
Todo son estimaciones a partir de la previsión.
"""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas import ajustes, declaraciones, prevision
from finanzas.fiscal import reta
from finanzas.models import Cuenta, Declaracion, Factura, GastoAutonomo, Nomina

CLAVE_HUCHA = "cuenta_hucha"


def _iva_facturas(s: Session, desde: date, hasta: date) -> float | None:
    """IVA repercutido menos soportado deducible de lo facturado entre dos fechas (ambas incluidas)."""
    facturas = s.scalars(select(Factura).where(Factura.fecha >= desde, Factura.fecha <= hasta)).all()
    if not facturas:
        return None
    gastos = s.scalars(select(GastoAutonomo).where(GastoAutonomo.fecha >= desde, GastoAutonomo.fecha <= hasta)).all()
    soportado = sum((g.cuota_iva * g.deducible_pct / 100 for g in gastos), Decimal(0))
    return float(sum((x.cuota_iva for x in facturas), Decimal(0)) - soportado)


def pendiente(s: Session, prev: dict | None = None, hoy: date | None = None) -> dict:
    """IVA, 130 y renta que ya se han generado y aún no has pagado. Lo del trimestre en curso cuenta en la
    parte de trimestre que ya ha pasado; la renta del año, en la parte de año."""
    hoy = hoy or date.today()
    prev = prev or prevision.calcular(s)
    lineas = []
    trimestre_actual = (hoy.month - 1) // 3 + 1
    # El trimestre anterior (se paga del 1 al 20 del mes siguiente) y el actual
    for anio, t in ({(hoy.year, trimestre_actual), (hoy.year - 1, 4) if trimestre_actual == 1
                     else (hoy.year, trimestre_actual - 1)}):
        datos = prev["trimestres"].get(f"{anio}-{t}")
        inicio_t = date(anio, 3 * t - 2, 1)
        en_curso = (anio, t) == (hoy.year, trimestre_actual)
        fraccion = ((hoy.month - inicio_t.month) + hoy.day / 31) / 3 if en_curso else 1.0
        if not declaraciones.presentada(s, "303", anio, f"{t}T"):
            iva = _iva_facturas(s, inicio_t, hoy) if en_curso else None
            if iva is None and datos:
                iva = datos["iva"] * fraccion
            if iva and iva > 0:
                lineas.append({"concepto": f"IVA {t}T {anio} (303)", "importe": round(iva, 2), "tipo": "iva",
                               "en_curso": en_curso})
        if datos and not datos["exento_130"] and not declaraciones.presentada(s, "130", anio, f"{t}T"):
            irpf = datos["irpf"] * fraccion
            if irpf > 0:
                lineas.append({"concepto": f"IRPF {t}T {anio} (130)", "importe": round(irpf, 2), "tipo": "130",
                               "en_curso": en_curso})
    # Renta: la del año pasado si aún no está presentada, y la parte que ya llevas de la de este año
    for r in prev.get("anios_todos", prev.get("anios", [])):
        if r["anio"] == hoy.year - 1 and r["resultado"] > 0 and not declaraciones.presentada(s, "100", r["anio"], "0A"):
            lineas.append({"concepto": f"Renta {r['anio']}", "importe": round(r["resultado"], 2), "tipo": "renta",
                           "en_curso": False})
        elif r["anio"] == hoy.year and r["resultado"] > 0:
            parte = (hoy.month - 1 + hoy.day / 31) / 12
            lineas.append({"concepto": f"Renta {r['anio']} (lo generado hasta hoy)",
                           "importe": round(r["resultado"] * parte, 2), "tipo": "renta", "en_curso": True})
    # Rentas presentadas con un pago aún por cargar (el 2.º plazo de noviembre)
    for p in prevision.plazos_rentas(s, hoy):
        lineas.append({"concepto": f"{p['concepto']}, se carga el {date.fromisoformat(p['fecha']):%d/%m/%Y}",
                       "importe": round(p["importe"], 2), "tipo": "renta", "en_curso": False})
    total = round(sum(x["importe"] for x in lineas), 2)
    return {"lineas": lineas, "total": total}


def cuota_reta_banco(s: Session, anio: int) -> tuple[float, int]:
    """Cuota de autónomos cargada en el banco en un año y en cuántos meses."""
    cargos = prevision.cargos_cuota_autonomos(s, date(anio, 1, 1), date(anio, 12, 31))
    return round(sum(i for _, i in cargos), 2), len({f.month for f, _ in cargos})


def bruto_nominas_12_meses(s: Session, pagas: int = 14, hoy: date | None = None) -> float:
    """Bruto anual según las nóminas registradas en los últimos 12 meses (0 si no hay ninguna). Con menos de un
    año subido, la media de las nóminas normales por las pagas del año."""
    hoy = hoy or date.today()
    ultimas = s.scalars(select(Nomina).where(Nomina.fecha > hoy - timedelta(days=365))).all()
    if not ultimas:
        return 0.0
    normales = [x for x in ultimas if not x.paga_extra]
    if normales and len({(x.fecha.year, x.fecha.month) for x in ultimas}) < 12:
        return round(float(sum((x.bruto for x in normales), Decimal(0))) / len(normales) * pagas, 2)
    return round(float(sum((x.bruto for x in ultimas), Decimal(0))), 2)


def _meses_hasta_regularizacion(anio: int, hoy: date) -> int:
    """Meses que quedan hasta que la Seguridad Social regularice ese año (hacia noviembre del siguiente)."""
    return max((anio + 1 - hoy.year) * 12 + prevision.MES_REGULARIZACION_RETA - hoy.month, 1)


def revision_reta(s: Session, prev: dict | None = None) -> list[dict]:
    """Por año: lo que cotizaste como autónomo frente a lo que te toca por tus rendimientos reales."""
    prev = prev or prevision.calcular(s)
    hoy = date.today()
    nomina = (prev["supuestos"].get("nomina") or {})
    bruto = float(nomina.get("bruto_anual") or 0) * (1 + float(nomina.get("variable_pct") or 0) / 100)
    if not bruto:  # sin sueldo en los supuestos: la pluriactividad sale de las nóminas que hayas subido
        bruto = bruto_nominas_12_meses(s, int(nomina.get("pagas") or 14), hoy)
    filas = []
    rentas = s.scalars(select(Declaracion).where(Declaracion.modelo == "100").order_by(Declaracion.ejercicio)).all()
    vistos = set()
    for d in rentas:
        c = declaraciones.casillas(d)
        if reta.anio_tabla(d.ejercicio) is None or d.ejercicio in vistos or "ingresos_actividad" not in c:
            continue
        vistos.add(d.ejercicio)
        cuota = c.get("ss_autonomo") or cuota_reta_banco(s, d.ejercicio)[0]
        rendimiento = c["ingresos_actividad"] - c.get("gastos_actividad", 0.0)
        r = reta.regularizar(d.ejercicio, rendimiento, cuota, bruto, f"renta {d.ejercicio}")
        if r:
            filas.append({**r.a_dict(), "previsto": False,
                          "meses_hasta_regularizacion": _meses_hasta_regularizacion(d.ejercicio, hoy)})
    # Este año y, mientras su renta no esté presentada, el pasado: con la previsión
    for actual in prev.get("anios_todos", []):
        anio = actual["anio"]
        if anio not in (hoy.year - 1, hoy.year) or anio in vistos or reta.anio_tabla(anio) is None:
            continue
        pagado, meses = cuota_reta_banco(s, anio)
        cuota = pagado / meses * 12 if meses else float(prev.get("gastos_autonomo_mes") or 0) * 12
        gastos = float(prev.get("gastos_autonomo_mes") or 0) * 12
        rendimiento = actual["entradas"]["facturado"] - gastos
        r = reta.regularizar(anio, rendimiento, cuota, bruto, "previsión del año")
        if r:
            filas.append({**r.a_dict(), "previsto": True,
                          "meses_hasta_regularizacion": _meses_hasta_regularizacion(anio, hoy)})
    return filas


def cuenta_hucha(s: Session) -> Cuenta | None:
    valor = ajustes.leer(s, CLAVE_HUCHA)
    return s.get(Cuenta, int(valor)) if valor.isdigit() else None


def hucha(s: Session, pend: dict, prev: dict) -> dict:
    """Cuánto tienes apartado (la cuenta que elijas) frente a lo que debes, y cuánto apartar al mes para
    llegar a junio con la renta de este año cubierta."""
    hoy = date.today()
    cuenta = cuenta_hucha(s)
    apartado = float(cuenta.saldo * cuenta.parte) if cuenta else None
    renta = next((a for a in prev.get("anios_todos", []) if a["anio"] == hoy.year), None)
    renta_total = max(renta["resultado"], 0.0) if renta else 0.0
    ya_generado = sum(x["importe"] for x in pend["lineas"] if x["tipo"] == "renta" and x["en_curso"])
    meses_hasta_junio = (hoy.year + 1 - hoy.year) * 12 + 6 - hoy.month
    falta = max(pend["total"] + (renta_total - ya_generado) - (apartado or 0.0), 0.0)
    return {"cuenta_id": cuenta.id if cuenta else None, "cuenta": cuenta.nombre if cuenta else None,
            "apartado": round(apartado, 2) if apartado is not None else None,
            "renta_prevista": round(renta_total, 2),
            "falta": round(falta, 2), "al_mes": round(falta / max(meses_hasta_junio, 1), 2),
            "meses_hasta_junio": meses_hasta_junio}
