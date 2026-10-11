"""Inicio, Gastos e Inversiones: histórico aligerado, tarjeta de gasto del mes, presupuestos, un mes concreto,
comparativas que no se inflan, suscripciones ocultas y aportaciones a Indexa (datos inventados en 2010-2011)."""
import json
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from finanzas import db, gastos, presupuestos, sync
from finanzas.integrations import indexa
from finanzas.main import app
from finanzas.models import Categoria, Cuenta, Instantanea, Movimiento

HOY = date(2011, 8, 20)  # «hoy» para los análisis que se llaman directamente


@pytest.fixture(scope="module")
def s():
    with TestClient(app):
        sesion = _preparar()
        yield sesion
        sesion.close()


def _preparar():
    s = db.SessionLocal()
    cuenta = Cuenta(nombre="Cuenta f6", participacion=100)
    s.add(cuenta)
    s.flush()
    super_ = s.scalar(select(Categoria).where(Categoria.nombre == "Supermercado")).id
    movs = [
        # De marzo a julio de 2011: 100 € de súper y Netflix 10 € cada mes
        *[(f"2011-{m:02d}-05", "MERCADONA F6", "-100", super_) for m in range(3, 8)],
        *[(f"2011-{m:02d}-02", "NETFLIX.COM F6", "-10", None) for m in range(3, 8)],
        ("2011-07-15", "VIAJE F6 GRANDE", "-300", None),
        ("2011-07-28", "NOMINA F6", "1500", None),
        # El mismo periodo del año pasado (julio de 2010): la mitad de súper
        ("2010-07-10", "MERCADONA F6", "-50", super_),
        # Lo que va de agosto de 2011
        ("2011-08-03", "MERCADONA F6", "-80", super_),
    ]
    for i, (f, concepto, importe, cat) in enumerate(movs):
        s.add(Movimiento(cuenta_id=cuenta.id, fecha=date.fromisoformat(f), concepto=concepto, importe=D(importe),
                         huella=f"f6-{i}", categoria_id=cat))
    s.commit()
    return s


# --- Inicio -------------------------------------------------------------------------

def test_muestrear_historico():
    hoy = date(2011, 12, 31)
    fotos = [SimpleNamespace(fecha=hoy - timedelta(days=i)) for i in range(500, -1, -1)]
    puntos = sync.muestrear(fotos, hoy)
    fechas = [p.fecha for p in puntos]
    assert fechas == sorted(fechas) and fechas[-1] == hoy and fechas[0] == date(2010, 8, 31)  # el último de agosto
    assert len(puntos) < 150  # 92 días + unas 39 semanas + unos 5 meses, en vez de 501
    assert date(2011, 11, 1) in fechas and date(2011, 11, 2) in fechas  # últimos 3 meses: todos los días
    assert fechas.count(date(2011, 3, 15)) == 0 and any(f.year == 2011 and f.month == 3 for f in fechas)
    assert date(2010, 12, 31) in fechas  # el cierre del año se conserva (último del mes)


def test_historico_con_otros_y_aligerado(s):
    for d in range(1, 6):
        s.add(Instantanea(fecha=date(2011, 1, d), liquidez=D("1000"), otros=D("500")))
    s.add(Instantanea(fecha=date(2011, 2, 1), liquidez=D("1000"), otros=D("700")))
    s.commit()
    try:
        with TestClient(app) as c:
            r = c.get("/api/resumen").json()
            assert "sync" not in r  # nadie lo leía: Layout usa /sync
            h = {x["fecha"]: x for x in r["historico"]}
            assert "2011-01-05" in h and "2011-01-01" not in h  # de hace años, una foto por mes
            assert h["2011-01-05"]["otros"] == 500 and h["2011-01-05"]["neto"] == 1500
            assert h["2011-02-01"]["otros"] == 700
    finally:
        s.query(Instantanea).filter(Instantanea.fecha < date(2012, 1, 1)).delete()
        s.commit()


def test_resumen_gasto_del_mes():
    with TestClient(app) as c:
        r = c.get("/api/resumen").json()
        g = r["gastos"]
        hoy = date.today()
        assert g["dia"] == hoy.day and g["este_mes"] >= 0 and g["media_mes"] >= 0
        dias = monthrange(hoy.year, hoy.month)[1]
        esperado = max(g["este_mes"], g["este_mes"] + (g["media_mes"] - g["este_mes"]) * (dias - hoy.day) / dias)
        assert abs(g["proyeccion"] - esperado) < 0.011 and g["proyeccion"] >= g["este_mes"]


