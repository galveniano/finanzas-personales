"""Aplicación. En local:  uvicorn finanzas.main:app   En Vercel la carga index.py.

Sirve la API JSON en /api y el frontal ya compilado (carpeta finanzas/web).
"""
import hmac
import logging
import warnings
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import exc as sa_exc

from finanzas import auth, config, db, sync
from finanzas.api import router
from finanzas.categorizar import sembrar_categorias
from finanzas.integrations import enablebanking

# SQLite no tiene tipo decimal nativo; el aviso es esperado.
warnings.filterwarnings("ignore", category=sa_exc.SAWarning, message=".*Decimal.*")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

WEB = Path(__file__).parent / "web"


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    with db.SessionLocal() as s:
        sembrar_categorias(s)
    programador = sync.Programador(config.SYNC_HORAS)
    programador.arrancar()
    yield
    programador.parar()


app = FastAPI(title="Finanzas personales", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(router)


@app.get("/api/cron/sync")
def cron_sync(request: Request):
    """Tarea programada de Vercel (vercel.json). Vercel manda Authorization: Bearer CRON_SECRET."""
    esperado = f"Bearer {config.CRON_SECRET}"
    if not config.CRON_SECRET or not hmac.compare_digest(request.headers.get("authorization", ""), esperado):
        raise HTTPException(401, "No autorizado")
    with db.SessionLocal() as s:
        return {"resultados": sync.sincronizar_todo(s)}


@app.get("/sabadell/vuelta", dependencies=[Depends(auth.requiere_sesion)])
def vuelta_sabadell(code: str = ""):
    """Vuelta desde el banco cuando la app se sirve por https (Vercel). En local se pega la URL en Conexiones."""
    if not code:
        return RedirectResponse("/#/conexiones")
    with db.SessionLocal() as s:
        try:
            enablebanking.completar_autorizacion(s, code)
            sync.sincronizar_sabadell(s)
            sync.guardar_instantanea(s)
        except enablebanking.EnableBankingError:
            pass
    return RedirectResponse("/#/conexiones")


if (WEB / "index.html").exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
else:
    @app.get("/", response_class=HTMLResponse)
    def sin_frontal():
        return ("<p style='font-family:system-ui;padding:2rem'>Falta compilar el frontal: "
                "<code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code></p>")
