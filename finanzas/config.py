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
