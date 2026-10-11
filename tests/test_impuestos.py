"""Impuestos y Hacienda: editar declaraciones, duplicados, pagado por año, ahorro fiscal con lo guardado,
exención del 130 en los avisos, calendario con pagos y llamadas, pluriactividad con nóminas reales y la base
de cotización equivalente. Datos inventados en 2011-2012 para no mezclarse con otros tests."""
from datetime import date, datetime, timedelta
from decimal import Decimal as D

from fastapi.testclient import TestClient
from sqlalchemy import delete

from finanzas import avisos, calendario, db, hacienda
from finanzas.fiscal import autonomo, reta
from finanzas.main import app
from finanzas.models import (Cliente, ConexionBancaria, Declaracion, Factura, InversionPrivada, Nomina, Objetivo,
                             PagoPrevisto)


def _limpiar(*modelos_y_filtros):
    with db.SessionLocal() as s:
        for modelo, filtro in modelos_y_filtros:
            s.execute(delete(modelo).where(filtro))
        s.commit()


def test_editar_declaracion_y_duplicados():
    with TestClient(app) as c:
        try:
            # El 303 del 1T llegó de su justificante PDF; apuntarlo otra vez a mano doblaría lo pagado
            with db.SessionLocal() as s:
                s.add(Declaracion(modelo="303", ejercicio=2011, periodo="1T", importe=D("400"), justificante="J2011"))
                s.commit()
            base = {"modelo": "303", "ejercicio": 2011, "periodo": "1T", "resultado": "ingresar", "importe": 50}
            r = c.post("/api/declaraciones", json=base)
            assert r.status_code == 409 and "complementaria" in r.json()["detail"]
            assert c.post("/api/declaraciones", json={**base, "complementaria": True}).status_code == 200
            d = c.get("/api/declaraciones").json()
            del_2011 = [x for x in d["declaraciones"] if x["ejercicio"] == 2011]
            assert sorted(x["importe"] for x in del_2011) == [50, 400]
            assert next(x for x in del_2011 if x["importe"] == 50)["notas"] == "Complementaria"
            # A mano no caben dos iguales sin justificante: se edita la que hay
            r = c.post("/api/declaraciones", json={**base, "complementaria": True})
            assert r.status_code == 409 and "edita" in r.json()["detail"]

            # Editar: solo cambia lo que llega, y el signo sigue al resultado
            uno = next(x for x in del_2011 if x["importe"] == 400)
            r = c.patch(f"/api/declaraciones/{uno['id']}", json={"importe": 410, "notas": " revisada ", "fecha_presentacion": "2011-04-15"})
            assert r.status_code == 200 and r.json()["importe"] == 410
            r = c.patch(f"/api/declaraciones/{uno['id']}", json={"resultado": "devolver"})
            assert r.json()["importe"] == -410
            x = next(x for x in c.get("/api/declaraciones").json()["declaraciones"] if x["id"] == uno["id"])
            assert x["notas"] == "revisada" and x["fecha_presentacion"] == "2011-04-15" and x["resultado"] == "devolver"
            assert c.patch(f"/api/declaraciones/{uno['id']}", json={"resultado": "inventado"}).status_code == 400
            assert c.patch("/api/declaraciones/999999", json={"importe": 1}).status_code == 404

            # Por año: pagado, devuelto, neto y el desglose por modelo
            c.post("/api/declaraciones", json={"modelo": "100", "ejercicio": 2011, "periodo": "0A", "resultado": "devolver", "importe": 300})
            c.post("/api/declaraciones", json={"modelo": "130", "ejercicio": 2011, "periodo": "2T", "importe": 120})
            a = next(x for x in c.get("/api/declaraciones").json()["por_anio"] if x["ejercicio"] == 2011)
            assert a["pagado"] == 170 and a["devuelto"] == 710 and a["neto"] == -540
            assert a["por_modelo"] == {"303": -360, "130": 120, "100": -300}
        finally:
            _limpiar((Declaracion, Declaracion.ejercicio == 2011))


def test_ahorro_fiscal_parte_de_lo_guardado():
    with TestClient(app) as c:
        try:
            c.put("/api/prevision/supuestos", json={"nomina": {"bruto_anual": 40000, "pagas": 14}})
            c.put("/api/hacienda/supuestos", json={"aportacion_pensiones_anio": 1500})
            h = c.get("/api/hacienda").json()
            assert "debes_hoy" not in h["hucha"] and h["supuestos"]["aportacion_pensiones_anio"] == 1500
            # Simular lo mismo que hay guardado no cambia nada; quitarlo sube la cuota
            igual = c.get("/api/hacienda/ahorro?pensiones=1500").json()
            assert igual["ahorro"] == 0 and igual["cuota_sin"] == igual["cuota_con"] == h["renta"]["cuota"]
            assert igual["reduccion_guardada"] == 1500 and igual["limites"]["pensiones"] == 1500
            sin = c.get("/api/hacienda/ahorro?pensiones=0").json()
            assert sin["ahorro"] < 0 and sin["cuota_sin"] == h["renta"]["cuota"]
            # Los plazos traen su estado y a qué sección llevan
            p = h["plazos"][0]
            assert {"presentado", "vencido", "ver", "detalle"} <= set(p) and p["ver"] in ("trimestres", "renta")
        finally:
            c.put("/api/prevision/supuestos", json={})


