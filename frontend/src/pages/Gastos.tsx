import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ArrowDownRight, ArrowUpRight, Copy, TrendingUp } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../lib/api'
import { eur, eurK, fecha, mesCorto } from '../lib/format'
import type { AnalisisGastos, Suscripcion } from '../lib/tipos'
import IconoServicio from '../components/IconoServicio'
import { Cabecera, Cargando, Dato, ErrorCarga, Etiqueta, Importe, Tabla, Tarjeta, Vacio } from '../components/ui'

const PERIODOS = [3, 6, 12] as const
const CADA: Record<Suscripcion['periodicidad'], string> = { mensual: 'al mes', trimestral: 'cada 3 meses', semestral: 'cada 6 meses', anual: 'al año' }
const pct = (v: number) => `${String(Math.abs(v)).replace('.', ',')} %`

export default function Gastos() {
  const [meses, setMeses] = useState<number>(6)
  const { data: g, isLoading, error, isFetching } = useQuery({
    queryKey: ['gastos', meses], queryFn: () => api.get<AnalisisGastos>(`/gastos?meses=${meses}`), placeholderData: keepPreviousData,
  })

  const selector = (
    <div className="flex rounded-xl border border-line bg-panel p-0.5 text-sm" role="group" aria-label="Periodo">
      {PERIODOS.map((m) => (
        <button key={m} onClick={() => setMeses(m)} aria-pressed={meses === m}
          className={`cursor-pointer rounded-lg px-3 py-1.5 font-medium transition ${meses === m ? 'bg-accent text-panel' : 'text-muted hover:text-ink'}`}>
          {m} meses
        </button>
      ))}
    </div>
  )

  return (
    <>
      <Cabecera titulo="Gastos" subtitulo={g ? `Del ${fecha(g.desde, { day: 'numeric', month: 'short', year: 'numeric' })} al ${fecha(g.hasta, { day: 'numeric', month: 'short', year: 'numeric' })}, meses completos` : undefined}>
        {selector}
      </Cabecera>
      {isLoading ? <Cargando /> : error ? <ErrorCarga error={error} /> : g && (
        <div className={`space-y-4 transition-opacity ${isFetching ? 'opacity-60' : ''}`}>
          <Resumen g={g} />
          <div className="grid gap-4 lg:grid-cols-2">
            <ListaFijos titulo="Suscripciones" lista={g.suscripciones} total={g.suscripciones_mes}
              vacio="Aquí saldrán Netflix, Spotify, el gimnasio, las apps… en cuanto se cobren en tus cuentas." />
            <ListaFijos titulo="Recibos fijos" lista={g.recibos} total={g.recibos_mes}
              vacio="Aquí saldrán la luz, el teléfono, los seguros, la hipoteca… los cargos que se repiten cada mes." />
          </div>
          <MesAMes g={g} />
          <div className="grid gap-4 lg:grid-cols-3">
            <Categorias g={g} />
            <Sitios g={g} />
          </div>
          <Mayores g={g} />
          <p className="text-xs text-muted">
            Sin traspasos entre tus cuentas, sin aportaciones a Indexa y sin la cuenta que no es tuya; de las compartidas solo cuenta tu parte.
            {g.aparte.total > 0 && ` Van aparte, y no suman aquí, ${eur(g.aparte.total)} de impuestos y pagos previstos (plazos de la casa, llamadas de capital…).`}
          </p>
        </div>
      )}
    </>
  )
}

