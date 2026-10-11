"""Plan: editar y conciliar pagos previstos, objetivos ligados a una cuenta, escenarios y arreglos de la previsión.
Datos inventados con fechas raras (2011, 2031...) para no mezclarse con otros tests; lo que se crea se borra."""
from datetime import date, timedelta
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from finanzas import db
from finanzas.fechas import sumar_meses
from finanzas.main import app
from finanzas.models import Cuenta, Movimiento
from tests.test_prevision import SUPUESTOS

HOY = date.today()
INICIO = HOY.replace(day=1)


@pytest.fixture(autouse=True)
def sin_supuestos_al_acabar():
    yield
    with TestClient(app) as c:
        c.put("/api/prevision/supuestos", json={})


def _pago(c, concepto, fecha, importe, **extra):
    r = c.post("/api/pagos", json={"concepto": concepto, "fecha": fecha, "importe": importe, **extra})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _pagos(c):
    return {p["id"]: p for p in c.get("/api/planificacion").json()["pagos"]}


def _mes_normal(desde: int = 2) -> date:
    """Un mes futuro que no sea agosto (los supuestos de ejemplo no facturan en agosto)."""
    d = sumar_meses(INICIO, desde)
    return sumar_meses(d, 1) if d.month == 8 else d


def test_editar_pago_previsto():
    with TestClient(app) as c:
        obra = c.post("/api/inmuebles", json={"nombre": "Obra edición ejemplo", "tipo": "inmueble_en_construccion"}).json()
        c.post("/api/objetivos", json={"nombre": "Objetivo edición ejemplo", "importe_objetivo": 100})
        objetivo = next(o for o in c.get("/api/planificacion").json()["objetivos"] if o["nombre"] == "Objetivo edición ejemplo")
        pid = _pago(c, "Pago edición ejemplo", "2011-02-01", 100)
        r = c.patch(f"/api/pagos/{pid}", json={"concepto": "Pago editado", "fecha": "2011-03-15", "importe": 250.5,
                                               "objetivo_id": objetivo["id"], "activo_id": obra["id"], "pagado": True})
        assert r.status_code == 200
        p = _pagos(c)[pid]
        assert (p["concepto"], p["fecha"], p["importe"], p["pagado"]) == ("Pago editado", "2011-03-15", 250.5, True)
        assert p["objetivo"] == "Objetivo edición ejemplo" and p["inmueble"] == "Obra edición ejemplo"
        assert p["objetivo_id"] == objetivo["id"] and p["activo_id"] == obra["id"]
        # Vacío no toca; null quita el enlace
        c.patch(f"/api/pagos/{pid}", json={"objetivo_id": None})
        p = _pagos(c)[pid]
        assert p["objetivo"] is None and p["inmueble"] == "Obra edición ejemplo" and p["importe"] == 250.5
        assert c.patch(f"/api/pagos/{pid}", json={"importe": 0}).status_code == 400
        assert c.patch(f"/api/pagos/{pid}", json={"activo_id": 999999}).status_code == 404
        assert c.patch("/api/pagos/999999", json={"pagado": True}).status_code == 404
        assert c.post("/api/pagos", json={"concepto": "Negativo", "fecha": "2011-01-01", "importe": -5}).status_code == 400
        c.delete(f"/api/pagos/{pid}")
        c.delete(f"/api/objetivos/{objetivo['id']}")
        c.delete(f"/api/inmuebles/{obra['id']}")


