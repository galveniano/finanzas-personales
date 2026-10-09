"""Lo transversal: búsqueda global, estado de la app, historial de sincronizaciones, restaurar una copia,
tope de tiempo del asistente y configuración tolerante. Datos con fechas de 2011 para no mezclarse con otros tests."""
import importlib
import json
import time
from datetime import date, datetime
from decimal import Decimal as D

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from finanzas import asistente, config, db, ia
from finanzas.importers import datos_json
from finanzas.main import app
from finanzas.models import (Activo, Cliente, Cuenta, Declaracion, Factura, Movimiento, Objetivo, PagoPrevisto,
                             RegistroSync)

CFG = ia.ConfigIA("anthropic", "sk-test", "claude-sonnet-5-5")


def subir(c, datos, previa=False):
    return c.post(f"/api/importar/datos{'?previa=true' if previa else ''}",
                  files={"fichero": ("datos.json", json.dumps(datos).encode(), "application/json")})


@pytest.fixture
def datos_2011():
    with TestClient(app):
        with db.SessionLocal() as s:
            cuenta = Cuenta(nombre="Cuenta búsqueda 2011", entidad="Banco de pruebas")
            cliente = Cliente(nombre="Cliente Búsqueda 2011", nif="B20110000")
            activo = Activo(nombre="Local búsqueda 2011", tipo="inmueble")
            s.add_all([cuenta, cliente, activo])
            s.flush()
            s.add_all([
                Movimiento(cuenta_id=cuenta.id, fecha=date(2011, 3, 3), concepto="RECIBO LUZ BÚSQUEDA 2011",
                           importe=D("-55.10"), huella="busqueda-2011"),
                Factura(numero="B-2011-1", cliente_id=cliente.id, fecha=date(2011, 4, 4), concepto="Trabajo 2011", base=D("100")),
                Objetivo(nombre="Viaje búsqueda 2011", tipo="viaje", fecha_objetivo=date(2011, 12, 1), importe_objetivo=D("500")),
                PagoPrevisto(concepto="Reserva búsqueda 2011", fecha=date(2011, 5, 5), importe=D("50")),
                Declaracion(modelo="303", ejercicio=2011, periodo="1T", importe=D("12.34"), justificante="J2011"),
            ])
            s.commit()
    yield
    with db.SessionLocal() as s:
        for modelo, col, valor in ((Movimiento, Movimiento.huella, "busqueda-2011"), (Factura, Factura.numero, "B-2011-1"),
                                   (Cliente, Cliente.nombre, "Cliente Búsqueda 2011"), (Cuenta, Cuenta.nombre, "Cuenta búsqueda 2011"),
                                   (Activo, Activo.nombre, "Local búsqueda 2011"), (Objetivo, Objetivo.nombre, "Viaje búsqueda 2011"),
                                   (PagoPrevisto, PagoPrevisto.concepto, "Reserva búsqueda 2011"),
                                   (Declaracion, Declaracion.justificante, "J2011")):
            s.query(modelo).filter(col == valor).delete()
        s.commit()


