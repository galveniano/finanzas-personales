import { Suspense, useCallback, useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Briefcase, Building2, CalendarClock, Ellipsis, Keyboard, LayoutDashboard, LogOut, PieChart, RefreshCw, Scale, Search, Settings, Sparkles, TrendingUp, Wallet } from 'lucide-react'
import { api, esDemo } from '../lib/api'
import type { EstadoAuth, EstadoSync } from '../lib/tipos'
import { fechaHora } from '../lib/format'
import { useAvisos } from '../lib/utilidades'
import { useSincronizar } from '../lib/sincronizar'
import { AYUDA_ATAJOS, TECLA_MOD, useAtajos } from '../lib/atajos'
import { aplicarTema, TEMAS, useTema } from '../lib/tema'
import Logo from './Logo'
import Paleta from './Paleta'
import { Boton, Cargando, Dialogo, Segmentos } from './ui'

const secciones: { a: string; texto: string; icono: typeof Wallet; movil?: boolean }[] = [
  { a: '/', texto: 'Inicio', icono: LayoutDashboard, movil: true },
  { a: '/cuentas', texto: 'Cuentas', icono: Wallet, movil: true },
  { a: '/gastos', texto: 'Gastos', icono: PieChart, movil: true },
  { a: '/ingresos', texto: 'Ingresos', icono: Briefcase, movil: true },
  { a: '/impuestos', texto: 'Impuestos', icono: Scale },
  { a: '/inmuebles', texto: 'Bienes', icono: Building2 },
  { a: '/plan', texto: 'Plan', icono: CalendarClock, movil: true },
  { a: '/inversiones', texto: 'Inversiones', icono: TrendingUp },
]
const ajustes = { a: '/ajustes', texto: 'Ajustes', icono: Settings }
const asistente = { a: '/asistente', texto: 'Asistente', icono: Sparkles }
const claseEnlace = (activo: boolean) =>
  `flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition ${activo ? 'bg-accent-soft font-semibold text-accent' : 'text-muted hover:bg-panel-2 hover:text-ink'}`

function Tema({ pequeno }: { pequeno?: boolean }) {
  const tema = useTema()
  return <Segmentos pequeno={pequeno} etiqueta="Tema" opciones={TEMAS} valor={tema} onCambiar={aplicarTema} />
}

function EstadoConexiones() {
  const { data } = useQuery({ queryKey: ['sync'], queryFn: () => api.get<EstadoSync>('/sync') })
  const sincronizar = useSincronizar('/sync')
  const ultima = [data?.sabadell.ultima, data?.indexa.ultima].filter(Boolean).sort((a, b) => (a!.fecha < b!.fecha ? 1 : -1))[0]
  return (
    <div className="flex items-center gap-3">
      {ultima && (
        <span className="hidden text-xs text-muted lg:inline">
          Última sincronización {fechaHora(ultima.fecha)}
        </span>
      )}
      <Boton variante="secundario" onClick={() => sincronizar.mutate(undefined)} disabled={sincronizar.isPending} aria-label="Sincronizar">
        <RefreshCw size={15} className={sincronizar.isPending ? 'animate-spin' : ''} />
        <span className="hidden sm:inline">{sincronizar.isPending ? 'Sincronizando…' : 'Sincronizar'}</span>
      </Boton>
    </div>
  )
}

function Sesion({ compacto }: { compacto?: boolean }) {
  const qc = useQueryClient()
  const avisar = useAvisos()
  const { data } = useQuery({ queryKey: ['auth'], queryFn: () => api.get<EstadoAuth>('/auth/estado'), enabled: !esDemo, staleTime: Infinity })
  if (!data?.email) return null
  const salir = async () => {
    try {
      await api.post('/auth/salir')
      qc.clear()
      location.reload()
    } catch (e) {
      avisar(`No se ha podido cerrar la sesión: ${(e as Error).message}`, 'error')
    }
  }
  return compacto
    ? <button onClick={salir} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-muted"><LogOut size={18} />Salir ({data.email})</button>
    : (
      <div className="mt-3 flex items-center justify-between gap-2 px-2 text-xs text-muted">
        <span className="truncate" title={data.email}>{data.email}</span>
        <button onClick={salir} aria-label="Cerrar sesión" className="rounded-lg p-1.5 hover:bg-panel-2 hover:text-ink"><LogOut size={15} /></button>
      </div>
    )
}

