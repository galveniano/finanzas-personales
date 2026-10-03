import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X } from 'lucide-react'

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')

export function Tarjeta({ children, className, titulo, accion }: {
  children: ReactNode; className?: string; titulo?: ReactNode; accion?: ReactNode
}) {
  return (
    <section className={cx('rounded-2xl border border-line bg-panel p-5 min-w-0', className)}>
      {(titulo || accion) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          {titulo && <h2 className="text-[15px] font-semibold">{titulo}</h2>}
          {accion}
        </div>
      )}
      {children}
    </section>
  )
}

export function Cabecera({ titulo, subtitulo, children }: { titulo: string; subtitulo?: ReactNode; children?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-bold tracking-tight sm:text-[28px]">{titulo}</h1>
        {subtitulo && <p className="mt-1 text-sm text-muted">{subtitulo}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </header>
  )
}

type Variante = 'primario' | 'secundario' | 'fantasma' | 'peligro'
export function Boton({ variante = 'primario', className, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variante?: Variante }) {
  const estilos: Record<Variante, string> = {
    primario: 'bg-accent text-panel hover:opacity-90',
    secundario: 'border border-line bg-panel hover:bg-panel-2',
    fantasma: 'text-muted hover:bg-panel-2 hover:text-ink',
    peligro: 'text-neg hover:bg-panel-2',
  }
  return (
    <button
      {...p}
      className={cx('inline-flex items-center justify-center gap-2 rounded-xl px-3.5 py-2 text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer', estilos[variante], className)}
    />
  )
}

export function Etiqueta({ children, tono = 'neutro' }: { children: ReactNode; tono?: 'neutro' | 'bien' | 'aviso' | 'mal' | 'acento' }) {
  const t = {
    neutro: 'bg-panel-2 text-muted',
    bien: 'bg-accent-soft text-pos',
    aviso: 'bg-warn-soft text-warn',
    mal: 'bg-panel-2 text-neg',
    acento: 'bg-accent-soft text-accent',
  }[tono]
  return <span className={cx('inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap', t)}>{children}</span>
}

export function Dato({ etiqueta, valor, nota, tono }: { etiqueta: string; valor: ReactNode; nota?: ReactNode; tono?: 'pos' | 'neg' }) {
  return (
    <div className="min-w-0">
      <div className="text-xs font-medium uppercase tracking-wider text-muted">{etiqueta}</div>
      <div className={cx('cifra mt-1.5 text-2xl font-medium break-words', tono === 'pos' && 'text-pos', tono === 'neg' && 'text-neg')}>{valor}</div>
      {nota && <div className="mt-1 text-xs text-muted">{nota}</div>}
    </div>
  )
}

export function Importe({ valor, signo = false, className }: { valor: number | null | undefined; signo?: boolean; className?: string }) {
  if (valor == null) return <span className={cx('cifra text-muted', className)}>—</span>
  const txt = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' }).format(valor)
  return (
    <span className={cx('cifra whitespace-nowrap', signo && valor > 0 && 'text-pos', signo && valor < 0 && 'text-neg', className)}>
      {signo && valor > 0 ? '+' : ''}{txt}
    </span>
  )
}

export function Tabla({ children }: { children: ReactNode }) {
  return (
    <div className="-mx-5 overflow-x-auto px-5">
      <table className="w-full text-sm [&_td]:border-t [&_td]:border-line [&_td]:px-2 [&_td]:py-2.5 [&_th]:px-2 [&_th]:pb-2 [&_th]:text-left [&_th]:text-xs [&_th]:font-medium [&_th]:text-muted [&_.num]:text-right">
        {children}
      </table>
    </div>
  )
}

export function Vacio({ children }: { children: ReactNode }) {
  return <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-muted">{children}</p>
}

export function Barra({ valor, max }: { valor: number; max: number }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (valor / max) * 100)) : 0
  return (
    <div className="h-2 overflow-hidden rounded-full bg-panel-2" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${pct}%` }} />
    </div>
  )
}

// --- Formularios -------------------------------------------------------------

const claseCampo = 'w-full rounded-xl border border-line bg-panel px-3 py-2 text-sm text-ink placeholder:text-muted/70'

export function Campo({ etiqueta, ayuda, className, ...p }: InputHTMLAttributes<HTMLInputElement> & { etiqueta: string; ayuda?: string }) {
  return (
    <label className={cx('flex flex-col gap-1.5 text-xs font-medium text-muted', className)}>
      {etiqueta}
      <input {...p} className={claseCampo} />
      {ayuda && <span className="font-normal">{ayuda}</span>}
    </label>
  )
}

export function Selector({ etiqueta, children, className, ...p }: SelectHTMLAttributes<HTMLSelectElement> & { etiqueta?: string }) {
  const sel = <select {...p} className={cx(claseCampo, !etiqueta && className)}>{children}</select>
  if (!etiqueta) return sel
  return <label className={cx('flex flex-col gap-1.5 text-xs font-medium text-muted', className)}>{etiqueta}{sel}</label>
}

export function Dialogo({ abierto, onCerrar, titulo, children }: { abierto: boolean; onCerrar: () => void; titulo: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (abierto && !d.open) d.showModal()
    if (!abierto && d.open) d.close()
  }, [abierto])
  return (
    <dialog
      ref={ref}
      onClose={onCerrar}
      onClick={(e) => { if (e.target === ref.current) onCerrar() }}
      className="m-auto w-[min(560px,calc(100vw-32px))] rounded-2xl border border-line bg-panel p-0 text-ink backdrop:bg-black/40"
    >
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <h2 className="font-semibold">{titulo}</h2>
        <Boton variante="fantasma" onClick={onCerrar} aria-label="Cerrar"><X size={16} /></Boton>
      </div>
      <div className="p-5">{abierto && children}</div>
    </dialog>
  )
}

/** Formulario simple: recoge los campos por `name` y los manda a la API. */
export function Formulario({ onEnviar, children, textoBoton = 'Guardar' }: {
  onEnviar: (datos: Record<string, string>) => Promise<unknown>; children: ReactNode; textoBoton?: string
}) {
  const [enviando, setEnviando] = useState(false)
  return (
    <form
      className="grid gap-4 sm:grid-cols-2"
      onSubmit={async (e) => {
        e.preventDefault()
        const fd = new FormData(e.currentTarget)
        const datos: Record<string, string> = {}
        fd.forEach((v, k) => { datos[k] = String(v) })
        setEnviando(true)
        try { await onEnviar(datos) } finally { setEnviando(false) }
      }}
    >
      {children}
      <div className="flex justify-end sm:col-span-2">
        <Boton type="submit" disabled={enviando}>{enviando ? 'Guardando…' : textoBoton}</Boton>
      </div>
    </form>
  )
}

/** Convierte '1.234,56' o '1234.56' a número; vacío → undefined. */
export function num(v: string | undefined): number | undefined {
  if (v == null || v.trim() === '') return undefined
  const t = v.includes(',') ? v.replace(/\./g, '').replace(',', '.') : v
  const n = Number(t)
  return Number.isFinite(n) ? n : undefined
}
export const opc = (v: string | undefined) => (v && v.trim() !== '' ? v : undefined)

// --- Avisos ------------------------------------------------------------------

type Aviso = { id: number; texto: string; tipo: 'ok' | 'error' }
const AvisosCtx = createContext<(texto: string, tipo?: 'ok' | 'error') => void>(() => {})

export function ProveedorAvisos({ children }: { children: ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([])
  const avisar = useCallback((texto: string, tipo: 'ok' | 'error' = 'ok') => {
    const id = Date.now() + Math.random()
    setAvisos((a) => [...a, { id, texto, tipo }])
    setTimeout(() => setAvisos((a) => a.filter((x) => x.id !== id)), 4500)
  }, [])
  return (
    <AvisosCtx.Provider value={avisar}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 z-50 flex flex-col items-center gap-2 px-4" style={{ bottom: 'calc(84px + env(safe-area-inset-bottom, 0px))' }} aria-live="polite">
        {avisos.map((a) => (
          <div key={a.id} className={cx('pointer-events-auto max-w-md rounded-xl px-4 py-2.5 text-sm shadow-lg', a.tipo === 'ok' ? 'bg-ink text-bg' : 'bg-neg text-white')}>
            {a.texto}
          </div>
        ))}
      </div>
    </AvisosCtx.Provider>
  )
}
export const useAvisos = () => useContext(AvisosCtx)

/** Mutación que, al terminar, refresca los datos y avisa. */
export function useAccion<T>(fn: (v: T) => Promise<unknown>, mensajeOk?: string) {
  const qc = useQueryClient()
  const avisar = useAvisos()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries()
      if (mensajeOk) avisar(mensajeOk)
    },
    onError: (e: Error) => avisar(e.message, 'error'),
  })
}

export function Cargando() {
  return (
    <div className="grid gap-4 sm:grid-cols-3" aria-busy="true">
      {[0, 1, 2].map((i) => <div key={i} className="h-28 animate-pulse rounded-2xl bg-panel-2" />)}
    </div>
  )
}

export function ErrorCarga({ error }: { error: Error }) {
  return <Vacio>No se han podido cargar los datos: {error.message}</Vacio>
}
