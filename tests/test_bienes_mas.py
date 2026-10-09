"""Bienes (flujo F4): editar la hipoteca y su cuadro desde el saldo real, simulador de amortización anticipada,
préstamos sueltos, escriturar la obra nueva, cobros del alquiler, avisos, vender con % de propiedad, editar gastos y
valoraciones e importar JSON que actualiza. Datos inventados, casi todos en 2011 y 2012 para no mezclarse."""
import json
from datetime import date, timedelta
from decimal import Decimal as D

from fastapi.testclient import TestClient
from sqlalchemy import select

from finanzas import bienes, db
from finanzas.hipoteca import cuadro_amortizacion, cuadro_desde, cuota_mensual, intereses_anio, saldo_pendiente
from finanzas.main import app
from finanzas.models import Categoria, Cuenta, Deuda, Movimiento

HOY = date.today()


def _ficha(c, activo_id):
    return next(i for i in c.get("/api/inmuebles").json()["inmuebles"] if i["id"] == activo_id)


def _subir(c, datos):
    return c.post("/api/importar/datos", files={"fichero": ("datos.json", json.dumps(datos).encode(), "application/json")})


def _borrar_cuenta(s, cuenta_id):
    s.query(Movimiento).filter(Movimiento.cuenta_id == cuenta_id).delete()
    s.delete(s.get(Cuenta, cuenta_id))
    s.commit()


# --- Cuadro desde el saldo real -------------------------------------------------------

def test_cuadro_desde_el_saldo_real():
    d = Deuda(nombre="H", capital_inicial=D("100000"), tipo_interes_anual=D("3"), fecha_inicio=date(2011, 1, 15), plazo_meses=300)
    teorico = cuadro_amortizacion(d)
    assert len(teorico) == 300 and teorico[-1].pendiente == 0
    # Sin saldo real: el pendiente y los intereses salen del cuadro teórico
    assert saldo_pendiente(d, date(2021, 1, 15)) == teorico[119].pendiente
    sin_manual = intereses_anio(d, 2021)
    # Con un saldo real menor en esa fecha, quedan 180 cuotas: se recalcula la cuota y acaba en la misma fecha
    desde = cuadro_desde(d, D("50000"), date(2021, 1, 15))
    assert len(desde) == 180 and desde[0].numero == 121 and desde[-1].fecha == teorico[-1].fecha and desde[-1].pendiente == 0
    assert desde[0].cuota == cuota_mensual(D("50000"), D("3"), 180) < teorico[0].cuota
    # Manteniendo la cuota de siempre se acaba antes
    misma_cuota = cuadro_desde(d, D("50000"), date(2021, 1, 15), cuota=teorico[0].cuota)
    assert len(misma_cuota) < 180 and misma_cuota[-1].pendiente == 0
    d.saldo_pendiente_manual, d.saldo_fecha = D("50000"), date(2021, 1, 15)
    assert saldo_pendiente(d, date(2021, 1, 15)) == 50000
    assert saldo_pendiente(d, date(2021, 2, 20)) == desde[0].pendiente < 50000
    assert saldo_pendiente(d, date(2020, 6, 1)) == teorico[111].pendiente  # antes del saldo real, el teórico (la de junio aún no)
    con_manual = intereses_anio(d, 2021)
    assert 0 < con_manual < sin_manual
    assert con_manual == teorico[119].intereses + sum(c.intereses for c in desde[:11])