def test_buscar_devuelve_grupos(datos_2011):
    with TestClient(app) as c:
        assert c.get("/api/buscar?q=x").json()["grupos"] == []  # menos de dos letras: nada
        r = c.get("/api/buscar?q=2011").json()
        grupos = {g["nombre"]: g["resultados"] for g in r["grupos"]}
        assert {"Movimientos", "Facturas", "Clientes", "Bienes", "Plan", "Hacienda"} <= set(grupos)
        mov = grupos["Movimientos"][0]
        assert mov["texto"] == "RECIBO LUZ BÚSQUEDA 2011" and mov["importe"] == -55.1 and mov["ir"] == "/cuentas?q=2011"
        assert "03/03/2011" in mov["detalle"] and "Cuenta búsqueda 2011" in mov["detalle"]
        assert grupos["Facturas"][0]["texto"] == "Factura B-2011-1 · Cliente Búsqueda 2011" and grupos["Facturas"][0]["ir"] == "/ingresos"
        assert grupos["Bienes"][0] == {"texto": "Local búsqueda 2011", "detalle": "Inmueble", "ir": "/inmuebles", "importe": None}
        assert {x["texto"] for x in grupos["Plan"]} == {"Viaje búsqueda 2011", "Reserva búsqueda 2011"}
        hacienda = grupos["Hacienda"][0]
        assert hacienda["texto"] == "Modelo 303 · 1T 2011" and hacienda["ir"] == "/impuestos?ver=presentadas" and hacienda["importe"] == 12.34
        assert all(len(v) <= 8 for v in grupos.values())

        r = c.get("/api/buscar?q=iva 2011").json()  # varias palabras en Hacienda
        assert any(g["nombre"] == "Hacienda" for g in r["grupos"])
        cat = c.get("/api/buscar?q=supermerc").json()["grupos"]
        assert cat and cat[0]["nombre"] == "Categorías" and cat[0]["resultados"][0]["ir"].startswith("/cuentas?categoria=")


def test_estado_de_la_app():
    with TestClient(app) as c:
        r = c.get("/api/app/estado").json()
        assert r["base_datos"]["tipo"] == "SQLite" and r["base_datos"]["detalle"].endswith("test.db")
        assert r["ccaa"] == config.CCAA and r["banco"]["nombre"] == config.BANCO and r["banco"]["configurado"] is False
        assert r["sincronizacion"]["modo"] == "manual"  # SYNC_HORAS=0 en los tests
        assert r["sesion"] == {"requerida": False, "email": None}
        assert r["version"] is None or isinstance(r["version"], str)
        assert c.get("/api/config").status_code == 404  # lo sustituye /app/estado

        # Una copia que se sube a Drive queda registrada con su destino
        assert c.get("/api/exportar?destino=drive").status_code == 200
        copia = c.get("/api/app/estado").json()["ultima_copia"]
        assert copia == {"fecha": date.today().isoformat(), "destino": "drive", "hace_dias": 0}
        assert c.get("/api/exportar").status_code == 200
        assert c.get("/api/app/estado").json()["ultima_copia"]["destino"] == "descarga"
        assert c.post("/api/exportar/hecha").status_code in (404, 405)


def test_historial_sync():
    with TestClient(app) as c:
        with db.SessionLocal() as s:
            for i in range(12):
                s.add(RegistroSync(fuente="indexa", fecha=datetime(2011, 1, 1, i), ok=i % 2 == 0, mensaje=f"prueba 2011 {i}"))
            s.commit()
        try:
            r = c.get("/api/sync/historial").json()
            assert set(r) == {"sabadell", "indexa"}
            assert len(r["indexa"]) == 10 and r["indexa"][0]["mensaje"] == "prueba 2011 11"  # las últimas, la más reciente primero
            assert r["indexa"][0]["ok"] is False and r["indexa"][0]["fecha"] == "2011-01-01T11:00Z"
            desde = c.get("/api/sync").json()["sabadell"]["historico_desde"]  # otros tests pueden dejar una conexión
            assert desde is None or date.fromisoformat(desde)
        finally:
            with db.SessionLocal() as s:
                s.query(RegistroSync).filter(RegistroSync.mensaje.like("prueba 2011%")).delete()
                s.commit()


