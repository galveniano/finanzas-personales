import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowDownRight, ArrowUpRight, Copy, Eye, EyeOff, SlidersHorizontal, TrendingUp, X } from 'lucide-react'
import { Bar, CartesianGrid, Cell, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../lib/api'
import { capitalizar, diasHasta, eur, eurK, fecha, mesCorto, pct } from '../lib/format'
import { cursorBarra, eje, estiloTooltip } from '../lib/graficas'
import type { AnalisisGastos, Categoria, CompararGastos, Presupuestos, Suscripcion } from '../lib/tipos'
import { num, useAccion } from '../lib/utilidades'
import BarraTono from '../components/BarraTono'
import IconoServicio from '../components/IconoServicio'
import { Boton, Cabecera, Campo, Cargando, Dato, Dialogo, ErrorCarga, Etiqueta, Formulario, Importe, Segmentos, Selector, Tabla, Tarjeta, Vacio } from '../components/ui'

const PERIODOS = [3, 6, 12].map((m) => ({ valor: m, texto: `${m} meses` }))
const COMPARAR = [{ valor: 'anterior', texto: 'Periodo anterior' }, { valor: 'anio_pasado', texto: 'Mismo periodo del año pasado' }] as const
const CADA: Record<Suscripcion['periodicidad'], string> = { mensual: 'al mes', trimestral: 'cada 3 meses', semestral: 'cada 6 meses', anual: 'al año' }
const SERIE: Record<string, string> = { ingresos: 'Entra', gastos: 'Gastas', aparte: 'Aparte', ahorro: 'Ahorro' }
const SIN_CATEGORIA = 'Sin categoría'

const nombreMes = (ym: string) => capitalizar(fecha(`${ym}-01`, { month: 'long', year: 'numeric' }))
const enCuentas = (q: string) => `/cuentas?q=${encodeURIComponent(q)}`

export default function Gastos() {
  const [meses, setMeses] = useState<number>(6)
  const [mes, setMes] = useState<string | null>(null)
  const [comparar, setComparar] = useState<CompararGastos>('anterior')
  const [presupuestar, setPresupuestar] = useState(false)
  const params = new URLSearchParams({ meses: String(meses), comparar })
  if (mes) params.set('mes', mes)
  const { data: g, isLoading, error, isFetching } = useQuery({
    queryKey: ['gastos', meses, mes, comparar], queryFn: () => api.get<AnalisisGastos>(`/gastos?${params}`), placeholderData: keepPreviousData,
  })
  const { data: presupuestos = {} } = useQuery({ queryKey: ['presupuestos'], queryFn: () => api.get<Presupuestos>('/gastos/presupuestos') })

  const subtitulo = g && (g.mes
    ? `${nombreMes(g.mes)}, el mes completo`
    : `Del ${fecha(g.desde, { day: 'numeric', month: 'short', year: 'numeric' })} al ${fecha(g.hasta, { day: 'numeric', month: 'short', year: 'numeric' })}, meses completos`)

  return (
    <>
      <Cabecera titulo="Gastos" subtitulo={subtitulo}>
        {mes && (
          <button type="button" onClick={() => setMes(null)} aria-label={`Quitar el mes elegido, ${nombreMes(mes)}`} className="cursor-pointer">
            <Etiqueta tono="acento">{nombreMes(mes)} · quitar <X size={12} aria-hidden /></Etiqueta>
          </button>
        )}
        <Segmentos etiqueta="Periodo" opciones={PERIODOS} valor={meses} onCambiar={setMeses} />
        <Boton variante="secundario" onClick={() => setPresupuestar(true)}><SlidersHorizontal size={15} />Presupuestos</Boton>
      </Cabecera>
      {isLoading ? <Cargando /> : error ? <ErrorCarga error={error} /> : g && (
        <div className={`space-y-4 transition-opacity ${isFetching ? 'opacity-60' : ''}`}>
          <Resumen g={g} presupuestos={presupuestos} comparar={comparar} onComparar={setComparar} />
          <SinCategoria g={g} />
          <div className="grid gap-4 lg:grid-cols-2">
            <ListaFijos titulo="Suscripciones" lista={g.suscripciones} ocultas={g.ignoradas.filter((x) => x.tipo === 'suscripcion')} total={g.suscripciones_mes}
              vacio="Aquí saldrán Netflix, Spotify, el gimnasio, las apps… en cuanto se cobren en tus cuentas." />
            <ListaFijos titulo="Recibos fijos" lista={g.recibos} ocultas={g.ignoradas.filter((x) => x.tipo === 'recibo')} total={g.recibos_mes}
              vacio="Aquí saldrán la luz, el teléfono, los seguros, la hipoteca… los cargos que se repiten cada mes." />
          </div>
          <MesAMes g={g} mes={mes} onMes={setMes} />
          <div className="grid gap-4 lg:grid-cols-3">
            <Categorias g={g} presupuestos={presupuestos} />
            <Sitios g={g} />
          </div>
          <Mayores g={g} />
          <p className="text-xs text-muted">
            Sin traspasos entre tus cuentas, sin aportaciones a Indexa y sin la cuenta que no es tuya; de las compartidas solo cuenta tu parte.
            {g.aparte.total > 0 && ` Van aparte, y no suman aquí, ${eur(g.aparte.total)} de impuestos y pagos previstos (plazos de la casa, llamadas de capital…).`}
          </p>
        </div>
      )}
      <Dialogo abierto={presupuestar} onCerrar={() => setPresupuestar(false)} titulo="Presupuestos por categoría">
        {g && <FormPresupuestos g={g} presupuestos={presupuestos} onCerrar={() => setPresupuestar(false)} />}
      </Dialogo>
    </>
  )
}

/** Con qué se compara el periodo analizado, en palabras. */
function periodoComparado(g: AnalisisGastos) {
  const base = g.comparar === 'anio_pasado' ? 'el mismo periodo del año pasado' : g.meses === 1 ? 'el mes anterior' : `los ${g.meses} meses anteriores`
  return g.antes && g.antes.meses < g.meses ? `${base} (solo ${g.antes.meses} con datos)` : base
}

function Resumen({ g, presupuestos, comparar, onComparar }: {
  g: AnalisisGastos; presupuestos: Presupuestos; comparar: CompararGastos; onComparar: (c: CompararGastos) => void
}) {
  const cambio = g.gastos_mes_antes ? ((g.gastos_mes - g.gastos_mes_antes) / g.gastos_mes_antes) * 100 : null
  const notaCambio = cambio === null ? (g.mes ? 'En ese mes' : 'De media; sin datos del periodo anterior')
    : Math.abs(cambio) < 0.05 ? `Igual que ${periodoComparado(g)}`
    : <span className={cambio > 0 ? 'text-neg' : 'text-pos'}>{cambio > 0 ? '▲' : '▼'} {pct(Math.abs(cambio), 1)} que {periodoComparado(g)}</span>
  const conPresupuesto = Object.keys(presupuestos)
  const presupuesto = conPresupuesto.reduce((s, c) => s + presupuestos[c], 0)
  const llevas = conPresupuesto.reduce((s, c) => s + (g.este_mes.por_categoria[c] ?? 0), 0)
  return (
    <Tarjeta accion={<Segmentos pequeno etiqueta="Comparar con" opciones={COMPARAR} valor={comparar} onCambiar={onComparar} />}>
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <Dato etiqueta={g.mes ? 'Gastaste' : 'Gastas al mes'} valor={eur(g.gastos_mes)} nota={notaCambio} />
        <Dato etiqueta={g.mes ? 'Entró' : 'Entra al mes'} valor={eur(g.ingresos_mes)} nota={g.mes ? 'Nómina, cobros y demás' : 'De media'} />
        <Dato etiqueta={g.mes ? 'Ahorraste' : 'Ahorras al mes'} valor={eur(g.ahorro_mes)} tono={g.ahorro_mes >= 0 ? 'pos' : 'neg'}
          nota={g.tasa_ahorro !== null ? `${pct(Math.abs(g.tasa_ahorro), 1)} de lo que entra` : undefined} />
        <Dato etiqueta={g.mes ? 'Fijo' : 'Fijo al mes'} valor={eur(g.fijo_mes)}
          nota={`Suscripciones y recibos cobrados en el periodo; el resto, ${eur(g.variable_mes)}, es variable`} />
      </div>
      {g.gastos_mes > 0 && (
        <div className="mt-5">
          <div className="flex h-2.5 overflow-hidden rounded-full bg-panel-2" role="img" aria-label={`Fijo ${pct((g.fijo_mes / g.gastos_mes) * 100, 0)}, variable el resto`}>
            <div className="h-full bg-[var(--chart-2)]" style={{ width: `${Math.min(100, (g.fijo_mes / g.gastos_mes) * 100)}%` }} />
            <div className="h-full bg-[var(--chart-3)]" style={{ width: `${Math.max(0, 100 - (g.fijo_mes / g.gastos_mes) * 100)}%` }} />
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
            <span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-[var(--chart-2)]" />Fijo</span>
            <span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-[var(--chart-3)]" />Variable</span>
            <span>Este mes llevas {eur(g.este_mes.gastos)} en {g.este_mes.dia} {g.este_mes.dia === 1 ? 'día' : 'días'}.</span>
          </div>
        </div>
      )}
      {conPresupuesto.length > 0 && (
        <div className="mt-5 border-t border-line pt-4">
          <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-2 text-sm">
            <span>Presupuesto del mes: <strong className="cifra">{eur(presupuesto)}</strong> · llevas <strong className={`cifra ${llevas > presupuesto ? 'text-neg' : ''}`}>{eur(llevas)}</strong> en esas categorías</span>
            <span className="text-xs text-muted">{conPresupuesto.length} {conPresupuesto.length === 1 ? 'categoría' : 'categorías'} con presupuesto</span>
          </div>
          <BarraTono valor={llevas} max={presupuesto} tono={llevas > presupuesto ? 'neg' : llevas > presupuesto * 0.9 ? 'aviso' : 'acento'} etiqueta="Gastado del presupuesto del mes" />
        </div>
      )}
    </Tarjeta>
  )
}

function SinCategoria({ g }: { g: AnalisisGastos }) {
  const sin = g.categorias.find((c) => c.categoria === SIN_CATEGORIA)
  if (!sin || sin.peso < 10) return null
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warn/40 bg-warn-soft px-4 py-2.5 text-sm text-warn">
      <span>{sin.veces} {sin.veces === 1 ? 'movimiento' : 'movimientos'} ({eur(sin.total)}) sin categoría en este periodo: el reparto por categorías se queda corto.</span>
      <Link to="/cuentas?categoria=0" className="text-xs font-medium underline underline-offset-2">Clasificarlos</Link>
    </div>
  )
}