def test_editar_hipoteca_y_cuadro_por_anios():
    with TestClient(app) as c:
        piso = c.post("/api/inmuebles", json={"nombre": "Piso F4 saldo", "uso": "alquiler", "precio_compra": 90000}).json()["id"]
        firma = date(HOY.year - 7, HOY.month, 28)
        c.post(f"/api/inmuebles/{piso}/hipotecas", json={"nombre": "Hipoteca F4", "entidad": "Banco F4", "capital_inicial": 50000,
                                                           "tipo_interes_anual": 2, "fecha_inicio": firma.isoformat(), "plazo_meses": 240})
        [h] = _ficha(c, piso)["hipotecas"]
        assert h["saldo_pendiente_manual"] is None and h["cuotas_restantes"] > 100 and h["fin"] and h["intereses_restantes"] > 0
        teorico = h["pendiente"]
        cuadro = c.get(f"/api/deudas/{h['id']}/cuadro").json()
        assert cuadro["resumen"]["cuotas_restantes"] == h["cuotas_restantes"] and not cuadro["resumen"]["desde_saldo_real"]
        assert sum(a["cuotas"] for a in cuadro["anios"]) == h["cuotas_restantes"] and cuadro["anios"][-1]["pendiente_fin"] == 0
        assert abs(sum(a["amortizado"] for a in cuadro["anios"]) - teorico) < 0.05

        r = c.patch(f"/api/deudas/{h['id']}", json={"saldo_pendiente_manual": 20000, "tipo_interes_anual": 3.5, "entidad": "Otro banco"})
        assert r.status_code == 200
        [h2] = _ficha(c, piso)["hipotecas"]
        assert h2["saldo_pendiente_manual"] == 20000 and h2["saldo_fecha"] == HOY.isoformat() and h2["entidad"] == "Otro banco"
        assert h2["pendiente"] == 20000 and h2["tipo_interes_anual"] == 3.5
        assert h2["intereses_anio"] <= h["intereses_anio"] * 3.5 / 2  # desde el saldo real, no desde el capital
        cuadro2 = c.get(f"/api/deudas/{h['id']}/cuadro").json()
        assert cuadro2["resumen"]["pendiente"] == 20000 and cuadro2["resumen"]["desde_saldo_real"]
        assert cuadro2["resumen"]["cuotas_restantes"] == h["cuotas_restantes"]  # mismo fin: cuota recalculada
        assert cuadro2["resumen"]["cuota"] < h["cuota"]

        # Quitar el saldo real vuelve al cuadro teórico
        assert c.patch(f"/api/deudas/{h['id']}", json={"saldo_pendiente_manual": None, "tipo_interes_anual": 2}).status_code == 200
        [h3] = _ficha(c, piso)["hipotecas"]
        assert h3["saldo_pendiente_manual"] is None and h3["saldo_fecha"] is None and h3["pendiente"] == teorico
        assert c.patch(f"/api/deudas/{h['id']}", json={"plazo_meses": 0}).status_code == 400
        assert c.patch(f"/api/deudas/{h['id']}", json={"activo_id": 999999}).status_code == 404
        assert c.delete(f"/api/inmuebles/{piso}").status_code == 200


# --- Simulador de amortización anticipada --------------------------------------------

def test_simulador_reduce_plazo_o_cuota():
    with TestClient(app) as c:
        piso = c.post("/api/inmuebles", json={"nombre": "Piso F4 simula", "uso": "alquiler", "precio_compra": 90000}).json()["id"]
        firma = date(HOY.year - 3, HOY.month, 28)
        c.post(f"/api/inmuebles/{piso}/hipotecas", json={"capital_inicial": 100000, "tipo_interes_anual": 3,
                                                           "fecha_inicio": firma.isoformat(), "plazo_meses": 300})
        [h] = _ficha(c, piso)["hipotecas"]
        plazo = c.get(f"/api/deudas/{h['id']}/simular?importe=10000&modo=plazo").json()
        assert plazo["ahorro_intereses"] > 0 and plazo["meses_menos"] > 12 and plazo["nueva_cuota"] == plazo["cuota_actual"]
        assert plazo["nuevo_fin"] < plazo["fin_actual"] and plazo["pendiente_hoy"] == h["pendiente"]
        assert abs(plazo["intereses_restantes"] - plazo["intereses_con"] - plazo["ahorro_intereses"]) < 0.01
        cuota = c.get(f"/api/deudas/{h['id']}/simular?importe=10000&modo=cuota").json()
        assert cuota["meses_menos"] == 0 and cuota["nueva_cuota"] < cuota["cuota_actual"] and cuota["nuevo_fin"] == plazo["fin_actual"]
        assert 0 < cuota["ahorro_intereses"] < plazo["ahorro_intereses"]
        # Piso alquilado: los intereses se deducen, el ahorro real es menor (sin previsión no se conoce el tipo marginal)
        assert plazo["fiscal"]["deducible"] and plazo["fiscal"]["tipo_marginal"] is None and plazo["comparativa"] is None
        c.put("/api/prevision/supuestos", json={"nomina": {"bruto_anual": 40000, "pagas": 12}})
        con_renta = c.get(f"/api/deudas/{h['id']}/simular?importe=10000&modo=plazo").json()["fiscal"]
        assert con_renta["tipo_marginal"] > 0 and 0 < con_renta["ahorro_neto"] < plazo["ahorro_intereses"]
        c.put("/api/prevision/supuestos", json={})
        # Con una cuenta de Indexa con rentabilidad esperada, compara con invertirlo
        s = db.SessionLocal()
        indexa = Cuenta(nombre="Indexa F4", tipo="inversion", origen="indexa", detalle=json.dumps({"rentabilidad_esperada": 5.0}))
        s.add(indexa)
        s.commit()
        comp = c.get(f"/api/deudas/{h['id']}/simular?importe=10000&modo=plazo").json()["comparativa"]
        assert comp["cuenta"] == "Indexa F4" and comp["rentabilidad_esperada"] == 5 and comp["rendiria"] > 0
        assert comp["rendiria_neto"] < comp["rendiria"] and comp["mejor"] in ("invertir", "amortizar")
        s.delete(s.get(Cuenta, indexa.id))
        s.commit()
        s.close()
        # Errores claros
        assert c.get(f"/api/deudas/{h['id']}/simular?importe=0").status_code == 400
        assert c.get(f"/api/deudas/{h['id']}/simular?importe=999999").status_code == 400
        assert c.get(f"/api/deudas/{h['id']}/simular?importe=100&modo=raro").status_code == 400
        # Vivienda habitual: sin deducción, el ahorro es íntegro
        c.patch(f"/api/inmuebles/{piso}", json={"uso": "vivienda_habitual"})
        fiscal = c.get(f"/api/deudas/{h['id']}/simular?importe=5000").json()["fiscal"]
        assert not fiscal["deducible"] and fiscal["ahorro_neto"] > 0
        assert c.delete(f"/api/inmuebles/{piso}").status_code == 200


