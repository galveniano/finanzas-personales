# Finanzas personales

Web local y privada para seguir tus finanzas: cuentas de Sabadell, fondos y planes de Indexa
Capital, nóminas, actividad como autónomo (IVA e IRPF trimestral), piso alquilado con hipoteca,
casa de obra nueva, objetivos (bodas, viajes) y patrimonio neto.

Todo se guarda en un fichero SQLite en `data/finanzas.db`, en tu ordenador. Lo único que sale
de él son llamadas de solo lectura a Sabadell (vía Enable Banking) y a Indexa.

## Arrancar

Necesitas Python 3.11 o superior. No hace falta Node: el frontal ya va compilado en
`finanzas/web`.

- macOS / Linux: `./arrancar.sh`
- Windows: doble clic en `arrancar.bat`

Abre http://127.0.0.1:8000. El script crea `.venv`, instala lo que falte y crea `.env` a partir
de `.env.example`.

## Conectar Sabadell y los fondos

Las dos conexiones son de solo lectura y se configuran en `.env`. Mientras la app está abierta
sincroniza sola al arrancar y cada `SYNC_HORAS` horas (6 por defecto); también hay un botón
**Sincronizar**. La pantalla **Conexiones** explica estos pasos y muestra el estado.

### Banco Sabadell (Enable Banking)

Sabadell no da API a particulares; se accede por open banking (PSD2) a través de
[Enable Banking](https://enablebanking.com), gratis para tus propias cuentas.

1. Crea una cuenta en Enable Banking y registra una aplicación en **Production**.
2. Como URL de vuelta pon `https://localhost:8000/sabadell/vuelta`.
3. Descarga la clave privada `.pem` y guárdala como `secretos/enablebanking.pem`
   (la carpeta `secretos/` está en `.gitignore`).
4. En el panel de Enable Banking, vincula tus cuentas de Sabadell (modo restringido gratuito).
5. Rellena `ENABLE_BANKING_APP_ID` en `.env` y reinicia la app.
6. En **Conexiones**, pulsa *Conectar con Sabadell*, entra con tus claves del banco y, al
   volver, copia la dirección de la pestaña (una página de localhost que no carga) y pégala en
   la app. El permiso dura 180 días; luego se renueva con un clic.

La primera sincronización trae los últimos 12 meses de movimientos y los categoriza.

### Indexa Capital

1. En tu área privada de Indexa: Configuración > Aplicaciones > generar token.
2. Pégalo en `.env` como `INDEXA_TOKEN=…` y reinicia la app.

### Sin conexión

En **Cuentas** también puedes importar el extracto (Excel o CSV) descargado de la web de
Sabadell. Reimportar el mismo extracto no duplica movimientos.

## Primeros pasos

1. **Inmuebles**: crea el piso alquilado con sus valores catastrales, la hipoteca, el contrato
   de alquiler con sus cambios de renta y los gastos (IBI, comunidad, seguro…). Crea también la
   casa de obra nueva.
2. **Planificación**: apunta los pagos a la promotora y los objetivos (boda, viajes).
3. **Autónomo**: registra facturas emitidas y gastos de la actividad para ver el 303 y el 130
   estimados de cada trimestre.
4. **Nóminas**: registra las nóminas de Indra.

## Privacidad

- La app escucha solo en `127.0.0.1`.
- Nunca subas `.env`, `secretos/` ni `data/`: ya están en `.gitignore`.
- Las cifras fiscales son estimaciones orientativas. No sustituyen a la declaración ni a un
  asesor.

## Desarrollo

Backend (FastAPI + SQLAlchemy):

```
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest
.venv/bin/uvicorn finanzas.main:app --reload
```

Frontal (React + Vite + Tailwind) en `frontend/`. Necesita Node 20 o superior:

```
cd frontend
npm install
npm run dev     # http://localhost:5173, con /api redirigido al backend en :8000
npm run build   # compila en finanzas/web, que es lo que sirve la app
```

Tras cambiar el frontal, ejecuta `npm run build` y sube también `finanzas/web`.