class _Hoy(date):
    @classmethod
    def today(cls):
        return cls(2012, 4, 10)


def test_exencion_del_130_silencia_el_aviso(monkeypatch):
    with TestClient(app):
        s = db.SessionLocal()
        cliente = Cliente(nombre="Cliente exento 2011")
        s.add(cliente)
        s.flush()
        s.add_all([Factura(numero="E-2011-1", cliente_id=cliente.id, fecha=date(2011, 3, 1), base=D("9000"), tipo_retencion=D("15")),
                   Declaracion(modelo="303", ejercicio=2012, periodo="1T", importe=D("100"), justificante="e1")])
        s.commit()
        try:
            hoy = date(2012, 4, 10)
            # Todo lo facturado en 2011 llevaba retención: el 130 de 2012 no se exige y el plazo está cubierto con el 303
            p = next(p for p in avisos.plazos_con_estado(s, hoy, hoy + timedelta(days=15), prev={}, hoy=hoy))
            assert p["titulo"] == "303 y 130 del 1T 2012" and p["presentado"] and [m[0] for m in p["exigidos"]] == ["303"]
            # Sin exención (la previsión tampoco la da) el 130 falta y el plazo vence sin presentar
            s.execute(delete(Factura).where(Factura.numero == "E-2011-1"))
            s.commit()
            p = next(p for p in avisos.plazos_con_estado(s, hoy, hoy + timedelta(days=15), prev={}, hoy=hoy))
            assert not p["presentado"] and len(p["exigidos"]) == 2
            assert avisos.plazos_con_estado(s, date(2012, 5, 1), date(2012, 5, 2), prev={}, hoy=date(2012, 5, 1)) == []
            pasados = avisos.plazos_con_estado(s, date(2012, 4, 1), date(2012, 5, 1), prev={}, hoy=date(2012, 5, 1))
            vencido = next(p for p in pasados if p["titulo"] == "303 y 130 del 1T 2012")
            assert vencido["vencido"] and not next(p for p in pasados if p["titulo"] == "Empieza la renta 2011")["vencido"]
            # La previsión también puede decir que estás exento
            prev = {"trimestres": {"2012-1": {"exento_130": True}}}
            assert avisos.plazos_con_estado(s, hoy, hoy + timedelta(days=15), prev=prev, hoy=hoy)[0]["presentado"]
            # Y los avisos de Inicio lo respetan (y llevan a la sección de los trimestres)
            monkeypatch.setattr(avisos, "date", _Hoy)
            textos = [a for a in avisos.calcular(s, [], prev=prev) if "1T 2012" in a["texto"]]
            assert textos == []
            textos = [a for a in avisos.calcular(s, [], prev={}) if "1T 2012" in a["texto"]]
            assert len(textos) == 1 and textos[0]["ir"] == "/impuestos?ver=trimestres"
        finally:
            s.close()
            _limpiar((Factura, Factura.numero == "E-2011-1"), (Cliente, Cliente.nombre == "Cliente exento 2011"),
                     (Declaracion, Declaracion.ejercicio == 2012))


def test_calendario_con_pagos_llamadas_objetivos_y_banco():
    with TestClient(app):
        s = db.SessionLocal()
        fondo = InversionPrivada(nombre="Fondo calendario", gestora="Gestora X", compromiso=D("10000"))
        s.add(fondo)
        s.flush()
        s.add_all([PagoPrevisto(concepto="Plazo obra calendario", fecha=date(2011, 6, 15), importe=D("5000")),
                   PagoPrevisto(concepto="Pago ya hecho calendario", fecha=date(2011, 6, 16), importe=D("10"), pagado=True),
                   PagoPrevisto(concepto="Llamada de capital Fondo calendario", fecha=date(2011, 7, 1), importe=D("2000"),
                                inversion_id=fondo.id),
                   Objetivo(nombre="Viaje calendario", tipo="viaje", fecha_objetivo=date(2011, 9, 1), importe_objetivo=D("3000")),
                   ConexionBancaria(banco="Banco calendario", session_id="x", valida_hasta=datetime(2011, 8, 20, 10, 0))])
        s.commit()
        try:
            texto = calendario.ics(s, date(2011, 5, 20))
            assert "SUMMARY:Plazo obra calendario" in texto and "UID:pago-" in texto
            assert "Pago ya hecho calendario" not in texto and "5000" not in texto  # sin pagados y sin importes
            assert "SUMMARY:Llamada de capital Fondo calendario" in texto and "DESCRIPTION:Llamada de capital de Fondo calendario (Gestora X)." in texto
            assert "SUMMARY:Objetivo: Viaje calendario" in texto and "DTSTART;VALUE=DATE:20110901" in texto
            assert "SUMMARY:Caduca el permiso de Banco calendario" in texto and "TRIGGER:-P15D" in texto
            assert "SUMMARY:303 y 130 del 2T 2011" in texto
        finally:
            s.close()
            _limpiar((PagoPrevisto, PagoPrevisto.concepto.like("%calendario%")), (InversionPrivada, InversionPrivada.nombre == "Fondo calendario"),
                     (Objetivo, Objetivo.nombre == "Viaje calendario"), (ConexionBancaria, ConexionBancaria.banco == "Banco calendario"))


