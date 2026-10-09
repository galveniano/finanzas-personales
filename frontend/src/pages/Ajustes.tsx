import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, ExternalLink, LogOut, RefreshCw, Upload } from 'lucide-react'
import { api } from '../lib/api'
import { diasHasta, fechaHora } from '../lib/format'
import type { DocumentosDrive, EstadoSync, UltimaSync } from '../lib/tipos'
import { permisoDrive, subirADrive } from '../lib/google'
import AjustesIA from '../components/AjustesIA'
import DriveImport from '../components/DriveImport'
import { useAccion, useAvisos } from '../lib/utilidades'
import { useSubida } from '../lib/subida'
import { Boton, Cabecera, Cargando, Etiqueta, ErrorCarga, Tarjeta } from '../components/ui'

function Ultima({ u }: { u: UltimaSync | null }) {
  if (!u) return <p className="text-sm text-muted">Todavía no se ha sincronizado.</p>
  return (
    <p className={`text-sm ${u.ok ? 'text-muted' : 'text-neg'}`}>
      {u.ok ? 'Última sincronización' : 'Falló la última vez'} el {fechaHora(u.fecha, { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}: {u.mensaje}
    </p>
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

function Sabadell({ s, enVercel }: { s: EstadoSync['sabadell']; enVercel: boolean }) {
  const avisar = useAvisos()
  const [urlBanco, setUrlBanco] = useState<string | null>(null)
  const [vuelta, setVuelta] = useState('')
  const conectar = useAccion(async () => {
    const r = await api.post<{ url: string }>('/sync/sabadell/conectar')
    // Publicada: el banco vuelve sola a la app. En local hay que pegar la dirección de vuelta.
    if (s.vuelta_automatica) { window.location.href = r.url; return }
    setUrlBanco(r.url)
    window.open(r.url, '_blank', 'noopener')
  })
  const completar = useAccion(async () => {
    const r = await api.post<{ sync: UltimaSync & { mensaje: string } }>('/sync/sabadell/completar', { codigo: vuelta })
    setUrlBanco(null)
    setVuelta('')
    avisar(`Sabadell conectado. ${r.sync.mensaje}`)
  })
  const sincronizar = useAccion(() => api.post('/sync/sabadell'), 'Sabadell sincronizado')
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
        </div>
      )}

      {urlBanco && (
        <div className="space-y-3 rounded-xl bg-panel-2 p-4 text-sm">
          <p>Se ha abierto la página de Sabadell en otra pestaña. Si no, <a href={urlBanco} target="_blank" rel="noreferrer" className="font-medium text-accent">ábrela aquí</a>.</p>
          <p className="text-muted">Al terminar, el navegador irá a una página de localhost que no carga. Es normal: copia la dirección completa de esa pestaña y pégala aquí.</p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input value={vuelta} onChange={(e) => setVuelta(e.target.value)} placeholder="https://localhost:8000/sabadell/vuelta?code=…"
              className="min-w-0 flex-1 rounded-xl border border-line bg-panel px-3 py-2" aria-label="Dirección de vuelta" />
            <Boton onClick={() => completar.mutate(undefined)} disabled={!vuelta || completar.isPending}>{completar.isPending ? 'Conectando…' : 'Terminar'}</Boton>
          </div>
        </div>
      )}
      <div className="mt-4"><Ultima u={s.ultima} /></div>
    </Tarjeta>
  )
}

function Indexa({ s, enVercel }: { s: EstadoSync['indexa']; enVercel: boolean }) {
  const sincronizar = useAccion(() => api.post('/sync/indexa'), 'Indexa actualizado')
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

function ImportarDatos() {
  const avisar = useAvisos()
  const importar = useAccion(async (f: File) => {
    const fd = new FormData()
    fd.append('fichero', f)
    const r = await api.post<{ mensajes: string[] }>('/importar/datos', fd)
    r.mensajes.forEach((m) => avisar(m))
  })
  const { input, elegir } = useSubida({ accept: '.json,application/json', onFicheros: (ficheros) => importar.mutate(ficheros[0]) })
  return (
    <Tarjeta titulo="Importar datos">
      <p className="text-sm text-muted">Carga de golpe tus bienes, hipotecas, inversiones y supuestos desde un fichero .json.
        Si algo ya existe, se actualiza en vez de duplicarse.</p>
      {input}
      <Boton variante="secundario" className="mt-4" onClick={elegir} disabled={importar.isPending}>
        <Upload size={16} />{importar.isPending ? 'Importando…' : 'Elegir fichero'}</Boton>
    </Tarjeta>
  )
}

const claseEnlace = 'inline-flex items-center gap-2 rounded-xl border border-line bg-panel px-4 py-2 text-sm font-medium hover:bg-panel-2'

function CopiaSeguridad() {
  const avisar = useAvisos()
  const { data: drive } = useQuery({ queryKey: ['drive'], queryFn: () => api.get<DocumentosDrive>('/drive/documentos') })
  const [subiendo, setSubiendo] = useState(false)
  const aDrive = async () => {
    if (!drive?.google_client_id) return
    setSubiendo(true)
    try {
      const token = await permisoDrive(drive.google_client_id, 'drive.file')
      const r = await fetch('/api/exportar')
      if (!r.ok) throw new Error(`No se pudo preparar la copia (error ${r.status})`)
      await subirADrive(token, `finanzas-${new Date().toISOString().slice(0, 10)}.json`, await r.blob())
      await api.post('/exportar/hecha')
      avisar('Copia guardada en tu Google Drive')
    } catch (e) {
      avisar((e as Error).message, 'error')
    } finally {
      setSubiendo(false)
    }
  }
  return (
    <Tarjeta titulo="Copia de seguridad">
      <p className="text-sm text-muted">Todos tus datos en un .json que puedes volver a cargar en «Importar datos» de otra instalación.
        Las claves de API no salen. Si pasa un mes sin copia, te aviso en Inicio.</p>
      <div className="mt-4 flex flex-wrap gap-2">
        <a className={claseEnlace} href="/api/exportar" download><Download size={16} />Descargar copia</a>
        <a className={claseEnlace} href="/api/exportar?pdfs=true" download><Download size={16} />Con los PDF de Hacienda</a>
        <a className={claseEnlace} href="/api/exportar/movimientos.xlsx" download><Download size={16} />Movimientos en Excel</a>
        {drive?.google_client_id && (
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
  if (isLoading) return <Cargando />
  if (error) return <ErrorCarga error={error} />
  if (!data) return null
  return (
    <>
      <Cabecera titulo="Ajustes" subtitulo={data.en_vercel ? 'Bancos, asistente e importación. Los bancos se sincronizan solos cada madrugada.' : data.cada_horas > 0
        ? `Mientras la app está abierta se sincroniza sola al arrancar y cada ${data.cada_horas} horas.`
        : 'La sincronización automática está desactivada (SYNC_HORAS=0).'} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Sabadell s={data.sabadell} enVercel={!!data.en_vercel} />
        <Indexa s={data.indexa} enVercel={!!data.en_vercel} />
        <div className="lg:col-span-2"><AjustesIA /></div>
        <div className="lg:col-span-2"><DriveImport /></div>
        <div className="lg:col-span-2"><ImportarDatos /></div>
        <CopiaSeguridad />
        <Sesiones />
      </div>
    </>
  )
}
