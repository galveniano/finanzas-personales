import sqlite3

from sqlalchemy import inspect

from finanzas import db


def test_base_de_datos_antigua_recibe_columnas_nuevas(tmp_path):
    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE cuentas (id INTEGER PRIMARY KEY, nombre VARCHAR(120), entidad VARCHAR(80), "
                "tipo VARCHAR(20), iban VARCHAR(34), origen VARCHAR(20), id_externo VARCHAR(80), "
                "saldo NUMERIC(14,2), saldo_fecha DATE, activa BOOLEAN)")
    con.execute("INSERT INTO cuentas (nombre, saldo, activa) VALUES ('Sabadell', 100, 1)")
    con.commit()
    con.close()

    eng = db.make_engine(f"sqlite:///{ruta}")
    db.init_db(eng)
    columnas = {c["name"] for c in inspect(eng).get_columns("cuentas")}
    assert {"conexion_id", "uid_externo", "ultima_sincronizacion"} <= columnas
    with eng.connect() as c:
        assert c.exec_driver_sql("SELECT nombre FROM cuentas").scalar() == "Sabadell"
