import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Briefcase, Building2, CalendarClock, Ellipsis, LayoutDashboard, Landmark, LogOut, PlugZap, RefreshCw, Scale, Wallet } from 'lucide-react'
import { api, esDemo } from '../lib/api'
import type { EstadoAuth, EstadoSync } from '../lib/tipos'
import { Boton, useAccion } from './ui'

const secciones: { a: string; texto: string; corto?: string; icono: typeof Wallet; movil?: boolean }[] = [
  { a: '/', texto: 'Panel', icono: LayoutDashboard, movil: true },
  { a: '/cuentas', texto: 'Cuentas', icono: Wallet, movil: true },
  { a: '/autonomo', texto: 'Autónomo', icono: Briefcase, movil: true },
  { a: '/hacienda', texto: 'Hacienda', icono: Scale, movil: true },
  { a: '/nominas', texto: 'Nóminas', icono: Landmark },
  { a: '/inmuebles', texto: 'Inmuebles', corto: 'Pisos', icono: Building2 },
  { a: '/planificacion', texto: 'Planificación', corto: 'Planes', icono: CalendarClock, movil: true },
  { a: '/conexiones', texto: 'Conexiones', corto: 'Bancos', icono: PlugZap },
]

function EstadoConexiones() {
  const { data } = useQuery({ queryKey: ['sync'], queryFn: () => api.get<EstadoSync>('/sync') })
  const sincronizar = useAccion(() => api.post('/sync'), 'Sincronización terminada')
  const ultima = [data?.sabadell.ultima, data?.indexa.ultima].filter(Boolean).sort((a, b) => (a!.fecha < b!.fecha ? 1 : -1))[0]
  return (
    <div className="flex items-center gap-3">
      {ultima && (
        <span className="hidden text-xs text-muted sm:inline">
          Última sincronización {new Date(ultima.fecha).toLocaleString('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
        </span>
      )}
      <Boton variante="secundario" onClick={() => sincronizar.mutate(undefined)} disabled={sincronizar.isPending}>
        <RefreshCw size={15} className={sincronizar.isPending ? 'animate-spin' : ''} />
        {sincronizar.isPending ? 'Sincronizando…' : 'Sincronizar'}
      </Boton>
    </div>
  )
}

function Sesion({ compacto }: { compacto?: boolean }) {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['auth'], queryFn: () => api.get<EstadoAuth>('/auth/estado'), enabled: !esDemo, staleTime: Infinity })
  if (!data?.email) return null
  const salir = async () => { await api.post('/auth/salir'); qc.clear(); location.reload() }
  return compacto
    ? <button onClick={salir} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-muted"><LogOut size={18} />Salir ({data.email})</button>
    : (
      <div className="mt-4 flex items-center justify-between gap-2 border-t border-line px-2 pt-4 text-xs text-muted">
        <span className="truncate" title={data.email}>{data.email}</span>
        <button onClick={salir} aria-label="Cerrar sesión" className="rounded-lg p-1.5 hover:bg-panel-2 hover:text-ink"><LogOut size={15} /></button>
      </div>
    )
}

function NavMovil() {
  const [mas, setMas] = useState(false)
  const { pathname } = useLocation()
  const resto = secciones.filter((x) => !x.movil)
  const enResto = resto.some((x) => x.a === pathname)
  const clase = (activo: boolean) => `flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-lg py-1 text-[10px] ${activo ? 'text-accent' : 'text-muted'}`
  return (
    <>
      {mas && (
        <div className="fixed inset-0 z-30 bg-black/30 md:hidden" onClick={() => setMas(false)}>
          <div className="absolute inset-x-3 rounded-2xl border border-line bg-panel p-2 shadow-xl" style={{ bottom: 'calc(72px + env(safe-area-inset-bottom, 0px))' }}>
            {resto.map(({ a, texto, icono: Icono }) => (
              <NavLink key={a} to={a} onClick={() => setMas(false)}
                className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm ${isActive ? 'bg-accent-soft font-semibold text-accent' : ''}`}>
                <Icono size={18} />{texto}
              </NavLink>
            ))}
            <Sesion compacto />
          </div>
        </div>
      )}
      <nav className="fixed inset-x-0 bottom-0 z-30 flex justify-around border-t border-line bg-panel px-1 pt-1.5 md:hidden" style={{ paddingBottom: 'calc(6px + env(safe-area-inset-bottom, 0px))' }}>
        {secciones.filter((x) => x.movil).map(({ a, texto, corto, icono: Icono }) => (
          <NavLink key={a} to={a} end={a === '/'} onClick={() => setMas(false)} className={({ isActive }) => clase(isActive)}>
            <Icono size={20} /><span className="max-w-full truncate">{corto ?? texto}</span>
          </NavLink>
        ))}
        <button className={clase(enResto || mas)} onClick={() => setMas(!mas)} aria-expanded={mas}>
          <Ellipsis size={20} /><span>Más</span>
        </button>
      </nav>
    </>
  )
}

export default function Layout() {
  return (
    <div className="min-h-full md:grid md:grid-cols-[232px_1fr]">
      <aside className="sticky top-0 hidden h-screen flex-col border-r border-line bg-panel px-4 py-6 md:flex">
        <div className="mb-8 flex items-center gap-2.5 px-2">
          <div className="grid size-8 place-items-center rounded-lg bg-accent text-panel">
            <svg viewBox="0 0 32 32" className="size-5" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round"><path d="M7 22l6-7 5 3.5 7-9" /></svg>
          </div>
          <span className="font-semibold tracking-tight">Finanzas</span>
        </div>
        <nav className="flex flex-col gap-1">
          {secciones.map(({ a, texto, icono: Icono }) => (
            <NavLink key={a} to={a} end={a === '/'}
              className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition ${isActive ? 'bg-accent-soft font-semibold text-accent' : 'text-muted hover:bg-panel-2 hover:text-ink'}`}>
              <Icono size={18} />{texto}
            </NavLink>
          ))}
        </nav>
        <p className="mt-auto px-2 text-xs leading-relaxed text-muted">Las cifras fiscales son estimaciones.</p>
        <Sesion />
      </aside>

      <div className="min-w-0 pb-24 md:pb-0">
        <div className="sticky z-20 flex items-center justify-between gap-3 border-b border-line bg-bg/85 px-4 py-3 backdrop-blur sm:px-8" style={{ top: 'env(safe-area-inset-top, 0px)' }}>
          <span className="font-semibold md:invisible">Finanzas</span>
          <EstadoConexiones />
        </div>
        {esDemo && (
          <div className="mx-4 mt-4 rounded-xl border border-dashed border-accent px-4 py-2.5 text-sm text-muted sm:mx-8">
            Vista previa con <strong className="text-ink">datos de ejemplo</strong>. No son tus cifras y aquí no se guarda nada.
          </div>
        )}
        <main className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-8">
          <Outlet />
        </main>
      </div>

      <NavMovil />
    </div>
  )
}