def test_restaurar_copia(datos_2011):
    with TestClient(app) as c:
        copia = c.get("/api/exportar?pdfs=true").json()
        assert datos_json.es_copia(copia)
        filas_antes = {t: len(f) for t, f in copia["tablas"].items()}
        assert filas_antes["objetivos"] >= 1 and filas_antes["categorias"] > 0

        # Cambios después de la copia, que la restauración deshace
        c.post("/api/objetivos", json={"nombre": "Objetivo posterior 2011", "importe_objetivo": 1})
        with db.SessionLocal() as s:
            s.query(Objetivo).filter(Objetivo.nombre == "Viaje búsqueda 2011").delete()
            s.commit()

        previa = subir(c, copia, previa=True).json()
        assert previa["copia"] is True and previa["fecha"] == copia["fecha"]
        assert {t["tabla"]: t["filas"] for t in previa["tablas"]}["objetivos"] == filas_antes["objetivos"]
        assert previa["filas"] == sum(filas_antes.values())
        nombres = {o["nombre"] for o in c.get("/api/planificacion").json()["objetivos"]}
        assert "Objetivo posterior 2011" in nombres and "Viaje búsqueda 2011" not in nombres  # la vista previa no toca nada

        r = subir(c, copia)
        assert r.status_code == 200, r.text
        mensajes = r.json()["mensajes"]
        assert mensajes[0].startswith(f"Copia del {copia['fecha']} restaurada") and any("objetivos:" in m for m in mensajes)
        assert "clave" in mensajes[-1]
        despues = c.get("/api/exportar?pdfs=true").json()["tablas"]
        assert {t: len(f) for t, f in despues.items() if t != "ajustes"} == {t: n for t, n in filas_antes.items() if t != "ajustes"}
        nombres = {o["nombre"] for o in c.get("/api/planificacion").json()["objetivos"]}
        assert "Viaje búsqueda 2011" in nombres and "Objetivo posterior 2011" not in nombres
        # Las fechas y los importes vuelven con su tipo
        mov = next(m for m in c.get("/api/movimientos?q=BÚSQUEDA 2011").json())
        assert mov["fecha"] == "2011-03-03" and mov["importe"] == -55.1
        # Se puede seguir creando después (los ids no chocan)
        assert c.post("/api/objetivos", json={"nombre": "Objetivo tras restaurar 2011", "importe_objetivo": 1}).status_code == 200
        with db.SessionLocal() as s:
            s.query(Objetivo).filter(Objetivo.nombre == "Objetivo tras restaurar 2011").delete()
            s.commit()

        # Un fichero normal sigue importando como siempre y su vista previa lo dice
        assert subir(c, {"activos": []}, previa=True).json() == {"copia": False, "activos": 0, "inversiones": 0, "prevision": False}
        assert subir(c, {"version": 1, "tablas": {"objetivos": "no"}}).status_code == 400
        assert subir(c, {"version": 1, "tablas": {"objetivos": [{"id": 1, "nombre": "x", "fecha_objetivo": "ayer"}]}}).status_code == 400
        assert "Viaje búsqueda 2011" in {o["nombre"] for o in c.get("/api/planificacion").json()["objetivos"]}  # todo o nada


