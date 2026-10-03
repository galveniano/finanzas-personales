from datetime import date
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from finanzas.importers import aeat, aeat_txt
from finanzas.main import app


def fichero(modelo="130", ejercicio=2022, periodo="2T", tipo="I", casillas=None, aux_importe=15000,
            apellidos="PÉREZ MUÑOZ", codificacion="latin-1") -> bytes:
    """Declaración inventada con el diseño de registro de la AEAT (cabecera, AUX y página 01)."""
    casillas = casillas or [123456, 23456, 100000, 20000, 5000, 0, 15000] + [0] * 11 + [15000]
    cuerpo = (f" {tipo}12345678Z{apellidos.ljust(60)}{'NOMBRE'.ljust(20)}{ejercicio}{periodo}"
              + "".join(f"{v:017d}" for v in casillas) + " " * 30)
    texto = (f"<T{modelo}0{ejercicio}{periodo}0000><AUX>{modelo}0000000001{tipo}{' ' * 40}{aux_importe:017d}{tipo}</AUX>"
             f"<T{modelo}01000>{cuerpo}</T{modelo}01000></T{modelo}0{ejercicio}{periodo}0000>")
    return texto.encode(codificacion)


def test_lee_130():
    t = aeat_txt.leer(fichero())
    assert (t.modelo, t.ejercicio, t.periodo, t.resultado, t.importe, t.exacto) == ("130", 2022, "2T", "ingresar", D("150.00"), True)


@pytest.mark.parametrize("codificacion", ["latin-1", "utf-8"])
def test_la_enye_no_descuadra(codificacion):
    assert aeat_txt.leer(fichero(codificacion=codificacion)).importe == D("150.00")


def test_negativa_y_modelo_sin_diseno():
    assert aeat_txt.leer(fichero(tipo="N", casillas=[0] * 19, aux_importe=0)).importe == 0
    t = aeat_txt.leer(fichero(modelo="303", aux_importe=42050))
    assert t.importe == D("420.50") and not t.exacto
    with pytest.raises(aeat.ErrorAEAT):
        aeat_txt.leer(b"hola")


def test_subir_varios_txt_y_luego_el_pdf(monkeypatch):
    with TestClient(app) as c:
        ficheros = [("ficheros", ("130_1T.txt", fichero(periodo="1T"), "text/plain")),
                    ("ficheros", ("130_2T.txt", fichero(periodo="2T"), "text/plain")),
                    ("ficheros", ("roto.txt", b"<T no vale", "text/plain"))]
        r = c.post("/api/declaraciones/pdf", files=ficheros).json()["resultados"]
        assert [x["ok"] for x in r] == [True, True, False]
        # Subirlo otra vez actualiza, no duplica
        r = c.post("/api/declaraciones/pdf", files=[ficheros[1]]).json()["resultados"]
        assert "actualizado" in r[0]["mensaje"]

        def de_2022(*, periodo):
            return [d for d in c.get("/api/declaraciones").json()["declaraciones"]
                    if d["modelo"] == "130" and d["ejercicio"] == 2022 and d["periodo"] == periodo]
        [d] = de_2022(periodo="2T")
        assert d["importe"] == 150 and d["justificante"] == "" and "txt" in d["notas"]

        # El justificante PDF del mismo periodo sustituye al .txt
        monkeypatch.setattr(aeat, "leer_pdf", lambda contenido: aeat.Justificante(
            "130", 2022, "2T", "ingresar", D("150.00"), date(2022, 7, 15), "1300000000099", "CSVPRUEBA"))
        c.post("/api/declaraciones/pdf", files=[("ficheros", ("j.pdf", b"%PDF", "application/pdf"))])
        [d] = de_2022(periodo="2T")
        assert d["justificante"] == "1300000000099" and d["notas"] == "" and d["tiene_pdf"]
        # Y un .txt posterior ya no lo pisa
        r = c.post("/api/declaraciones/pdf", files=[ficheros[1]]).json()["resultados"]
        assert "justificante PDF" in r[0]["mensaje"] and len(de_2022(periodo="2T")) == 1


def test_autonomo_usa_lo_presentado():
    """Con el 130 y el 303 subidos, Autónomo enseña lo presentado aunque las facturas digan otra cosa."""
    with TestClient(app) as c:
        c.post("/api/autonomo/facturas", json={"numero": "F1", "cliente": "Cliente Ejemplo", "fecha": "2023-02-10",
                                               "base": 1000, "tipo_iva": 21, "tipo_retencion": 0})
        c.post("/api/declaraciones/pdf", files=[
            ("ficheros", ("130.txt", fichero(ejercicio=2023, periodo="1T"), "text/plain")),
            ("ficheros", ("303.txt", fichero(modelo="303", ejercicio=2023, periodo="1T", aux_importe=33300), "text/plain"))])
        d = c.get("/api/autonomo?anio=2023").json()
        t1, t2 = d["trimestres"][:2]
        assert (t1["iva_fuente"], t1["iva_resultado"], t1["iva_estimado"]) == ("presentado", 333.0, 210.0)
        assert (t1["irpf_fuente"], t1["irpf_resultado"]) == ("presentado", 150.0)
        assert (t1["ingresos_acumulados"], t1["rendimiento_acumulado"], t1["retenciones_acumuladas"]) == (1234.56, 1000.0, 0.0)
        assert t2["iva_fuente"] == "estimado" and t2["ingresos_acumulados"] is None
        assert (d["ingresos_declarados"], d["ultimo_130"], d["pagado_iva"], d["pagado_irpf"]) == (1234.56, 1, 333.0, 150.0)