# --- Gastos --------------------------------------------------------------------------

def test_presupuestos_y_aviso_al_pasarse(s):
    with TestClient(app) as c:
        assert c.put("/api/gastos/presupuestos", json={"Supermercado": -5}).status_code == 400
        r = c.put("/api/gastos/presupuestos", json={"Supermercado": 50, "Viajes": 0, "Otros": None, " ": 20})
        assert r.status_code == 200 and r.json() == {"Supermercado": 50}
        assert c.get("/api/gastos/presupuestos").json() == {"Supermercado": 50}
        # Un gasto de súper este mes por encima del presupuesto dispara el aviso de Inicio
        cuenta = s.scalar(select(Cuenta).where(Cuenta.nombre == "Cuenta f6"))
        super_ = s.scalar(select(Categoria).where(Categoria.nombre == "Supermercado")).id
        mov = Movimiento(cuenta_id=cuenta.id, fecha=date.today(), concepto="MERCADONA F6 HOY", importe=D("-120"),
                         huella="f6-hoy", categoria_id=super_)
        s.add(mov)
        s.commit()
        try:
            avisos = [a for a in presupuestos.avisos(s) if "presupuesto de Supermercado" in a["texto"]]
            assert len(avisos) == 1 and avisos[0]["nivel"] == "aviso" and avisos[0]["ir"] == "/gastos"
            assert any("presupuesto de Supermercado" in a["texto"] for a in c.get("/api/resumen").json()["avisos"])
            assert c.get("/api/gastos").json()["este_mes"]["por_categoria"]["Supermercado"] >= 120
        finally:
            s.delete(mov)
            s.commit()
            c.put("/api/gastos/presupuestos", json={})
        assert c.get("/api/gastos/presupuestos").json() == {}
        assert not [a for a in presupuestos.avisos(s) if "presupuesto" in a["texto"]]


def test_un_mes_concreto_y_el_anio_pasado(s):
    d = gastos.analisis(s, 6, HOY, mes=date(2011, 7, 1), comparar="anio_pasado")
    assert (d["desde"], d["hasta"], d["meses"], d["mes"]) == ("2011-07-01", "2011-07-31", 1, "2011-07")
    assert d["gastos_mes"] == 410 and d["ingresos_mes"] == 1500  # súper 100 + Netflix 10 + viaje 300
    assert d["antes"] == {"desde": "2010-07-01", "hasta": "2010-07-31", "meses": 1} and d["gastos_mes_antes"] == 50
    sup = next(x for x in d["categorias"] if x["categoria"] == "Supermercado")
    assert sup["mes"] == 100 and sup["mes_antes"] == 50 and sup["cambio"] == 100 and sup["veces"] == 1
    assert d["fijo_mes"] == 10 and d["variable_mes"] == 400  # el fijo real de ese mes, no el de ahora
    assert d["este_mes"] == {"gastos": 80, "dia": 20, "por_categoria": {"Supermercado": 80}}
    # «Mes a mes» sigue enseñando los 6 últimos meses completos aunque solo se analice julio
    assert [m["mes"] for m in d["por_mes"]] == ["2011-02", "2011-03", "2011-04", "2011-05", "2011-06", "2011-07"]
    with TestClient(app) as c:
        r = c.get("/api/gastos?mes=2011-07&comparar=anio_pasado").json()
        assert r["meses"] == 1 and r["gastos_mes"] == 410 and r["gastos_mes_antes"] == 50 and r["comparar"] == "anio_pasado"
        assert c.get("/api/gastos?mes=2011-7").status_code == 400
        assert c.get(f"/api/gastos?mes={date.today():%Y-%m}").status_code == 400
        assert c.get("/api/gastos?comparar=otro").status_code == 400


def test_comparativa_con_historico_corto(s):
    # Seis meses (feb-jul) frente a los seis anteriores: no hay nada en ago 2010-ene 2011 → sin comparación
    d = gastos.analisis(s, 6, HOY)
    assert d["gastos_mes_antes"] is None and d["antes"] is None
    assert all(c["cambio"] is None and c["mes_antes"] is None for c in d["categorias"])
    # Tres meses (may-jul) frente a feb-abr: solo marzo y abril tienen datos → la media es entre 2, no entre 3
    d = gastos.analisis(s, 3, HOY)
    assert d["antes"]["meses"] == 2 and d["gastos_mes_antes"] == 110
    sup = next(x for x in d["categorias"] if x["categoria"] == "Supermercado")
    assert sup["mes"] == 100 and sup["mes_antes"] == 100 and sup["cambio"] == 0


