import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { keepPreviousData, useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { InfiniteData } from '@tanstack/react-query'
import { Ellipsis, FileSpreadsheet, Pencil, Plus, Search, SquarePen } from 'lucide-react'
import { api } from '../../lib/api'
import { capitalizar, eur, fecha } from '../../lib/format'
import type { Categoria, Cuenta, Movimiento, Movimientos as Pagina } from '../../lib/tipos'
import { useAccion, useAvisos } from '../../lib/utilidades'
import { Boton, Campo, Casilla, Dialogo, ErrorCarga, Etiqueta, Importe, Segmentos, Selector, Tabla, Tarjeta, Vacio } from '../ui'
import Apuntar from './Apuntar'
import { FormMovimiento, NotaMovimiento } from './FormMovimiento'
import { OpcionesCategoria, SelectorEnLinea } from './Selectores'
import { APUNTADO, esManual, rangosPeriodo } from './comun'

const CLAVES = ['cuenta', 'categoria', 'q', 'desde', 'hasta', 'tipo'] as const
type Filtros = Record<typeof CLAVES[number], string>
const PERIODOS = [
  { valor: 'mes', texto: 'Este mes' }, { valor: 'mes_pasado', texto: 'Mes pasado' }, { valor: 'anio', texto: 'Este año' },
  { valor: 'doce', texto: '12 meses' }, { valor: 'todo', texto: 'Todo' },
] as const
const TIPOS = [{ valor: '', texto: 'Todos' }, { valor: 'ingresos', texto: 'Entran' }, { valor: 'gastos', texto: 'Salen' }] as const
const claseEnlace = 'inline-flex items-center gap-1.5 rounded-xl border border-line bg-panel px-3 py-1.5 text-xs font-medium hover:bg-panel-2'
const VACIO: Set<number> = new Set()

type Lote = { ids: number[]; categoria_id: number | null }

/** Lista de movimientos con filtros (en la URL, para enlazar desde otras pantallas), paginación, categoría por
 *  fila o en lote, notas, movimientos a mano y «apuntar como gasto». */
export default function Movimientos({ cuentas, categorias }: { cuentas: Cuenta[]; categorias: Categoria[] }) {
  const [params, setParams] = useSearchParams()
  const filtros = useMemo(() => Object.fromEntries(CLAVES.map((k) => [k, params.get(k) ?? ''])) as Filtros, [params])
  const cambiar = (cambios: Partial<Filtros>) => {
    const p = new URLSearchParams(params)
    for (const [k, v] of Object.entries(cambios)) { if (v) p.set(k, v); else p.delete(k) }
    setParams(p, { replace: true })
  }
  // La búsqueda espera a que dejes de teclear; si la URL cambia por fuera (un enlace, el menú), manda la URL
  const [busqueda, setBusqueda] = useState({ base: filtros.q, texto: filtros.q })
  const texto = busqueda.base === filtros.q ? busqueda.texto : filtros.q
  const setTexto = (v: string) => setBusqueda({ base: filtros.q, texto: v })
  useEffect(() => {
    if (texto.trim() === filtros.q) return
    const t = setTimeout(() => {
      const q = texto.trim()
      const p = new URLSearchParams(params)
      if (q) p.set('q', q); else p.delete('q')
      setBusqueda((b) => ({ ...b, base: q }))
      setParams(p, { replace: true })
    }, 300)
    return () => clearTimeout(t)
  }, [texto, filtros.q, params, setParams])

  const qs = useMemo(() => {
    const p = new URLSearchParams()
    if (filtros.cuenta) p.set('cuenta_id', filtros.cuenta)
    else p.set('solo_tuyas', 'true')  // las cuentas que no son tuyas, solo si las eliges
    if (filtros.categoria) p.set('categoria_id', filtros.categoria)
    if (filtros.q) p.set('q', filtros.q)
    if (filtros.desde) p.set('desde', filtros.desde)
    if (filtros.hasta) p.set('hasta', filtros.hasta)
    if (filtros.tipo) p.set('tipo', filtros.tipo)
    return p.toString()
  }, [filtros])
  const clave = useMemo(() => ['movimientos', qs], [qs])
  const movs = useInfiniteQuery({
    queryKey: clave,
    queryFn: ({ pageParam }) => api.get<Pagina>(`/movimientos?${qs}&offset=${pageParam}`),
    initialPageParam: 0,
    getNextPageParam: (ultima, paginas) => {
      const cargados = paginas.reduce((n, p) => n + p.movimientos.length, 0)
      return ultima.movimientos.length && cargados < ultima.total ? cargados : undefined
    },
    placeholderData: keepPreviousData,
  })
  const filas = useMemo(() => movs.data?.pages.flatMap((p) => p.movimientos) ?? [], [movs.data])
  const resumen = movs.data?.pages[0]

  // Selección para categorizar en lote (se vacía sola al cambiar los filtros)
  const [sel, setSel] = useState<{ qs: string; ids: Set<number> }>({ qs, ids: VACIO })
  const seleccion = sel.qs === qs ? sel.ids : VACIO
  const alternar = (id: number) => {
    const ids = new Set(seleccion)
    if (ids.has(id)) ids.delete(id); else ids.add(id)
    setSel({ qs, ids })
  }
  const todosMarcados = filas.length > 0 && filas.every((m) => seleccion.has(m.id))
  const [catLote, setCatLote] = useState('')
  const qc = useQueryClient()
  const avisar = useAvisos()
  const lote = useMutation({
    mutationFn: (d: Lote) => api.patch<{ cambiados: number }>('/movimientos/categoria', d),
    onMutate: ({ ids, categoria_id }) => {  // la fila cambia al momento; si falla, vuelve
      const antes = qc.getQueryData<InfiniteData<Pagina>>(clave)
      if (antes) {
        qc.setQueryData<InfiniteData<Pagina>>(clave, {
          ...antes,
          pages: antes.pages.map((p) => ({ ...p, movimientos: p.movimientos.map((m) => (ids.includes(m.id) ? { ...m, categoria_id } : m)) })),
        })
      }
      return { antes }
    },
    onError: (e: Error, _v, ctx) => { if (ctx?.antes) qc.setQueryData(clave, ctx.antes); avisar(e.message, 'error') },
    onSuccess: (r) => { avisar(`${r.cambiados} movimientos cambiados`); setSel({ qs, ids: VACIO }) },
    onSettled: () => { qc.invalidateQueries({ queryKey: ['movimientos'] }); qc.invalidateQueries({ queryKey: ['categorias'] }) },
  })

  // Categoría de una fila: la app aprende la regla y ofrece aplicarla a los parecidos
  const [aprendido, setAprendido] = useState<{ id: number; patron: string; parecidos: number; categoria: string } | null>(null)
  const categorizar = useAccion(({ id, cat }: { id: number; cat: string }) =>
    api.patch<{ patron: string | null; parecidos: number }>(`/movimientos/${id}`, { categoria_id: cat ? Number(cat) : null }).then((r) => {
      const nombre = categorias.find((c) => String(c.id) === cat)?.nombre ?? ''
      setAprendido(r.patron && cat ? { id, patron: r.patron, parecidos: r.parecidos, categoria: nombre } : null)
    }))
  const aplicar = useAccion((id: number) => api.post<{ cambiados: number }>(`/movimientos/${id}/aplicar-a-parecidos`, {})
    .then((r) => { setAprendido(null); avisar(`${r.cambiados} movimientos cambiados`) }))

  const [nuevo, setNuevo] = useState(false)
  const [editar, setEditar] = useState<Movimiento | null>(null)
  const [nota, setNota] = useState<Movimiento | null>(null)
  const [apuntar, setApuntar] = useState<Movimiento | null>(null)

  const cuentasManuales = cuentas.filter(esManual)
  const [rangos] = useState(rangosPeriodo)  // los atajos de periodo, fijos mientras la página está abierta
  const [anio] = useState(() => String(new Date().getFullYear()))
  const periodo = Object.keys(rangos).find((k) => rangos[k][0] === filtros.desde && rangos[k][1] === filtros.hasta) ?? ''
  const hayFiltros = CLAVES.some((k) => filtros[k])

  const celdaConcepto = (m: Movimiento) => {
    const apuntadoYa = m.nota.startsWith(APUNTADO)
    return (
      <div className="min-w-0">
        <div className="truncate" title={m.concepto}>{m.concepto}</div>
        {(m.traspaso || m.nota) && (
          <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs">
            {m.traspaso && <Etiqueta>Traspaso</Etiqueta>}
            {apuntadoYa
              ? <span className="min-w-0 truncate" title={m.nota}><Etiqueta tono="acento">{capitalizar(m.nota.slice(APUNTADO.length))}</Etiqueta></span>
              : m.nota && <span className="truncate text-muted" title={m.nota}>{m.nota}</span>}
          </div>
        )}
      </div>
    )
  }
  const celdaCategoria = (m: Movimiento) => (
    <SelectorEnLinea value={m.categoria_id ?? ''} aria-label={`Categoría de ${m.concepto}`} className={m.categoria_id ? '' : 'text-warn'}
      disabled={categorizar.isPending && categorizar.variables?.id === m.id} onChange={(e) => categorizar.mutate({ id: m.id, cat: e.target.value })}>
      <OpcionesCategoria categorias={categorias} />
    </SelectorEnLinea>
  )
  const acciones = (m: Movimiento) => (
    <span className="flex items-center justify-end gap-0.5">
      <Boton variante="fantasma" className="px-1.5 py-1" aria-label={m.nota ? `Nota: ${m.nota}` : 'Añadir nota'} title={m.nota || 'Añadir nota'} onClick={() => setNota(m)}>
        <Pencil size={13} className={m.nota ? 'text-accent' : undefined} />
      </Boton>
      {m.manual && <Boton variante="fantasma" className="px-1.5 py-1" aria-label="Editar movimiento" title="Editar" onClick={() => setEditar(m)}><SquarePen size={14} /></Boton>}
      {m.importe < 0 && (
        <Boton variante="fantasma" className="px-1.5 py-1" aria-label="Apuntar como gasto de la actividad o del piso" title="Apuntar como gasto…" onClick={() => setApuntar(m)}>
          <Ellipsis size={15} />
        </Boton>
      )}
    </span>
  )
  const fechaCorta = (m: Movimiento) => fecha(m.fecha, m.fecha.startsWith(anio) ? { day: '2-digit', month: 'short' } : { day: '2-digit', month: 'short', year: '2-digit' })

  return (
    <Tarjeta className="mt-6" titulo="Movimientos">
      <div className="mb-4 space-y-3">
        <div className="grid gap-3 sm:grid-cols-[1fr_1fr_1.4fr]">
          <Selector value={filtros.cuenta} onChange={(e) => cambiar({ cuenta: e.target.value })} aria-label="Cuenta">
            <option value="">Todas tus cuentas</option>
            {cuentas.map((c) => <option key={c.id} value={c.id}>{c.nombre}{c.participacion === 0 ? ' (no es tuya)' : ''}</option>)}
          </Selector>
          <Selector value={filtros.categoria} onChange={(e) => cambiar({ categoria: e.target.value })} aria-label="Categoría">
            <option value="">Todas las categorías</option>
            <option value="0">Sin categoría</option>
            {categorias.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
          </Selector>
          <label className="relative">
            <Search size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-muted" />
            <Campo value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Buscar concepto" className="pl-9" aria-label="Buscar concepto" />
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="max-w-full overflow-x-auto">
            <Segmentos pequeno etiqueta="Periodo" opciones={PERIODOS} valor={periodo} onCambiar={(p) => cambiar({ desde: rangos[p][0], hasta: rangos[p][1] })} />
          </div>
          <span className="flex items-center gap-1.5 text-xs text-muted">
            <Campo type="date" value={filtros.desde} onChange={(e) => cambiar({ desde: e.target.value })} aria-label="Desde" className="w-auto! py-1.5! text-xs" />
            –
            <Campo type="date" value={filtros.hasta} onChange={(e) => cambiar({ hasta: e.target.value })} aria-label="Hasta" className="w-auto! py-1.5! text-xs" />
          </span>
          <Segmentos pequeno etiqueta="Tipo" opciones={TIPOS} valor={filtros.tipo} onCambiar={(t) => cambiar({ tipo: t })} />
          <span className="ml-auto flex flex-wrap items-center gap-2">
            {cuentasManuales.length > 0 && (
              <Boton variante="secundario" className="px-3 py-1.5 text-xs" onClick={() => setNuevo(true)}><Plus size={14} />Nuevo movimiento</Boton>
            )}
            <a className={claseEnlace} href={`/api/exportar/movimientos.xlsx?${qs}`} download title="Descargar en Excel lo que ves con estos filtros">
              <FileSpreadsheet size={14} />Excel
            </a>
          </span>
        </div>
      </div>

      {aprendido && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-accent-soft px-4 py-3 text-sm">
          <span>Desde ahora, lo que contenga «{aprendido.patron}» irá a {aprendido.categoria}.
            {aprendido.parecidos > 0 && ` Hay ${aprendido.parecidos} movimientos anteriores parecidos con otra categoría.`}</span>
          <span className="flex gap-2">
            {aprendido.parecidos > 0 && <Boton className="px-3 py-1.5 text-xs" disabled={aplicar.isPending} onClick={() => aplicar.mutate(aprendido.id)}>
              Cambiar los {aprendido.parecidos}</Boton>}
            <Boton variante="fantasma" className="px-3 py-1.5 text-xs" onClick={() => setAprendido(null)}>Cerrar</Boton>
          </span>
        </div>
      )}
      {seleccion.size > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl bg-accent-soft px-4 py-3 text-sm" role="region" aria-label="Categorizar en lote">
          <span className="font-medium">{seleccion.size} {seleccion.size === 1 ? 'seleccionado' : 'seleccionados'}</span>
          <Selector value={catLote} onChange={(e) => setCatLote(e.target.value)} aria-label="Categoría para los seleccionados" className="w-auto! py-1.5!">
            <OpcionesCategoria categorias={categorias} />
          </Selector>
          <Boton className="px-3 py-1.5 text-xs" disabled={lote.isPending} onClick={() => lote.mutate({ ids: [...seleccion], categoria_id: catLote ? Number(catLote) : null })}>
            {lote.isPending ? 'Aplicando…' : 'Aplicar'}
          </Boton>
          <Boton variante="fantasma" className="px-3 py-1.5 text-xs" onClick={() => setSel({ qs, ids: VACIO })}>Quitar selección</Boton>
        </div>
      )}

      {movs.error && !movs.data ? <ErrorCarga error={movs.error} /> : filas.length ? (
        <div className={movs.isPlaceholderData ? 'opacity-60 transition' : undefined}>
          <ul className="divide-y divide-line sm:hidden">
            {filas.map((m) => (
              <li key={m.id} className="flex items-start gap-2 py-3 text-sm first:pt-0">
                <Casilla etiqueta={null} className="mt-0.5" aria-label={`Seleccionar ${m.concepto}`} checked={seleccion.has(m.id)} onChange={() => alternar(m.id)} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    {celdaConcepto(m)}
                    <Importe valor={m.importe} signo className="shrink-0" />
                  </div>
                  <div className="mt-0.5 truncate text-xs text-muted">{fechaCorta(m)} · {m.cuenta}{m.saldo != null && ` · saldo ${eur(m.saldo)}`}</div>
                  <div className="mt-1 flex items-center justify-between gap-2">{celdaCategoria(m)}{acciones(m)}</div>
                </div>
              </li>
            ))}
          </ul>
          <div className="hidden sm:block">
            <Tabla>
              <thead>
                <tr>
                  <th className="w-8"><Casilla etiqueta={null} aria-label="Seleccionar todos los de la lista" checked={todosMarcados}
                    onChange={() => setSel({ qs, ids: todosMarcados ? VACIO : new Set(filas.map((m) => m.id)) })} /></th>
                  <th>Fecha</th><th>Concepto</th><th className="hidden md:table-cell">Cuenta</th><th>Categoría</th>
                  <th className="num">Importe</th><th className="num hidden lg:table-cell">Saldo</th><th><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {filas.map((m) => (
                  <tr key={m.id} className={seleccion.has(m.id) ? 'bg-accent-soft/40' : undefined}>
                    <td><Casilla etiqueta={null} aria-label={`Seleccionar ${m.concepto}`} checked={seleccion.has(m.id)} onChange={() => alternar(m.id)} /></td>
                    <td className="cifra whitespace-nowrap text-muted" title={fecha(m.fecha)}>{fechaCorta(m)}</td>
                    <td className="max-w-[320px]">{celdaConcepto(m)}</td>
                    <td className="hidden text-muted md:table-cell">{m.cuenta}</td>
                    <td>{celdaCategoria(m)}</td>
                    <td className="num"><Importe valor={m.importe} signo /></td>
                    <td className="num cifra hidden text-muted lg:table-cell">{m.saldo == null ? '' : eur(m.saldo)}</td>
                    <td className="whitespace-nowrap">{acciones(m)}</td>
                  </tr>
                ))}
              </tbody>
            </Tabla>
          </div>
          {resumen && (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-muted">
              <span>
                {resumen.total} {resumen.total === 1 ? 'movimiento' : 'movimientos'} · entran <Importe valor={resumen.suma_ingresos} signo /> · salen <Importe valor={-resumen.suma_gastos} signo />
                {filas.length < resumen.total && ` · se ven ${filas.length}`}
              </span>
              {movs.hasNextPage && (
                <Boton variante="secundario" className="px-3 py-1.5 text-xs" disabled={movs.isFetchingNextPage} onClick={() => movs.fetchNextPage()}>
                  {movs.isFetchingNextPage ? 'Cargando…' : `Ver ${Math.min(300, resumen.total - filas.length)} más`}
                </Boton>
              )}
            </div>
          )}
        </div>
      ) : movs.isLoading ? <Vacio>Cargando…</Vacio> : hayFiltros ? (
        <Vacio>
          No hay movimientos con estos filtros.{' '}
          <button type="button" className="cursor-pointer font-medium text-accent" onClick={() => { setTexto(''); setParams({}, { replace: true }) }}>Quitar filtros</button>
        </Vacio>
      ) : (
        <Vacio>
          Aún no hay movimientos: conecta Sabadell en Ajustes, importa un extracto en una cuenta
          {cuentasManuales.length > 0 ? ' o apunta uno a mano con «Nuevo movimiento».' : ' o crea una cuenta manual y apunta los tuyos.'}
        </Vacio>
      )}

      <Dialogo abierto={nuevo} onCerrar={() => setNuevo(false)} titulo="Nuevo movimiento">
        <FormMovimiento cuentas={cuentasManuales} categorias={categorias} onCerrar={() => setNuevo(false)} />
      </Dialogo>
      <Dialogo abierto={!!editar} onCerrar={() => setEditar(null)} titulo="Editar movimiento">
        {editar && <FormMovimiento cuentas={cuentasManuales} categorias={categorias} editar={editar} onCerrar={() => setEditar(null)} />}
      </Dialogo>
      <Dialogo abierto={!!nota} onCerrar={() => setNota(null)} titulo="Nota del movimiento">
        {nota && <NotaMovimiento m={nota} onCerrar={() => setNota(null)} />}
      </Dialogo>
      <Apuntar m={apuntar} onCerrar={() => setApuntar(null)} />
    </Tarjeta>
  )
}
