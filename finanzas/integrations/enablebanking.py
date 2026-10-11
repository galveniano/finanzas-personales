"""Sincronización de cuentas bancarias (Banco Sabadell) vía Enable Banking (PSD2).

Enable Banking permite, gratis y en modo "restringido", leer las cuentas propias del
titular de la aplicación. Flujo:

1. `iniciar_autorizacion()` devuelve una URL del banco. Ahí entras con tus claves de Sabadell.
2. El banco te devuelve a `ENABLE_BANKING_REDIRECT_URL?code=...`.
3. `completar_autorizacion(code)` crea la sesión y guarda las cuentas autorizadas.
4. `sincronizar()` trae saldos y movimientos de esas cuentas mientras el consentimiento siga vivo.

Documentación: https://enablebanking.com/docs/api/reference/
"""
import hashlib
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finanzas import config
from finanzas.fechas import ahora_utc
from finanzas.categorizar import categorizar
from finanzas.models import ConexionBancaria, Cuenta, Movimiento

CONSENTIMIENTO_DIAS = 180
DIAS_PRIMERA_CARGA = 365
TRAMO_DIAS = 60  # el histórico se trae en tramos de 60 días
# Vercel corta las peticiones a los 60 s: se deja margen y lo que falte se trae en la siguiente sincronización
SEGUNDOS_MAXIMOS = 40


class EnableBankingError(Exception):
    pass


def configurado() -> bool:
    return bool(config.ENABLE_BANKING_APP_ID and config.ENABLE_BANKING_KEY)


def _leer_clave(valor: str) -> str:
    """La clave puede ser la ruta al .pem o su contenido (en Vercel va en una variable de entorno,
    a veces con los saltos de línea escritos como \\n)."""
    if "-----BEGIN" in valor:
        return valor.replace("\\n", "\n")
    ruta = Path(valor)
    if not ruta.is_absolute():
        ruta = config.ROOT / ruta
    if not valor or not ruta.is_file():
        raise EnableBankingError(f"No encuentro la clave privada de Enable Banking en {ruta}")
    return ruta.read_text()


class EnableBankingClient:
    def __init__(self, app_id: str | None = None, clave_privada: str | None = None,
                 base_url: str | None = None, transport=None):
        self.app_id = app_id or config.ENABLE_BANKING_APP_ID
        if clave_privada is None:
            if not self.app_id:
                raise EnableBankingError("Falta configurar Enable Banking: ENABLE_BANKING_APP_ID en .env")
            clave_privada = _leer_clave(config.ENABLE_BANKING_KEY)
        self.clave_privada = clave_privada
        self.http = httpx.Client(base_url=base_url or config.ENABLE_BANKING_BASE_URL,
                                 timeout=30, transport=transport)

    def _token(self) -> str:
        ahora = int(time.time())
        return jwt.encode(
            {"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": ahora, "exp": ahora + 3600},
            self.clave_privada, algorithm="RS256", headers={"kid": self.app_id},
        )

    def _peticion(self, metodo: str, ruta: str, **kw) -> dict:
        r = self.http.request(metodo, ruta, headers={"Authorization": f"Bearer {self._token()}"}, **kw)
        if r.status_code >= 400:
            try:
                detalle = r.json().get("message") or r.text
            except ValueError:
                detalle = r.text
            raise EnableBankingError(f"Enable Banking respondió {r.status_code}: {detalle}")
        return r.json()

    def nombre_banco(self, banco: str, pais: str = "ES") -> str:
        """Nombre exacto del banco en Enable Banking (si no coincide responde 422 "Wrong ASPSP name").
        Busca en su lista: primero igual, luego que contenga la palabra clave (\"Sabadell\")."""
        try:
            lista = self._peticion("GET", "/aspsps", params={"country": pais}).get("aspsps", [])
        except EnableBankingError:
            return banco
        personales = [a for a in lista if "personal" in (a.get("psu_types") or ["personal"])]
        clave = banco.lower().replace("banco ", "").strip()
        for candidatos in (
            [a for a in personales if a.get("name", "").lower() == banco.lower()],
            [a for a in personales if clave in a.get("name", "").lower()],
        ):
            if candidatos:
                return min(candidatos, key=lambda a: len(a["name"]))["name"]  # el más corto: no "Sabadell Empresas"
        raise EnableBankingError(f"Enable Banking no tiene ningún banco llamado {banco} en {pais}")

    def iniciar(self, banco: str, redirect_url: str, estado: str) -> str:
        banco = self.nombre_banco(banco)
        valida_hasta = datetime.now(timezone.utc) + timedelta(days=CONSENTIMIENTO_DIAS)
        datos = self._peticion("POST", "/auth", json={
            "access": {"valid_until": valida_hasta.isoformat(timespec="seconds")},
            "aspsp": {"name": banco, "country": "ES"},
            "state": estado,
            "redirect_url": redirect_url,
            "psu_type": "personal",
            "language": "es",
        })
        return datos["url"]

    def crear_sesion(self, code: str) -> dict:
        return self._peticion("POST", "/sessions", json={"code": code})

    def saldos(self, uid: str) -> list[dict]:
        return self._peticion("GET", f"/accounts/{uid}/balances").get("balances", [])

    def movimientos(self, uid: str, desde: date, hasta: date | None = None) -> list[dict]:
        resultado, clave = [], None
        while True:
            params = {"date_from": desde.isoformat()}
            if hasta:
                params["date_to"] = hasta.isoformat()
            if clave:
                params["continuation_key"] = clave
            datos = self._peticion("GET", f"/accounts/{uid}/transactions", params=params)
            resultado.extend(datos.get("transactions", []))
            clave = datos.get("continuation_key")
            if not clave:
                return resultado


