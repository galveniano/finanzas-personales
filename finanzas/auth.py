"""Inicio de sesión con Google para cuando la app está publicada (Vercel).

El frontal obtiene de Google un ID token (Google Identity Services). Aquí se comprueba su firma
con las claves públicas de Google, que va dirigido a nuestro GOOGLE_CLIENT_ID y que el email está
en EMAILS_PERMITIDOS. Si todo cuadra se guarda una cookie de sesión firmada con SESSION_SECRET.
"""
import time

import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from finanzas import config

COOKIE = "finanzas_sesion"
DURACION = 30 * 24 * 3600  # 30 días
GOOGLE_CERTS = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISS = ("accounts.google.com", "https://accounts.google.com")

router = APIRouter(prefix="/api/auth")
_jwks: jwt.PyJWKClient | None = None


def _clave_google(token: str):
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(GOOGLE_CERTS, cache_keys=True)
    return _jwks.get_signing_key_from_jwt(token).key


def verificar_google(token: str, obtener_clave=None) -> str:
    """Devuelve el email del ID token de Google si es válido y está permitido."""
    try:
        clave = (obtener_clave or _clave_google)(token)
        datos = jwt.decode(token, clave, algorithms=["RS256"], audience=config.GOOGLE_CLIENT_ID,
                           options={"require": ["exp", "iss", "aud", "email"]})
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"No se pudo verificar el inicio de sesión de Google: {e}")
    if datos.get("iss") not in GOOGLE_ISS or not datos.get("email_verified"):
        raise HTTPException(401, "La cuenta de Google no es válida")
    email = str(datos["email"]).lower()
    if email not in config.EMAILS_PERMITIDOS:
        raise HTTPException(403, f"{email} no tiene acceso a esta app")
    return email


def _secreto() -> str:
    if len(config.SESSION_SECRET) < 32:
        raise HTTPException(503, "Falta SESSION_SECRET (al menos 32 caracteres) en la configuración")
    return config.SESSION_SECRET


CLAVE_VERSION = "sesion_version"


def _version() -> str:
    """Al cerrar sesión en todos los dispositivos cambia la versión y las cookies anteriores dejan de valer."""
    from finanzas import ajustes, db
    if db.engine is None:
        return ""
    db.asegurar_tablas()
    with db.SessionLocal() as s:
        return ajustes.leer(s, CLAVE_VERSION, "")


def crear_sesion(email: str) -> str:
    ahora = int(time.time())
    return jwt.encode({"sub": email, "iat": ahora, "exp": ahora + DURACION, "v": _version()}, _secreto(),
                      algorithm="HS256")


def email_de_sesion(request: Request) -> str | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        datos = jwt.decode(token, _secreto(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if datos.get("v", "") != _version():
        return None
    email = datos["sub"]
    # Si quitas un email de EMAILS_PERMITIDOS, su sesión deja de valer
    return email if email in config.EMAILS_PERMITIDOS else None


def requiere_sesion(request: Request) -> None:
    """Dependencia de todas las rutas con datos."""
    if not config.AUTH_REQUERIDA:
        return
    if not config.GOOGLE_CLIENT_ID or not config.EMAILS_PERMITIDOS:
        raise HTTPException(503, "Falta configurar GOOGLE_CLIENT_ID y EMAILS_PERMITIDOS")
    if email_de_sesion(request) is None:
        raise HTTPException(401, "Inicia sesión")


@router.get("/estado")
def estado(request: Request):
    if not config.AUTH_REQUERIDA:
        return {"requerida": False, "email": None, "client_id": None}
    return {"requerida": True, "client_id": config.GOOGLE_CLIENT_ID or None,
            "email": email_de_sesion(request) if config.SESSION_SECRET else None}


class CredencialIn(BaseModel):
    credential: str


@router.post("/google")
def entrar(datos: CredencialIn, response: Response):
    if not config.GOOGLE_CLIENT_ID or not config.EMAILS_PERMITIDOS:
        raise HTTPException(503, "Falta configurar GOOGLE_CLIENT_ID y EMAILS_PERMITIDOS")
    email = verificar_google(datos.credential)
    response.set_cookie(COOKIE, crear_sesion(email), max_age=DURACION, httponly=True,
                        secure=config.EN_VERCEL, samesite="lax", path="/")
    return {"email": email}


@router.post("/salir")
def salir(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.post("/salir-en-todos")
def salir_en_todos(request: Request, response: Response):
    """Invalida todas las sesiones abiertas (otros dispositivos, o una cookie que alguien haya copiado)."""
    import secrets
    from finanzas import ajustes, db
    requiere_sesion(request)
    with db.SessionLocal() as s:
        ajustes.guardar(s, CLAVE_VERSION, secrets.token_hex(8))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}
