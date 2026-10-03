"""Configuración leída del entorno y de un fichero .env opcional en la raíz."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(ROOT / ".env")

DB_PATH = Path(os.environ.get("FINANZAS_DB") or ROOT / "data" / "finanzas.db")
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH

INDEXA_TOKEN = os.environ.get("INDEXA_TOKEN", "")
INDEXA_BASE_URL = os.environ.get("INDEXA_BASE_URL", "https://api.indexacapital.com")

# Comunidad autónoma de residencia (tramo autonómico del IRPF, Patrimonio)
CCAA = os.environ.get("CCAA", "Murcia")

# Enable Banking (sincronización de Sabadell). Ver README.
ENABLE_BANKING_APP_ID = os.environ.get("ENABLE_BANKING_APP_ID", "")
ENABLE_BANKING_KEY = os.environ.get("ENABLE_BANKING_KEY", "")  # ruta al .pem de la aplicación
ENABLE_BANKING_REDIRECT_URL = os.environ.get(
    "ENABLE_BANKING_REDIRECT_URL", "https://localhost:8000/sabadell/vuelta"
)
ENABLE_BANKING_BASE_URL = os.environ.get("ENABLE_BANKING_BASE_URL", "https://api.enablebanking.com")
BANCO = os.environ.get("BANCO", "Banco Sabadell")

# Cada cuántas horas sincroniza sola mientras la app está abierta (0 = nunca)
SYNC_HORAS = float(os.environ.get("SYNC_HORAS", "6"))
