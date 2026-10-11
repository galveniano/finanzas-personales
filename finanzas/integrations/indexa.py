"""Cliente de solo lectura de la API de Indexa Capital.

Documentación: https://indexacapital.com/en/api-rest-v1
El token se genera en el área privada de Indexa y no caduca.
"""
import json
import logging
from datetime import date
from decimal import Decimal

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finanzas import config
from finanzas.fechas import ahora_utc, sumar_meses
from finanzas.models import Categoria, Cuenta, Movimiento

# Categoría de serie de los traspasos del banco a Indexa (finanzas/categorizar.py)
CATEGORIA_APORTACION = "Inversión (Indexa)"


class IndexaError(Exception):
    pass


class IndexaClient:
    def __init__(self, token: str | None = None, base_url: str | None = None, transport=None):
        self.token = token if token is not None else config.INDEXA_TOKEN
        if not self.token:
            raise IndexaError("Falta INDEXA_TOKEN en el fichero .env")
        self.http = httpx.Client(
            base_url=base_url or config.INDEXA_BASE_URL,
            headers={"X-AUTH-TOKEN": self.token, "Accept": "application/json"},
            timeout=20,
            transport=transport,
        )

    def _get(self, ruta: str) -> dict:
        r = self.http.get(ruta)
        if r.status_code == 401 or r.status_code == 403:
            raise IndexaError("Indexa ha rechazado el token. Genera uno nuevo en tu área privada.")
        r.raise_for_status()
        return r.json()

    def cuenta(self, numero: str) -> dict:
        return self._get(f"/accounts/{numero}")

    def cuentas(self) -> list[dict]:
        return self._get("/users/me").get("accounts", [])

    def cartera(self, numero: str) -> dict:
        return self._get(f"/accounts/{numero}/portfolio")

    def rentabilidad(self, numero: str) -> dict:
        return self._get(f"/accounts/{numero}/performance")

    def movimientos(self, numero: str) -> list[dict]:
        datos = self._get(f"/accounts/{numero}/transactions")
        return datos if isinstance(datos, list) else datos.get("transactions", [])


def valor_total(cartera: dict) -> Decimal:
    bloque = cartera.get("portfolio", cartera)
    total = bloque.get("total_amount")
    if total is None:
        raise IndexaError("La respuesta de cartera no trae total_amount")
    return Decimal(str(total)).quantize(Decimal("0.01"))


log = logging.getLogger(__name__)

TIPOS = {"mutual": "Fondos de inversión", "pension": "Plan de pensiones", "epsv": "EPSV"}


def _num(v) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _identificador(instrumento: dict) -> str:
    """ISIN en fondos; en planes de pensiones, código DGS (o EPSV) del plan y del fondo."""
    nombre = instrumento.get("identifier_name") or "ISIN"
    campos = {"ISIN": ("isin_code", None), "DGS": ("dgs_code", "dgs_fund_code"),
              "EPSV": ("epsv_plan_code", "epsv_fund_code")}.get(nombre, ("isin_code", None))
    codigo = instrumento.get(campos[0]) or instrumento.get("isin_code") or ""
    if campos[1] and instrumento.get(campos[1]):
        codigo = f"{codigo} - {instrumento[campos[1]]}"
    return codigo


def detalle(cartera: dict, rentabilidad: dict | None = None, cuenta: dict | None = None) -> dict:
    """Resumen de una cuenta de Indexa a partir de sus respuestas de la API. La API no documenta
    todos los campos, así que todo es opcional: lo que no venga se queda en None."""
    bloque = cartera.get("portfolio", cartera) or {}
    total = _num(bloque.get("total_amount")) or 0.0
    posiciones = []
    for ia in cartera.get("instrument_accounts") or []:
        for p in ia.get("positions") or []:
            ins = p.get("instrument") or {}
            valor = _num(p.get("amount")) or 0.0
            peso = _num(p.get("weight_real"))
            posiciones.append({
                "nombre": ins.get("name") or ins.get("description") or "Fondo",
                "codigo": _identificador(ins), "clase": ins.get("asset_class") or "",
                "gestora": ins.get("management_company_description") or "",
                "titulos": _num(p.get("titles")), "precio": _num(p.get("price")), "valor": round(valor, 2),
                "coste": _num(p.get("cost_amount")), "fecha": p.get("date"),
                "peso": round(peso * 100 if peso is not None else (valor / total * 100 if total else 0), 2),
            })
    posiciones.sort(key=lambda x: -x["valor"])
    costes = [x["coste"] for x in posiciones if x["coste"] is not None]
    coste = round(sum(costes), 2) if costes and len(costes) == len(posiciones) else None
    invertido = sum(x["valor"] for x in posiciones)
    r = (rentabilidad or {}).get("return") or {}
    pct = lambda v: round(v * 100, 2) if v is not None else None  # noqa: E731  (la API da tantos por uno)
    perfil = (cuenta or {}).get("profile") or {}
    return {
        "tipo": (cuenta or {}).get("type"), "producto": TIPOS.get((cuenta or {}).get("type"), (cuenta or {}).get("type")),
        "perfil_riesgo": perfil.get("selected_risk") or perfil.get("risk") or perfil.get("recommended_risk"),
        "total": round(total, 2), "efectivo": _num(bloque.get("cash_amount")),
        "invertido": round(_num(bloque.get("instruments_amount")) or invertido, 2),
        "coste": coste, "plusvalia": round(invertido - coste, 2) if coste is not None else None,
        "rentabilidad_anual": pct(_num(r.get("time_return_annual"))),
        "rentabilidad_total": pct(_num(r.get("time_return"))),
        "rentabilidad_dinero": pct(_num(r.get("money_return"))),
        "rentabilidad_esperada": pct(_num((rentabilidad or {}).get("plan_expected_return"))),
        "volatilidad": pct(_num((rentabilidad or {}).get("volatility"))),
        "posiciones": posiciones,
    }


