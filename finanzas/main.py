"""Aplicación. En local:  uvicorn finanzas.main:app   En Vercel la carga index.py.
Sirve la API JSON en /api y el frontal ya compilado (carpeta finanzas/web).
"""
import hmac
import logging
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import exc as sa_exc

from finanzas import auth, calendario, config, db, facturacion, gastos, sync
from finanzas.api import COOKIE_ESTADO_BANCO, router
from finanzas.categorizar import sembrar_categorias
from finanzas.integrations import enablebanking

# SQLite no tiene tipo decimal nativo; el aviso es esperado.
warnings.filterwarnings("ignore", category=sa_exc.SAWarning, message=".*Decimal.*")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

WEB = Path(__file__).parent / "web"
log = logging.getLogger("finanzas")


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    if db.engine is not None:
        with db.SessionLocal() as s:
            sembrar_categorias(s)
    programador = sync.Programador(config.SYNC_HORAS)
    programador.arrancar()
    yield
    programador.parar()


app = FastAPI(title="Finanzas personales", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(calendario.router)
app.include_router(gastos.router)
app.include_router(facturacion.router)
app.include_router(router)


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    respuesta = await call_next(request)
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("X-Frame-Options", "DENY")
    respuesta.headers.setdefault("Referrer-Policy", "same-origin")
    respuesta.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if config.EN_VERCEL:
        respuesta.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return respuesta


@app.get("/api/cron/sync")
def cron_sync(request: Request):
    """Tarea programada de Vercel (vercel.json). Vercel manda Authorization: Bearer CRON_SECRET."""
    esperado = f"Bearer {config.CRON_SECRET}"
    if not config.CRON_SECRET or not hmac.compare_digest(request.headers.get("authorization", ""), esperado):
        raise HTTPException(401, "No autorizado")
    db.asegurar_tablas()
    with db.SessionLocal() as s:
        return {"resultados": sync.sincronizar_todo(s)}


@app.get("/sabadell/vuelta", dependencies=[Depends(auth.requiere_sesion)])
def vuelta_sabadell(request: Request, code: str = "", state: str = ""):
    """Vuelta desde el banco cuando la app se sirve por https (Vercel). En local se pega la URL en Ajustes."""
    if not code:
        return RedirectResponse("/#/ajustes")
    esperado = request.cookies.get(COOKIE_ESTADO_BANCO, "")
    if not esperado or not hmac.compare_digest(state, esperado):
        motivo = "La vuelta del banco no corresponde a una conexión que hayas empezado aquí. Vuelve a pulsar Conectar."
        return RedirectResponse("/#/ajustes?" + urlencode({"sabadell_error": motivo}))
    db.asegurar_tablas()
    with db.SessionLocal() as s:
        try:
            enablebanking.completar_autorizacion(s, code)
        except Exception as e:  # el code del banco es de un solo uso: hay que enseñar el motivo
            s.rollback()
            log.exception("Fallo al completar la autorización de Sabadell")
            motivo = str(e) if isinstance(e, enablebanking.EnableBankingError) else f"{type(e).__name__}: {e}"
            return RedirectResponse("/#/ajustes?" + urlencode({"sabadell_error": motivo[:300]}))
        # La conexión ya está guardada; si la primera carga falla, queda registrada en Ajustes
        sync.sincronizar_sabadell(s)
        try:
            sync.guardar_instantanea(s)
        except Exception:
            s.rollback()
            log.exception("Fallo al guardar la foto del patrimonio")
    respuesta = RedirectResponse("/#/ajustes?sabadell=ok")
    respuesta.delete_cookie(COOKIE_ESTADO_BANCO, path="/")
    return respuesta


if (WEB / "index.html").exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
else:
    @app.get("/", response_class=HTMLResponse)
    def sin_frontal():
        return ("<p style='font-family:system-ui;padding:2rem'>Falta compilar el frontal: "
                "<code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code></p>")
