import json

import httpx
import pytest
from fastapi.testclient import TestClient

from finanzas import config, db, documentos, ia
from finanzas.integrations import drive
from finanzas.main import app
from finanzas.models import Ajuste, DocumentoDrive

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
# Lo que ve Drive en cada test (se puede cambiar el modifiedTime) y si la IA debe fallar
DRIVE = {"modificado": "2026-09-01T00:00:00Z"}
FALLOS = {"ia": False}


def pide_documento(cuerpo: dict) -> bool:
    return any(t["name"] == "registrar_documento" for t in cuerpo.get("tools", []))


def falso(peticion: httpx.Request) -> httpx.Response:
    url = str(peticion.url)
    if "googleapis.com/drive/v3/files/" in url:
        fid = peticion.url.path.rsplit("/", 1)[1]
        return httpx.Response(200, content=fid.encode())  # el "PDF" es el id; texto_pdf está simulado
    if "googleapis.com/drive/v3/files" in url:
        assert peticion.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json={"files": [
            {"id": f, "name": f"{f}.pdf", "modifiedTime": DRIVE["modificado"], "webViewLink": "https://x"} for f in TEXTOS]})
    if "api.anthropic.com" in url:
        if FALLOS["ia"]:
            return httpx.Response(500, json={"error": {"message": "caído"}})
        cuerpo = json.loads(peticion.content)
        texto = cuerpo["messages"][-1]["content"]
        if pide_documento(cuerpo):
            # Los modelos actuales no admiten forzar la herramienta: se pide en el sistema y va con tool_choice auto
            assert cuerpo["tool_choice"]["type"] == "auto" and "registrar_documento" in cuerpo["system"]
            fid = "f1" if "ACME" in texto else "f2"
            return httpx.Response(200, json={"stop_reason": "tool_use", "content": [
                {"type": "tool_use", "id": "t1", "name": "registrar_documento", "input": EXTRAIDO[fid]}]})
        # Asistente: primero consulta Hacienda, luego responde
        if isinstance(texto, str):
            return httpx.Response(200, json={"stop_reason": "tool_use", "content": [
                {"type": "tool_use", "id": "t2", "name": "hacienda", "input": {}}]})
        return httpx.Response(200, json={"stop_reason": "end_turn", "content": [
            {"type": "text", "text": "Este año has pagado 312,40 € en el 130."}]})
    if "api.openai.com" in url:
        return falso_openai(peticion)
    return httpx.Response(404)


def falso_openai(peticion: httpx.Request) -> httpx.Response:
    assert peticion.headers["authorization"] == "Bearer sk-openai"
    cuerpo = json.loads(peticion.content)
    assert all(h["type"] == "function" and "parameters" in h["function"] for h in cuerpo.get("tools", []))

    def llamada(nombre, args):
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": nombre, "arguments": json.dumps(args)}}]}}]})

    if cuerpo.get("tool_choice", {}).get("function", {}).get("name") == "registrar_documento":
        texto = cuerpo["messages"][-1]["content"]
        return llamada("registrar_documento", EXTRAIDO["f1" if "ACME" in texto else "f2"])
    if cuerpo["messages"][-1]["role"] == "user" and "tools" in cuerpo:
        assert cuerpo["max_completion_tokens"] == ia.MAX_TOKENS
        return llamada("hacienda", {})
    respuesta = "OK" if "tools" not in cuerpo else "Este año has pagado 312,40 € en el 130."
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": respuesta}}]})


def _limpiar():
    with db.SessionLocal() as s:
        s.query(Ajuste).delete()
        s.query(DocumentoDrive).delete()
        s.commit()