def _opcional(fn, *args) -> dict | None:
    """Rentabilidad y datos de la cuenta son un extra: si fallan, el saldo se actualiza igual."""
    try:
        return fn(*args)
    except Exception as e:
        log.warning("Indexa: no se pudo leer %s: %s", fn.__name__, e)
        return None


def sincronizar(session: Session, cliente: IndexaClient | None = None) -> list[Cuenta]:
    """Crea o actualiza una Cuenta de tipo inversión por cada cuenta de Indexa."""
    cliente = cliente or IndexaClient()
    actualizadas = []
    for c in cliente.cuentas():
        numero = c.get("account_number")
        if not numero:
            continue
        cartera = cliente.cartera(numero)
        total = valor_total(cartera)
        cuenta = session.scalar(
            select(Cuenta).where(Cuenta.origen == "indexa", Cuenta.id_externo == numero)
        )
        if cuenta is None:
            tipo_producto = c.get("type") or c.get("product") or "cuenta"
            cuenta = Cuenta(nombre=f"Indexa {tipo_producto} {numero}", entidad="Indexa Capital",
                            tipo="inversion", origen="indexa", id_externo=numero)
            session.add(cuenta)
        cuenta.saldo, cuenta.saldo_fecha = total, date.today()
        cuenta.ultima_sincronizacion = ahora_utc()
        info = _opcional(cliente.cuenta, numero) or c
        cuenta.detalle = json.dumps(detalle(cartera, _opcional(cliente.rentabilidad, numero), info), ensure_ascii=False)
        actualizadas.append(cuenta)
    session.commit()
    return actualizadas


def aportaciones_banco(session: Session, cuentas: list[Cuenta], hoy: date | None = None) -> dict[int, dict]:
    """Lo que has mandado a Indexa desde tus cuentas del banco, por cuenta de Indexa (clave: id de la cuenta):
    los cargos de la categoría «Inversión (Indexa)», con tu parte. Un cargo va a la cuenta cuyo número aparece
    en el concepto; si no aparece ninguno, a la primera (con una sola cuenta de Indexa, todo va a ella)."""
    if not cuentas:
        return {}
    hoy = hoy or date.today()
    parte = func.coalesce(Cuenta.participacion, 100) / 100
    filas = session.execute(
        select(Movimiento.fecha, Movimiento.concepto, Movimiento.importe * parte)
        .join(Cuenta, Movimiento.cuenta_id == Cuenta.id)
        .join(Categoria, Movimiento.categoria_id == Categoria.id)
        .where(Categoria.nombre == CATEGORIA_APORTACION, Movimiento.importe < 0, parte > 0, Cuenta.origen != "indexa")
    ).all()
    hace_un_anio = sumar_meses(hoy, -12)
    suma = {c.id: {"total": 0.0, "ultimos_12_meses": 0.0, "primera_fecha": None} for c in cuentas}
    for fecha, concepto, tuyo in filas:
        destino = next((c for c in cuentas if c.id_externo and c.id_externo in (concepto or "")), cuentas[0])
        d = suma[destino.id]
        d["total"] -= float(tuyo)
        if fecha >= hace_un_anio:
            d["ultimos_12_meses"] -= float(tuyo)
        if d["primera_fecha"] is None or fecha < d["primera_fecha"]:
            d["primera_fecha"] = fecha
    return {k: {"total": round(v["total"], 2), "ultimos_12_meses": round(v["ultimos_12_meses"], 2),
                "primera_fecha": v["primera_fecha"].isoformat() if v["primera_fecha"] else None}
            for k, v in suma.items()}
