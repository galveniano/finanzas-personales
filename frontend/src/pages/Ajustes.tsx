import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, Download, ExternalLink, LogOut, RefreshCw, Unplug, Upload, X } from 'lucide-react'
import { api, esDemo } from '../lib/api'
import { diasHasta, fecha, fechaHora } from '../lib/format'
import type { ConexionSabadell, EstadoApp, EstadoAuth, EstadoSync, HistorialSync, ResultadoImportacion, UltimaSync, UrlBanco, VistaPreviaImportacion } from '../lib/tipos'
import { permisoDrive, subirADrive } from '../lib/google'
import { aplicarTema, TEMAS, useTema } from '../lib/tema'
import AjustesIA from '../components/AjustesIA'
import DriveImport from '../components/DriveImport'
import { useAccion, useAvisos } from '../lib/utilidades'
import { useSubida } from '../lib/subida'
import { useSincronizar } from '../lib/sincronizar'
import { Boton, Cabecera, Campo, Cargando, Dialogo, EnDosPasos, Etiqueta, ErrorCarga, Fila, Segmentos, Tarjeta } from '../components/ui'

const useAuth = () => useQuery({ queryKey: ['auth'], queryFn: () => api.get<EstadoAuth>('/auth/estado'), enabled: !esDemo, staleTime: Infinity })

