#!/usr/bin/env bash
# Arranca la app en http://127.0.0.1:8000 (solo accesible desde tu ordenador)
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
[ -f .env ] || cp .env.example .env
exec .venv/bin/uvicorn finanzas.main:app --host 127.0.0.1 --port 8000