def test_suscripcion_oculta_desaparece(s):
    assert any(x["clave"] == "netflix" for x in gastos.suscripciones(s, HOY))
    with TestClient(app) as c:
        assert c.put("/api/gastos/suscripciones/netflix", json={"ignorada": True}).json()["ignoradas"] == ["netflix"]
        try:
            assert not any(x["clave"] == "netflix" for x in gastos.suscripciones(s, HOY))
            d = gastos.analisis(s, 3, HOY)
            assert [x["clave"] for x in d["ignoradas"]] == ["netflix"] and d["ignoradas"][0]["ignorada"]
            assert not any(x["clave"] == "netflix" for x in d["suscripciones"])
            assert d["fijo_mes"] == 0  # sus cargos pasan a ser variable
            assert "ignoradas" in c.get("/api/gastos?meses=3").json()  # por la API «hoy» es 2026: la lista va vacía
        finally:
            assert c.put("/api/gastos/suscripciones/netflix", json={"ignorada": False}).json()["ignoradas"] == []
    assert any(x["clave"] == "netflix" for x in gastos.suscripciones(s, HOY))
    assert gastos.analisis(s, 3, HOY)["fijo_mes"] == 10


# --- Inversiones ---------------------------------------------------------------------

def test_aportado_banco_e_indexa(s):
    idx = Cuenta(nombre="Indexa f6", entidad="Indexa Capital", tipo="inversion", origen="indexa", id_externo="F6IDX",
                 saldo=D("1000"), detalle=json.dumps({"total": 1000, "posiciones": []}))
    s.add(idx)
    s.flush()
    cuenta = s.scalar(select(Cuenta).where(Cuenta.nombre == "Cuenta f6"))
    cat = s.scalar(select(Categoria).where(Categoria.nombre == "Inversión (Indexa)")).id
    movs = [Movimiento(cuenta_id=cuenta.id, fecha=date(2011, 3, 1), concepto="TRASPASO INDEXA F6IDX", importe=D("-500"),
                       huella="f6-idx-1", categoria_id=cat),
            Movimiento(cuenta_id=cuenta.id, fecha=date(2011, 4, 1), concepto="TRASPASO INDEXA F6IDX", importe=D("-250"),
                       huella="f6-idx-2", categoria_id=cat),
            Movimiento(cuenta_id=cuenta.id, fecha=date(2011, 5, 1), concepto="REEMBOLSO INDEXA F6IDX", importe=D("100"),
                       huella="f6-idx-3", categoria_id=cat)]
    s.add_all(movs)
    s.commit()
    try:
        with TestClient(app) as c:
            r = next(x for x in c.get("/api/indexa").json() if x["numero"] == "F6IDX")
            assert r["aportado_banco"] == {"total": 750, "ultimos_12_meses": 0, "primera_fecha": "2011-03-01"}
            assert r["ultima_sincronizacion"] is None and r["total"] == 1000
            # Un punto de la evolución de las inversiones por foto, ligero
            e = c.get("/api/inversiones/evolucion?meses=12").json()
            assert {"desde", "hasta", "puntos", "cambio"} <= e.keys()
            # Las aportaciones no son gasto
            assert not any("INDEXA" in m["concepto"] for m in c.get("/api/gastos?mes=2011-03").json()["mayores"])
    finally:
        for m in movs:
            s.delete(m)
        s.delete(idx)
        s.commit()


def test_indexa_guarda_ultima_sincronizacion():
    def responder(req: httpx.Request):
        if req.url.path == "/users/me":
            return httpx.Response(200, json={"accounts": [{"account_number": "F6SYNC", "type": "mutual"}]})
        if req.url.path == "/accounts/F6SYNC/portfolio":
            return httpx.Response(200, json={"portfolio": {"total_amount": 100}})
        return httpx.Response(404)

    with TestClient(app):
        s = db.SessionLocal()
        cliente = indexa.IndexaClient(token="tok", base_url="https://x", transport=httpx.MockTransport(responder))
        [c] = indexa.sincronizar(s, cliente)
        try:
            assert c.ultima_sincronizacion is not None and c.saldo_fecha == date.today()
        finally:
            s.delete(c)
            s.commit()
            s.close()