# --- Conversión de datos ----------------------------------------------------

def _iban(cuenta_api: dict) -> str:
    ident = cuenta_api.get("account_id") or {}
    return (ident.get("iban") or ident.get("other", {}).get("identification") or "").replace(" ", "").upper()


def _importe(tx: dict) -> Decimal:
    valor = Decimal(str(tx["transaction_amount"]["amount"])).quantize(Decimal("0.01"))
    return -abs(valor) if tx.get("credit_debit_indicator") in ("DBIT", "DBTR") else abs(valor)


def _concepto(tx: dict) -> str:
    lineas = tx.get("remittance_information") or []
    if isinstance(lineas, str):
        lineas = [lineas]
    texto = " ".join(l.strip() for l in lineas if l).strip()
    if not texto:
        contraparte = (tx.get("creditor") or tx.get("debtor") or {}).get("name", "")
        texto = contraparte or tx.get("bank_transaction_code", {}).get("description", "") or "Movimiento"
    return texto


def _huella(tx: dict) -> str:
    ident = tx.get("entry_reference") or tx.get("transaction_id")
    if not ident:
        base = f"{tx.get('booking_date')}|{tx['transaction_amount']['amount']}|{_concepto(tx)}"
        ident = hashlib.sha256(base.encode()).hexdigest()[:24]
    return f"eb:{ident}"[:64]


def _saldo_principal(saldos: list[dict]) -> Decimal | None:
    """Prefiere el saldo contable o disponible (CLBD, ITAV, CLAV...)."""
    preferencia = ["CLBD", "ITBD", "XPCD", "ITAV", "CLAV", "OPBD"]
    por_tipo = {s.get("balance_type"): s for s in saldos}
    for t in preferencia:
        if t in por_tipo:
            return Decimal(str(por_tipo[t]["balance_amount"]["amount"])).quantize(Decimal("0.01"))
    if saldos:
        return Decimal(str(saldos[0]["balance_amount"]["amount"])).quantize(Decimal("0.01"))
    return None


# --- Flujo ------------------------------------------------------------------

def nuevo_estado() -> str:
    """Valor aleatorio que viaja al banco y vuelve; la app lo guarda en una cookie para comprobar
    que la vuelta es de una conexión que empezaste tú."""
    return secrets.token_urlsafe(16)


def iniciar_autorizacion(cliente: EnableBankingClient | None = None, estado: str | None = None) -> str:
    cliente = cliente or EnableBankingClient()
    return cliente.iniciar(config.BANCO, config.ENABLE_BANKING_REDIRECT_URL, estado or nuevo_estado())


def extraer_estado(texto: str) -> str | None:
    """El state de la URL de vuelta que se pega a mano, si viene."""
    if "state=" not in texto:
        return None
    return parse_qs(urlparse(texto.strip()).query).get("state", [None])[0]


def extraer_code(texto: str) -> str:
    """Acepta el code a pelo o la URL completa a la que te devolvió el banco."""
    texto = texto.strip()
    if "code=" in texto:
        code = parse_qs(urlparse(texto).query).get("code", [""])[0]
        if code:
            return code
    if not texto or " " in texto:
        raise EnableBankingError("No encuentro el código de autorización en lo que has pegado.")
    return texto


def _id_cuenta(cta: dict) -> str:
    """identification_hash identifica la cuenta entre sesiones; si no cabe en la columna, su sha256."""
    h = cta.get("identification_hash") or ""
    return h if len(h) <= 80 else hashlib.sha256(h.encode()).hexdigest()


def completar_autorizacion(session: Session, code: str,
                           cliente: EnableBankingClient | None = None) -> ConexionBancaria:
    cliente = cliente or EnableBankingClient()
    datos = cliente.crear_sesion(code)
    valida_hasta = None
    if datos.get("access", {}).get("valid_until"):
        valida_hasta = datetime.fromisoformat(datos["access"]["valid_until"].replace("Z", "+00:00"))
        valida_hasta = valida_hasta.astimezone(timezone.utc).replace(tzinfo=None)
    for anterior in session.scalars(select(ConexionBancaria).where(ConexionBancaria.activa)):
        anterior.activa = False
    con = ConexionBancaria(banco=config.BANCO, session_id=datos["session_id"], valida_hasta=valida_hasta)
    session.add(con)
    session.flush()
    for cta in datos.get("accounts", []):
        iban = _iban(cta)
        cuenta = None
        if iban:  # una cuenta creada a mano con el mismo IBAN (aunque lo escribieras con espacios) es esta
            cuenta = session.scalar(select(Cuenta).where(func.upper(func.replace(Cuenta.iban, " ", "")) == iban))
        if cuenta is None:
            cuenta = session.scalar(select(Cuenta).where(
                Cuenta.origen == "enable_banking", Cuenta.id_externo == _id_cuenta(cta)
            ))
        if cuenta is None:
            nombre = cta.get("name") or cta.get("product") or "Cuenta"
            cuenta = Cuenta(nombre=f"{config.BANCO.replace('Banco ', '')} {iban[-4:] or nombre}"[:120],
                            entidad=config.BANCO)
            session.add(cuenta)
        if iban:
            cuenta.iban = iban
        cuenta.activa = True  # si estaba oculta, al autorizarla otra vez en el banco vuelve a verse
        cuenta.origen = "enable_banking"
        cuenta.id_externo = _id_cuenta(cta) or cuenta.id_externo
        cuenta.uid_externo = cta["uid"]
        cuenta.conexion_id = con.id
    session.commit()
    return con


