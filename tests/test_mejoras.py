"""Mejoras de la revisión de octubre de 2026 (datos inventados)."""
from datetime import date, timedelta
from decimal import Decimal as D

from fastapi.testclient import TestClient

from finanzas import calendario, categorizar, db, prevision
from finanzas.fiscal import alquiler, reta
from finanzas.main import app
from finanzas.models import Activo, Cuenta, Declaracion, Instantanea, Movimiento
from finanzas.prevision import MovTuyo


def _mov(i, dias, cuenta, importe, tipo=None, categoria=None):
    return MovTuyo(i, date(2026, 5, 10) + timedelta(days=dias), cuenta, importe, importe, "X", categoria, tipo)


def test_traspasos_entre_cuentas_sin_la_palabra_traspaso():
    movs = [_mov(1, 0, 1, -500), _mov(2, 1, 2, 500),  # de tu cuenta a la compartida
            _mov(3, 0, 1, -40), _mov(4, 10, 2, 40),  # mismo importe pero lejos en el tiempo: no
            _mov(5, 0, 1, -70), _mov(6, 0, 1, 70)]  # misma cuenta (devolución): no
    assert prevision.ids_traspaso(movs) == {1, 2}


def test_cuota_de_autonomos_por_ingresos_reales():
    r = reta.regularizar(2025, rendimiento_neto=45000, cuota_pagada=3600, bruto_nomina=50000)
    # (45.000 + 3.600) × 0,93 / 12 = 3.766,5 €/mes → tramo de 3.620 a 4.050, base mínima 1.601,31
    assert r.tramo == 13 and r.base_minima == 1601.31
    assert r.a_pagar == round(1601.31 * 12 * 0.314 - 3600, 2) and r.a_devolver == 0
    assert r.devolucion_pluriactividad > 0
    poco = reta.regularizar(2026, rendimiento_neto=9000, cuota_pagada=6000)
    assert poco.a_pagar == 0 and poco.a_devolver > 0 and poco.devolucion_pluriactividad == 0
    assert reta.regularizar(2024, 1, 1) is None


def test_renta_fraccionada_ahorro_y_pensiones():
    nom = {"bruto": 50000.0, "ss": 3200.0, "irpf": 9000.0}
    cfg = {"gastos_autonomo_mes": 300, "factor_renta": 1.0}
    base = prevision._renta(cfg, nom, 40000, 3000, 2000, 1500)
    con_ahorro = prevision._renta({**cfg, "rentas_ahorro_anio": 1000}, nom, 40000, 3000, 2000, 1500)
    assert round(con_ahorro["cuota"] - base["cuota"], 2) == 190  # 19 % de 1.000
    con_planes = prevision._renta(cfg, nom, 40000, 3000, 2000, 1500, extra={"pensiones": 5000, "ppes": 9000})
    assert con_planes["reduccion_pensiones"] == 1500 + 4250  # topes
    assert 0.4 * 5750 < base["cuota"] - con_planes["cuota"] < 0.5 * 5750  # al tipo marginal
    assert 40 < base["tipo_marginal"] < 50


def test_130_con_gastos_de_dificil_justificacion():
    assert prevision._rendimiento_130(10000) == 9500
    assert prevision._rendimiento_130(100000) == 98000  # tope de 2.000 €
    assert round(prevision._previo_de_casillas(9500), 2) == 10000
    assert prevision._previo_de_casillas(98000) == 100000


def test_reduccion_del_alquiler_segun_la_fecha():
    assert alquiler.reduccion_por_defecto(date(2021, 2, 26)) == 60
    assert alquiler.reduccion_por_defecto(date(2024, 1, 1)) == 50