# --- Préstamos sin inmueble ----------------------------------------------------------

def test_prestamo_suelto_resta_en_el_patrimonio():
    with TestClient(app) as c:
        antes = c.get("/api/resumen").json()["pasivos"]
        assert c.post("/api/deudas", json={"nombre": "X", "tipo": "hipoteca", "capital_inicial": 1000, "fecha_inicio": "2011-01-01",
                                           "plazo_meses": 12}).status_code == 400
        firma = HOY - timedelta(days=730)
        r = c.post("/api/deudas", json={"nombre": "Préstamo coche F4", "entidad": "Financiera F4", "tipo": "prestamo", "capital_inicial": 12000,
                                        "tipo_interes_anual": 4, "fecha_inicio": firma.isoformat(), "plazo_meses": 60})
        assert r.status_code == 200
        deuda_id = r.json()["id"]
        p = next(d for d in c.get("/api/deudas").json() if d["id"] == deuda_id)
        assert p["tipo"] == "prestamo" and p["activo"] is None and 0 < p["pendiente"] < 12000 and p["cuota"] > 0 and p["fin"]
        res = c.get("/api/resumen").json()
        linea = next(l for l in res["lineas_pasivo"] if l["nombre"] == "Préstamo coche F4")
        assert linea["grupo"] == "Préstamo" and abs(res["pasivos"] - antes - p["pendiente"]) < 0.05
        # Un préstamo también tiene cuadro y simulador
        assert c.get(f"/api/deudas/{deuda_id}/cuadro").json()["resumen"]["cuotas_restantes"] == p["cuotas_restantes"]
        assert c.get(f"/api/deudas/{deuda_id}/simular?importe=1000&modo=plazo").json()["ahorro_intereses"] > 0
        assert c.delete(f"/api/deudas/{deuda_id}").status_code == 200
        assert not any(d["id"] == deuda_id for d in c.get("/api/deudas").json())


# --- Escriturar la obra nueva -------------------------------------------------------

