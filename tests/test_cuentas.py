"""Cuentas y movimientos: reglas aprendidas, edición de cuentas, cuentas ocultas, movimientos a mano, filtros,
categorización en lote, categorías y reglas, avisos y Excel (datos inventados en 2011 para no mezclarse)."""
import io
from datetime import date, timedelta
from decimal import Decimal as D

import openpyxl
from fastapi.testclient import TestClient
from sqlalchemy import select

from finanzas import categorizar, cuentas, db, prevision
from finanzas.main import app
from finanzas.models import Categoria, Cuenta, Movimiento, ReglaCategoria


def _mov(cuenta_id: int, fecha: str, concepto: str, importe: str, huella: str, **kw) -> Movimiento:
    return Movimiento(cuenta_id=cuenta_id, fecha=date.fromisoformat(fecha), concepto=concepto, importe=D(importe),
                      huella=huella, **kw)


def _borrar_cuentas(*ids: int) -> None:
    with db.SessionLocal() as s:
        for i in ids:
            s.query(Movimiento).filter(Movimiento.cuenta_id == i).delete()
            s.query(Cuenta).filter(Cuenta.id == i).delete()
        s.commit()


def _categoria(c: TestClient, nombre: str) -> dict:
    return next(x for x in c.get("/api/categorias").json() if x["nombre"] == nombre)


def test_reglas_aprendidas_se_aplican_se_olvidan_y_no_revientan():
    with TestClient(app):
        s = db.SessionLocal()
        cuenta = Cuenta(nombre="Cuenta reglas 2011")
        s.add(cuenta)
        s.flush()
        compras = s.scalar(select(Categoria).where(Categoria.nombre == "Compras"))
        m = _mov(cuenta.id, "2011-03-01", "COMPRA TARJ. 5402 KIOSKOPRUEBA.COM 12/09", "-9.99", "r2011-1", categoria_id=compras.id)
        s.add(m)
        s.commit()
        assert categorizar.aprender(s, m)["patron"] == "kioskoprueba com"
        # (a) la regla aprendida vale para el siguiente cargo aunque cambien los dígitos y la fecha
        assert categorizar.categorizar(s, "COMPRA TARJ. 9999 KIOSKOPRUEBA.COM 03/10") == compras.id
        # y las de serie siguen mirando el texto tal cual
        assert categorizar.categorizar(s, "RECIBO NETFLIX.COM") == s.scalar(
            select(Categoria.id).where(Categoria.nombre == "Ocio y suscripciones"))
        # (b) ponerle «Sin categoría» borra la regla aprendida de ese patrón
        m.categoria_id = None
        s.commit()
        assert categorizar.aprender(s, m) == {"patron": None, "parecidos": 0}
        assert s.scalar(select(ReglaCategoria).where(ReglaCategoria.patron == "kioskoprueba com")) is None
        assert categorizar.categorizar(s, "COMPRA TARJ. 9999 KIOSKOPRUEBA.COM 03/10") is None
        # (c) un concepto sin letras no rompe nada
        raro = _mov(cuenta.id, "2011-03-02", "1234 5678", "-1", "r2011-2", categoria_id=compras.id)
        s.add(raro)
        s.commit()
        assert categorizar.parecidos(s, raro) == [] and categorizar.aprender(s, raro) == {"patron": None, "parecidos": 0}
        s.close()
        _borrar_cuentas(cuenta.id)


