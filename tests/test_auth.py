import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from finanzas import auth, config
from finanzas.main import app

CLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CLIENT_ID = "123.apps.googleusercontent.com"


def token_google(email="yo@gmail.com", aud=CLIENT_ID, iss="https://accounts.google.com", verificado=True, exp=3600):
    return jwt.encode({"iss": iss, "aud": aud, "email": email, "email_verified": verificado,
                       "exp": int(time.time()) + exp}, CLAVE, algorithm="RS256")


@pytest.fixture
def con_login(monkeypatch):
    monkeypatch.setattr(config, "AUTH_REQUERIDA", True)
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(config, "EMAILS_PERMITIDOS", {"yo@gmail.com"})
    monkeypatch.setattr(config, "SESSION_SECRET", "x" * 40)
    monkeypatch.setattr(config, "CRON_SECRET", "secreto-cron")
    monkeypatch.setattr(auth, "_clave_google", lambda _t: CLAVE.public_key())


def test_sin_sesion_no_hay_datos(con_login):
    with TestClient(app) as c:
        assert c.get("/api/resumen").status_code == 401
        assert c.get("/api/declaraciones").status_code == 401
        assert c.get("/api/auth/estado").json() == {"requerida": True, "client_id": CLIENT_ID, "email": None}


def test_entrar_con_google(con_login):
    with TestClient(app) as c:
        r = c.post("/api/auth/google", json={"credential": token_google()})
        assert r.status_code == 200 and r.json()["email"] == "yo@gmail.com"
        assert c.get("/api/resumen").status_code == 200
        assert c.get("/api/auth/estado").json()["email"] == "yo@gmail.com"
        c.post("/api/auth/salir")
        assert c.get("/api/resumen").status_code == 401


def test_salir_en_todos_invalida_las_cookies_copiadas(con_login):
    with TestClient(app) as c:
        c.post("/api/auth/google", json={"credential": token_google()})
        copiada = c.cookies.get(auth.COOKIE)
        assert c.post("/api/auth/salir-en-todos").status_code == 200
        c.cookies.set(auth.COOKIE, copiada)
        assert c.get("/api/resumen").status_code == 401
        c.cookies.clear()
        c.post("/api/auth/google", json={"credential": token_google()})
        assert c.get("/api/resumen").status_code == 200


@pytest.mark.parametrize("token, codigo", [
    (lambda: token_google(email="otro@gmail.com"), 403),
    (lambda: token_google(aud="otra-app"), 401),
    (lambda: token_google(iss="https://malo.com"), 401),
    (lambda: token_google(verificado=False), 401),
    (lambda: token_google(exp=-10), 401),
])
def test_rechaza_tokens_malos(con_login, token, codigo):
    with TestClient(app) as c:
        assert c.post("/api/auth/google", json={"credential": token()}).status_code == codigo
        assert c.get("/api/resumen").status_code == 401


def test_cookie_falsificada(con_login):
    with TestClient(app) as c:
        falsa = jwt.encode({"sub": "yo@gmail.com", "exp": int(time.time()) + 60}, "otro-secreto" * 4, algorithm="HS256")
        c.cookies.set(auth.COOKIE, falsa)
        assert c.get("/api/resumen").status_code == 401


def test_cron(con_login):
    with TestClient(app) as c:
        assert c.get("/api/cron/sync").status_code == 401
        assert c.get("/api/cron/sync", headers={"Authorization": "Bearer otro"}).status_code == 401
        assert c.get("/api/cron/sync", headers={"Authorization": "Bearer secreto-cron"}).status_code == 200


def test_en_vercel_sin_configurar_no_abre(monkeypatch):
    monkeypatch.setattr(config, "AUTH_REQUERIDA", True)
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "")
    with TestClient(app) as c:
        assert c.get("/api/resumen").status_code == 503