def test_escriturar_la_obra_nueva():
    with TestClient(app) as c:
        obra = c.post("/api/inmuebles", json={"nombre": "Obra F4", "tipo": "inmueble_en_construccion", "precio_compra": 200000}).json()["id"]
        pagos = [c.post("/api/pagos", json={"concepto": concepto, "fecha": fecha, "importe": importe, "activo_id": obra, "pagado": pagado}).json()
                 for concepto, fecha, importe, pagado in (("Reserva", "2011-01-10", 6000, True), ("Entregas", "2011-06-01", 24000, False),
                                                           ("Llave", "2012-03-01", 170000, False), ("Muebles", "2012-09-01", 5000, False))]
        esc = c.post(f"/api/inmuebles/{obra}/gastos-escritura", json={"fecha": "2012-03-01", "precio": 200000}).json()
        assert esc["importe"] == 4200 and esc["constantes"]["ajd_pct"] == 1.5 and esc["constantes"]["notaria"] == 1200
        c.post(f"/api/inmuebles/{obra}/hipotecas", json={"nombre": "Hipoteca obra F4", "capital_inicial": 170000, "tipo_interes_anual": 3,
                                                           "fecha_inicio": "2012-06-01", "plazo_meses": 300})
        r = c.post(f"/api/inmuebles/{obra}/escriturar", json={"fecha": "2012-03-01"})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "precio_compra": 200000, "gastos_compra": 4200, "pagos_marcados": 3, "hipotecas_actualizadas": 1}
        ficha = _ficha(c, obra)
        assert ficha["tipo"] == "inmueble" and ficha["uso"] == "vivienda_habitual" and ficha["fecha_compra"] == "2012-03-01"
        assert ficha["precio_compra"] == 200000 and ficha["gastos_compra"] == 4200
        assert [p["pagado"] for p in ficha["pagos"]] == [True, True, True, True, False]  # los muebles son de después
        assert ficha["hipotecas"][0]["fecha_inicio"] == "2012-03-01" and not ficha["hipotecas"][0]["futura"]
        assert c.post(f"/api/inmuebles/{obra}/escriturar", json={"fecha": "2012-03-01"}).status_code == 400
        # Con precio dado, manda ese precio
        otra = c.post("/api/inmuebles", json={"nombre": "Obra F4 bis", "tipo": "inmueble_en_construccion"}).json()["id"]
        assert c.post(f"/api/inmuebles/{otra}/escriturar", json={"fecha": "2012-05-01", "precio_total": 150000}).json()["precio_compra"] == 150000
        for a in (obra, otra):
            c.delete(f"/api/inmuebles/{a}")
        for p in ficha["pagos"]:
            c.delete(f"/api/pagos/{p['id']}")
        assert len(pagos) == 4


# --- ¿Ha pagado el inquilino? y avisos --------------------------------------------------

def test_cobros_del_alquiler_cuadran_o_no():
    with TestClient(app) as c:
        piso = c.post("/api/inmuebles", json={"nombre": "Piso F4 cobros", "uso": "alquiler", "precio_compra": 90000}).json()["id"]
        c.post(f"/api/inmuebles/{piso}/contratos", json={"inquilino": "Inquilina F4", "fecha_inicio": (HOY - timedelta(days=400)).isoformat(),
                                                           "renta_mensual": 777})
        s = db.SessionLocal()
        cuenta = Cuenta(nombre="Cuenta cobros F4")
        s.add(cuenta)
        s.flush()
        categoria = s.scalar(select(Categoria).where(Categoria.nombre == "Alquiler cobrado"))
        este_mes, mes_pasado = HOY.replace(day=1), (HOY.replace(day=1) - timedelta(days=1)).replace(day=1)
        s.add_all([Movimiento(cuenta_id=cuenta.id, fecha=este_mes, concepto="TRANSFERENCIA ALQUILER F4", importe=D("777"), huella="f4-cobro-1"),
                   Movimiento(cuenta_id=cuenta.id, fecha=mes_pasado + timedelta(days=4), concepto="ALQUILER F4 CORTO", importe=D("700"),
                              huella="f4-cobro-2", categoria_id=categoria.id)])
        s.commit()
        [contrato] = _ficha(c, piso)["contratos"]
        cobros = contrato["cobros"]
        assert len(cobros) == 3 and all(x["renta"] == 777 for x in cobros)
        assert cobros[-1]["mes"] == este_mes.strftime("%Y-%m") and cobros[-1]["fecha"] == este_mes.isoformat() and cobros[-1]["cuadra"]
        assert cobros[-2]["importe"] == 700 and cobros[-2]["fecha"] and not cobros[-2]["cuadra"]  # llegó, pero no la renta entera
        assert cobros[-3]["fecha"] is None and cobros[-3]["importe"] is None and not cobros[-3]["cuadra"]
        _borrar_cuenta(s, cuenta.id)
        s.close()
        c.delete(f"/api/inmuebles/{piso}")


class _Hoy2011(date):
    @classmethod
    def today(cls):
        return date(2011, 10, 15)