def test_editar_cuenta_iban_normalizado_y_extractos():
    with TestClient(app) as c:
        cta = c.post("/api/cuentas", json={"nombre": "Manual 2011", "iban": "es00 0081 0000 0000 0000 0101"}).json()
        assert cta["iban"] == "ES0000810000000000000101" and cta["saldo_fecha"] is None and cta["activa"]
        assert cta["evolucion"] == [] and cta["mes"] == {"entran": 0, "salen": 0}
        assert c.post("/api/cuentas", json={"nombre": " ", "tipo": "corriente"}).status_code == 400
        r = c.patch(f"/api/cuentas/{cta['id']}", json={"nombre": "Ahorro 2011", "entidad": "Caja 2011", "tipo": "ahorro",
                                                       "iban": "es00 0081 0000 0000 0000 0102", "saldo": 1500,
                                                       "participacion": 50}).json()
        assert (r["nombre"], r["entidad"], r["tipo"], r["iban"]) == ("Ahorro 2011", "Caja 2011", "ahorro", "ES0000810000000000000102")
        assert r["saldo"] == 1500 and r["saldo_fecha"] == date.today().isoformat() and r["saldo_tuyo"] == 750
        assert c.patch(f"/api/cuentas/{cta['id']}", json={"tipo": "cripto"}).status_code == 400
        # Las sincronizadas no admiten ni saldo a mano ni extractos (saldrían los movimientos dos veces)
        with db.SessionLocal() as s:
            banco = Cuenta(nombre="Banco 2011", origen="enable_banking", saldo=D("100"))
            s.add(banco)
            s.commit()
            banco_id = banco.id
        assert c.patch(f"/api/cuentas/{banco_id}", json={"saldo": 1}).status_code == 400
        csv = "Fecha;Concepto;Importe;Saldo\n05/01/2011;COMPRA 2011;-20,00;1480,00\n".encode()
        r = c.post(f"/api/cuentas/{banco_id}/importar", files={"fichero": ("e.csv", io.BytesIO(csv), "text/csv")})
        assert r.status_code == 400 and "dos veces" in r.json()["detail"]
        # En una manual el extracto entra y la cuenta pasa a ser «de extracto»
        r = c.post(f"/api/cuentas/{cta['id']}/importar", files={"fichero": ("e.csv", io.BytesIO(csv), "text/csv")})
        assert r.json()["nuevos"] == 1
        assert next(x for x in c.get("/api/cuentas").json() if x["id"] == cta["id"])["origen"] == "csv"
        _borrar_cuentas(cta["id"], banco_id)


def test_cuentas_ocultas_no_cuentan_y_se_recuperan():
    with TestClient(app) as c:
        hoy = date.today()
        with db.SessionLocal() as s:
            nomina = s.scalar(select(Categoria.id).where(Categoria.nombre == "Nómina"))
            banco = Cuenta(nombre="Oculta 2011", origen="enable_banking", saldo=D("100"))
            s.add(banco)
            s.flush()
            s.add(_mov(banco.id, hoy.isoformat(), "NOMINA OCULTA 2011", "1000", "oc2011-1", categoria_id=nomina))
            s.commit()
            bid = banco.id
        buscar = lambda: c.get("/api/movimientos?q=OCULTA 2011").json()["total"]  # noqa: E731
        assert buscar() == 1
        assert c.delete(f"/api/cuentas/{bid}").json()["oculta"]
        assert bid not in {x["id"] for x in c.get("/api/cuentas").json()}
        assert next(x for x in c.get("/api/cuentas?todas=true").json() if x["id"] == bid)["activa"] is False
        # Ni en la lista, ni en las nóminas del banco, ni en gastos y previsión
        assert buscar() == 0
        assert "NOMINA OCULTA 2011" not in {m["concepto"] for m in c.get("/api/nominas").json()["banco"]}
        with db.SessionLocal() as s:
            assert not [m for m in prevision.movimientos_tuyos(s, hoy - timedelta(days=1)) if m.concepto == "NOMINA OCULTA 2011"]
        r = c.patch(f"/api/cuentas/{bid}", json={"activa": True}).json()
        assert r["activa"] and bid in {x["id"] for x in c.get("/api/cuentas").json()} and buscar() == 1
        _borrar_cuentas(bid)