def test_patron_y_reglas_aprendidas():
    assert categorizar.patron_de("COMPRA TARJ. 5402 STREAMFLIX.COM 12/09") == "streamflix com"
    with TestClient(app) as c:
        s = db.SessionLocal()
        cuenta = Cuenta(nombre="Cuenta reglas ejemplo")
        s.add(cuenta)
        s.flush()
        viejos = [Movimiento(cuenta_id=cuenta.id, fecha=date(2026, m, 3), concepto=f"COMPRA TARJ. {m}1 LIBRERIA EJEMPLO",
                             importe=D("-20"), huella=f"regla-{m}") for m in (1, 2, 3)]
        s.add_all(viejos)
        s.commit()
        ids = [m.id for m in viejos]
        s.close()
        cat = next(x for x in c.get("/api/categorias").json() if x["nombre"] == "Compras")
        r = c.patch(f"/api/movimientos/{ids[0]}", json={"categoria_id": cat["id"]}).json()
        assert r["patron"] == "libreria ejemplo" and r["parecidos"] == 2
        assert c.post(f"/api/movimientos/{ids[0]}/aplicar-a-parecidos").json()["cambiados"] == 2
        s = db.SessionLocal()
        assert categorizar.categorizar(s, "COMPRA TARJ. 99 LIBRERIA EJEMPLO") == cat["id"]
        # La regla vieja «reta» ya no existe: «AMAZON RETAIL» no es cuota de autónomos
        cuota = s.scalar(db.Base.metadata.tables["categorias"].select().where(
            db.Base.metadata.tables["categorias"].c.nombre == "Cuota autónomos"))
        assert categorizar.categorizar(s, "AMAZON EU RETAIL") != cuota
        s.close()


def test_calendario_de_plazos():
    with TestClient(app) as c:
        with db.SessionLocal() as s:
            texto = calendario.ics(s, date(2026, 10, 4))
        assert "BEGIN:VCALENDAR" in texto and "DTSTART;VALUE=DATE:20261020" in texto and "303 y 130 del 3T 2026" in texto
        ruta = c.get("/api/calendario/enlace").json()["ruta"]
        assert c.get(ruta).status_code == 200 and c.get("/calendario/otro.ics").status_code == 404


def test_exportar_e_historico_con_coche():
    with TestClient(app) as c:
        s = db.SessionLocal()
        s.add(Activo(nombre="Coche ejemplo", tipo="vehiculo", precio_compra=D("20000"), fecha_compra=date(2020, 1, 1)))
        s.add(Instantanea(fecha=date(2021, 1, 1), liquidez=D("1000")))  # foto antigua sin vehículos
        s.commit()
        s.close()
        r = c.get("/api/resumen").json()
        vieja = next(h for h in r["historico"] if h["fecha"] == "2021-01-01")
        assert 15000 < vieja["vehiculos"] < 20000 and vieja["neto"] > 1000
        assert "avisos" in r and "hacienda_pendiente" in r and "disponible" in r
        datos = c.get("/api/exportar").json()
        assert datos["tablas"]["activos"] and not any(str(a["valor"]).startswith("enc:") for a in datos["tablas"]["ajustes"])
        assert c.get("/api/exportar/movimientos.xlsx").status_code == 200
        s = db.SessionLocal()  # no dejar la foto inventada para otros tests
        s.query(Instantanea).filter(Instantanea.fecha == date(2021, 1, 1)).delete()
        s.query(Activo).filter(Activo.nombre == "Coche ejemplo").delete()
        s.commit()
        s.close()


def test_complementaria_suma_lo_pagado():
    with TestClient(app) as c:
        s = db.SessionLocal()
        s.add_all([Declaracion(modelo="303", ejercicio=2017, periodo="2T", resultado="ingresar", importe=D("1000"),
                               justificante="A1"),
                   Declaracion(modelo="303", ejercicio=2017, periodo="2T", resultado="ingresar", importe=D("150"),
                               justificante="A2")])
        s.commit()
        s.close()
        t2 = c.get("/api/autonomo?anio=2017").json()["trimestres"][1]
        assert t2["iva_resultado"] == 1150 and t2["iva_fuente"] == "presentado"