def test_conciliar_pagos_con_el_banco():
    s = db.SessionLocal()
    cuenta = Cuenta(nombre="Cuenta conciliar ejemplo")
    s.add(cuenta)
    s.flush()
    mov = Movimiento(cuenta_id=cuenta.id, fecha=date(2011, 6, 10), concepto="PROMOTORA PLAZO EJEMPLO",
                     importe=D("-1234.56"), huella="concilia-ej-1")
    s.add(mov)
    s.add(Movimiento(cuenta_id=cuenta.id, fecha=date(2011, 6, 12), concepto="OTRO CARGO EJEMPLO", importe=D("-70"),
                     huella="concilia-ej-2"))
    s.commit()
    mov_id, cuenta_id = mov.id, cuenta.id
    s.close()
    with TestClient(app) as c:
        visto = _pago(c, "Plazo conciliar ejemplo", "2011-06-01", 1234.56)
        sin_banco = _pago(c, "Plazo sin banco ejemplo", "2011-06-01", 999)
        pagos = _pagos(c)
        assert pagos[visto]["visto_en_banco"] == {"movimiento_id": mov_id, "fecha": "2011-06-10", "importe": 1234.56}
        assert pagos[sin_banco]["visto_en_banco"] is None
        avisos = c.get("/api/resumen").json()["avisos"]
        assert any(a["nivel"] == "info" and "Plazo conciliar ejemplo" in a["texto"] and "10/06" in a["texto"]
                   and a["ir"] == "/plan" for a in avisos)
        assert any(a["nivel"] == "aviso" and "Plazo sin banco ejemplo" in a["texto"] and "venció el 01/06" in a["texto"]
                   for a in avisos)
        # Ese cargo ya no cuenta como gasto corriente ni se asigna a dos pagos
        from finanzas import prevision
        s = db.SessionLocal()
        movs = prevision.movimientos_tuyos(s, date(2011, 5, 1), date(2011, 7, 1))
        assert prevision.ids_pagos_previstos(s, movs) == {mov_id}
        s.close()
        r = c.post("/api/pagos/conciliar")
        assert r.status_code == 200 and r.json()["marcados"] == 1
        pagos = _pagos(c)
        assert pagos[visto]["pagado"] and not pagos[sin_banco]["pagado"]
        assert c.post("/api/pagos/conciliar").json()["marcados"] == 0
        c.delete(f"/api/pagos/{visto}")
        c.delete(f"/api/pagos/{sin_banco}")
        c.delete(f"/api/cuentas/{cuenta_id}")
    s = db.SessionLocal()
    assert s.scalar(select(Movimiento.id).where(Movimiento.huella == "concilia-ej-1")) is None
    s.close()


def test_pagos_vencidos_sin_marcar_cuentan_en_el_mes_en_curso():
    with TestClient(app) as c:
        c.put("/api/prevision/supuestos", json={"nomina": {"bruto_anual": 30000, "pagas": 12}})
        antes = c.get("/api/prevision").json()["meses"]
        pid = _pago(c, "Vencido ejemplo", "2011-05-05", 321.5)
        despues = c.get("/api/prevision").json()["meses"]
        assert despues[0]["mes"] == INICIO.strftime("%Y-%m")
        assert round(despues[0]["pagos_previstos"] - antes[0]["pagos_previstos"], 2) == 321.5
        assert all(round(a["pagos_previstos"], 2) == round(b["pagos_previstos"], 2) for a, b in zip(antes[1:], despues[1:]))
        plan = c.get("/api/planificacion").json()
        assert plan["pendiente_12_meses"] >= 321.5
        c.delete(f"/api/pagos/{pid}")


