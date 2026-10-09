# Finanzas personales

Web privada para seguir tus finanzas: cuentas de Sabadell, fondos y planes de Indexa Capital,
nómina, actividad como autónomo (IVA e IRPF trimestral, renta), piso alquilado con hipoteca, casa
de obra nueva, inversiones en private equity, objetivos (boda, viajes) y patrimonio neto.

En tu ordenador todo se guarda en un fichero SQLite en `data/finanzas.db`. Si la publicas en
Vercel, los datos van a una base de datos Postgres y solo se entra con tu cuenta de Google.

## Arrancar

Necesitas Python 3.12 o superior. No hace falta Node: el frontal ya va compilado en
`finanzas/web`.

- macOS / Linux: `./arrancar.sh`
- Windows: doble clic en `arrancar.bat`

Abre http://127.0.0.1:8000. El script crea `.venv`, instala lo que falte y crea `.env` a partir
de `.env.example`. En el móvil puedes añadirla a la pantalla de inicio: se abre como una app.

## Qué hay en cada pantalla

- **Inicio**: patrimonio neto y su evolución, lo que tienes disponible de verdad (descontando lo
  que debes a Hacienda), lo que ganas al mes, próximos pagos y avisos (plazos, permiso del banco a
  punto de caducar, valoraciones viejas, copia de seguridad pendiente…).
- **Cuentas**: saldos y movimientos de tus cuentas, sincronizados con el banco o importados del
  extracto (Excel o CSV) sin duplicar nada. Categorías, reglas que aprenden al corregir un
  movimiento, movimientos a mano y de quién es cada cuenta (tuya, compartida o de otra persona).
- **Gastos**: análisis de los últimos meses (ingresos, gastos, ahorro, por categoría y por sitio),
  los gastos más grandes, suscripciones y recibos fijos con su logo, y presupuestos.
- **Ingresos**: pestaña **Autónomo** (facturas emitidas con su documento para imprimir o guardar
  en PDF, numeración automática, calendario de días trabajados y vacaciones, cobros pendientes,
  libro de facturas, gastos de la actividad) y pestaña **Nómina** (nóminas registradas o leídas
  de su PDF, lo que el banco ve de ellas y una calculadora de sueldo). Arriba, lo que ganas al mes
  según tu sueldo y tus tarifas.
- **Impuestos**: 303 y 130 de cada trimestre (presentado, previsto o estimado), los modelos ya
  presentados leídos de sus justificantes PDF o .txt de la AEAT, la renta estimada del año, lo
  que debes hoy, la hucha para impuestos, la revisión de la cuota de autónomos, cuánto te
  ahorrarías aportando a un plan de pensiones y un calendario de plazos al que suscribirte desde
  Google Calendar.
- **Bienes**: inmuebles (precio, catastro, valoraciones, contratos de alquiler con sus cambios de
  renta, gastos, rendimiento fiscal del alquiler y rentabilidad), hipotecas con su cuadro y la
  simulación de amortizar anticipadamente, préstamos, la obra nueva con sus pagos a la promotora y
  su escritura, coches que se deprecen solos, y «vender o seguir alquilando».
- **Plan**: objetivos de ahorro, pagos previstos (conciliados con lo que sale del banco), previsión
  mes a mes de liquidez con nómina, cobros, alquiler, gastos e impuestos que vienen, y escenarios.
- **Inversiones**: cartera de Indexa (fondos, peso, rentabilidad) y fondos de private equity con
  sus llamadas de capital, NAV y TVPI.
- **Ajustes**: conexiones con Sabadell e Indexa (con su historial de sincronizaciones), asistente
  (IA), facturas de Google Drive, importar datos, copia de seguridad y restaurarla, apariencia,
  estado de la app y sesiones.
- **Asistente**: pregunta en lenguaje natural sobre tus finanzas; ve los datos de la app y dice
  qué ha mirado en cada respuesta. Solo puede leer.

En cualquier pantalla, **Ctrl K** (⌘ K en Mac) o el botón **Buscar** abre la paleta: busca
movimientos, facturas, clientes, bienes, objetivos, declaraciones y categorías, salta a cualquier
sección y ejecuta acciones (nueva factura, nuevo objetivo, sincronizar, cambiar el tema). Con `g`
seguido de una letra vas a una pantalla (`g c` Cuentas, `g p` Plan…) y `?` enseña la lista de
atajos. El tema (claro, oscuro o el del sistema) se cambia en el menú lateral o en Ajustes.

## Conectar Sabadell y los fondos

Las dos conexiones son de solo lectura y se configuran en `.env`. Mientras la app está abierta
sincroniza sola al arrancar y cada `SYNC_HORAS` horas (6 por defecto); también hay un botón
**Sincronizar**. La pantalla **Ajustes** explica estos pasos, muestra el estado y las últimas
sincronizaciones de cada fuente.

### Banco Sabadell (Enable Banking)