function Ultima({ u }: { u: UltimaSync | null }) {
  if (!u) return <p className="text-sm text-muted">Todavía no se ha sincronizado.</p>
  return (
    <p className={`text-sm ${u.ok ? 'text-muted' : 'text-neg'}`}>
      {u.ok ? 'Última sincronización' : 'Falló la última vez'} el {fechaHora(u.fecha, { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}: {u.mensaje}
    </p>
  )
}

/** Las últimas sincronizaciones de una fuente, plegadas. */
function Historial({ filas }: { filas: UltimaSync[] | undefined }) {
  if (!filas?.length) return null
  return (
    <details className="mt-3 text-sm">
      <summary className="cursor-pointer text-muted">Últimas {filas.length} sincronizaciones</summary>
      <ul className="mt-2 divide-y divide-line text-xs">
        {filas.map((r, i) => (
          <li key={i} className="flex items-start gap-2 py-1.5">
            {r.ok ? <Check size={14} className="mt-0.5 shrink-0 text-pos" aria-label="Bien" /> : <X size={14} className="mt-0.5 shrink-0 text-neg" aria-label="Falló" />}
            <span className="cifra shrink-0 text-muted">{fechaHora(r.fecha)}</span>
            <span className={`min-w-0 break-words ${r.ok ? '' : 'text-neg'}`}>{r.mensaje}</span>
          </li>
        ))}
      </ul>
    </details>
  )
}

function Paso({ n, children }: { n: number; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="cifra grid size-6 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-medium text-accent">{n}</span>
      <span className="min-w-0 pt-0.5">{children}</span>
    </li>
  )
}

const Codigo = ({ children }: { children: ReactNode }) => (
  <code className="cifra rounded bg-panel-2 px-1.5 py-0.5 text-[13px] break-all">{children}</code>
)

function Sabadell({ s, enVercel, historial }: { s: EstadoSync['sabadell']; enVercel: boolean; historial?: UltimaSync[] }) {
  const avisar = useAvisos()
  const [urlBanco, setUrlBanco] = useState<string | null>(null)
  const [vuelta, setVuelta] = useState('')
  const conectar = useAccion(async () => {
    const r = await api.post<UrlBanco>('/sync/sabadell/conectar')
    // Publicada: el banco vuelve sola a la app. En local hay que pegar la dirección de vuelta.
    if (s.vuelta_automatica) { window.location.href = r.url; return }
    setUrlBanco(r.url)
    window.open(r.url, '_blank', 'noopener')
  })
  const completar = useAccion(async () => {
    const r = await api.post<ConexionSabadell>('/sync/sabadell/completar', { codigo: vuelta })
    setUrlBanco(null)
    setVuelta('')
    avisar(`Sabadell conectado. ${r.sync.mensaje}`, r.sync.ok ? 'ok' : 'error')
  })
  const sincronizar = useSincronizar('/sync/sabadell')
  const desconectar = useAccion(() => api.post('/sync/sabadell/desconectar'), 'Sabadell desconectado: las cuentas se quedan, pero ya no se sincronizan')
  const dias = s.valida_hasta ? diasHasta(s.valida_hasta) : null

  return (
    <Tarjeta titulo="Banco Sabadell" accion={
      !s.configurado ? <Etiqueta tono="aviso">Sin configurar</Etiqueta>
        : s.conectado ? <Etiqueta tono={dias != null && dias < 15 ? 'aviso' : 'bien'}>Conectado{dias != null && ` · caduca en ${dias} días`}</Etiqueta>
          : <Etiqueta tono="aviso">Sin conectar</Etiqueta>}>
      <p className="mb-4 text-sm text-muted">
        Lee saldos y movimientos de tus cuentas mediante open banking (PSD2) a través de Enable Banking, gratis para tus propias cuentas.
        Solo lectura: nadie puede mover dinero desde aquí. El permiso dura 180 días y luego se renueva con un clic.
      </p>

      {!s.configurado && (enVercel ? (
        <ol className="space-y-3 text-sm">
          <Paso n={1}>Crea una aplicación en <a className="font-medium text-accent" href="https://enablebanking.com/cp/applications" target="_blank" rel="noreferrer">enablebanking.com</a> en <strong>Production</strong>, con la URL de vuelta <Codigo>{s.url_vuelta?.startsWith('https://localhost') ? `${window.location.origin}/sabadell/vuelta` : s.url_vuelta}</Codigo>, y guarda el fichero .pem que descarga.</Paso>
          <Paso n={2}>En el panel de Enable Banking, pulsa <strong>Activate by linking accounts</strong> y vincula tu cuenta de Sabadell.</Paso>
          <Paso n={3}>En Vercel, Settings → Environment Variables, añade <Codigo>ENABLE_BANKING_APP_ID</Codigo> (el nombre del .pem sin la extensión), <Codigo>ENABLE_BANKING_KEY</Codigo> (todo el contenido del .pem) y <Codigo>ENABLE_BANKING_REDIRECT_URL</Codigo> (la URL de vuelta).</Paso>
          <Paso n={4}>Vuelve a desplegar (Deployments → ⋯ → Redeploy) y aquí aparecerá el botón para conectar.</Paso>
        </ol>
      ) : (
        <ol className="space-y-3 text-sm">
          <Paso n={1}>Crea una cuenta en <a className="font-medium text-accent" href="https://enablebanking.com/cp/applications" target="_blank" rel="noreferrer">enablebanking.com</a> y registra una aplicación en <strong>Production</strong>.</Paso>
          <Paso n={2}>Como URL de vuelta pon <Codigo>https://localhost:8000/sabadell/vuelta</Codigo>. No hace falta que funcione: luego copiarás la dirección.</Paso>
          <Paso n={3}>Descarga la clave privada (.pem) y guárdala en la carpeta <Codigo>secretos/</Codigo> de la app.</Paso>
          <Paso n={4}>En el panel de Enable Banking, vincula tus cuentas de Sabadell para activar el modo restringido gratuito.</Paso>
          <Paso n={5}>En el fichero <Codigo>.env</Codigo> rellena <Codigo>ENABLE_BANKING_APP_ID</Codigo> y <Codigo>ENABLE_BANKING_KEY=secretos/tu-clave.pem</Codigo>, y reinicia la app.</Paso>
        </ol>
      ))}

      {s.configurado && !urlBanco && (
        <div className="flex flex-wrap gap-2">
          <Boton onClick={() => conectar.mutate(undefined)} disabled={conectar.isPending}>
            <ExternalLink size={15} />{s.conectado ? 'Renovar permiso' : 'Conectar con Sabadell'}
          </Boton>
          {s.conectado && (
            <Boton variante="secundario" onClick={() => sincronizar.mutate(undefined)} disabled={sincronizar.isPending}>
              <RefreshCw size={15} className={sincronizar.isPending ? 'animate-spin' : ''} />Sincronizar ahora
            </Boton>
          )}
          {s.conectado && (
            <EnDosPasos variante="fantasma" icono={<Unplug size={15} />} texto="Desconectar" textoConfirmar="¿Seguro? Desconectar el banco"
              disabled={desconectar.isPending} onConfirmar={() => desconectar.mutate(undefined)} />
          )}
        </div>
      )}

      {urlBanco && (
        <div className="space-y-3 rounded-xl bg-panel-2 p-4 text-sm">
          <p>Se ha abierto la página de Sabadell en otra pestaña. Si no, <a href={urlBanco} target="_blank" rel="noreferrer" className="font-medium text-accent">ábrela aquí</a>.</p>
          <p className="text-muted">Al terminar, el navegador irá a una página de localhost que no carga. Es normal: copia la dirección completa de esa pestaña y pégala aquí.</p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Campo value={vuelta} onChange={(e) => setVuelta(e.target.value)} placeholder="https://localhost:8000/sabadell/vuelta?code=…"
              className="min-w-0 flex-1" aria-label="Dirección de vuelta" />
            <Boton onClick={() => completar.mutate(undefined)} disabled={!vuelta || completar.isPending}>{completar.isPending ? 'Conectando…' : 'Terminar'}</Boton>
          </div>
        </div>
      )}
      <div className="mt-4"><Ultima u={s.ultima} /></div>
      {s.historico_desde && (
        <p className="mt-1 text-xs text-muted">Movimientos del banco desde el {fecha(s.historico_desde)}. La primera carga va por tramos hacia atrás: sincroniza otra vez si quieres más historial.</p>
      )}
      <Historial filas={historial} />
    </Tarjeta>
  )
}

function Indexa({ s, enVercel, historial }: { s: EstadoSync['indexa']; enVercel: boolean; historial?: UltimaSync[] }) {
  const sincronizar = useSincronizar('/sync/indexa')
  return (
    <Tarjeta titulo="Indexa Capital" accion={<Etiqueta tono={s.configurado ? 'bien' : 'aviso'}>{s.configurado ? 'Conectado' : 'Sin configurar'}</Etiqueta>}>
      <p className="mb-4 text-sm text-muted">Trae el valor de tus fondos y planes con la API oficial de Indexa. Solo lectura.</p>
      {s.configurado ? (
        <Boton variante="secundario" onClick={() => sincronizar.mutate(undefined)} disabled={sincronizar.isPending}>
          <RefreshCw size={15} className={sincronizar.isPending ? 'animate-spin' : ''} />Sincronizar ahora
        </Boton>
      ) : (
        <ol className="space-y-3 text-sm">
          <Paso n={1}>En tu área privada de Indexa, entra en Configuración y genera un token de API.</Paso>
          <Paso n={2}>{enVercel
            ? <>En Vercel, Settings → Environment Variables, añade <Codigo>INDEXA_TOKEN</Codigo> y vuelve a desplegar.</>
            : <>Pégalo en <Codigo>.env</Codigo> como <Codigo>INDEXA_TOKEN=…</Codigo> y reinicia la app.</>}</Paso>
        </ol>
      )}
      <div className="mt-4"><Ultima u={s.ultima} /></div>
      <Historial filas={historial} />
    </Tarjeta>
  )
}

/** Al volver del banco (app publicada) la dirección trae el resultado: se avisa y se limpia. */
function useVueltaBanco() {
  const [params, setParams] = useSearchParams()
  const avisar = useAvisos()
  const errorBanco = params.get('sabadell_error')
  const ok = params.get('sabadell')
  useEffect(() => {
    if (!errorBanco && !ok) return
    avisar(errorBanco ? `No se pudo conectar Sabadell: ${errorBanco}` : 'Sabadell conectado', errorBanco ? 'error' : 'ok')
    setParams({}, { replace: true })
  }, [errorBanco, ok, avisar, setParams])
}

function Apariencia() {
  const tema = useTema()
  return (
    <Tarjeta titulo="Apariencia">
      <p className="mb-4 text-sm text-muted">Claro, oscuro o el que tenga el sistema. Se recuerda en este navegador.</p>
      <Segmentos etiqueta="Tema" opciones={TEMAS} valor={tema} onCambiar={aplicarTema} />
    </Tarjeta>
  )
}

function EstadoDeLaApp() {
  const { data: e, error } = useQuery({ queryKey: ['app-estado'], queryFn: () => api.get<EstadoApp>('/app/estado') })
  if (error && !e) return <Tarjeta titulo="Estado de la app"><ErrorCarga error={error} /></Tarjeta>
  if (!e) return null
  const copia = e.ultima_copia
  const textoCopia = !copia ? 'ninguna todavía'
    : `${fecha(copia.fecha)}${copia.destino === 'drive' ? ' (Google Drive)' : ''} · ${copia.hace_dias === 0 ? 'hoy' : copia.hace_dias === 1 ? 'ayer' : `hace ${copia.hace_dias} días`}`
  return (
    <Tarjeta titulo="Estado de la app" accion={e.version && <span className="cifra text-xs text-muted" title="Versión desplegada">{e.version}</span>}>
      <div>
        <Fila etiqueta="Base de datos" valor={<span className="cifra min-w-0 truncate text-right text-xs" title={e.base_datos.detalle}>{e.base_datos.tipo}{e.base_datos.detalle && ` · ${e.base_datos.detalle}`}</span>} />
        <Fila etiqueta="Comunidad autónoma (IRPF)" valor={e.ccaa} />
        <Fila etiqueta="Banco" valor={`${e.banco.nombre} · ${e.banco.conectado ? 'conectado' : e.banco.configurado ? 'sin conectar' : 'sin configurar'}`} />
        <Fila etiqueta="Indexa" valor={e.indexa_configurado ? 'configurado' : 'sin configurar'} />
        <Fila etiqueta="Última copia" valor={<span className={!copia || copia.hace_dias > 31 ? 'text-warn' : undefined}>{textoCopia}</span>} />
        <Fila etiqueta="Sincronización" valor={<span className="min-w-0 text-right">{e.sincronizacion.texto}</span>} />
        <Fila etiqueta="Sesión" valor={e.sesion.requerida ? `${e.sesion.email ?? '—'} · con Google` : 'no hace falta (app en tu ordenador)'} />
      </div>
      <p className="mt-3 text-xs text-muted">La comunidad autónoma, el banco y la sincronización salen de las variables de entorno (CCAA, BANCO, SYNC_HORAS).</p>
    </Tarjeta>
  )
}

function ImportarDatos() {
  const avisar = useAvisos()
  const [copia, setCopia] = useState<{ fichero: File; previa: VistaPreviaImportacion } | null>(null)
  const [resultado, setResultado] = useState<string[] | null>(null)
  const [mirando, setMirando] = useState(false)
  const enviar = (f: File, previa = false) => {
    const fd = new FormData()
    fd.append('fichero', f)
    return api.post<ResultadoImportacion | VistaPreviaImportacion>(`/importar/datos${previa ? '?previa=true' : ''}`, fd)
  }
  const importar = useAccion(async (f: File) => {
    const r = (await enviar(f)) as ResultadoImportacion
    if (copia) setResultado(r.mensajes)
    else r.mensajes.forEach((m) => avisar(m))
  })
  const elegido = async (f: File) => {
    setMirando(true)
    try {
      const previa = (await enviar(f, true)) as VistaPreviaImportacion
      if (previa.copia) setCopia({ fichero: f, previa })
      else importar.mutate(f)
    } catch (e) {
      avisar((e as Error).message, 'error')
    } finally {
      setMirando(false)
    }
  }
  const { input, elegir } = useSubida({ accept: '.json,application/json', onFicheros: (ficheros) => elegido(ficheros[0]) })
  const cerrar = () => { setCopia(null); setResultado(null) }
  const ocupado = mirando || importar.isPending
  const tablas = copia?.previa.tablas ?? []
  return (
    <Tarjeta titulo="Importar datos">
      <p className="text-sm text-muted">Carga de golpe tus bienes, hipotecas, inversiones y supuestos desde un fichero .json: si algo ya existe,
        se actualiza en vez de duplicarse. Si el fichero es una copia de seguridad completa (la que baja «Copia de seguridad»),
        te lo digo y, si confirmas, sustituye todos los datos actuales por los de la copia.</p>
      {input}
      <Boton variante="secundario" className="mt-4" onClick={elegir} disabled={ocupado}>
        <Upload size={16} />{importar.isPending ? 'Importando…' : mirando ? 'Mirando el fichero…' : 'Elegir fichero'}</Boton>

      <Dialogo abierto={!!copia} onCerrar={cerrar} titulo={resultado ? 'Copia restaurada' : 'Restaurar una copia de seguridad'}>
        {resultado ? (
          <div className="space-y-3 text-sm">
            <p className="font-medium">{resultado[0]}</p>
            <ul className="columns-2 text-xs text-muted">{resultado.slice(1, -1).map((m) => <li key={m}>{m}</li>)}</ul>
            <p className="rounded-xl bg-warn-soft px-3 py-2 text-xs text-warn">{resultado[resultado.length - 1]}</p>
            <div className="flex justify-end"><Boton onClick={cerrar}>Cerrar</Boton></div>
          </div>
        ) : copia && (
          <div className="space-y-3 text-sm">
            <p>El fichero <strong>{copia.fichero.name}</strong> es una copia completa del <strong>{fecha(copia.previa.fecha)}</strong> con {copia.previa.filas} filas:</p>
            <ul className="columns-2 text-xs text-muted">
              {tablas.map((t) => <li key={t.tabla}>{t.tabla.replace(/_/g, ' ')}: {t.filas}</li>)}
            </ul>
            <p className="rounded-xl bg-warn-soft px-3 py-2 text-xs text-warn">
              Sustituye <strong>TODOS</strong> los datos actuales por los de la copia. No se puede deshacer: si tienes dudas, descarga antes una copia de lo que hay ahora.
              Las claves del asistente no viajan en la copia; tendrás que volver a ponerlas.
            </p>
            <div className="flex justify-end gap-2">
              <Boton variante="fantasma" onClick={cerrar} disabled={importar.isPending}>Cancelar</Boton>
              <EnDosPasos variante="primario" texto="Restaurar" textoConfirmar="¿Seguro? Sustituir todos los datos" disabled={importar.isPending}
                onConfirmar={() => importar.mutate(copia.fichero)} />
            </div>
          </div>
        )}
      </Dialogo>
    </Tarjeta>
  )
}

const claseEnlace = 'inline-flex items-center gap-2 rounded-xl border border-line bg-panel px-4 py-2 text-sm font-medium hover:bg-panel-2'

function CopiaSeguridad() {
  const avisar = useAvisos()
  const { data: auth } = useAuth()
  const [subiendo, setSubiendo] = useState(false)
  const aDrive = async () => {
    if (!auth?.client_id) return
    setSubiendo(true)
    try {
      const token = await permisoDrive(auth.client_id, 'drive.file')
      const r = await fetch('/api/exportar?destino=drive')  // el servidor ya la apunta como última copia
      if (!r.ok) throw new Error(`No se pudo preparar la copia (error ${r.status})`)
      await subirADrive(token, `finanzas-${new Date().toISOString().slice(0, 10)}.json`, await r.blob())
      avisar('Copia guardada en tu Google Drive')
    } catch (e) {
      avisar((e as Error).message, 'error')
    } finally {
      setSubiendo(false)
    }
  }
  return (
    <Tarjeta titulo="Copia de seguridad">
      <p className="text-sm text-muted">Todos tus datos en un .json. Para volver a cargarlo, elígelo en «Importar datos»: la app lo reconoce,
        te enseña qué trae y, si confirmas, sustituye todo lo que haya (aquí o en otra instalación). Las claves del asistente no salen en la copia.
        Si pasa un mes sin copia, te aviso en Inicio.</p>
      <div className="mt-4 flex flex-wrap gap-2">
        <a className={claseEnlace} href="/api/exportar" download><Download size={16} />Descargar copia</a>
        <a className={claseEnlace} href="/api/exportar?pdfs=true" download><Download size={16} />Con los PDF de Hacienda</a>
        <a className={claseEnlace} href="/api/exportar/movimientos.xlsx" download><Download size={16} />Movimientos en Excel</a>
        {auth?.client_id && (
          <Boton variante="secundario" onClick={aDrive} disabled={subiendo}><Upload size={16} />{subiendo ? 'Guardando…' : 'Guardar en Google Drive'}</Boton>
        )}
      </div>
    </Tarjeta>
  )
}

function Sesiones() {
  const salir = useAccion(() => api.post('/auth/salir-en-todos').then(() => window.location.reload()))
  return (
    <Tarjeta titulo="Sesiones">
      <p className="text-sm text-muted">Si has entrado desde un ordenador que no es tuyo o has perdido el móvil, cierra la sesión en todos los dispositivos.
        Tendrás que volver a entrar con Google aquí también.</p>
      <Boton variante="secundario" className="mt-4" onClick={() => salir.mutate(undefined)} disabled={salir.isPending}>
        <LogOut size={16} />Cerrar sesión en todos</Boton>
    </Tarjeta>
  )
}

export default function Ajustes() {
  useVueltaBanco()
  const { data, isLoading, error } = useQuery({ queryKey: ['sync'], queryFn: () => api.get<EstadoSync>('/sync') })
  const { data: historial } = useQuery({ queryKey: ['sync-historial'], queryFn: () => api.get<HistorialSync>('/sync/historial') })
  const { data: auth } = useAuth()
  if (isLoading) return <Cargando />
  if (error) return <ErrorCarga error={error} />
  if (!data) return null
  return (
    <>
      <Cabecera titulo="Ajustes" subtitulo={data.en_vercel ? 'Bancos, aspecto, asistente, copias y estado de la app. Los bancos se sincronizan solos cada madrugada.' : data.cada_horas > 0
        ? `Bancos, aspecto, asistente, copias y estado de la app. Mientras está abierta se sincroniza sola al arrancar y cada ${data.cada_horas} horas.`
        : 'Bancos, aspecto, asistente, copias y estado de la app. La sincronización automática está desactivada (SYNC_HORAS=0).'} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Sabadell s={data.sabadell} enVercel={!!data.en_vercel} historial={historial?.sabadell} />
        <Indexa s={data.indexa} enVercel={!!data.en_vercel} historial={historial?.indexa} />
        <div className="lg:col-span-2"><AjustesIA /></div>
        <div className="lg:col-span-2"><DriveImport /></div>
        <div className="lg:col-span-2"><ImportarDatos /></div>
        <CopiaSeguridad />
        <Apariencia />
        <EstadoDeLaApp />
        {auth?.requerida && <Sesiones />}
      </div>
    </>
  )
}
