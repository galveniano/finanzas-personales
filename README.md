# Finanzas personales

Web local y privada para seguir tus finanzas: cuentas de Sabadell, fondos y planes de Indexa
Capital, nóminas, actividad como autónomo (IVA e IRPF trimestral), piso alquilado con hipoteca,
casa de obra nueva, objetivos (bodas, viajes) y patrimonio neto.

En tu ordenador todo se guarda en un fichero SQLite en `data/finanzas.db`. Si la publicas en
Vercel, los datos van a una base de datos Postgres y solo se entra con tu cuenta de Google.

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

## Publicarla en Vercel

Así la ves desde el móvil o cualquier ordenador. Solo entran las cuentas de Google que pongas en
`EMAILS_PERMITIDOS`; sin sesión la API no devuelve ningún dato. Todo cabe en los planes gratuitos.

1. **Proyecto**: en [vercel.com](https://vercel.com) entra con GitHub, *Add New > Project* e
   importa `finanzas-personales`. No cambies nada de la configuración y despliega. Saldrá un
   error porque falta la base de datos: es normal.
2. **Base de datos**: en el proyecto, *Storage > Create Database > Neon (Postgres)*, región
   Frankfurt, y conéctala al proyecto. Vercel añade `DATABASE_URL` sola.
3. **Google**: en [Google Cloud Console](https://console.cloud.google.com/apis/credentials) crea
   un proyecto, configura la pantalla de consentimiento (tipo *Externo*, en modo prueba, con tu
   email como usuario de prueba) y después *Crear credenciales > ID de cliente de OAuth >
   Aplicación web*. En *Orígenes de JavaScript autorizados* pon la URL de Vercel
   (`https://tu-proyecto.vercel.app`). Copia el ID de cliente.
4. **Variables** (*Settings > Environment Variables*):
   - `GOOGLE_CLIENT_ID`: el ID del paso anterior.
   - `EMAILS_PERMITIDOS`: tu Gmail.
   - `SESSION_SECRET` y `CRON_SECRET`: dos cadenas aleatorias distintas (`openssl rand -hex 32`).
   - `INDEXA_TOKEN`, `ENABLE_BANKING_APP_ID` y `ENABLE_BANKING_KEY` con el **contenido** del
     `.pem` pegado tal cual.
   - `ENABLE_BANKING_REDIRECT_URL=https://tu-proyecto.vercel.app/sabadell/vuelta` (añade esa
     misma URL de vuelta en tu aplicación de Enable Banking). Así el banco vuelve directo a la
     app y no hace falta pegar ninguna dirección.
5. *Deployments > Redeploy*. Abre la URL y entra con Google.

En Vercel no hay un proceso siempre encendido: una tarea programada (`vercel.json`) sincroniza
Sabadell e Indexa cada día a las 6:00 UTC, y el botón **Sincronizar** lo hace al momento. Cada
vez que se fusiona algo en `main`, Vercel publica la versión nueva sola.

## Asistente y facturas de Google Drive

Los dos usan un modelo de IA: OpenAI por defecto, o Claude (Anthropic) si lo prefieres. La clave se
pone desde la propia app, en **Conexiones → Asistente (IA)**, y se guarda cifrada en la base de datos
(con `SESSION_SECRET`). Saca la clave en [platform.openai.com/api-keys](https://platform.openai.com/api-keys);
es de pago por uso, aparte de cualquier suscripción. También vale ponerla en las variables de entorno
(`OPENAI_API_KEY` o `ANTHROPIC_API_KEY`). Pon también `NOMBRE_TITULAR` y
`NIF_TITULAR` para que distinga bien las facturas que emites de las que recibes.

- **Asistente**: responde preguntas sobre tus finanzas con los datos de la app. Solo puede leer.
- **Drive** (en Conexiones): necesita la app publicada con Google y la *Google Drive API*
  habilitada en tu proyecto de Google Cloud. Busca PDF de facturas y justificantes de Hacienda:
  tus facturas emitidas pasan a Autónomo, los justificantes a Hacienda y las facturas recibidas
  quedan para que marques si son gasto de la actividad. El permiso de Drive es de solo lectura,
  dura una hora y no se guarda.

## Primeros pasos

1. **Inmuebles**: crea el piso alquilado con sus valores catastrales, la hipoteca, el contrato
   de alquiler con sus cambios de renta y los gastos (IBI, comunidad, seguro…). Crea también la
   casa de obra nueva.
2. **Planificación**: apunta los pagos a la promotora y los objetivos (boda, viajes).
3. **Autónomo**: registra facturas emitidas y gastos de la actividad para ver el 303 y el 130
   estimados de cada trimestre.
4. **Hacienda**: sube los justificantes PDF de los modelos que ya has presentado (303, 130,
   renta). La app lee el modelo, el periodo y el importe y los compara con lo que calcula.
5. **Nóminas**: registra las nóminas de Indra.

## Privacidad

- En local la app escucha solo en `127.0.0.1` y no pide sesión (salvo que pongas `GOOGLE_CLIENT_ID`).
- Publicada, solo entran los emails de `EMAILS_PERMITIDOS`.
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