function ListaFijos({ titulo, lista, ocultas, total, vacio }: { titulo: string; lista: Suscripcion[]; ocultas: Suscripcion[]; total: number; vacio: string }) {
  const activas = lista.filter((x) => x.activa)
  const pasadas = lista.filter((x) => !x.activa)
  const proximos = activas.filter((x) => x.proximo && diasHasta(x.proximo) <= 30).reduce((s, x) => s + x.importe, 0)
  return (
    <Tarjeta titulo={titulo} accion={activas.length > 0 && (
      <span className="text-right text-sm"><span className="cifra font-semibold">{eur(total)}</span><span className="text-muted">/mes</span>
        <span className="block text-xs text-muted">{eur(total * 12)} al año</span></span>)}>
      {activas.length ? <ul className="divide-y divide-line">{activas.map((x) => <FilaFijo key={x.clave} x={x} />)}</ul> : <Vacio>{vacio}</Vacio>}
      {proximos > 0 && <p className="mt-3 text-xs text-muted">Te van a cobrar {eur(proximos)} en los próximos 30 días (según cuándo se cobró la última vez).</p>}
      {pasadas.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm font-medium text-accent">Ya no se cobran ({pasadas.length})</summary>
          <ul className="mt-1 divide-y divide-line opacity-70">{pasadas.map((x) => <FilaFijo key={x.clave} x={x} />)}</ul>
        </details>
      )}
      {ocultas.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm font-medium text-muted">Ocultas ({ocultas.length})</summary>
          <p className="mt-1 text-xs text-muted">Cargos que marcaste como «no es un fijo»: cuentan como gasto variable.</p>
          <ul className="mt-1 divide-y divide-line opacity-70">{ocultas.map((x) => <FilaFijo key={x.clave} x={x} />)}</ul>
        </details>
      )}
    </Tarjeta>
  )
}