def test_movimientos_a_mano_filtros_lote_y_excel():
    with TestClient(app) as c:
        cta = c.post("/api/cuentas", json={"nombre": "A mano 2011", "saldo": 1000}).json()
        otra = c.post("/api/cuentas", json={"nombre": "Otra a mano 2011"}).json()
        super_ = _categoria(c, "Supermercado")

        def saldo(id_: int) -> float:
            return next(x for x in c.get("/api/cuentas").json() if x["id"] == id_)["saldo"]

        m1 = c.post("/api/movimientos", json={"cuenta_id": cta["id"], "fecha": "2011-05-10", "concepto": "MERCADONA 2011", "importe": -50}).json()
        assert m1["manual"] and m1["categoria_id"] == super_["id"] and m1["nota"] == "" and m1["cuenta"] == "A mano 2011"
        m2 = c.post("/api/movimientos", json={"cuenta_id": cta["id"], "fecha": "2011-05-12", "concepto": "INGRESO 2011", "importe": 200, "nota": "regalo"}).json()
        m3 = c.post("/api/movimientos", json={"cuenta_id": cta["id"], "fecha": "2011-05-20", "concepto": "A LA OTRA 2011", "importe": -300}).json()
        m4 = c.post("/api/movimientos", json={"cuenta_id": otra["id"], "fecha": "2011-05-21", "concepto": "DE LA PRIMERA 2011", "importe": 300}).json()
        assert m2["nota"] == "regalo" and saldo(cta["id"]) == 850 and saldo(otra["id"]) == 300
        assert c.post("/api/movimientos", json={"cuenta_id": cta["id"], "fecha": "2011-05-10", "concepto": " ", "importe": 1}).status_code == 400

        # Filtros por fechas, totales, sumas y traspaso detectado entre las dos cuentas
        r = c.get("/api/movimientos?desde=2011-05-01&hasta=2011-05-31").json()
        assert r["total"] == 4 and r["suma_ingresos"] == 500 and r["suma_gastos"] == 350
        assert [m["id"] for m in r["movimientos"]] == [m4["id"], m3["id"], m2["id"], m1["id"]]
        por_id = {m["id"]: m for m in r["movimientos"]}
        assert por_id[m3["id"]]["traspaso"] and por_id[m4["id"]]["traspaso"] and not por_id[m1["id"]]["traspaso"]
        r = c.get("/api/movimientos?desde=2011-05-01&hasta=2011-05-31&tipo=gastos&limite=1&offset=1").json()
        assert r["total"] == 2 and [m["id"] for m in r["movimientos"]] == [m1["id"]]
        assert c.get(f"/api/movimientos?cuenta_id={otra['id']}&tipo=ingresos").json()["total"] == 1
        assert c.get("/api/movimientos?tipo=raro").status_code == 400

        # Editar y borrar solo los apuntados a mano, con el saldo de la cuenta detrás
        r = c.put(f"/api/movimientos/{m1['id']}", json={"fecha": "2011-05-11", "concepto": "MERCADONA 2011 BIS", "importe": -80,
                                                        "categoria_id": None, "nota": "editado"}).json()
        assert r["importe"] == -80 and r["nota"] == "editado" and r["categoria_id"] is None and r["fecha"] == "2011-05-11"
        assert saldo(cta["id"]) == 820
        assert c.delete(f"/api/movimientos/{m2['id']}").json()["ok"] and saldo(cta["id"]) == 620
        with db.SessionLocal() as s:
            banco = Cuenta(nombre="Banco a mano 2011", origen="enable_banking")
            s.add(banco)
            s.flush()
            mb = _mov(banco.id, "2011-05-01", "DEL BANCO 2011", "-5", "eb:2011")
            s.add(mb)
            s.commit()
            bid, mbid = banco.id, mb.id
        assert c.post("/api/movimientos", json={"cuenta_id": bid, "fecha": "2011-05-01", "concepto": "X", "importe": 1}).status_code == 400
        assert c.put(f"/api/movimientos/{mbid}", json={"fecha": "2011-05-01", "concepto": "X", "importe": 1}).status_code == 400
        assert c.delete(f"/api/movimientos/{mbid}").status_code == 400
        # …pero sí la nota, sin tocar la categoría
        c.patch(f"/api/movimientos/{mbid}", json={"categoria_id": super_["id"]})
        assert c.patch(f"/api/movimientos/{mbid}", json={"nota": "Apuntado como gasto del piso"}).json()["ok"]
        mov = c.get("/api/movimientos?q=DEL BANCO 2011").json()["movimientos"][0]
        assert mov["nota"] == "Apuntado como gasto del piso" and mov["categoria_id"] == super_["id"] and not mov["manual"]

        # Categorizar en lote (también a «sin categoría»)
        r = c.patch("/api/movimientos/categoria", json={"ids": [m3["id"], m4["id"], mbid], "categoria_id": super_["id"]}).json()
        assert r["cambiados"] == 3
        assert c.get(f"/api/movimientos?q=2011&categoria_id={super_['id']}").json()["total"] == 3
        assert c.patch("/api/movimientos/categoria", json={"ids": [m3["id"], m4["id"]], "categoria_id": None}).json()["cambiados"] == 2
        assert {m["id"] for m in c.get("/api/movimientos?q=2011&categoria_id=0").json()["movimientos"]} >= {m1["id"], m3["id"], m4["id"]}

        # Excel con los mismos filtros
        r = c.get("/api/exportar/movimientos.xlsx?q=2011&tipo=gastos&desde=2011-05-01")
        assert r.status_code == 200
        filas = list(openpyxl.load_workbook(io.BytesIO(r.content)).active.iter_rows(values_only=True))
        assert filas[0][:3] == ("Fecha", "Cuenta", "Concepto") and filas[0][-1] == "Nota"
        assert {f[2] for f in filas[1:]} == {"MERCADONA 2011 BIS", "A LA OTRA 2011", "DEL BANCO 2011"}
        assert all(f[3] < 0 for f in filas[1:]) and next(f for f in filas[1:] if f[2] == "DEL BANCO 2011")[7] == "Apuntado como gasto del piso"
        _borrar_cuentas(cta["id"], otra["id"], bid)


