@echo off
REM Arranca la app en http://127.0.0.1:8000 (solo accesible desde tu ordenador)
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\pip install -q -r requirements.txt
)
if not exist .env copy .env.example .env
.venv\Scripts\uvicorn finanzas.main:app --host 127.0.0.1 --port 8000
