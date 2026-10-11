"""Ajustes guardados en la base de datos. Los secretos (claves de API) se cifran con SESSION_SECRET."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from finanzas import config
from finanzas.models import Ajuste

PREFIJO = "enc:"


def _fernet() -> Fernet:
    # En local sin SESSION_SECRET la base de datos está en tu ordenador; el cifrado es un extra.
    semilla = config.secreto(obligatorio=False).encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"ajustes:" + semilla).digest()))


def leer(s: Session, clave: str, defecto: str = "") -> str:
    a = s.get(Ajuste, clave)
    if a is None or not a.valor:
        return defecto
    if a.valor.startswith(PREFIJO):
        try:
            return _fernet().decrypt(a.valor[len(PREFIJO):].encode()).decode()
        except InvalidToken:  # cambió SESSION_SECRET: hay que volver a guardar la clave
            return defecto
    return a.valor


def guardar(s: Session, clave: str, valor: str, secreto: bool = False) -> None:
    if secreto and valor:
        valor = PREFIJO + _fernet().encrypt(valor.encode()).decode()
    a = s.get(Ajuste, clave) or Ajuste(clave=clave)
    a.valor = valor
    s.add(a)
    s.commit()


def oculto(valor: str) -> str | None:
    return f"…{valor[-4:]}" if valor else None