function FilaFijo({ x }: { x: Suscripcion }) {
  const ocultar = useAccion((ignorada: boolean) => api.put(`/gastos/suscripciones/${encodeURIComponent(x.clave)}`, { ignorada }),
    x.ignorada ? `${x.nombre} vuelve a contar como fijo` : `${x.nombre} oculto: sus cargos cuentan como variable`)
  const detalle = [
    x.activa ? (x.proximo ? `Próximo ${fecha(x.proximo, { day: 'numeric', month: 'short' })}` : null) : `Último ${fecha(x.ultimo_cargo, { day: 'numeric', month: 'short', year: '2-digit' })}`,
    x.cuentas.length === 1 ? x.cuentas[0] : `${x.cuentas.length} cuentas`,
  ].filter(Boolean).join(' · ')
  return (
    <li className="flex items-center gap-3 py-2.5">
      <IconoServicio icono={x.icono} color={x.color} nombre={x.nombre} categoria={x.categoria} grupo={x.grupo} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <Link to={enCuentas(x.nombre)} className="truncate text-sm font-medium hover:text-accent" title={`Ver los movimientos de ${x.nombre} (${x.concepto})`}>{x.nombre}</Link>
          {x.subida && x.activa && <Etiqueta tono="aviso"><TrendingUp size={12} />Sube de {eur(x.subida.antes)} a {eur(x.subida.ahora)}</Etiqueta>}
          {x.cobro_doble && x.activa && <Etiqueta tono="mal"><Copy size={12} />Cobrado en dos cuentas el mismo mes</Etiqueta>}
        </div>
        <div className="truncate text-xs text-muted">{x.grupo} · {detalle}</div>
      </div>
      <div className="text-right text-sm">
        <Importe valor={x.periodicidad === 'mensual' ? x.mes : x.importe} />
        <span className="block text-xs text-muted">{CADA[x.periodicidad]}</span>
      </div>
      <Boton variante="fantasma" className="px-2 py-1" disabled={ocultar.isPending} onClick={() => ocultar.mutate(!x.ignorada)}
        aria-label={x.ignorada ? `Volver a contar ${x.nombre} como fijo` : `Ocultar ${x.nombre}: no es un fijo`} title={x.ignorada ? 'Volver a contar como fijo' : 'No es un fijo: ocultar'}>
        {x.ignorada ? <Eye size={15} /> : <EyeOff size={15} />}
      </Boton>
    </li>
  )
}