function Resumen({ g }: { g: AnalisisGastos }) {
  const cambio = g.gastos_mes_antes ? Math.round(((g.gastos_mes - g.gastos_mes_antes) / g.gastos_mes_antes) * 1000) / 10 : null
  return (
    <Tarjeta>
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <Dato etiqueta="Gastas al mes" valor={eur(g.gastos_mes)}
          nota={cambio !== null ? <span className={cambio > 0 ? 'text-neg' : 'text-pos'}>{cambio > 0 ? '▲' : '▼'} {pct(cambio)} que los {g.meses} meses anteriores</span> : 'De media'} />
        <Dato etiqueta="Entra al mes" valor={eur(g.ingresos_mes)} nota="De media" />
        <Dato etiqueta="Ahorras al mes" valor={eur(g.ahorro_mes)} tono={g.ahorro_mes >= 0 ? 'pos' : 'neg'}
          nota={g.tasa_ahorro !== null ? `${pct(g.tasa_ahorro)} de lo que entra` : undefined} />
        <Dato etiqueta="Fijo al mes" valor={eur(g.fijo_mes)}
          nota={`Suscripciones y recibos; el resto, ${eur(g.variable_mes)}, es variable`} />
      </div>
      {g.gastos_mes > 0 && (
        <div className="mt-5">
          <div className="flex h-2.5 overflow-hidden rounded-full bg-panel-2">
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
    </Tarjeta>
  )
}

function ListaFijos({ titulo, lista, total, vacio }: { titulo: string; lista: Suscripcion[]; total: number; vacio: string }) {
  const activas = lista.filter((x) => x.activa)
  const pasadas = lista.filter((x) => !x.activa)
  return (
    <Tarjeta titulo={titulo} accion={activas.length > 0 && (
      <span className="text-right text-sm"><span className="cifra font-semibold">{eur(total)}</span><span className="text-muted">/mes</span>
        <span className="block text-xs text-muted">{eur(total * 12)} al año</span></span>)}>
      {activas.length ? <ul className="divide-y divide-line">{activas.map((x) => <FilaFijo key={x.clave} x={x} />)}</ul> : <Vacio>{vacio}</Vacio>}
      {pasadas.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm font-medium text-accent">Ya no se cobran ({pasadas.length})</summary>
          <ul className="mt-1 divide-y divide-line opacity-70">{pasadas.map((x) => <FilaFijo key={x.clave} x={x} />)}</ul>
        </details>
      )}
    </Tarjeta>
  )
}

function FilaFijo({ x }: { x: Suscripcion }) {
  const detalle = [
    x.activa ? (x.proximo ? `Próximo ${fecha(x.proximo, { day: 'numeric', month: 'short' })}` : null) : `Último ${fecha(x.ultimo_cargo, { day: 'numeric', month: 'short', year: '2-digit' })}`,
    x.cuentas.length === 1 ? x.cuentas[0] : `${x.cuentas.length} cuentas`,
  ].filter(Boolean).join(' · ')
  return (
    <li className="flex items-center gap-3 py-2.5">
      <IconoServicio icono={x.icono} color={x.color} nombre={x.nombre} categoria={x.categoria} grupo={x.grupo} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="truncate text-sm font-medium" title={x.concepto}>{x.nombre}</span>
          {x.subida && x.activa && <Etiqueta tono="aviso"><TrendingUp size={12} />Sube de {eur(x.subida.antes)} a {eur(x.subida.ahora)}</Etiqueta>}
          {x.cobro_doble && x.activa && <Etiqueta tono="mal"><Copy size={12} />Cobrado en dos cuentas el mismo mes</Etiqueta>}
        </div>
        <div className="truncate text-xs text-muted">{x.grupo} · {detalle}</div>
      </div>
      <div className="text-right text-sm">
        <Importe valor={x.periodicidad === 'mensual' ? x.mes : x.importe} />
        <span className="block text-xs text-muted">{CADA[x.periodicidad]}</span>
      </div>
    </li>
  )
}

function MesAMes({ g }: { g: AnalisisGastos }) {
  if (g.por_mes.length < 2) return null
  return (
    <Tarjeta titulo="Mes a mes"
      accion={<span className="flex gap-3 text-xs text-muted"><span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-[var(--chart-1)]" />Entra</span><span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-[var(--chart-3)]" />Gastas</span></span>}>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={g.por_mes} margin={{ top: 8, right: 4, left: 4, bottom: 0 }} barGap={3}>
            <CartesianGrid vertical={false} stroke="var(--line)" />
            <XAxis dataKey="mes" tickFormatter={mesCorto} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tickFormatter={eurK} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} width={68} />
            <Tooltip contentStyle={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, fontSize: 12 }}
              cursor={{ fill: 'var(--panel-2)' }} formatter={(v, n) => [eur(Number(v)), n === 'ingresos' ? 'Entra' : 'Gastas']} labelFormatter={(v) => mesCorto(String(v))} />
            <Bar dataKey="ingresos" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={22} />
            <Bar dataKey="gastos" fill="var(--chart-3)" radius={[4, 4, 0, 0]} maxBarSize={22} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Tarjeta>
  )
}

function Categorias({ g }: { g: AnalisisGastos }) {
  const max = Math.max(1, ...g.categorias.map((c) => c.mes))
  return (
    <Tarjeta className="lg:col-span-2" titulo="En qué se va" accion={<span className="text-xs text-muted">Media al mes</span>}>
      {g.categorias.length ? (
        <ul className="space-y-1">
          {g.categorias.map((c) => (
            <li key={c.categoria}>
              <details className="group rounded-xl px-2 py-1.5 open:bg-panel-2/60">
                <summary className="cursor-pointer list-none">
                  <div className="mb-1 flex items-center justify-between gap-2 text-sm">
                    <span className="truncate">{c.categoria} <span className="text-xs text-muted">· {String(c.peso).replace('.', ',')} %</span></span>
                    <span className="flex items-center gap-2">
                      {c.cambio !== null && Math.abs(c.cambio) >= 10 && (
                        <span className={`flex items-center text-xs ${c.cambio > 0 ? 'text-neg' : 'text-pos'}`} title={`Antes: ${eur(c.mes_antes)} al mes`}>
                          {c.cambio > 0 ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}{pct(c.cambio)}
                        </span>)}
                      <Importe valor={c.mes} />
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-panel-2"><div className="h-full rounded-full bg-accent" style={{ width: `${(c.mes / max) * 100}%` }} /></div>
                </summary>
                <ul className="mt-2 space-y-1 text-xs">
                  {c.sitios.map((x) => (
                    <li key={x.nombre} className="flex justify-between gap-2"><span className="truncate text-muted">{x.nombre} · {x.veces} {x.veces === 1 ? 'vez' : 'veces'}</span><Importe valor={x.total} /></li>
                  ))}
                </ul>
              </details>
            </li>
          ))}
        </ul>
      ) : <Vacio>Sincroniza el banco para ver en qué se va el dinero.</Vacio>}
      {g.categorias.length > 0 && <p className="mt-3 text-xs text-muted">Toca una categoría para ver dónde gastas en ella. Las flechas comparan con los {g.meses} meses anteriores.</p>}
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
              <span className="min-w-0 flex-1"><span className="block truncate text-sm">{x.nombre}</span>
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
              <td className="max-w-[16rem] truncate" title={m.concepto}>{m.nombre}</td>
              <td className="hidden text-muted sm:table-cell">{m.categoria ?? 'Sin categoría'}</td>
              <td className="num"><Importe valor={m.importe} /></td>
            </tr>
          ))}
        </tbody>
      </Tabla>
    </Tarjeta>
  )
}
