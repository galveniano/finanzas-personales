import json
from datetime import date
from decimal import Decimal as D

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from finanzas import db, sync
from finanzas.categorizar import sembrar_categorias
from finanzas.integrations import enablebanking as eb
from finanzas.models import Cuenta, Movimiento

CLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = CLAVE.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                          serialization.NoEncryption()).decode()


def banco_falso(peticiones: list):
    def responder(req: httpx.Request):
        peticiones.append(req)
        token = req.headers["Authorization"].removeprefix("Bearer ")
        cab = jwt.get_unverified_header(token)
        datos = jwt.decode(token, CLAVE.public_key(), algorithms=["RS256"], audience="api.enablebanking.com")
        assert cab["kid"] == "app-123" and datos["iss"] == "enablebanking.com"
        ruta = req.url.path
        if ruta == "/aspsps":
            return httpx.Response(200, json={"aspsps": [
                {"name": "Sabadell Empresas", "country": "ES", "psu_types": ["business"]},
                {"name": "Sabadell", "country": "ES", "psu_types": ["business", "personal"]},
                {"name": "Santander", "country": "ES", "psu_types": ["personal"]}]})
        if ruta == "/auth":
            assert json.loads(req.content)["aspsp"] == {"name": "Sabadell", "country": "ES"}
            return httpx.Response(200, json={"url": "https://banco.example/login", "authorization_id": "a1"})
        if ruta == "/sessions":
            return httpx.Response(200, json={
                "session_id": "s1", "access": {"valid_until": "2027-04-01T00:00:00+00:00"},
                "accounts": [{"uid": "u1", "account_id": {"iban": "ES0000810000000000000001"},
                              "identification_hash": "h1", "name": "Cuenta"}]})
        if ruta == "/accounts/u1/balances":
            return httpx.Response(200, json={"balances": [
                {"balance_type": "CLBD", "balance_amount": {"amount": "2345.67", "currency": "EUR"}}]})
        if ruta == "/accounts/u1/transactions":
            if req.url.params.get("continuation_key") == "pag2":
                return httpx.Response(200, json={"transactions": [
                    {"entry_reference": "r3", "transaction_amount": {"amount": "45.20", "currency": "EUR"},
                     "credit_debit_indicator": "DBIT", "booking_date": "2026-09-03", "status": "BOOK",
                     "remittance_information": ["COMPRA TARJ. MERCADONA"]}]})
            return httpx.Response(200, json={"continuation_key": "pag2", "transactions": [
                {"entry_reference": "r1", "transaction_amount": {"amount": "2180.40", "currency": "EUR"},
                 "credit_debit_indicator": "CRDT", "booking_date": "2026-09-30", "status": "BOOK",
                 "remittance_information": ["NOMINA INDRA SISTEMAS"]},
                {"entry_reference": "r2", "transaction_amount": {"amount": "10", "currency": "EUR"},
                 "credit_debit_indicator": "DBIT", "booking_date": "2026-10-02", "status": "PDNG",
                 "remittance_information": ["PENDIENTE"]}]})
        return httpx.Response(404, json={"message": "no existe"})
    return responder


def test_flujo_enable_banking(monkeypatch):
    monkeypatch.setattr(eb.config, "ENABLE_BANKING_APP_ID", "app-123")
    monkeypatch.setattr(eb.config, "ENABLE_BANKING_KEY", "x.pem")
    db.init_db()
    s = db.SessionLocal()
    sembrar_categorias(s)
    # Cuenta creada antes a mano con el mismo IBAN: se reutiliza en vez de duplicarse
    s.add(Cuenta(nombre="Mi Sabadell", iban="ES0000810000000000000001"))
    s.commit()
    peticiones: list = []
    cliente = eb.EnableBankingClient(app_id="app-123", clave_privada=PEM, base_url="https://eb",
                                     transport=httpx.MockTransport(banco_falso(peticiones)))

    assert eb.iniciar_autorizacion(cliente) == "https://banco.example/login"
    code = eb.extraer_code("https://localhost:8000/sabadell/vuelta?state=x&code=abc123")
    assert code == "abc123"
    con = eb.completar_autorizacion(s, code, cliente)
    assert con.valida_hasta.date() == date(2027, 4, 1)

    r = sync.sincronizar_sabadell(s, cliente)
    assert r["ok"], r["mensaje"]
    cuenta = s.query(Cuenta).filter_by(nombre="Mi Sabadell").one()
    assert cuenta.origen == "enable_banking" and cuenta.saldo == D("2345.67")
    movs = s.query(Movimiento).filter_by(cuenta_id=cuenta.id).order_by(Movimiento.fecha).all()
    assert [m.importe for m in movs] == [D("-45.20"), D("2180.40")]  # el pendiente no entra
    assert movs[1].categoria.nombre == "Nómina"

    sync.sincronizar_sabadell(s, cliente)  # repetir no duplica
    assert s.query(Movimiento).filter_by(cuenta_id=cuenta.id).count() == 2
    s.close()


def test_extraer_code_rechaza_basura():
    import pytest
    with pytest.raises(eb.EnableBankingError):
        eb.extraer_code("esto no es un código")


def test_vuelta_del_banco_ensenya_el_error(monkeypatch):
    """Si algo inesperado falla al volver del banco, se vuelve a Conexiones con el motivo (no un 500)."""
    from fastapi.testclient import TestClient
    from finanzas.main import app

    def roto(s, code, cliente=None):
        raise KeyError("uid")
    monkeypatch.setattr(eb, "completar_autorizacion", roto)
    with TestClient(app) as c:
        r = c.get("/sabadell/vuelta?state=x&code=abc", follow_redirects=False)
        assert r.status_code == 307 and "sabadell_error=KeyError" in r.headers["location"]

    sincronizado = []
    monkeypatch.setattr(eb, "completar_autorizacion", lambda s, code, cliente=None: None)
    monkeypatch.setattr(sync, "sincronizar_sabadell", lambda s, cliente=None: sincronizado.append(1))
    with TestClient(app) as c:
        r = c.get("/sabadell/vuelta?state=x&code=abc", follow_redirects=False)
        assert r.headers["location"].endswith("sabadell=ok") and sincronizado