def test_categorias_y_reglas():
    with TestClient(app) as c:
        nomina = _categoria(c, "Nómina")
        assert nomina["de_serie"] and not _categoria(c, "Compras")["de_serie"]
        assert c.patch(f"/api/categorias/{nomina['id']}", json={"nombre": "Sueldo"}).status_code == 400
        assert c.delete(f"/api/categorias/{nomina['id']}").status_code == 400
        assert c.patch(f"/api/categorias/{nomina['id']}", json={"nombre": "Nómina", "ambito": "nomina"}).status_code == 200
        nueva = c.post("/api/categorias", json={"nombre": " Mascotas 2011 "}).json()
        assert nueva["nombre"] == "Mascotas 2011" and nueva["tipo"] == "gasto" and nueva["ambito"] == "personal" and not nueva["de_serie"]
        assert c.post("/api/categorias", json={"nombre": "mascotas 2011"}).status_code == 400
        assert c.post("/api/categorias", json={"nombre": "Rara 2011", "tipo": "raro"}).status_code == 400
        assert c.post("/api/categorias", json={"nombre": ""}).status_code == 400
        r = c.patch(f"/api/categorias/{nueva['id']}", json={"nombre": "Perro 2011", "ambito": "piso"}).json()
        assert r["nombre"] == "Perro 2011" and r["ambito"] == "piso" and r["tipo"] == "gasto"
        assert c.patch(f"/api/categorias/{nueva['id']}", json={"nombre": "compras"}).status_code == 400  # ya existe

        # Un movimiento con esa categoría aprende una regla; las de serie no se borran, las aprendidas sí
        cta = c.post("/api/cuentas", json={"nombre": "Cuenta categorías 2011"}).json()
        m = c.post("/api/movimientos", json={"cuenta_id": cta["id"], "fecha": "2011-06-01",
                                              "concepto": "COMPRA TARJ. 1 VETERINARIO PRUEBA 2011", "importe": -40}).json()
        assert c.patch(f"/api/movimientos/{m['id']}", json={"categoria_id": nueva["id"]}).json()["patron"] == "veterinario prueba"
        reglas = c.get("/api/categorias/reglas").json()
        aprendida = next(x for x in reglas if x["patron"] == "veterinario prueba")
        assert aprendida["aprendida"] and aprendida["categoria"] == "Perro 2011" and reglas[0]["id"] == aprendida["id"]
        de_serie = next(x for x in reglas if not x["aprendida"])
        assert c.delete(f"/api/categorias/reglas/{de_serie['id']}").status_code == 400
        assert c.delete(f"/api/categorias/reglas/{aprendida['id']}").json()["ok"]
        assert not any(x["patron"] == "veterinario prueba" for x in c.get("/api/categorias/reglas").json())

        # Borrar la categoría deja sus movimientos sin categoría y se lleva sus reglas
        c.patch(f"/api/movimientos/{m['id']}", json={"categoria_id": nueva["id"]})
        assert c.delete(f"/api/categorias/{nueva['id']}").json()["movimientos"] == 1
        assert c.get("/api/movimientos?q=VETERINARIO PRUEBA 2011").json()["movimientos"][0]["categoria_id"] is None
        assert not any(x["patron"] == "veterinario prueba" for x in c.get("/api/categorias/reglas").json())
        assert c.delete(f"/api/categorias/{nueva['id']}").status_code == 404
        _borrar_cuentas(cta["id"])


