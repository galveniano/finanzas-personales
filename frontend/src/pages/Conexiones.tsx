import { useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ExternalLink, RefreshCw } from 'lucide-react'
import { api } from '../lib/api'
import { diasHasta, fecha } from '../lib/format'
import type { EstadoSync, UltimaSync } from '../lib/tipos'
import AjustesIA from '../components/AjustesIA'
import DriveImport from '../components/DriveImport'
import { Boton, Cabecera, Cargando, Etiqueta, ErrorCarga, Tarjeta, useAccion, useAvisos } from '../components/ui'

function Ultima({ u }: { u: UltimaSync | null }) {
  if (!u) return <p className="text-sm text-muted">Todavía no se ha sincronizado.</p>
  return (
    <p className={`text-sm ${u.ok ? 'text-muted' : 'text-neg'}`}>
      {u.ok ? 'Última sincronización' : 'Falló la última vez'} el {fecha(u.fecha, { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}: {u.mensaje}
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

function Sabadell({ s }: { s: EstadoSync['sabadell'] }) {
  const avisar = useAvisos()
  const [urlBanco, setUrlBanco] = useState<string | null>(null)
  const [vuelta, setVuelta] = useState('')
  const conectar = useAccion(async () => {
    const r = await api.post<{ url: string }>('/sync/sabadell/conectar')
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

      {!s.configurado && (
        <ol className="space-y-3 text-sm">
          <Paso n={1}>Crea una cuenta en <a className="font-medium text-accent" href="https://enablebanking.com/cp/applications" target="_blank" rel="noreferrer">enablebanking.com</a> y registra una aplicación en <strong>Production</strong>.</Paso>
          <Paso n={2}>Como URL de vuelta pon <Codigo>https://localhost:8000/sabadell/vuelta</Codigo>. No hace falta que funcione: luego copiarás la dirección.</Paso>
          <Paso n={3}>Descarga la clave privada (.pem) y guárdala en la carpeta <Codigo>secretos/</Codigo> de la app.</Paso>
          <Paso n={4}>En el panel de Enable Banking, vincula tus cuentas de Sabadell para activar el modo restringido gratuito.</Paso>
          <Paso n={5}>En el fichero <Codigo>.env</Codigo> rellena <Codigo>ENABLE_BANKING_APP_ID</Codigo> y <Codigo>ENABLE_BANKING_KEY=secretos/tu-clave.pem</Codigo>, y reinicia la app.</Paso>
        </ol>
      )}

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

function Indexa({ s }: { s: EstadoSync['indexa'] }) {
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
          <Paso n={2}>Pégalo en <Codigo>.env</Codigo> como <Codigo>INDEXA_TOKEN=…</Codigo> y reinicia la app.</Paso>
        </ol>
      )}
      <div className="mt-4"><Ultima u={s.ultima} /></div>
    </Tarjeta>
  )
}

export default function Conexiones() {
  const { data, isLoading, error } = useQuery({ queryKey: ['sync'], queryFn: () => api.get<EstadoSync>('/sync') })
  if (isLoading) return <Cargando />
  if (error) return <ErrorCarga error={error} />
  if (!data) return null
  return (
    <>
      <Cabecera titulo="Conexiones" subtitulo={data.cada_horas > 0
        ? `Mientras la app está abierta se sincroniza sola al arrancar y cada ${data.cada_horas} horas.`
        : 'La sincronización automática está desactivada (SYNC_HORAS=0).'} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Sabadell s={data.sabadell} />
        <Indexa s={data.indexa} />
        <div className="lg:col-span-2"><AjustesIA /></div>
        <div className="lg:col-span-2"><DriveImport /></div>
      </div>
    </>
  )
}