def test_hipoteca_prevista_no_deja_pagos_negativos():
    firma = sumar_meses(INICIO, 3).replace(day=15)
    mes_firma, mes_siguiente = firma.strftime("%Y-%m"), sumar_meses(firma, 1).strftime("%Y-%m")
    with TestClient(app) as c:
        c.put("/api/prevision/supuestos", json={"nomina": {"bruto_anual": 30000, "pagas": 12}})
        obra = c.post("/api/inmuebles", json={"nombre": "Obra financiada ejemplo", "tipo": "inmueble_en_construccion"}).json()
        llave = _pago(c, "Llave ejemplo", firma.replace(day=1).isoformat(), 170000, activo_id=obra["id"])
        extras = _pago(c, "Extras ejemplo", sumar_meses(firma, 1).isoformat(), 10000, activo_id=obra["id"])
        muebles = _pago(c, "Muebles ejemplo", firma.isoformat(), 5000)  # sin bien: no lo pone la hipoteca
        c.post(f"/api/inmuebles/{obra['id']}/hipotecas", json={"nombre": "Hipoteca ejemplo", "capital_inicial": 175000,
                                                                 "tipo_interes_anual": 3, "fecha_inicio": firma.isoformat(),
                                                                 "plazo_meses": 300})
        meses = {m["mes"]: m for m in c.get("/api/prevision?meses=12").json()["meses"]}
        assert all(m["pagos_previstos"] >= 0 for m in meses.values())
        # El mes de la firma el banco pone 170.000 de la llave; de los 5.000 que sobran, el mes siguiente cubre parte de los extras
        assert meses[mes_firma]["financiado"] == 170000 and meses[mes_firma]["pagos_previstos"] == 5000
        assert meses[mes_siguiente]["financiado"] == 5000
        cuota = meses[mes_siguiente]["pagos_previstos"] - 5000
        assert 700 < cuota < 1000  # 10.000 de extras − 5.000 del banco + la primera cuota
        plan = c.get("/api/planificacion").json()
        assert plan["financiado_hipoteca"] == 175000 and plan["pendiente_12_meses"] >= 10000
        # Con más capital del que hay que pagar, lo que sobra no se resta de nada
        ficha = next(i for i in c.get("/api/inmuebles").json()["inmuebles"] if i["id"] == obra["id"])
        c.delete(f"/api/deudas/{ficha['hipotecas'][0]['id']}")
        c.post(f"/api/inmuebles/{obra['id']}/hipotecas", json={"capital_inicial": 300000, "tipo_interes_anual": 3,
                                                                 "fecha_inicio": firma.isoformat(), "plazo_meses": 300})
        meses = {m["mes"]: m for m in c.get("/api/prevision?meses=12").json()["meses"]}
        assert all(m["pagos_previstos"] >= 0 for m in meses.values())
        assert meses[mes_firma]["financiado"] == 170000 and meses[mes_firma]["pagos_previstos"] == 5000
        assert meses[mes_siguiente]["financiado"] == 10000 and 0 < meses[mes_siguiente]["pagos_previstos"] < 2000
        assert c.get("/api/planificacion").json()["financiado_hipoteca"] == 180000
        c.delete(f"/api/inmuebles/{obra['id']}")
        for pid in (llave, extras, muebles):
            c.delete(f"/api/pagos/{pid}")


def test_objetivo_ligado_a_una_cuenta():
    with TestClient(app) as c:
        cuenta = c.post("/api/cuentas", json={"nombre": "Hucha boda ejemplo", "tipo": "ahorro", "saldo": 4000}).json()
        c.patch(f"/api/cuentas/{cuenta['id']}", json={"participacion": 50})
        assert c.post("/api/objetivos", json={"nombre": "Boda con hucha ejemplo", "importe_objetivo": 10000, "ahorrado": 123,
                                              "fecha_objetivo": "2031-05-01", "notas": "La mitad de la hucha es tuya",
                                              "cuenta_id": cuenta["id"]}).status_code == 200
        o = next(o for o in c.get("/api/planificacion").json()["objetivos"] if o["nombre"] == "Boda con hucha ejemplo")
        assert o["ahorrado"] == 2000 and o["ahorrado_automatico"] and o["cuenta"] == "Hucha boda ejemplo"
        assert o["cuenta_id"] == cuenta["id"] and o["notas"] == "La mitad de la hucha es tuya"
        meses = (2031 - HOY.year) * 12 + 5 - HOY.month
        assert o["ahorro_mensual"] == round(8000 / meses, 2)
        # Sin cuenta vuelve a mandar lo apuntado a mano
        assert c.patch(f"/api/objetivos/{o['id']}", json={"cuenta_id": None, "ahorrado": 300}).status_code == 200
        o = next(o for o in c.get("/api/planificacion").json()["objetivos"] if o["id"] == o["id"] and o["nombre"] == "Boda con hucha ejemplo")
        assert o["ahorrado"] == 300 and not o["ahorrado_automatico"] and o["cuenta"] is None
        assert c.patch(f"/api/objetivos/{o['id']}", json={"cuenta_id": 999999}).status_code == 404
        assert c.post("/api/objetivos", json={"nombre": "Mal", "cuenta_id": 999999}).status_code == 404
        c.delete(f"/api/objetivos/{o['id']}")
        c.delete(f"/api/cuentas/{cuenta['id']}")