function NavMovil() {
  const [mas, setMas] = useState(false)
  const { pathname } = useLocation()
  const resto = [...secciones.filter((x) => !x.movil), asistente, ajustes]
  const enResto = resto.some((x) => x.a === pathname)
  useEffect(() => {
    if (!mas) return
    const tecla = (e: KeyboardEvent) => { if (e.key === 'Escape') setMas(false) }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [mas])
  const clase = (activo: boolean) => `flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-lg py-1 text-[10px] ${activo ? 'text-accent' : 'text-muted'}`
  return (
    <>
      {mas && (
        <div className="fixed inset-0 z-30 bg-black/30 md:hidden" onClick={() => setMas(false)}>
          <div className="absolute inset-x-3 rounded-2xl border border-line bg-panel p-2 shadow-xl" style={{ bottom: 'calc(72px + env(safe-area-inset-bottom, 0px))' }}
            onClick={(e) => e.stopPropagation()}>
            {resto.map(({ a, texto, icono: Icono }) => (
              <NavLink key={a} to={a} onClick={() => setMas(false)}
                className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm ${isActive ? 'bg-accent-soft font-semibold text-accent' : ''}`}>
                <Icono size={18} />{texto}
              </NavLink>
            ))}
            <div className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm">
              <span>Tema</span><Tema pequeno />
            </div>
            <Sesion compacto />
          </div>
        </div>
      )}
      <nav className="fixed inset-x-0 bottom-0 z-30 flex justify-around border-t border-line bg-panel px-1 pt-1.5 md:hidden" style={{ paddingBottom: 'calc(6px + env(safe-area-inset-bottom, 0px))' }}>
        {secciones.filter((x) => x.movil).map(({ a, texto, icono: Icono }) => (
          <NavLink key={a} to={a} end={a === '/'} onClick={() => setMas(false)} className={({ isActive }) => clase(isActive)}>
            <Icono size={20} /><span className="max-w-full truncate">{texto}</span>
          </NavLink>
        ))}
        <button className={clase(enResto || mas)} onClick={() => setMas(!mas)} aria-expanded={mas} aria-label="Más secciones">
          <Ellipsis size={20} /><span>Más</span>
        </button>
      </nav>
    </>
  )
}

export default function Layout() {
  const [paleta, setPaleta] = useState(false)
  const [ayuda, setAyuda] = useState(false)
  const abrirPaleta = useCallback(() => { setAyuda(false); setPaleta((v) => !v) }, [])
  const abrirAyuda = useCallback(() => setAyuda(true), [])
  useAtajos({ onBuscar: abrirPaleta, onAyuda: abrirAyuda })

  return (
    <div className="min-h-full md:grid md:grid-cols-[232px_1fr]">
      <aside className="sticky top-0 hidden h-screen flex-col border-r border-line bg-panel px-4 py-6 md:flex">
        <div className="mb-8 flex items-center gap-2.5 px-2">
          <Logo />
          <span className="font-semibold tracking-tight">Finanzas</span>
        </div>
        <nav className="flex flex-col gap-1">
          {secciones.map(({ a, texto, icono: Icono }) => (
            <NavLink key={a} to={a} end={a === '/'} className={({ isActive }) => claseEnlace(isActive)}>
              <Icono size={18} />{texto}
            </NavLink>
          ))}
        </nav>
        <nav className="mt-auto flex flex-col gap-1">
          {[asistente, ajustes].map(({ a, texto, icono: Icono }) => (
            <NavLink key={a} to={a} className={({ isActive }) => claseEnlace(isActive)}>
              <Icono size={18} />{texto}
            </NavLink>
          ))}
          <button type="button" onClick={abrirAyuda} className={claseEnlace(false)} aria-label="Atajos de teclado">
            <Keyboard size={18} />Atajos<kbd className="ml-auto">?</kbd>
          </button>
        </nav>
        <div className="mt-4 border-t border-line pt-4">
          <Tema pequeno />
          <Sesion />
        </div>
      </aside>

      <div className="min-w-0 pb-24 md:pb-0">
        <div className="sticky z-20 flex items-center justify-between gap-3 border-b border-line bg-bg/85 px-4 py-3 backdrop-blur sm:px-8" style={{ top: 'env(safe-area-inset-top, 0px)' }}>
          <span className="font-semibold md:invisible">Finanzas</span>
          <div className="flex items-center gap-2">
            <Boton variante="secundario" onClick={abrirPaleta} aria-label="Buscar" aria-keyshortcuts="Control+K Meta+K">
              <Search size={15} /><span className="hidden sm:inline">Buscar</span><kbd className="hidden sm:inline-block">{TECLA_MOD} K</kbd>
            </Boton>
            <Link to="/asistente" aria-label="Asistente" className="rounded-xl border border-line bg-panel p-2 text-muted hover:text-ink md:hidden"><Sparkles size={16} /></Link>
            <EstadoConexiones />
          </div>
        </div>
        {esDemo && (
          <div className="mx-4 mt-4 rounded-xl border border-dashed border-accent px-4 py-2.5 text-sm text-muted sm:mx-8">
            Vista previa con <strong className="text-ink">datos de ejemplo</strong>. No son tus cifras y aquí no se guarda nada.
          </div>
        )}
        <main className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-8">
          <Suspense fallback={<Cargando />}><Outlet /></Suspense>
        </main>
      </div>

      <NavMovil />
      <Paleta abierto={paleta} onCerrar={() => setPaleta(false)} />
      <Dialogo abierto={ayuda} onCerrar={() => setAyuda(false)} titulo="Atajos de teclado">
        <ul className="divide-y divide-line text-sm">
          {AYUDA_ATAJOS.map((a) => (
            <li key={a.texto} className="flex items-center justify-between gap-3 py-2">
              <span>{a.texto}</span>
              <span className="flex shrink-0 gap-1">{a.teclas.map((t, i) => <kbd key={i}>{t}</kbd>)}</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-muted">Los atajos de una letra no funcionan mientras escribes en un campo ni con una ventana abierta.</p>
      </Dialogo>
    </div>
  )
}
