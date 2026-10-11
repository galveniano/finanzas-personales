import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as TeclaReact } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { api } from '../lib/api'
import { DESTINOS } from '../lib/atajos'
import { aplicarTema, temaEfectivo, useTema } from '../lib/tema'
import type { Busqueda } from '../lib/tipos'
import { useSincronizar } from '../lib/sincronizar'
import { Importe } from './ui'

interface Opcion { id: string; texto: string; detalle?: string; grupo: string; importe?: number | null; ejecutar: () => void }

/** Sin tildes ni mayúsculas, para que «nomina» encuentre «Nómina». */
const plano = (t: string) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

function useRetardo<T>(valor: T, ms: number) {
  const [v, setV] = useState(valor)
  useEffect(() => {
    const t = setTimeout(() => setV(valor), ms)
    return () => clearTimeout(t)
  }, [valor, ms])
  return v
}

/** Paleta de comandos (Ctrl/Cmd+K): pantallas, acciones y, al escribir, lo que encuentra /buscar. */
export default function Paleta({ abierto, onCerrar }: { abierto: boolean; onCerrar: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const entrada = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const [texto, setTexto] = useState('')
  const [activo, setActivo] = useState(0)
  const q = useRetardo(texto.trim(), 200)
  const buscando = q.length >= 2
  useTema()  // para que «Tema oscuro/claro» cambie de nombre al cambiar el tema
  const sincronizar = useSincronizar('/sync')
  const { data, isFetching } = useQuery({
    queryKey: ['buscar', q], queryFn: () => api.get<Busqueda>(`/buscar?q=${encodeURIComponent(q)}`),
    enabled: abierto && buscando, staleTime: 60_000, placeholderData: keepPreviousData,
  })

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (abierto && !d.open) {
      setTexto('')
      setActivo(0)
      d.showModal()
      entrada.current?.focus()
    }
    if (!abierto && d.open) d.close()
  }, [abierto])

  const ir = (ruta: string) => { onCerrar(); navigate(ruta) }
  const oscuro = temaEfectivo() === 'oscuro'
  const acciones: Opcion[] = [
    { id: 'a-factura', texto: 'Nueva factura', detalle: 'Ingresos › Autónomo', grupo: 'Acciones', ejecutar: () => ir('/ingresos?accion=factura') },
    { id: 'a-objetivo', texto: 'Nuevo objetivo', detalle: 'Plan', grupo: 'Acciones', ejecutar: () => ir('/plan?accion=objetivo') },
    { id: 'a-pago', texto: 'Nuevo pago previsto', detalle: 'Plan', grupo: 'Acciones', ejecutar: () => ir('/plan?accion=pago') },
    { id: 'a-sync', texto: 'Sincronizar', detalle: 'Sabadell e Indexa ahora', grupo: 'Acciones', ejecutar: () => { onCerrar(); sincronizar.mutate(undefined) } },
    { id: 'a-tema', texto: oscuro ? 'Tema claro' : 'Tema oscuro', detalle: 'Cambiar el aspecto de la app', grupo: 'Acciones',
      ejecutar: () => { aplicarTema(oscuro ? 'claro' : 'oscuro'); onCerrar() } },
  ]
  const destinos: Opcion[] = DESTINOS.map((d) => ({
    id: `d-${d.ruta}`, texto: d.texto, detalle: d.tecla ? `g ${d.tecla}` : undefined, grupo: 'Ir a', ejecutar: () => ir(d.ruta),
  }))
  const coincide = (o: Opcion) => !q || plano(o.texto).includes(plano(q))
  const remotos: Opcion[] = (buscando ? data?.grupos ?? [] : []).flatMap((g) => g.resultados.map((r, i) => ({
    id: `r-${g.nombre}-${i}`, texto: r.texto, detalle: r.detalle, importe: r.importe, grupo: g.nombre, ejecutar: () => ir(r.ir),
  })))
  const opciones = [...remotos, ...destinos.filter(coincide), ...acciones.filter(coincide)]
  const seleccionada = Math.min(activo, Math.max(opciones.length - 1, 0))

  useEffect(() => {
    document.getElementById(`paleta-op-${seleccionada}`)?.scrollIntoView({ block: 'nearest' })
  }, [seleccionada])

  const teclas = (e: TeclaReact<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActivo((a) => (opciones.length ? (a + 1) % opciones.length : 0)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActivo((a) => (opciones.length ? (a - 1 + opciones.length) % opciones.length : 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); opciones[seleccionada]?.ejecutar() }
    else if (e.key === 'Home') { setActivo(0) }
    else if (e.key === 'End') { setActivo(Math.max(opciones.length - 1, 0)) }
  }

  // Las opciones ya vienen agrupadas y en orden: se pinta un rótulo cada vez que cambia el grupo
  let grupoAnterior = ''
  return (
    <dialog
      ref={ref}
      onClose={onCerrar}
      onClick={(e) => { if (e.target === ref.current) onCerrar() }}
      aria-label="Buscar y acciones"
      className="m-0 mx-auto mt-[6vh] w-[min(640px,calc(100vw-24px))] rounded-2xl border border-line bg-panel p-0 text-ink shadow-2xl backdrop:bg-black/40 sm:mt-[12vh]"
    >
      <div className="flex items-center gap-3 border-b border-line px-4">
        <Search size={18} className="shrink-0 text-muted" aria-hidden />
        <input
          ref={entrada}
          value={texto}
          onChange={(e) => { setTexto(e.target.value); setActivo(0) }}
          onKeyDown={teclas}
          role="combobox"
          aria-expanded={opciones.length > 0}
          aria-controls="paleta-lista"
          aria-activedescendant={opciones.length ? `paleta-op-${seleccionada}` : undefined}
          aria-autocomplete="list"
          autoComplete="off"
          spellCheck={false}
          placeholder="Movimientos, facturas, bienes… o una pantalla o acción"
          className="min-w-0 flex-1 bg-transparent py-3.5 text-sm outline-none placeholder:text-muted/70"
        />
        {isFetching && <span className="text-xs text-muted" aria-live="polite">Buscando…</span>}
        <kbd className="hidden sm:inline-block">Esc</kbd>
      </div>
      <ul id="paleta-lista" role="listbox" aria-label="Resultados" className="max-h-[60vh] overflow-y-auto p-2">
        {opciones.map((o, i) => {
          const nuevoGrupo = o.grupo !== grupoAnterior
          grupoAnterior = o.grupo
          return (
            <li key={o.id} role="presentation">
              {nuevoGrupo && <div className="px-2 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wider text-muted" aria-hidden>{o.grupo}</div>}
              <div
                id={`paleta-op-${i}`}
                role="option"
                aria-selected={i === seleccionada}
                onMouseEnter={() => setActivo(i)}
                onClick={o.ejecutar}
                className={`flex cursor-pointer items-center justify-between gap-3 rounded-xl px-3 py-2 text-sm ${i === seleccionada ? 'bg-accent-soft text-accent' : ''}`}
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">{o.texto}</span>
                  {o.detalle && <span className={`block truncate text-xs ${i === seleccionada ? 'text-accent/80' : 'text-muted'}`}>{o.detalle}</span>}
                </span>
                {o.importe != null && <Importe valor={o.importe} signo className="text-xs" />}
              </div>
            </li>
          )
        })}
        {!opciones.length && (
          <li className="px-3 py-8 text-center text-sm text-muted">
            {buscando && isFetching ? 'Buscando…' : `Nada que encaje con «${texto.trim()}»`}
          </li>
        )}
      </ul>
      <div className="hidden items-center gap-4 border-t border-line px-4 py-2 text-xs text-muted sm:flex">
        <span><kbd>↑</kbd> <kbd>↓</kbd> moverte</span><span><kbd>↵</kbd> abrir</span><span><kbd>Esc</kbd> cerrar</span>
        <span className="ml-auto">Escribe dos letras para buscar en tus datos</span>
      </div>
    </dialog>
  )
}