def test_sintesis_y_si_llegas_a_los_objetivos():
    with TestClient(app) as c:
        c.post("/api/objetivos", json={"nombre": "Meta fácil ejemplo", "importe_objetivo": 1000, "fecha_objetivo": "2040-01-01"})
        c.post("/api/objetivos", json={"nombre": "Meta imposible ejemplo", "importe_objetivo": 10_000_000,
                                       "fecha_objetivo": sumar_meses(HOY, 2).isoformat()})
        c.post("/api/objetivos", json={"nombre": "Meta hecha ejemplo", "importe_objetivo": 500, "ahorrado": 600})
        plan = c.get("/api/planificacion").json()
        por_nombre = {o["nombre"]: o for o in plan["objetivos"]}
        assert plan["sintesis"]["ahorro_prevision_mes"] is None and plan["sintesis"]["meses"] == 0
        # Los objetivos con fecha sin pagos cuentan en «Pagos en 12 meses», como en la previsión
        assert plan["objetivos_12_meses"] >= 10_000_000 and plan["pendiente_12_meses"] >= plan["objetivos_12_meses"]
        mes = sumar_meses(HOY, 2).strftime("%Y-%m")
        fila = next(m for m in c.get("/api/prevision").json()["meses"] if m["mes"] == mes)
        assert any(o["concepto"] == "Meta imposible ejemplo" for o in fila["objetivos"])
        assert all(por_nombre[k]["llegas_en"] is None for k in ("Meta fácil ejemplo", "Meta imposible ejemplo", "Meta hecha ejemplo"))
        # Un sueldo enorme para que el ahorro medio sea positivo aunque otros tests dejen pagos previstos grandes
        c.put("/api/prevision/supuestos", json={**SUPUESTOS, "nomina": {**SUPUESTOS["nomina"], "bruto_anual": 2_000_000}})
        meses = c.get("/api/prevision").json()["meses"]
        plan = c.get("/api/planificacion").json()
        por_nombre = {o["nombre"]: o for o in plan["objetivos"]}
        ahorro = plan["sintesis"]["ahorro_prevision_mes"]
        # La media de lo que queda cada mes, sin contar lo que gastarías en los propios objetivos con fecha
        assert ahorro == round(sum(m["neto"] + m["total_objetivos"] for m in meses) / 12, 2)
        assert ahorro > 0 and plan["sintesis"]["meses"] == 12
        assert plan["sintesis"]["ahorro_objetivos_mes"] >= por_nombre["Meta fácil ejemplo"]["ahorro_mensual"] + 5_000_000
        facil, imposible, hecha = (por_nombre[k]["llegas_en"] for k in ("Meta fácil ejemplo", "Meta imposible ejemplo", "Meta hecha ejemplo"))
        assert facil["a_tiempo"] and facil["faltara"] == 0 and facil["mes"] == sumar_meses(INICIO, 1).strftime("%Y-%m")
        assert imposible["a_tiempo"] is False and imposible["faltara"] == round(10_000_000 - ahorro * 2, 2)
        assert hecha is None
        for o in por_nombre.values():
            if o["nombre"].endswith("ejemplo"):
                c.delete(f"/api/objetivos/{o['id']}")
        assert c.get("/api/planificacion").json()["objetivos_12_meses"] < 10_000_000


def test_escenario_cambia_la_prevision_sin_guardarla():
    with TestClient(app) as c:
        c.put("/api/prevision/supuestos", json=SUPUESTOS)
        mes = _mes_normal().strftime("%Y-%m")
        base = next(m for m in c.get("/api/prevision").json()["meses"] if m["mes"] == mes)
        assert base["facturado"] == 8800 and base["cobros"] == 9088 and base["gastos"] == 2000
        d = c.get("/api/prevision?tarifa_pct=10").json()
        m = next(m for m in d["meses"] if m["mes"] == mes)
        assert m["facturado"] == 9680 and m["cobros"] == 9996.8 and d["escenario"] == {"tarifa_pct": 10.0}
        assert d["anios"][-1]["cuota"] > c.get("/api/prevision").json()["anios"][-1]["cuota"]  # más renta
        m = next(m for m in c.get("/api/prevision?dias_mes=10").json()["meses"] if m["mes"] == mes)
        assert m["facturado"] == 4400
        d = c.get("/api/prevision?gasto_habitual=500&ahorro_extra_mes=200").json()
        m = next(m for m in d["meses"] if m["mes"] == mes)
        assert m["gastos"] == 700 and d["escenario"] == {"gasto_habitual": 500.0, "ahorro_extra_mes": 200.0}
        assert d["meses"][0]["gastos"] >= 200  # el extra también se aparta este mes
        assert c.get("/api/prevision?tarifa_pct=200").status_code == 400
        assert c.get("/api/prevision?dias_mes=-1").status_code == 400
        # Nada se guarda
        d = c.get("/api/prevision").json()
        assert d["escenario"] is None and next(m for m in d["meses"] if m["mes"] == mes)["facturado"] == 8800
        assert d["supuestos"]["clientes"][0]["tarifa_hora"] == 30


