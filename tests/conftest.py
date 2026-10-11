import os
import tempfile

import pytest

# Base de datos temporal y sin sincronización automática antes de importar la app.
# DATABASE_URL se vacía para que la suite nunca use la base de datos real del .env.
os.environ["FINANZAS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["SYNC_HORAS"] = "0"
os.environ["INDEXA_TOKEN"] = ""
os.environ["DATABASE_URL"] = ""
os.environ["POSTGRES_URL"] = ""


@pytest.fixture(autouse=True)
def sin_supuestos_al_acabar():
    """La base de datos de los tests es compartida: ningún test deja supuestos de la previsión
    (sueldo, clientes, aportaciones a pensiones...) que cambien los cálculos de los siguientes."""
    yield
    from finanzas import ajustes, db, prevision
    db.asegurar_tablas()
    with db.SessionLocal() as s:
        ajustes.guardar(s, prevision.CLAVE, "")