@pytest.fixture(autouse=True)
def sin_ajustes(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    DRIVE["modificado"], FALLOS["ia"] = "2026-09-01T00:00:00Z", False
    with TestClient(app):
        _limpiar()
    yield
    _limpiar()


@pytest.fixture
def solo_drive(monkeypatch):
    """Google y los modelos simulados, sin clave de IA."""
    monkeypatch.setattr(documentos, "texto_pdf", lambda contenido, max_paginas=4: [TEXTOS[contenido.decode()]])
    transporte = httpx.MockTransport(falso)
    original = httpx.Client.__init__

    def con_mock(self, *a, **k):
        if not isinstance(self, TestClient):  # solo las llamadas a Google y a los modelos
            k["transport"] = transporte
        original(self, *a, **k)
    monkeypatch.setattr(httpx.Client, "__init__", con_mock)


@pytest.fixture
def entorno(solo_drive, monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test")


def importar(c):
    return c.post("/api/drive/importar", json={"access_token": "tok"}).json()


def estados(c) -> dict[str, dict]:
    return {d["nombre"]: d for d in c.get("/api/drive/documentos").json()["documentos"]}


def test_importar_drive(entorno):
    with TestClient(app) as c:
        r = importar(c)
        assert {p["estado"] for p in r["procesados"]} == {"importado", "pendiente"} and r["quedan"] == 0
        a = c.get("/api/autonomo?anio=2023").json()
        assert any(f["numero"] == "7" and f["base"] == 1000 for f in a["facturas"])
        assert any(d["modelo"] == "130" and d["importe"] == 312.4 for d in c.get("/api/declaraciones").json()["declaraciones"])

        d = c.get("/api/drive/documentos").json()
        assert "google_client_id" not in d  # ahora sale de /auth/estado
        pendiente = next(x for x in d["documentos"] if x["estado"] == "pendiente")
        assert pendiente["datos"]["total"] == 21.99 and pendiente["datos"]["categoria_gasto"] == "software"
        assert c.post(f"/api/drive/documentos/{pendiente['id']}/gasto", json={"deducible_pct": 100}).status_code == 200
        assert any(g["proveedor"] == "Google" for g in c.get("/api/autonomo?anio=2023").json()["gastos"])

        # Una segunda importación no vuelve a leer lo mismo
        assert importar(c)["procesados"] == []

        # Si el fichero cambia en Drive, lo ya apuntado (factura o gasto) no vuelve a «pendiente»
        DRIVE["modificado"] = "2026-09-02T00:00:00Z"
        r = importar(c)
        assert {p["nombre"] for p in r["procesados"]} == {"f1.pdf", "f2.pdf", "f3.pdf"}
        assert estados(c)["f2.pdf"]["estado"] == "importado" and estados(c)["f1.pdf"]["estado"] == "importado"
        assert estados(c)["f2.pdf"]["revisado"] is not None


def test_aeat_sin_clave_de_ia(solo_drive):
    """Sin clave de IA se importan igual los justificantes de Hacienda; las facturas esperan a la clave."""
    with TestClient(app) as c:
        r = importar(c)
        assert r["quedan"] == 0 and len(r["procesados"]) == 3
        docs = estados(c)
        assert docs["f3.pdf"]["estado"] == "importado" and docs["f3.pdf"]["mensaje"] == "Modelo 130 2T 2026"
        for f in ("f1.pdf", "f2.pdf"):
            assert docs[f]["estado"] == "pendiente" and docs[f]["mensaje"].startswith(drive.SIN_CLAVE)
        # Lo que no se ha leído no se puede apuntar como gasto
        assert c.post(f"/api/drive/documentos/{docs['f1.pdf']['id']}/gasto", json={"deducible_pct": 100}).status_code == 400
        assert importar(c)["procesados"] == []  # siguen esperando, no se reintentan sin clave

        # Al poner la clave, la siguiente importación lee las que esperaban
        c.put("/api/ajustes/ia", json={"proveedor": "anthropic", "clave": "sk-test"})
        r = importar(c)
        assert {p["nombre"] for p in r["procesados"]} == {"f1.pdf", "f2.pdf"}
        docs = estados(c)
        assert docs["f1.pdf"]["estado"] == "importado" and docs["f2.pdf"]["estado"] == "pendiente"
        assert docs["f2.pdf"]["mensaje"].startswith("Factura de Google")


def test_errores_no_se_reprocesan_y_volver_a_leer(entorno):
    with TestClient(app) as c:
        FALLOS["ia"] = True
        r = importar(c)
        assert {p["estado"] for p in r["procesados"]} == {"error", "importado"}  # el justificante no necesita IA
        FALLOS["ia"] = False
        assert importar(c)["procesados"] == []  # un error no se reintenta en cada importación
        docs = estados(c)
        assert docs["f1.pdf"]["estado"] == "error" and "500" in docs["f1.pdf"]["mensaje"]

        r = c.post(f"/api/drive/documentos/{docs['f1.pdf']['id']}/releer", json={"access_token": "tok"})
        assert r.status_code == 200 and r.json()["estado"] == "importado" and r.json()["datos"]["numero"] == "7"
        assert c.post("/api/drive/documentos/99999/releer", json={"access_token": "tok"}).status_code == 404

        # Si cambia en Drive, un documento con error sí se vuelve a leer
        DRIVE["modificado"] = "2026-09-03T00:00:00Z"
        assert estados(c)["f2.pdf"]["estado"] == "error"
        importar(c)
        assert estados(c)["f2.pdf"]["estado"] == "pendiente"


def test_desde_no_valido(entorno):
    with TestClient(app) as c:
        r = c.post("/api/drive/importar", json={"access_token": "tok", "desde": "ayer"})
        assert r.status_code == 400 and "desde" in r.json()["detail"]


def test_asistente(entorno):
    with TestClient(app) as c:
        r = c.post("/api/asistente", json={"mensajes": [{"role": "user", "content": "¿Cuánto he pagado de 130?"}]}).json()
        assert r["consultas"] == ["hacienda"] and "312,40" in r["respuesta"]


def test_sin_clave():
    with TestClient(app) as c:
        assert c.post("/api/asistente", json={"mensajes": [{"role": "user", "content": "hola"}]}).status_code == 400


def test_titular_de_las_facturas(monkeypatch):
    """El prompt de lectura usa tu nombre y NIF de Datos de facturación; el entorno solo si no están."""
    monkeypatch.setattr(config, "NOMBRE_TITULAR", "Entorno")
    monkeypatch.setattr(config, "NIF_TITULAR", "00000000T")
    with TestClient(app) as c:
        assert documentos.titular(None) == "Entorno, 00000000T"
        with db.SessionLocal() as s:
            assert documentos.titular(s) == "Entorno, 00000000T"
        c.put("/api/facturacion/emisor", json={"nombre": "Ana Ejemplo", "nif": "12345678 z"})
        with db.SessionLocal() as s:
            assert documentos.titular(s) == "Ana Ejemplo, 12345678Z"
            assert "Ana Ejemplo" in documentos._prompt(documentos.titular(s))
        c.put("/api/facturacion/emisor", json={"nombre": "", "nif": ""})


def test_openai_desde_la_app(entorno):
    """Con la clave guardada desde Ajustes, el asistente usa OpenAI aunque haya clave de Anthropic en el entorno."""
    with TestClient(app) as c:
        r = c.put("/api/ajustes/ia", json={"proveedor": "openai", "clave": "sk-openai"}).json()
        assert r["proveedor"] == "openai" and r["disponible"] and r["modelo"] == "gpt-5.4-mini"
        assert r["proveedores"]["openai"]["clave"] == "…enai" and r["proveedores"]["openai"]["origen_clave"] == "app"
        assert "sk-openai" not in json.dumps(r)
        with db.SessionLocal() as s:  # cifrada en la base de datos
            assert s.get(Ajuste, "openai_api_key").valor.startswith("enc:")

        assert c.post("/api/ajustes/ia/probar").json()["respuesta"] == "OK"
        r = c.post("/api/asistente", json={"mensajes": [{"role": "user", "content": "¿Cuánto he pagado de 130?"}]}).json()
        assert r["proveedor"] == "OpenAI" and r["consultas"] == ["hacienda"] and "312,40" in r["respuesta"]
        assert c.get("/api/asistente/estado").json()["proveedor"] == "openai"

        with db.SessionLocal() as s:  # la lectura de facturas también va por OpenAI
            cfg = ia.configuracion(s)
        leido = documentos.interpretar([TEXTOS["f1"]], "f1.pdf", cfg)
        assert leido.tipo == "emitida" and leido.datos["base"] == 1000

        # Cambiar el modelo y borrar la clave
        r = c.put("/api/ajustes/ia", json={"proveedor": "openai", "modelo": "gpt-5.4"}).json()
        assert r["modelo"] == "gpt-5.4" and r["proveedores"]["openai"]["clave"] == "…enai"
        r = c.put("/api/ajustes/ia", json={"proveedor": "openai", "clave": ""}).json()
        assert not r["disponible"]
        assert c.post("/api/ajustes/ia/probar").status_code == 400
        assert c.put("/api/ajustes/ia", json={"proveedor": "otro"}).status_code == 400


def test_numero_de_factura_repetido(entorno):
    """Si la factura leída lleva un número que ya tiene otra, no se crea: queda pendiente para revisarla."""
    from datetime import date
    from finanzas.models import Cliente, Factura
    with TestClient(app) as c:
        with db.SessionLocal() as s:
            s.query(Factura).filter(Factura.numero == "7").delete()
            otro = Cliente(nombre="Otro cliente 2011")
            s.add(otro)
            s.flush()
            s.add(Factura(numero="7", cliente_id=otro.id, fecha=date(2011, 1, 1), base=1))
            s.commit()
        try:
            importar(c)
            doc = estados(c)["f1.pdf"]
            assert doc["estado"] == "pendiente" and doc["mensaje"] == "El número 7 ya existe: revísala"
            assert doc["datos"]["contraparte"] == "ACME"  # lo leído se conserva para revisarla
            facturas = c.get("/api/autonomo?anio=2023").json()["facturas"]
            assert not any(f["numero"] == "7" for f in facturas)
        finally:
            with db.SessionLocal() as s:
                s.query(Factura).filter(Factura.numero == "7", Factura.fecha == date(2011, 1, 1)).delete()
                s.query(Cliente).filter(Cliente.nombre == "Otro cliente 2011").delete()
                s.commit()
