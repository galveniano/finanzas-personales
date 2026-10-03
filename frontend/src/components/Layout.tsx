import { NavLink, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Briefcase, Building2, CalendarClock, LayoutDashboard, Landmark, PlugZap, RefreshCw, Wallet } from 'lucide-react'
import { api, esDemo } from '../lib/api'
import type { EstadoSync } from '../lib/tipos'
import { Boton, useAccion } from './ui'

const secciones: { a: string; texto: string; corto?: string; icono: typeof Wallet }[] = [
  { a: '/', texto: 'Panel', icono: LayoutDashboard },
  { a: '/cuentas', texto: 'Cuentas', icono: Wallet },
  { a: '/autonomo', texto: 'Autónomo', icono: Briefcase },
  { a: '/nominas', texto: 'Nóminas', icono: Landmark },
  { a: '/inmuebles', texto: 'Inmuebles', corto: 'Pisos', icono: Building2 },
  { a: '/planificacion', texto: 'Planificación', corto: 'Planes', icono: CalendarClock },
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
        <p className="mt-auto px-2 text-xs leading-relaxed text-muted">Todo se guarda en tu ordenador. Las cifras fiscales son estimaciones.</p>
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

      <nav className="fixed inset-x-0 bottom-0 z-30 flex justify-around border-t border-line bg-panel px-1 pt-1.5 md:hidden" style={{ paddingBottom: 'calc(6px + env(safe-area-inset-bottom, 0px))' }}>
        {secciones.map(({ a, texto, corto, icono: Icono }) => (
          <NavLink key={a} to={a} end={a === '/'}
            className={({ isActive }) => `flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-lg py-1 text-[10px] ${isActive ? 'text-accent' : 'text-muted'}`}>
            <Icono size={20} /><span className="max-w-full truncate">{corto ?? texto}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