def test_las_vacaciones_restan_dias_a_los_meses_que_vienen():
    mes = _mes_normal()
    laborables = [mes + timedelta(days=i) for i in range(31) if (mes + timedelta(days=i)).month == mes.month
                  and (mes + timedelta(days=i)).weekday() < 5][:5]
    finde = next(mes + timedelta(days=i) for i in range(7) if (mes + timedelta(days=i)).weekday() == 5)
    with TestClient(app) as c:
        c.put("/api/prevision/supuestos", json=SUPUESTOS)
        r = c.put("/api/facturacion/dias", json={"dias": [d.isoformat() for d in laborables] + [finde.isoformat()],
                                                 "tipo": "vacaciones"})
        assert r.status_code == 200
        d = c.get("/api/prevision").json()
        fila = next(m for m in d["meses"] if m["mes"] == mes.strftime("%Y-%m"))
        assert fila["facturado"] == 8800 - 5 * 8 * 30 - 5 * 8 * 25  # el sábado no cuenta
        assert d["dias_fuera"][mes.strftime("%Y-%m")] == 5 and d["clientes"][0]["dias_mes"] == 20
        # Los días planificados a mano para ese mes mandan
        c.put("/api/prevision/dias", json={"cliente": "Cliente A", "mes": mes.strftime("%Y-%m"), "dias": 10})
        fila = next(m for m in c.get("/api/prevision").json()["meses"] if m["mes"] == mes.strftime("%Y-%m"))
        assert fila["facturado"] == 30 * 8 * 10 + 25 * 8 * 15
        c.put("/api/prevision/dias", json={"cliente": "Cliente A", "mes": mes.strftime("%Y-%m"), "dias": None})
        c.put("/api/facturacion/dias", json={"dias": [d.isoformat() for d in laborables] + [finde.isoformat()], "tipo": None})
        assert mes.strftime("%Y-%m") not in c.get("/api/prevision").json()["dias_fuera"]


def test_la_renta_del_anio_pasado_sigue_en_anios_hasta_presentarla(monkeypatch):
    """Entre enero y junio toca presentar la renta del año pasado: sale en `anios` aunque no esté en la ventana."""
    from datetime import date as fecha_real
    from finanzas import prevision

    class Marzo(fecha_real):
        @classmethod
        def today(cls):
            return cls(2013, 3, 15)

    monkeypatch.setattr(prevision, "date", Marzo)
    with TestClient(app) as c:
        s = db.SessionLocal()
        assert [a["anio"] for a in prevision.calcular(s, 12)["anios"]] == [2012, 2013, 2014]
        s.close()
        decl = c.post("/api/declaraciones", json={"modelo": "100", "ejercicio": 2012, "periodo": "0A", "resultado": "ingresar",
                                                  "importe": 10, "fecha_presentacion": "2013-05-02"})
        assert decl.status_code == 200, decl.text
        s = db.SessionLocal()
        assert [a["anio"] for a in prevision.calcular(s, 12)["anios"]] == [2013, 2014]  # ya presentada: fuera
        s.close()
        decl_id = next(d["id"] for d in c.get("/api/declaraciones").json()["declaraciones"]
                       if d["modelo"] == "100" and d["ejercicio"] == 2012)
        c.delete(f"/api/declaraciones/{decl_id}")