function MesAMes({ g, mes, onMes }: { g: AnalisisGastos; mes: string | null; onMes: (m: string | null) => void }) {
  if (g.por_mes.length < 2) return null
  const datos = g.por_mes.map((m) => ({ ...m, ahorro: Math.round((m.ingresos - m.gastos - m.aparte) * 100) / 100 }))
  const celdas = (serie: string) => datos.map((m) => <Cell key={`${serie}-${m.mes}`} fillOpacity={mes && m.mes !== mes ? 0.35 : 1} />)
  const elegir = (i: number) => { const k = datos[i]?.mes; if (k) onMes(k === mes ? null : k) }
  return (
    <Tarjeta titulo="Mes a mes" accion={
      <Selector value={mes ?? ''} onChange={(e) => onMes(e.target.value || null)} aria-label="Mes a analizar" className="!w-auto !py-1 !text-xs">
        <option value="">Todos los meses</option>
        {datos.map((m) => <option key={m.mes} value={m.mes}>{nombreMes(m.mes)}</option>)}
      </Selector>}>
      <div className="h-56 [&_.recharts-bar-rectangle]:cursor-pointer">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={datos} margin={{ top: 8, right: 4, left: 4, bottom: 0 }} barGap={3}>
            <CartesianGrid vertical={false} stroke="var(--line)" />
            <XAxis dataKey="mes" tickFormatter={mesCorto} {...eje} />
            <YAxis tickFormatter={eurK} {...eje} width={68} />
            <Tooltip {...estiloTooltip} cursor={cursorBarra} formatter={(v, n) => [eur(Number(v)), SERIE[String(n)] ?? String(n)]} labelFormatter={(v) => nombreMes(String(v))} />
            <Bar dataKey="ingresos" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={22} onClick={(_, i) => elegir(i)}>{celdas('ingresos')}</Bar>
            <Bar dataKey="gastos" fill="var(--chart-3)" radius={[4, 4, 0, 0]} maxBarSize={22} onClick={(_, i) => elegir(i)}>{celdas('gastos')}</Bar>
            <Bar dataKey="aparte" fill="var(--chart-4)" radius={[4, 4, 0, 0]} maxBarSize={22} onClick={(_, i) => elegir(i)}>{celdas('aparte')}</Bar>
            <Line type="monotone" dataKey="ahorro" stroke="var(--ink)" strokeWidth={2} dot={{ r: 3 }} strokeDasharray="5 3" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-[var(--chart-1)]" />Entra</span>
        <span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-[var(--chart-3)]" />Gastas</span>
        <span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-[var(--chart-4)]" />Aparte (impuestos y pagos previstos)</span>
        <span className="flex items-center gap-1.5"><i className="h-0.5 w-3 border-t-2 border-dashed border-ink" />Ahorro (entra − gastas − aparte)</span>
        <span>Toca un mes para analizarlo solo.</span>
      </div>
    </Tarjeta>
  )
}

