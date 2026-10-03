#!/usr/bin/env bash
# Arranca la app en http://127.0.0.1:8000 (solo accesible desde tu ordenador)
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
# Instala lo que falte (tras actualizar la app pueden aparecer dependencias nuevas)
.venv/bin/pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
mkdir -p data secretos
exec .venv/bin/uvicorn finanzas.main:app --host 127.0.0.1 --port 8000