def conexion_activa(session: Session) -> ConexionBancaria | None:
    con = session.scalar(select(ConexionBancaria).where(ConexionBancaria.activa)
                         .order_by(ConexionBancaria.id.desc()))
    if con and con.valida_hasta and con.valida_hasta < ahora_utc():
        return None
    return con


def _guardar_movimientos(session: Session, cuenta: Cuenta, txs: list[dict]) -> int:
    existentes = set(session.scalars(select(Movimiento.huella).where(Movimiento.cuenta_id == cuenta.id)))
    nuevos = 0
    for tx in txs:
        if tx.get("status") not in (None, "BOOK"):
            continue  # solo movimientos contabilizados
        h = _huella(tx)
        if h in existentes:
            continue
        fecha = date.fromisoformat(tx.get("booking_date") or tx.get("transaction_date") or tx["value_date"])
        concepto = _concepto(tx)
        saldo_tras = (tx.get("balance_after_transaction") or {}).get("balance_amount", {}).get("amount")
        session.add(Movimiento(
            cuenta_id=cuenta.id, fecha=fecha, concepto=concepto, importe=_importe(tx),
            fecha_valor=date.fromisoformat(tx["value_date"]) if tx.get("value_date") else None,
            saldo=Decimal(str(saldo_tras)) if saldo_tras is not None else None,
            huella=h, categoria_id=categorizar(session, concepto),
        ))
        existentes.add(h)
        nuevos += 1
    return nuevos


def sincronizar(session: Session, cliente: EnableBankingClient | None = None,
                segundos: float = SEGUNDOS_MAXIMOS) -> dict:
    """Saldos primero; luego los movimientos recientes y, con el tiempo que quede, el histórico hacia atrás
    por tramos. Cada paso se guarda en cuanto termina, así un corte por tiempo no pierde lo ya traído."""
    con = conexion_activa(session)
    if con is None:
        raise EnableBankingError("No hay conexión con el banco o ha caducado. Vuelve a conectar Sabadell.")
    cliente = cliente or EnableBankingClient()
    limite = time.monotonic() + segundos
    hoy = date.today()
    cuentas = session.scalars(select(Cuenta).where(Cuenta.conexion_id == con.id, Cuenta.activa)).all()
    for cuenta in cuentas:
        saldo = _saldo_principal(cliente.saldos(cuenta.uid_externo))
        if saldo is not None:
            cuenta.saldo, cuenta.saldo_fecha = saldo, hoy
        cuenta.ultima_sincronizacion = ahora_utc()
    session.commit()

    nuevos = 0
    for cuenta in cuentas:  # lo reciente
        if time.monotonic() > limite:
            break
        ultimo = session.scalar(select(Movimiento.fecha).where(Movimiento.cuenta_id == cuenta.id)
                                .order_by(Movimiento.fecha.desc()).limit(1))
        desde = (ultimo - timedelta(days=5)) if ultimo else hoy - timedelta(days=TRAMO_DIAS)
        nuevos += _guardar_movimientos(session, cuenta, cliente.movimientos(cuenta.uid_externo, desde))
        if cuenta.historico_desde is None or cuenta.historico_desde > desde:
            cuenta.historico_desde = desde
        session.commit()

    objetivo = hoy - timedelta(days=DIAS_PRIMERA_CARGA)
    while time.monotonic() < limite:  # el histórico, de tramo en tramo y de cuenta en cuenta
        pendientes = [c for c in cuentas if c.historico_desde and c.historico_desde > objetivo]
        if not pendientes:
            break
        for cuenta in pendientes:
            if time.monotonic() > limite:
                break
            hasta = cuenta.historico_desde - timedelta(days=1)
            desde = max(hasta - timedelta(days=TRAMO_DIAS - 1), objetivo)
            nuevos += _guardar_movimientos(session, cuenta, cliente.movimientos(cuenta.uid_externo, desde, hasta))
            cuenta.historico_desde = desde
            session.commit()
    falta = any(c.historico_desde is None or c.historico_desde > objetivo for c in cuentas)
    return {"cuentas": len(cuentas), "movimientos_nuevos": nuevos, "historico_pendiente": falta}
