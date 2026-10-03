# Finanzas personales

Web local y privada para seguir tus finanzas: cuentas de Sabadell, Indexa Capital, nóminas,
actividad como autónomo (IVA e IRPF trimestral), piso alquilado con hipoteca, obra nueva,
objetivos (bodas, viajes) y patrimonio neto.

Todo se guarda en un fichero SQLite en `data/finanzas.db`, en tu ordenador. Nada sale de él
salvo las llamadas de solo lectura a la API de Indexa.

## Arrancar

Necesitas Python 3.11 o superior.

- macOS / Linux: `./arrancar.sh`
- Windows: doble clic en `arrancar.bat`

Abre http://127.0.0.1:8000. La primera vez instala las dependencias en `.venv`.

## Configurar

Edita `.env` (se crea a partir de `.env.example`):

- `INDEXA_TOKEN`: genéralo en tu área privada de Indexa (Configuración > Aplicaciones). Después,
  en **Cuentas**, pulsa *Actualizar Indexa Capital*.

## Primeros pasos

1. **Cuentas**: crea tu cuenta de Sabadell e importa el extracto (Excel o CSV descargado de la
   web del banco). Reimportar el mismo extracto no duplica movimientos.
2. **Inmuebles**: crea el piso alquilado con sus valores catastrales, añade la hipoteca de
   Sabadell, el contrato de alquiler y los gastos (IBI, comunidad, seguro...). Crea también la
   casa de obra nueva como *Obra nueva*.
3. **Planificación**: apunta los pagos a la promotora (marcando los ya pagados) y los objetivos
   (bodas, viajes).
4. **Autónomo**: registra facturas emitidas y gastos de la actividad. Verás el 303 y el 130
   estimados por trimestre.
5. **Nóminas**: registra las nóminas de Indra.

## Avisos

Las cifras fiscales son estimaciones orientativas. No sustituyen a la declaración ni a un asesor.

## Desarrollo

```
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest
.venv/bin/uvicorn finanzas.main:app --reload
```