def test_avisos_de_alquiler_contratos_e_hipoteca(monkeypatch):
    monkeypatch.setattr(bienes, "date", _Hoy2011)
    with TestClient(app) as c:
        piso = c.post("/api/inmuebles", json={"nombre": "Piso F4 avisos", "uso": "alquiler", "precio_compra": 90000}).json()["id"]
        c.post(f"/api/inmuebles/{piso}/contratos", json={"inquilino": "Inquilino F4", "fecha_inicio": "2010-11-01", "renta_mensual": 500})
        c.post(f"/api/inmuebles/{piso}/hipotecas", json={"capital_inicial": 100000, "tipo_interes_anual": 3, "fecha_inicio": "2009-01-10",
                                                           "plazo_meses": 300})
        otro = c.post("/api/inmuebles", json={"nombre": "Piso F4 fin", "uso": "alquiler", "precio_compra": 90000}).json()["id"]
        c.post(f"/api/inmuebles/{otro}/contratos", json={"fecha_inicio": "2009-01-01", "fecha_fin": "2011-11-30", "renta_mensual": 600})
        s = db.SessionLocal()
        cuenta = Cuenta(nombre="Cuenta avisos F4")
        s.add(cuenta)
        s.flush()
        hipoteca = s.scalar(select(Categoria).where(Categoria.nombre == "Cuota hipoteca"))
        s.add_all([Movimiento(cuenta_id=cuenta.id, fecha=date(2011, m, 10), concepto="RECIBO PRESTAMO HIPOTECARIO", importe=D("-520"),
                              huella=f"f4-cuota-{m}", categoria_id=hipoteca.id) for m in (8, 9, 10)]
                  + [Movimiento(cuenta_id=cuenta.id, fecha=date(2011, 10, 3), concepto="COMPRA", importe=D("-20"), huella="f4-compra"),
                     Movimiento(cuenta_id=cuenta.id, fecha=date(2011, 9, 5), concepto="ALQUILER", importe=D("500"), huella="f4-alq-sep"),
                     Movimiento(cuenta_id=cuenta.id, fecha=date(2011, 10, 6), concepto="ALQUILER OTRO", importe=D("600"), huella="f4-alq-otro")])
        s.commit()
        textos = [a["texto"] for a in bienes.avisos(s)]
        assert "El alquiler de octubre aún no ha llegado (Inquilino F4)." in textos
        assert "El contrato de Inquilino F4 cumple 1 año el 01/11: puedes actualizar la renta." in textos
        assert "El contrato de Piso F4 fin termina el 30/11/2011." in textos
        assert "Tu hipoteca cobra 520 € y la app supone 474 €: actualiza el tipo o el pendiente." in textos
        assert len(textos) == 4  # el otro piso sí ha cobrado octubre y no cumple años
        # Si llega el alquiler, se va el aviso; si la renta se actualizó hace poco, no toca subirla
        s.add(Movimiento(cuenta_id=cuenta.id, fecha=date(2011, 10, 12), concepto="ALQUILER", importe=D("520"), huella="f4-alq-oct"))
        s.commit()
        [contrato] = _ficha(c, piso)["contratos"]
        c.post(f"/api/contratos/{contrato['id']}/rentas", json={"desde": "2011-06-01", "renta_mensual": 520})
        textos = [a["texto"] for a in bienes.avisos(s)]
        assert not any("alquiler de octubre" in t or "cumple" in t for t in textos) and len(textos) == 2
        _borrar_cuenta(s, cuenta.id)
        s.close()
        for a in (piso, otro):
            c.delete(f"/api/inmuebles/{a}")


# --- Vender o seguir alquilando con parte de la propiedad ----------------------------------