function Categorias({ g, presupuestos }: { g: AnalisisGastos; presupuestos: Presupuestos }) {
  const max = Math.max(1, ...g.categorias.map((c) => c.mes))
  return (
    <Tarjeta className="lg:col-span-2" titulo="En qué se va" accion={<span className="text-xs text-muted">{g.mes ? 'En ese mes' : 'Media al mes'}</span>}>
      {g.categorias.length ? (
        <ul className="space-y-1">
          {g.categorias.map((c) => {
            const limite = presupuestos[c.categoria]
            const llevas = g.este_mes.por_categoria[c.categoria] ?? 0
            return (
              <li key={c.categoria}>
                <details className="group rounded-xl px-2 py-1.5 open:bg-panel-2/60">
                  <summary className="cursor-pointer list-none">
                    <div className="mb-1 flex items-center justify-between gap-2 text-sm">
                      <span className="truncate">{c.categoria} <span className="text-xs text-muted">· {pct(c.peso, 1)}</span></span>
                      <span className="flex items-center gap-2">
                        {c.cambio !== null && Math.abs(c.cambio) >= 10 && (
                          <span className={`flex items-center text-xs ${c.cambio > 0 ? 'text-neg' : 'text-pos'}`} title={`Antes: ${eur(c.mes_antes)} al mes`}>
                            {c.cambio > 0 ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}{pct(Math.abs(c.cambio), 1)}
                          </span>)}
                        <Importe valor={c.mes} />
                      </span>
                    </div>
                    {limite ? <>
                      <BarraTono fina valor={llevas} max={limite} tono={llevas > limite ? 'neg' : llevas > limite * 0.9 ? 'aviso' : 'acento'} etiqueta={`Presupuesto de ${c.categoria}`} />
                      <div className={`mt-1 text-xs ${llevas > limite ? 'text-neg' : 'text-muted'}`}>{eur(llevas)} de {eur(limite)} este mes{llevas > limite ? ': te has pasado' : ''}</div>
                    </> : <BarraTono fina valor={c.mes} max={max} etiqueta={`${c.categoria}: peso sobre la categoría mayor`} />}
                  </summary>
                  <ul className="mt-2 space-y-1 text-xs">
                    {c.sitios.map((x) => (
                      <li key={x.nombre} className="flex justify-between gap-2">
                        <Link to={enCuentas(x.nombre)} className="truncate text-muted hover:text-accent">{x.nombre} · {x.veces} {x.veces === 1 ? 'vez' : 'veces'}</Link><Importe valor={x.total} />
                      </li>
                    ))}
                  </ul>
                </details>
              </li>
            )
          })}
        </ul>
      ) : <Vacio>Sincroniza el banco para ver en qué se va el dinero.</Vacio>}
      {g.categorias.length > 0 && <p className="mt-3 text-xs text-muted">
        Toca una categoría para ver dónde gastas en ella. Las flechas comparan con {periodoComparado(g)}.
        {Object.keys(presupuestos).length > 0 && ' Las barras de las categorías con presupuesto son lo gastado este mes.'}
      </p>}
    </Tarjeta>
  )
}

