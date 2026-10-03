import io
from datetime import date
from decimal import Decimal as D

import httpx
import openpyxl

from finanzas import db
from finanzas.categorizar import sembrar_categorias
from finanzas.importers import sabadell
from finanzas.integrations import indexa
from finanzas.models import Categoria, Cuenta, Movimiento

CSV = """Cuenta;ES00 0081 0000 0000 0000 0000
Movimientos del 01/09/2026 al 30/09/2026

F. Operativa;Concepto;F. Valor;Importe;Saldo;Referencia 1;Referencia 2
02/09/2026;NOMINA INDRA SISTEMAS;02/09/2026;2.345,67;5.345,67;;
03/09/2026;COMPRA TARJ. MERCADONA;03/09/2026;-45,20;5.300,47;;
03/09/2026;COMPRA TARJ. MERCADONA;03/09/2026;-45,20;5.255,27;;
""".encode("latin-1")


def nueva_sesion():
    db.init_db()
    s = db.SessionLocal()
    sembrar_categorias(s)
    return s


def test_parsear_csv_sabadell():
    filas = sabadell.parsear("extracto.csv", CSV)
    assert len(filas) == 3
    assert filas[0].importe == D("2345.67")
    assert filas[1].fecha == date(2026, 9, 3)


def test_parsear_xlsx():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Movimientos"])
    ws.append(["Fecha", "Concepto", "Fecha valor", "Importe", "Saldo"])
    ws.append([date(2026, 9, 2), "TRASPASO INDEXA", date(2026, 9, 2), -500.0, 1000.0])
    buf = io.BytesIO()
    wb.save(buf)
    filas = sabadell.parsear("x.xlsx", buf.getvalue())
    assert filas[0].importe == D("-500.00") and filas[0].fecha == date(2026, 9, 2)


def test_importar_no_duplica_y_categoriza():
    s = nueva_sesion()
    cuenta = Cuenta(nombre="Sabadell", entidad="Banco Sabadell")
    s.add(cuenta)
    s.commit()
    r1 = sabadell.importar(s, cuenta, "e.csv", CSV)
    r2 = sabadell.importar(s, cuenta, "e.csv", CSV)
    assert (r1.nuevos, r2.nuevos, r2.duplicados) == (3, 0, 3)
    assert cuenta.saldo == D("5255.27")
    nomina = s.query(Movimiento).filter(Movimiento.concepto.like("NOMINA%")).one()
    assert s.get(Categoria, nomina.categoria_id).nombre == "Nómina"


def test_sincronizar_indexa():
    def responder(req: httpx.Request):
        assert req.headers["X-AUTH-TOKEN"] == "tok"
        if req.url.path == "/users/me":
            return httpx.Response(200, json={"accounts": [{"account_number": "ABC123", "type": "mutual"}]})
        if req.url.path == "/accounts/ABC123/portfolio":
            return httpx.Response(200, json={"portfolio": {"total_amount": 12345.678}})
        return httpx.Response(404)

    s = nueva_sesion()
    cliente = indexa.IndexaClient(token="tok", base_url="https://x", transport=httpx.MockTransport(responder))
    [c] = indexa.sincronizar(s, cliente)
    assert c.saldo == D("12345.68") and c.tipo == "inversion"
    indexa.sincronizar(s, cliente)
    assert s.query(Cuenta).filter_by(origen="indexa").count() == 1