Sabadell no da API a particulares; se accede por open banking (PSD2) a través de
[Enable Banking](https://enablebanking.com), gratis para tus propias cuentas.

1. Crea una cuenta en Enable Banking y registra una aplicación en **Production**.
2. Como URL de vuelta pon `https://localhost:8000/sabadell/vuelta`.
3. Descarga la clave privada `.pem` y guárdala como `secretos/enablebanking.pem`
   (la carpeta `secretos/` está en `.gitignore`).
4. En el panel de Enable Banking, vincula tus cuentas de Sabadell (modo restringido gratuito).
5. Rellena `ENABLE_BANKING_APP_ID` en `.env` y reinicia la app.
6. En **Ajustes**, pulsa *Conectar con Sabadell*, entra con tus claves del banco y, al volver,
   copia la dirección de la pestaña (una página de localhost que no carga) y pégala en la app.
   El permiso dura 180 días; luego se renueva con un clic, y con *Desconectar* se da de baja
   (las cuentas y sus movimientos se quedan).

La primera sincronización trae los últimos meses de movimientos por tramos y los categoriza;
Ajustes dice desde qué fecha los tienes.

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
vez que se fusiona algo en `main`, Vercel publica la versión nueva sola. Si el despliegue deja un
fichero `finanzas/version.txt` con el hash corto de git, Ajustes lo enseña.

## Asistente y facturas de Google Drive

Los dos usan un modelo de IA: OpenAI por defecto, o Claude (Anthropic) si lo prefieres. La clave se
pone desde la propia app, en **Ajustes → Asistente (IA)**, y se guarda cifrada en la base de datos
(con `SESSION_SECRET`). Saca la clave en [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
o en [console.anthropic.com](https://console.anthropic.com/settings/keys); es de pago por uso, aparte
de cualquier suscripción. También vale ponerla en las variables de entorno (`OPENAI_API_KEY` o
`ANTHROPIC_API_KEY`).

- **Asistente**: responde preguntas sobre tus finanzas con los datos de la app (lo que debes a
  Hacienda, el ahorro fiscal de aportar al plan de pensiones, vender o alquilar el piso, en qué
  gastas, la previsión…) y enseña qué ha mirado. Solo puede leer. Cada respuesta tiene un tope de
  tiempo: si se agota, lo dice y te pide concretar.
- **Drive** (en Ajustes): necesita la app publicada con Google y la *Google Drive API*
  habilitada en tu proyecto de Google Cloud. Busca PDF de facturas y justificantes de Hacienda:
  tus facturas emitidas pasan a Autónomo, los justificantes a Impuestos (estos no necesitan clave
  de IA) y las facturas recibidas quedan para que marques si son gasto de la actividad. Un
  documento se lee una vez; si cambia en Drive o pulsas «Volver a leer», se lee otra vez. Para
  distinguir tus facturas de las que recibes usa tu nombre y NIF de **Ingresos → Datos de
  facturación** (o, si no están, `NOMBRE_TITULAR` y `NIF_TITULAR` del `.env`). El permiso de
  Drive es de solo lectura, dura una hora y no se guarda.

## Copia de seguridad

En **Ajustes → Copia de seguridad** bajas todos tus datos en un `.json` (con o sin los PDF de
Hacienda), los movimientos en Excel, o guardas la copia en tu Google Drive. Para restaurarla,
elige ese fichero en **Importar datos**: la app lo reconoce como copia completa, enseña qué trae
y, si confirmas, sustituye todos los datos (aquí o en otra instalación). Las claves del
asistente no viajan en la copia. Si pasa un mes sin copia, Inicio te lo recuerda.

## Primeros pasos

1. **Bienes**: crea el piso alquilado con sus valores catastrales, la hipoteca, el contrato de
   alquiler con sus cambios de renta y los gastos (IBI, comunidad, seguro…). Crea también la
   casa de obra nueva con sus pagos a la promotora.
2. **Plan**: apunta los objetivos (boda, viajes) y los pagos previstos.
3. **Ingresos**: pon tu sueldo y tus tarifas en «Sueldo y tarifas», registra las facturas
   emitidas y los gastos de la actividad para ver el 303 y el 130 estimados de cada trimestre, y
   sube las nóminas en PDF.
4. **Impuestos**: sube los justificantes PDF o .txt de los modelos que ya has presentado (303,
   130, renta). La app lee el modelo, el periodo y el importe y los compara con lo que calcula.
5. **Ajustes**: conecta el banco e Indexa, pon la clave del asistente y haz una copia.

## Privacidad

- En local la app escucha solo en `127.0.0.1` y no pide sesión (salvo que pongas `GOOGLE_CLIENT_ID`).
- Publicada, solo entran los emails de `EMAILS_PERMITIDOS`.
- Nunca subas `.env`, `secretos/` ni `data/`: ya están en `.gitignore`.
- Las cifras fiscales son estimaciones orientativas. No sustituyen a la declaración ni a un
  asesor.

## Desarrollo

Backend (FastAPI + SQLAlchemy 2):

```
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest
.venv/bin/uvicorn finanzas.main:app --reload
```

Frontal (React 19 + Vite + Tailwind 4) en `frontend/`. Necesita Node 22 o superior:

```
cd frontend
npm install
npm run dev     # http://localhost:5173, con /api redirigido al backend en :8000
npm run lint    # oxlint
npm run build   # tsc + compila en finanzas/web, que es lo que sirve la app
```

Tras cambiar el frontal, ejecuta `npm run build` y sube también `finanzas/web`. Los iconos de
`frontend/public/` (favicon, pantalla de inicio del móvil) salen del mismo trazo que el logo.