def test_vender_con_porcentaje_de_propiedad():
    with TestClient(app) as c:
        piso = c.post("/api/inmuebles", json={"nombre": "Piso F4 mitad", "uso": "alquiler", "precio_compra": 100000, "gastos_compra": 5000,
                                              "fecha_compra": "2011-01-01", "porcentaje_propiedad": 50, "valor_catastral": 50000,
                                              "valor_catastral_construccion": 30000}).json()["id"]
        c.post(f"/api/inmuebles/{piso}/valoraciones", json={"fecha": "2012-01-01", "valor": 200000})
        c.post(f"/api/inmuebles/{piso}/contratos", json={"fecha_inicio": "2011-02-01", "renta_mensual": 600})
        c.post(f"/api/inmuebles/{piso}/hipotecas", json={"capital_inicial": 60000, "tipo_interes_anual": 2, "fecha_inicio": "2011-01-01",
                                                           "plazo_meses": 360})
        ficha = _ficha(c, piso)
        assert ficha["valor"] == 100000 and ficha["coste"] == 52500 and ficha["plusvalia_latente"] == 47500
        assert ficha["deuda_compra"] == 60000 and ficha["valoraciones"][0]["deuda"] < 60000
        assert c.get("/api/inmuebles").json()["constantes"] == {"gastos_venta_pct": 3, "ajd_pct": 1.5, "notaria": 1200, "amortizacion_pct": 3}
        v = c.get(f"/api/inmuebles/{piso}/vender").json()
        assert v["precio_venta"] == 100000 and v["precio_entero"] == 200000 and v["porcentaje_propiedad"] == 50
        assert v["gastos_venta_pct"] == 3 and v["gastos_venta"] == 3000 and v["valor_adquisicion"] < 52500
        assert v["hipoteca_pendiente"] == ficha["deuda"] and any("50 %" in nota for nota in v["notas"])
        assert v["alquiler_tributa"] is not None and v["tipo_marginal"] > 0 and v["constantes"]["amortizacion_pct"] == 3
        v2 = c.get(f"/api/inmuebles/{piso}/vender?precio=300000&gastos_venta_pct=5").json()
        assert v2["precio_venta"] == 150000 and v2["precio_entero"] == 300000 and v2["gastos_venta"] == 7500 and v2["gastos_venta_pct"] == 5
        assert v2["valor_detalle"] == "el precio que has puesto"
        c.delete(f"/api/inmuebles/{piso}")


# --- Gastos, valoraciones, contratos y cambios de renta editables ---------------------------

def test_editar_gasto_valoracion_contrato_y_borrar_cambio_de_renta():
    with TestClient(app) as c:
        piso = c.post("/api/inmuebles", json={"nombre": "Piso F4 edita", "uso": "alquiler", "precio_compra": 90000, "notas": "Hola"}).json()["id"]
        assert _ficha(c, piso)["notas"] == "Hola"
        assert c.post(f"/api/inmuebles/{piso}/gastos", json={"fecha": "2011-05-05", "tipo": "raro", "importe": 1}).status_code == 400
        c.post(f"/api/inmuebles/{piso}/gastos", json={"fecha": "2011-05-05", "tipo": "ibi", "importe": 300})
        c.post(f"/api/inmuebles/{piso}/valoraciones", json={"fecha": "2011-06-01", "valor": 95000})
        c.post(f"/api/inmuebles/{piso}/contratos", json={"inquilino": "A", "fecha_inicio": "2011-03-01", "renta_mensual": 500})
        ficha = _ficha(c, piso)
        [g], [v], [contrato] = ficha["gastos"], ficha["valoraciones"], ficha["contratos"]
        assert c.patch(f"/api/gastos-inmueble/{g['id']}", json={"tipo": "raro"}).status_code == 400
        assert c.patch(f"/api/gastos-inmueble/{g['id']}", json={"tipo": "comunidad", "importe": 350, "concepto": "Derrama"}).status_code == 200
        assert c.patch(f"/api/valoraciones/{v['id']}", json={"valor": 99000, "fecha": "2011-07-01"}).status_code == 200
        assert c.patch(f"/api/contratos/{contrato['id']}", json={"fecha_inicio": "2011-02-01", "renta_mensual": 480}).status_code == 200
        c.post(f"/api/contratos/{contrato['id']}/rentas", json={"desde": "2012-02-01", "renta_mensual": 510})
        ficha = _ficha(c, piso)
        assert ficha["gastos"][0]["tipo"] == "comunidad" and ficha["gastos"][0]["importe"] == 350 and ficha["gastos"][0]["concepto"] == "Derrama"
        assert ficha["valoraciones"][0]["valor"] == 99000 and ficha["valoraciones"][0]["fecha"] == "2011-07-01"
        [contrato] = ficha["contratos"]
        assert contrato["fecha_inicio"] == "2011-02-01" and contrato["renta_inicial"] == 480 and contrato["renta_actual"] == 510
        [cambio] = contrato["cambios"]
        assert cambio["id"] and cambio["renta"] == 510
        assert c.delete(f"/api/rentas/{cambio['id']}").status_code == 200
        assert _ficha(c, piso)["contratos"][0]["cambios"] == []
        # Editar el tipo del bien, incluido «otro bien»
        assert c.patch(f"/api/inmuebles/{piso}", json={"tipo": "raro"}).status_code == 400
        assert c.patch(f"/api/inmuebles/{piso}", json={"tipo": "otro", "uso": "otro"}).status_code == 200
        assert _ficha(c, piso)["tipo"] == "otro"
        assert any(l["nombre"] == "Piso F4 edita" and l["grupo"] == "Otros" for l in c.get("/api/resumen").json()["lineas_activo"])
        assert c.post("/api/inmuebles", json={"nombre": "Nada F4", "tipo": "cohete"}).status_code == 400
        c.delete(f"/api/inmuebles/{piso}")