def test_conversar_sin_tiempo():
    """Con el plazo agotado el asistente responde con el texto de tiempo en vez de cortarse a medias."""
    vueltas = {"n": 0}

    def lento(peticion: httpx.Request) -> httpx.Response:
        vueltas["n"] += 1
        time.sleep(0.35)
        return httpx.Response(200, json={"stop_reason": "tool_use", "content": [
            {"type": "tool_use", "id": f"t{vueltas['n']}", "name": "hacienda", "input": {}}]})

    texto, consultas = ia.conversar(CFG, "sistema", [{"role": "user", "content": "hola"}], asistente.HERRAMIENTAS,
                                    lambda n, a: "{}", plazo_s=1.6, transport=httpx.MockTransport(lento))
    assert texto == ia.SIN_TIEMPO and consultas and 1 <= vueltas["n"] < ia.MAX_VUELTAS

    def se_cuelga(_peticion: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("tarde")

    texto, consultas = ia.conversar(CFG, "sistema", [{"role": "user", "content": "hola"}], [], lambda n, a: "{}",
                                    plazo_s=30, transport=httpx.MockTransport(se_cuelga))
    assert texto == ia.SIN_TIEMPO and consultas == []

    with pytest.raises(ia.ErrorIA):  # sin plazo, un corte de red sigue siendo un error normal
        ia.conversar(CFG, "sistema", [{"role": "user", "content": "hola"}], [], lambda n, a: "{}",
                     transport=httpx.MockTransport(lambda _p: (_ for _ in ()).throw(httpx.ConnectError("no"))))


def test_herramientas_del_asistente():
    nombres = {h["name"] for h in asistente.HERRAMIENTAS}
    assert {"hacienda_hoy", "ahorro_fiscal", "vender_o_alquilar", "gastos"} <= nombres
    assert all(n in asistente.SISTEMA for n in ("hacienda_hoy", "ahorro_fiscal", "vender_o_alquilar"))
    assert not hasattr(asistente, "MAX_VUELTAS") and ia.MAX_VUELTAS == 6 and ia.MAX_TOKENS == 4096
    assert asistente.PLAZO_S == 170  # en local; en Vercel 50
    with TestClient(app):
        with db.SessionLocal() as s:
            hoy = asistente._ejecutar(s, "hacienda_hoy", {})
            assert {"pendiente", "hucha", "cuota_autonomos", "plazos"} <= set(hoy)
            with pytest.raises(HTTPException):
                asistente._ejecutar(s, "vender_o_alquilar", {"activo_id": 999999})


def test_sync_horas_vacio_y_secreto(monkeypatch):
    monkeypatch.setenv("SYNC_HORAS", "")
    assert importlib.reload(config).SYNC_HORAS == 6.0
    monkeypatch.setenv("SYNC_HORAS", "0")
    assert importlib.reload(config).SYNC_HORAS == 0.0

    monkeypatch.setattr(config, "SESSION_SECRET", "")
    assert config.secreto(obligatorio=False) == "finanzas-local"
    with pytest.raises(HTTPException) as e:
        config.secreto()
    assert e.value.status_code == 503 and "SESSION_SECRET" in e.value.detail
    monkeypatch.setattr(config, "SESSION_SECRET", "corto")
    assert config.secreto(obligatorio=False) == "corto"
    monkeypatch.setattr(config, "SESSION_SECRET", "s" * 32)
    assert config.secreto() == "s" * 32


def test_recortar_historial_del_asistente():
    """Claude rechaza un historial que empiece por «assistant» o con dos papeles seguidos: el recorte lo evita."""
    largo = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(25)]
    r = asistente.recortar(largo)
    assert len(r) <= asistente.TOPE_MENSAJES and r[0]["role"] == "user" and r[-1]["content"] == "m24"
    assert all(a["role"] != b["role"] for a, b in zip(r, r[1:]))
    repetidos = [{"role": "assistant", "content": "hola"}, {"role": "user", "content": "a"}, {"role": "user", "content": "b"},
                 {"role": "system", "content": "x"}, {"role": "assistant", "content": " "}, {"role": "assistant", "content": "c"}]
    assert asistente.recortar(repetidos) == [{"role": "user", "content": "a\n\nb"}, {"role": "assistant", "content": "c"}]
    assert asistente.recortar([{"role": "assistant", "content": "solo yo"}]) == []


def test_desconectar_sabadell():
    from finanzas.models import ConexionBancaria
    with TestClient(app) as c:
        with db.SessionLocal() as s:
            s.add(ConexionBancaria(banco="Banco 2011", session_id="sesion-2011", valida_hasta=datetime(2099, 1, 1)))
            s.commit()
        try:
            assert c.get("/api/sync").json()["sabadell"]["conectado"] is True
            r = c.post("/api/sync/sabadell/desconectar").json()
            assert r["ok"] and r["desconectadas"] >= 1
            assert c.get("/api/sync").json()["sabadell"]["conectado"] is False
            assert c.post("/api/sync/sabadell/desconectar").json()["desconectadas"] == 0
        finally:
            with db.SessionLocal() as s:
                s.query(ConexionBancaria).filter(ConexionBancaria.session_id == "sesion-2011").delete()
                s.commit()