def test_pluriactividad_con_nominas_reales():
    hoy = date.today()
    with TestClient(app):
        s = db.SessionLocal()
        prev = {"supuestos": {"nomina": None}, "gastos_autonomo_mes": 300,
                "anios_todos": [{"anio": hoy.year, "entradas": {"facturado": 40000.0}}]}
        assert hacienda.bruto_nominas_12_meses(s) == 0
        sin_nominas = next(r for r in hacienda.revision_reta(s, prev) if r["anio"] == hoy.year)
        assert sin_nominas["devolucion_pluriactividad"] == 0 and sin_nominas["previsto"]
        s.add_all([Nomina(empresa="Empresa test", fecha=hoy - timedelta(days=30 * i), bruto=D("4000"), retencion_irpf=D("800"),
                          seguridad_social=D("260"), neto=D("2940")) for i in (1, 2, 3)])
        s.commit()
        try:
            assert hacienda.bruto_nominas_12_meses(s) == 56000  # 3 nóminas normales → media × 14 pagas
            con = next(r for r in hacienda.revision_reta(s, prev) if r["anio"] == hoy.year)
            assert con["devolucion_pluriactividad"] > 0 and con["meses_hasta_regularizacion"] >= 1
            assert con["base_cotizada_mes"] == round(con["cuota_pagada"] / 12 / (con["tipo"] / 100), 2)
        finally:
            s.close()
            _limpiar((Nomina, Nomina.empresa == "Empresa test"))


def test_base_de_cotizacion_equivalente():
    r = reta.regularizar(2026, rendimiento_neto=45000, cuota_pagada=3600)
    assert r.tipo == 31.5 and r.base_cotizada_mes == round(3600 / 12 / 0.315, 2) == 952.38
    assert r.base_cotizada_mes < r.base_minima and r.a_pagar == round(r.base_minima * 12 * 0.315 - 3600, 2)
    assert "base_cotizada_mes" in r.a_dict()


def test_sin_tabla_del_anio_se_usa_la_ultima():
    """Cuando llega un año sin tramos publicados, la regularización no desaparece: usa la última tabla y lo dice."""
    ultimo, futuro = max(reta.TABLAS), max(reta.TABLAS) + 1
    assert reta.anio_tabla(ultimo) == ultimo and reta.anio_tabla(futuro) == ultimo and reta.anio_tabla(2024) is None
    con_tabla = reta.regularizar(ultimo, 45000, 3600, 50000, "previsión del año")
    sin_tabla = reta.regularizar(futuro, 45000, 3600, 50000, "previsión del año")
    assert sin_tabla is not None and sin_tabla.anio == futuro
    assert sin_tabla.fuente == f"previsión del año (tramos de {ultimo}, pendientes de actualizar)"
    assert {k: v for k, v in sin_tabla.a_dict().items() if k not in ("anio", "fuente")} == \
        {k: v for k, v in con_tabla.a_dict().items() if k not in ("anio", "fuente")}
    assert reta.devolucion_pluriactividad(futuro, 3600, 50000) == reta.devolucion_pluriactividad(ultimo, 3600, 50000) > 0
    assert reta.regularizar(2024, 1, 1) is None


def test_trimestre_a_pagar():
    """El anterior mientras dura su plazo; después, el que está en curso (la regla de Inicio)."""
    assert autonomo.trimestre_a_pagar(date(2026, 1, 15)) == (2025, 4)
    assert autonomo.trimestre_a_pagar(date(2026, 1, 30)) == (2025, 4)
    assert autonomo.trimestre_a_pagar(date(2026, 1, 31)) == (2026, 1)
    assert autonomo.trimestre_a_pagar(date(2026, 4, 20)) == (2026, 1)
    assert autonomo.trimestre_a_pagar(date(2026, 4, 21)) == (2026, 2)
    assert autonomo.trimestre_a_pagar(date(2026, 10, 9)) == (2026, 3)
    assert autonomo.trimestre_a_pagar(date(2026, 11, 1)) == (2026, 4)
    assert autonomo.vencimiento(*autonomo.trimestre_a_pagar(date(2026, 10, 9))) == date(2026, 10, 20)