function Sitios({ g }: { g: AnalisisGastos }) {
  return (
    <Tarjeta titulo="Dónde más gastas">
      {g.sitios.length ? (
        <ul className="divide-y divide-line">
          {g.sitios.map((x) => (
            <li key={x.nombre} className="flex items-center gap-3 py-2">
              <IconoServicio icono={x.icono} color={x.color} nombre={x.nombre} categoria={x.categoria} sitio tamano={30} />
              <span className="min-w-0 flex-1"><Link to={enCuentas(x.nombre)} className="block truncate text-sm hover:text-accent">{x.nombre}</Link>
                <span className="text-xs text-muted">{x.veces} {x.veces === 1 ? 'vez' : 'veces'} · {eur(x.mes)}/mes</span></span>
              <Importe valor={x.total} className="text-sm" />
            </li>
          ))}
        </ul>
      ) : <Vacio>Todavía no hay gastos en este periodo.</Vacio>}
    </Tarjeta>
  )
}

function Mayores({ g }: { g: AnalisisGastos }) {
  if (!g.mayores.length) return null
  return (
    <Tarjeta titulo="Los gastos más grandes" accion={<span className="text-xs text-muted">Sin recibos ni suscripciones</span>}>
      <Tabla>
        <thead><tr><th>Fecha</th><th>Concepto</th><th className="hidden sm:table-cell">Categoría</th><th className="num">Importe</th></tr></thead>
        <tbody>
          {g.mayores.map((m, i) => (
            <tr key={i}>
              <td className="cifra whitespace-nowrap text-muted">{fecha(m.fecha, { day: 'numeric', month: 'short' })}</td>
              <td className="max-w-[16rem] truncate"><Link to={enCuentas(m.concepto)} className="hover:text-accent" title={m.concepto}>{m.nombre}</Link></td>
              <td className="hidden text-muted sm:table-cell">{m.categoria ?? SIN_CATEGORIA}</td>
              <td className="num"><Importe valor={m.importe} /></td>
            </tr>
          ))}
        </tbody>
      </Tabla>
    </Tarjeta>
  )
}

/** Un campo por categoría de gasto; vacío = sin presupuesto. Sustituye todos los presupuestos al guardar. */
function FormPresupuestos({ g, presupuestos, onCerrar }: { g: AnalisisGastos; presupuestos: Presupuestos; onCerrar: () => void }) {
  const { data: categorias } = useQuery({ queryKey: ['categorias'], queryFn: () => api.get<Categoria[]>('/categorias') })
  const nombres = [...new Set([
    ...(categorias ?? []).filter((c) => c.tipo === 'gasto').map((c) => c.nombre),
    ...g.categorias.map((c) => c.categoria), ...Object.keys(presupuestos),
  ])].filter((n) => n !== SIN_CATEGORIA && n !== 'Impuestos').sort((a, b) => a.localeCompare(b, 'es'))
  const media = Object.fromEntries(g.categorias.map((c) => [c.categoria, c.mes]))
  const guardar = useAccion((v: Record<string, string>) => api.put('/gastos/presupuestos',
    Object.fromEntries(nombres.map((n) => [n, num(v[n]) ?? null]))).then(onCerrar), 'Presupuestos guardados')
  return (
    <>
      <p className="mb-4 text-sm text-muted">Cuánto quieres gastar al mes en cada categoría. Déjalo vacío donde no quieras presupuesto; como pista, la media del periodo.</p>
      <Formulario onEnviar={(v) => guardar.mutateAsync(v)}>
        {nombres.map((n) => (
          <Campo key={n} etiqueta={n} name={n} inputMode="decimal" placeholder="Sin presupuesto"
            defaultValue={presupuestos[n] != null ? String(presupuestos[n]) : ''} ayuda={media[n] != null ? `Media: ${eur(media[n])}` : undefined} />
        ))}
      </Formulario>
    </>
  )
}
