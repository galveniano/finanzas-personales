import os
import tempfile

# Base de datos temporal y sin sincronización automática antes de importar la app
os.environ["FINANZAS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["SYNC_HORAS"] = "0"
os.environ["INDEXA_TOKEN"] = ""
