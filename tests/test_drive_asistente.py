import json

import httpx
import pytest
from fastapi.testclient import TestClient

from finanzas import config, documentos
from finanzas.main import app

TEXTOS = {
    "f1": "FACTURA Nº 7 Fecha 1/09/2026 Cliente: ACME Consultoría Net 1000 IVA 21% Retención 15%",
    "f2": "Google One factura 2 mar 2026 Subtotal 18,17 IVA 21% Total 21,99",
    "f3": ("INFORMACIÓN DE LA PRESENTACIÓN DE LA DECLARACIÓN\nModelo 130\nPresentación realizada el: 20-07-2026\n"
           "Expediente/Referencia: 202613000000000X\nCódigo Seguro de Verificación: ZZZZZZZZZZZZ\n"
           "Número de justificante: 1300000000001\nINGRESAR\nIMPORTE: 312,40\n"
           "Agencia Tributaria\nEjercicio Período\n2026 2T\n"),
}
EXTRAIDO = {
    "f1": {"tipo": "emitida", "numero": "7", "fecha": "2023-09-01", "contraparte": "ACME", "base": 1000,
           "tipo_iva": 21, "tipo_retencion": 15, "total": 1060, "concepto": "Consultoría"},
    "f2": {"tipo": "recibida", "fecha": "2023-03-02", "contraparte": "Google", "base": 18.17, "tipo_iva": 21,
           "total": 21.99, "categoria_gasto": "software", "concepto": "Google One"},
}


def falso(peticion: httpx.Request) -> httpx.Response:
    url = str(peticion.url)
    if "googleapis.com/drive/v3/files/" in url:
        fid = peticion.url.path.rsplit("/", 1)[1]
        return httpx.Response(200, content=fid.encode())  # el "PDF" es el id; texto_pdf está simulado
    if "googleapis.com/drive/v3/files" in url:
        assert peticion.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json={"files": [
            {"id": f, "name": f"{f}.pdf", "modifiedTime": "2026-09-01T00:00:00Z", "webViewLink": "https://x"} for f in TEXTOS]})
    if "api.anthropic.com" in url:
        cuerpo = json.loads(peticion.content)
        texto = cuerpo["messages"][-1]["content"]
        if "tools" in cuerpo and cuerpo.get("tool_choice", {}).get("name") == "registrar_documento":
            fid = "f1" if "ACME" in texto else "f2"
            return httpx.Response(200, json={"stop_reason": "tool_use", "content": [
                {"type": "tool_use", "id": "t1", "name": "registrar_documento", "input": EXTRAIDO[fid]}]})
        # Asistente: primero consulta Hacienda, luego responde
        if isinstance(texto, str):
            return httpx.Response(200, json={"stop_reason": "tool_use", "content": [
                {"type": "tool_use", "id": "t2", "name": "hacienda", "input": {}}]})
        return httpx.Response(200, json={"stop_reason": "end_turn", "content": [
            {"type": "text", "text": "Este año has pagado 312,40 € en el 130."}]})
    return httpx.Response(404)


@pytest.fixture
def entorno(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(documentos, "texto_pdf", lambda contenido, max_paginas=4: [TEXTOS[contenido.decode()]])
    transporte = httpx.MockTransport(falso)
    original = httpx.Client.__init__

    def con_mock(self, *a, **k):
        if not isinstance(self, TestClient):  # solo las llamadas a Google y Anthropic
            k["transport"] = transporte
        original(self, *a, **k)
    monkeypatch.setattr(httpx.Client, "__init__", con_mock)


def test_importar_drive(entorno):
    with TestClient(app) as c:
        r = c.post("/api/drive/importar", json={"access_token": "tok"}).json()
        assert {p["estado"] for p in r["procesados"]} == {"importado", "pendiente"} and r["quedan"] == 0
        a = c.get("/api/autonomo?anio=2023").json()
        assert any(f["numero"] == "7" and f["base"] == 1000 for f in a["facturas"])
        assert any(d["modelo"] == "130" and d["importe"] == 312.4 for d in c.get("/api/declaraciones").json()["declaraciones"])

        docs = c.get("/api/drive/documentos").json()["documentos"]
        pendiente = next(d for d in docs if d["estado"] == "pendiente")
        assert c.post(f"/api/drive/documentos/{pendiente['id']}/gasto", json={"deducible_pct": 100}).status_code == 200
        assert any(g["proveedor"] == "Google" for g in c.get("/api/autonomo?anio=2023").json()["gastos"])

        # Una segunda importación no vuelve a leer lo mismo
        assert c.post("/api/drive/importar", json={"access_token": "tok"}).json()["procesados"] == []


def test_asistente(entorno):
    with TestClient(app) as c:
        r = c.post("/api/asistente", json={"mensajes": [{"role": "user", "content": "¿Cuánto he pagado de 130?"}]}).json()
        assert r["consultas"] == ["hacienda"] and "312,40" in r["respuesta"]


def test_sin_clave(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    with TestClient(app) as c:
        assert c.post("/api/asistente", json={"mensajes": [{"role": "user", "content": "hola"}]}).status_code == 400
        assert c.post("/api/drive/importar", json={"access_token": "x"}).status_code == 400
