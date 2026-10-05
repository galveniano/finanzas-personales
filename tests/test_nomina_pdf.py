from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from finanzas.importers import nomina_pdf
from finanzas.main import app

# Recibo inventado con el formato del modelo oficial (no son datos reales)
RECIBO = """EMPRESA: EJEMPLO SISTEMAS, S.A.   C.I.F. A00000000
TRABAJADOR: PERSONA DE PRUEBA
PERIODO DE LIQUIDACION DEL 01/09/2026 AL 30/09/2026   TOTAL DIAS 30
I. DEVENGOS
SALARIO BASE 2.900,00
COMPLEMENTO PUESTO 950,00
RETRIBUCION EN ESPECIE SEGURO MEDICO 40,00
A. TOTAL DEVENGADO 3.890,00
II. DEDUCCIONES
CONTINGENCIAS COMUNES 4,70 % 4.531,67 212,99
DESEMPLEO 1,55 % 4.531,67 70,24
FORMACION PROFESIONAL 0,10 % 4.531,67 4,53
MEI 0,15 % 4.531,67 6,80
TRIBUTACION I.R.P.F. 27,50 % 1.069,75
DESCUENTO ESPECIE SEGURO MEDICO 40,00
B. TOTAL A DEDUCIR 1.404,31
LIQUIDO TOTAL A PERCIBIR (A-B) 2.485,69
BASE SUJETA A RETENCION DEL IRPF 3.890,00
"""


def _pdf(texto: str) -> bytes:
    """PDF mínimo con una línea de texto por renglón, para probar la lectura de verdad."""
    lineas = texto.strip().splitlines()
    ops = ["BT /F1 9 Tf 40 800 Td 12 TL"] + [
        "(" + l.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for l in lineas] + ["ET"]
    flujo = "\n".join(ops).encode("latin-1")
    objetos = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d >>\nstream\n" % len(flujo) + flujo + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    salida, posiciones = b"%PDF-1.4\n", []
    for i, o in enumerate(objetos, 1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    salida += b"".join(b"%010d 00000 n \n" % p for p in posiciones)
    salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, xref)
    return salida


def test_lee_el_recibo():
    r = nomina_pdf.interpretar([RECIBO])
    assert r.fecha == date(2026, 9, 30) and not r.paga_extra
    assert r.empresa == "Ejemplo Sistemas"
    assert r.bruto == Decimal("3890.00") and r.neto == Decimal("2485.69")
    assert r.seguridad_social == Decimal("294.56")
    assert r.retencion_irpf == Decimal("1069.75") and r.tipo_irpf == Decimal("27.50")
    assert r.base_irpf == Decimal("3890.00") and r.especie == Decimal("40.00")
    assert r.otras_deducciones == Decimal("40.00")
    assert r.cuadra and not r.avisos


def test_paga_extra_y_mes_en_letra():
    texto = RECIBO.replace("PERIODO DE LIQUIDACION DEL 01/09/2026 AL 30/09/2026", "PAGA EXTRA DICIEMBRE 2026")
    r = nomina_pdf.interpretar([texto])
    assert r.paga_extra and r.fecha == date(2026, 12, 31)


def test_no_es_una_nomina():
    try:
        nomina_pdf.interpretar(["Factura número 12 total 100,00"])
    except nomina_pdf.ErrorNomina:
        pass
    else:
        raise AssertionError("debería fallar")


def test_desde_ia():
    r = nomina_pdf.desde_ia({"empresa": "Ejemplo", "fecha": "2026-08-31", "bruto": 3000, "seguridad_social": 195,
                             "retencion_irpf": 750, "neto": 2055, "tipo_irpf": 25})
    assert r.cuadra and r.tipo_irpf == Decimal("25.00")


def test_subir_pdf_y_prevision():
    pdf = _pdf(RECIBO)
    assert nomina_pdf.leer_pdf(pdf).neto == Decimal("2485.69")
    with TestClient(app) as c:
        r = c.post("/api/nominas/pdf", files=[("ficheros", ("sept.pdf", pdf, "application/pdf")),
                                              ("ficheros", ("roto.pdf", b"no es un pdf", "application/pdf"))]).json()
        bien, mal = r["resultados"]
        assert bien["ok"] and bien["mensaje"] == "Nómina de septiembre de 2026" and not bien["avisos"]
        assert not mal["ok"]
        # Subirla otra vez la actualiza en vez de duplicarla
        otra = c.post("/api/nominas/pdf", files=[("ficheros", ("sept.pdf", pdf, "application/pdf"))]).json()
        assert otra["resultados"][0]["mensaje"].endswith("(actualizada)")
        d = c.get("/api/nominas?anio=2026").json()
        sept = [x for x in d["nominas"] if x["fecha"] == "2026-09-30"]
        assert len(sept) == 1 and sept[0]["tiene_pdf"] and sept[0]["tipo_irpf"] == 27.5
        assert d["tipo_irpf_actual"] == 27.5
        assert c.get(f"/api/nominas/{sept[0]['id']}/pdf").content == pdf
        # Corregirla a mano
        fila = dict(sept[0], neto=2485.70)
        assert c.put(f"/api/nominas/{sept[0]['id']}", json=fila).json()["ok"]
        c.delete(f"/api/nominas/{sept[0]['id']}")


def test_prevision_usa_el_tipo_de_la_nomina():
    from finanzas import db, prevision
    from finanzas.models import Nomina

    prevista = prevision._nomina_anual({"bruto_anual": 50000, "pagas": 14})
    with db.SessionLocal() as s:
        x = Nomina(empresa="Ejemplo", fecha=date(2031, 1, 31), bruto=Decimal("3571.43"),
                   seguridad_social=Decimal("232.14"), retencion_irpf=Decimal("1071.43"), neto=Decimal("2267.86"),
                   tipo_irpf=Decimal("30"))
        s.add(x)
        s.commit()
        try:
            r = prevision._nomina_con_reales(s, 2031, prevista)
        finally:
            s.delete(x)
            s.commit()
    assert r["tipo_real"] == 30
    # Febrero sigue la previsión pero con el 30 % de la empresa
    assert abs(r["meses"][2] - (prevista["meses"][2] + prevista["brutos"][2] * (prevista["tipo"] - 30) / 100)) < 0.01
    assert abs(r["irpf"] - (1071.43 + sum(v for m, v in prevista["brutos"].items() if m != 1) * 0.30)) < 0.5
