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

# En Vercel (o cualquier nube) el disco no persiste: hace falta una base de datos Postgres.
EN_VERCEL = bool(os.environ.get("VERCEL"))
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or ""

DB_PATH = Path(os.environ.get("FINANZAS_DB") or ROOT / "data" / "finanzas.db")
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH

INDEXA_TOKEN = os.environ.get("INDEXA_TOKEN", "")
INDEXA_BASE_URL = os.environ.get("INDEXA_BASE_URL", "https://api.indexacapital.com")

# Comunidad autónoma de residencia (tramo autonómico del IRPF, Patrimonio)
CCAA = os.environ.get("CCAA", "Murcia")

# Enable Banking (sincronización de Sabadell). Ver README.
ENABLE_BANKING_APP_ID = os.environ.get("ENABLE_BANKING_APP_ID", "")
# Ruta al .pem de la aplicación, o su contenido entero (así se guarda en Vercel)
ENABLE_BANKING_KEY = os.environ.get("ENABLE_BANKING_KEY", "")
ENABLE_BANKING_REDIRECT_URL = os.environ.get(
    "ENABLE_BANKING_REDIRECT_URL", "https://localhost:8000/sabadell/vuelta"
)
ENABLE_BANKING_BASE_URL = os.environ.get("ENABLE_BANKING_BASE_URL", "https://api.enablebanking.com")
BANCO = os.environ.get("BANCO", "Banco Sabadell")

# Cada cuántas horas sincroniza sola mientras la app está abierta (0 = nunca).
# En Vercel no hay procesos permanentes: sincroniza una tarea programada (vercel.json).
# SYNC_HORAS= vacío en el .env vale como «no dicho»: 6 horas.
SYNC_HORAS = 0.0 if EN_VERCEL else float(os.environ.get("SYNC_HORAS") or "6")
# Secreto con el que Vercel llama a la tarea programada (Authorization: Bearer ...)
CRON_SECRET = os.environ.get("CRON_SECRET", "")

# Acceso con Google. Si GOOGLE_CLIENT_ID está vacío y la app corre en tu ordenador, no pide
# iniciar sesión. En Vercel siempre lo pide.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
EMAILS_PERMITIDOS = {e.strip().lower() for e in os.environ.get("EMAILS_PERMITIDOS", "").split(",") if e.strip()}
SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
AUTH_REQUERIDA = bool(GOOGLE_CLIENT_ID) or EN_VERCEL


def secreto(obligatorio: bool = True) -> str:
    """SESSION_SECRET comprobado en un solo sitio: firma la sesión (auth), cifra las claves guardadas (ajustes)
    y deriva el token del calendario. Si falta o es corto y es obligatorio, 503 con el motivo; si no es obligatorio
    (en local, sin sesión) vale lo que haya o un secreto fijo: la base de datos está en tu ordenador."""
    if len(SESSION_SECRET) >= 32:
        return SESSION_SECRET
    if obligatorio:
        from fastapi import HTTPException
        raise HTTPException(503, "Falta SESSION_SECRET (al menos 32 caracteres) en la configuración")
    return SESSION_SECRET or "finanzas-local"

# Asistente y lectura de documentos (OpenAI o Claude). Se puede configurar también desde la app.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "")
# Tu NIF y nombre, para distinguir las facturas que emites de las que recibes (opcional)
NIF_TITULAR = os.environ.get("NIF_TITULAR", "").upper().replace(" ", "")
NOMBRE_TITULAR = os.environ.get("NOMBRE_TITULAR", "")