# --- Importar JSON actualiza lo que ya existe ---------------------------------------------

def test_importar_json_actualiza_hipoteca_valoraciones_pagos_y_contrato():
    datos = {"activos": [{"nombre": "Piso F4 json", "tipo": "inmueble_en_construccion", "uso": "otro", "precio_compra": 100000,
                          "hipotecas": [{"nombre": "Hipoteca F4 json", "capital_inicial": 80000, "tipo_interes_anual": 3,
                                         "fecha_inicio": "2011-01-01", "plazo_meses": 300}],
                          "pagos": [{"concepto": "Entrega", "fecha": "2011-02-01", "importe": 10000}],
                          "contratos": [{"fecha_inicio": "2011-03-01", "renta_mensual": 500}]}]}
    with TestClient(app) as c:
        assert "añadido" in _subir(c, datos).json()["mensajes"][0]
        datos["activos"][0].update({
            "tipo": "inmueble", "uso": "alquiler",
            "hipotecas": [{"nombre": "Hipoteca F4 json", "tipo_interes_anual": 2, "saldo_pendiente_manual": 70000, "saldo_fecha": "2012-01-01"},
                          {"nombre": "Segunda F4 json", "capital_inicial": 5000, "tipo_interes_anual": 5, "fecha_inicio": "2012-01-01", "plazo_meses": 24}],
            "valoraciones": [{"fecha": "2012-01-01", "valor": 120000}],
            "pagos": [{"concepto": "Entrega", "fecha": "2011-02-01", "importe": 12000, "pagado": True},
                      {"concepto": "Llave", "fecha": "2012-06-01", "importe": 50000}],
            "contratos": [{"fecha_inicio": "2011-03-01", "renta_mensual": 500, "inquilino": "Pepe", "fecha_fin": "2012-02-28"}]})
        [mensaje] = _subir(c, datos).json()["mensajes"]
        for trozo in ("ya existía", "actualizado", "tipo", "uso", "hipoteca Hipoteca F4 json", "hipoteca Segunda F4 json (nueva)",
                      "1 valoraciones", "2 pagos", "contrato"):
            assert trozo in mensaje, (trozo, mensaje)
        _subir(c, datos)  # dos veces no duplica
        piso = next(i for i in c.get("/api/inmuebles").json()["inmuebles"] if i["nombre"] == "Piso F4 json")
        assert piso["tipo"] == "inmueble" and piso["uso"] == "alquiler" and len(piso["valoraciones"]) == 1 and len(piso["pagos"]) == 2
        hip = {h["nombre"]: h for h in piso["hipotecas"]}
        assert len(hip) == 2 and hip["Hipoteca F4 json"]["tipo_interes_anual"] == 2 and hip["Hipoteca F4 json"]["capital_inicial"] == 80000
        assert hip["Hipoteca F4 json"]["saldo_pendiente_manual"] == 70000 and hip["Hipoteca F4 json"]["saldo_fecha"] == "2012-01-01"
        entrega = next(p for p in piso["pagos"] if p["concepto"] == "Entrega")
        assert entrega["importe"] == 12000 and entrega["pagado"]
        [contrato] = piso["contratos"]
        assert contrato["inquilino"] == "Pepe" and contrato["fecha_fin"] == "2012-02-28"
        assert "sin cambios" in _subir(c, {"activos": [{"nombre": "Piso F4 json"}]}).json()["mensajes"][0]
        for p in piso["pagos"]:
            c.delete(f"/api/pagos/{p['id']}")
        c.delete(f"/api/inmuebles/{piso['id']}")