def test_evolucion_y_mes_de_cada_cuenta():
    with TestClient(app) as c:
        hoy = date.today()
        with db.SessionLocal() as s:
            cta = Cuenta(nombre="Evolución 2011", origen="csv", saldo=D("900"), saldo_fecha=hoy)
            s.add(cta)
            s.flush()
            hace_dos_meses = (hoy.replace(day=1) - timedelta(days=1)).replace(day=1) - timedelta(days=1)
            s.add_all([_mov(cta.id, hace_dos_meses.isoformat(), "VIEJO 2011", "-10", "ev2011-1", saldo=D("1000")),
                       _mov(cta.id, hoy.isoformat(), "ENTRA 2011", "150", "ev2011-2", saldo=D("1050")),
                       _mov(cta.id, hoy.isoformat(), "SALE 2011", "-250", "ev2011-3", saldo=D("900"))])
            s.commit()
            cid = cta.id
        r = next(x for x in c.get("/api/cuentas").json() if x["id"] == cid)
        assert r["mes"] == {"entran": 150, "salen": 250}
        saldos = [p["saldo"] for p in r["evolucion"]]
        assert saldos == [1000, 1000, 900]  # el mes sin movimientos repite el anterior; el último es el de hoy
        assert r["evolucion"][-1]["fecha"] == hoy.isoformat()
        _borrar_cuentas(cid)


def test_avisos_de_cuentas():
    with TestClient(app) as c:
        hoy = date.today()
        with db.SessionLocal() as s:
            vieja = Cuenta(nombre="Saldo viejo 2011", saldo=D("10"), saldo_fecha=hoy - timedelta(days=90))
            reciente = Cuenta(nombre="Saldo reciente 2011", saldo=D("10"), saldo_fecha=hoy - timedelta(days=10))
            banco = Cuenta(nombre="Banco viejo 2011", origen="enable_banking", saldo_fecha=hoy - timedelta(days=90))
            sin_cat = Cuenta(nombre="Sin categoría 2011")
            s.add_all([vieja, reciente, banco, sin_cat])
            s.flush()
            for i in range(5):
                s.add(_mov(sin_cat.id, hoy.replace(day=1).isoformat(), f"RARO {i} 2011", "-1", f"sc2011-{i}"))
            s.commit()
            ids = [vieja.id, reciente.id, banco.id, sin_cat.id]
            textos = [a["texto"] for a in cuentas.avisos(s)]
        assert any(t.startswith("El saldo de Saldo viejo 2011 es del") for t in textos)
        assert not any("reciente 2011" in t or "Banco viejo 2011" in t for t in textos)
        assert any("movimientos de este mes sin categoría" in t for t in textos)
        assert any(a["ir"] == "/cuentas?categoria=0" for a in c.get("/api/resumen").json()["avisos"])
        _borrar_cuentas(*ids)
