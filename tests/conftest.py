import os
import tempfile

# Base de datos temporal antes de importar la app
os.environ["FINANZAS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
