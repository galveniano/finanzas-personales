"""Cliente de solo lectura de la API de Indexa Capital.

Documentación: https://indexacapital.com/en/api-rest-v1
El token se genera en el área privada de Indexa y no caduca.
"""
from datetime import date
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas import config
from finanzas.models import Cuenta


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


def sincronizar(session: Session, cliente: IndexaClient | None = None) -> list[Cuenta]:
    """Crea o actualiza una Cuenta de tipo inversión por cada cuenta de Indexa."""
    cliente = cliente or IndexaClient()
    actualizadas = []
    for c in cliente.cuentas():
        numero = c.get("account_number")
        if not numero:
            continue
        total = valor_total(cliente.cartera(numero))
        cuenta = session.scalar(
            select(Cuenta).where(Cuenta.origen == "indexa", Cuenta.id_externo == numero)
        )
        if cuenta is None:
            tipo_producto = c.get("type") or c.get("product") or "cuenta"
            cuenta = Cuenta(nombre=f"Indexa {tipo_producto} {numero}", entidad="Indexa Capital",
                            tipo="inversion", origen="indexa", id_externo=numero)
            session.add(cuenta)
        cuenta.saldo, cuenta.saldo_fecha = total, date.today()
        actualizadas.append(cuenta)
    session.commit()
    return actualizadas
