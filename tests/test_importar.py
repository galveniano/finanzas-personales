import json
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


def test_parse_importe_con_puntos_de_miles():
    assert sabadell.parse_importe("1.000") == D("1000.00")
    assert sabadell.parse_importe("1.000,50") == D("1000.50")
    assert sabadell.parse_importe("1234.56") == D("1234.56")
    assert sabadell.parse_importe("-1.500") == D("-1500.00")
    assert sabadell.parse_importe("1.5") == D("1.50")
    assert sabadell.parse_importe(1000) == D("1000.00")


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
    nomina = s.query(Movimiento).filter(Movimiento.cuenta_id == cuenta.id, Movimiento.concepto.like("NOMINA%")).one()
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
    assert json.loads(c.detalle)["posiciones"] == []  # sin rentabilidad ni posiciones, el saldo se actualiza igual


def test_detalle_indexa():
    """Posiciones y rentabilidad con la forma que devuelve la API (datos de ejemplo)."""
    cartera = {"portfolio": {"total_amount": 10100, "cash_amount": 100, "instruments_amount": 10000},
               "instrument_accounts": [{"positions": [
                   {"instrument": {"identifier_name": "ISIN", "isin_code": "IE00TEST0001", "name": "Fondo RV Europa",
                                   "asset_class": "equity_europe", "management_company_description": "Gestora A"},
                    "titles": 100, "price": 30, "amount": 3000, "cost_amount": 2500, "weight_real": 0.3},
                   {"instrument": {"identifier_name": "DGS", "dgs_code": "N5000", "dgs_fund_code": "F0001",
                                   "name": "Fondo RF"}, "titles": 70, "price": 100, "amount": 7000, "cost_amount": 7100}]}]}
    rentabilidad = {"return": {"time_return_annual": 0.0654, "time_return": 0.2, "money_return": 0.18},
                    "plan_expected_return": 0.05, "volatility": 0.11}
    d = indexa.detalle(cartera, rentabilidad, {"type": "pension", "profile": {"selected_risk": 6}})
    assert d["producto"] == "Plan de pensiones" and d["perfil_riesgo"] == 6
    assert d["total"] == 10100 and d["efectivo"] == 100 and d["invertido"] == 10000
    assert d["coste"] == 9600 and d["plusvalia"] == 400
    assert d["rentabilidad_anual"] == 6.54 and d["volatilidad"] == 11 and d["rentabilidad_esperada"] == 5
    rf, rv = d["posiciones"]
    assert rf["codigo"] == "N5000 - F0001" and rf["peso"] == 69.31  # sin weight_real: valor / total
    assert rv["codigo"] == "IE00TEST0001" and rv["peso"] == 30