def test_inmueble_editar_borrar_escritura_y_vender():
    with TestClient(app) as c:
        piso = c.post("/api/inmuebles", json={"nombre": "Piso venta ejemplo", "uso": "alquiler", "precio_compra": 100000,
                                              "gastos_compra": 5000, "fecha_compra": "2019-01-01",
                                              "valor_catastral": 50000, "valor_catastral_construccion": 30000}).json()["id"]
        c.post(f"/api/inmuebles/{piso}/contratos", json={"fecha_inicio": "2024-02-01", "renta_mensual": 700})
        ficha = next(x for x in c.get("/api/inmuebles").json()["inmuebles"] if x["id"] == piso)
        assert ficha["contratos"][0]["reduccion_pct"] == 50
        c.post(f"/api/inmuebles/{piso}/valoraciones", json={"fecha": "2026-01-01", "valor": 150000})
        v = c.get(f"/api/inmuebles/{piso}/vender").json()
        assert v["precio_venta"] == 150000 and v["amortizacion_acumulada"] > 0 and v["en_mano"] < 150000
        r = c.post(f"/api/inmuebles/{piso}/gastos-escritura", json={"fecha": "2027-10-01", "precio": 300000}).json()
        assert r["importe"] == 300000 * 0.015 + 1200
        assert c.patch(f"/api/inmuebles/{piso}", json={"nombre": "Piso renombrado"}).status_code == 200
        assert c.delete(f"/api/inmuebles/{piso}").status_code == 200
        assert not any(x["id"] == piso for x in c.get("/api/inmuebles").json()["inmuebles"])


def test_hacienda_y_ahorro_fiscal():
    with TestClient(app) as c:
        c.put("/api/prevision/supuestos", json={"nomina": {"bruto_anual": 40000, "pagas": 14},
                                                "clientes": [{"nombre": "Cliente H", "tarifa_hora": 30, "dias_mes": 20,
                                                              "iva": 21, "retencion": 15}]})
        h = c.get("/api/hacienda").json()
        assert h["pendiente"]["total"] >= 0 and "hucha" in h and h["plazos"]
        a = c.get("/api/hacienda/ahorro?pensiones=1500").json()
        assert a["ahorro"] > 0 and a["reduccion_aplicada"] == 1500
        assert c.put("/api/hacienda/supuestos", json={"fraccionar_renta": True}).status_code == 200
        meses = c.get("/api/prevision?meses=24").json()["meses"]
        assert any("2.º plazo" in i["concepto"] for m in meses for i in m["impuestos"])
        c.put("/api/prevision/supuestos", json={})


def test_el_mes_en_curso_no_cuenta_dos_veces_lo_ya_cobrado():
    with TestClient(app) as c:
        c.put("/api/prevision/supuestos", json={"nomina": {"bruto_anual": 40000, "pagas": 12}, "gasto_habitual_mes": 100})
        antes = c.get("/api/prevision").json()["meses"][0]
        assert antes["nomina"] > 0
        nomina = next(x for x in c.get("/api/categorias").json() if x["nombre"] == "Nómina")
        s = db.SessionLocal()
        cuenta = Cuenta(nombre="Cuenta nómina mes ejemplo")
        s.add(cuenta)
        s.flush()
        s.add(Movimiento(cuenta_id=cuenta.id, fecha=date.today().replace(day=1), concepto="NOMINA EMPRESA EJEMPLO",
                         importe=D("99999"), huella="nomina-mes-ejemplo", categoria_id=nomina["id"]))
        s.commit()
        despues = c.get("/api/prevision").json()["meses"][0]
        assert despues["nomina"] == 0 and despues["ya_este_mes"]["nomina"] >= 99999
        s.query(Movimiento).filter(Movimiento.huella == "nomina-mes-ejemplo").delete()
        s.delete(s.get(Cuenta, cuenta.id))
        s.commit()
        s.close()
        c.put("/api/prevision/supuestos", json={})
