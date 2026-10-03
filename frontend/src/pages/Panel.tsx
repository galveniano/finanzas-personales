import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../lib/api'
import { diasHasta, eur, eurK, fecha, mesCorto } from '../lib/format'
import type { Resumen } from '../lib/tipos'
import { Cabecera, Cargando, Dato, Etiqueta, ErrorCarga, Importe, Tarjeta, Vacio } from '../components/ui'

const COLORES: Record<string, string> = {
  Liquidez: 'var(--chart-2)', Inversiones: 'var(--chart-1)', Inmuebles: 'var(--chart-3)', Otros: 'var(--chart-4)',
}

const estiloTooltip = {
  contentStyle: { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, fontSize: 12, color: 'var(--ink)' },
  labelStyle: { color: 'var(--muted)' },
}

function Composicion({ r }: { r: Resumen }) {
  const total = r.activos || 1
  return (
    <div className="space-y-4">
      <div className="flex h-3 overflow-hidden rounded-full bg-panel-2">
        {r.grupos.filter((g) => g.importe > 0).map((g) => (
          <div key={g.grupo} style={{ width: `${(g.importe / total) * 100}%`, background: COLORES[g.grupo] ?? 'var(--chart-5)' }} title={g.grupo} />
        ))}
      </div>
      <ul className="space-y-2.5">
        {r.grupos.map((g) => (
          <li key={g.grupo} className="flex items-center justify-between gap-3 text-sm">
            <span className="flex items-center gap-2">
              <span className="size-2.5 rounded-sm" style={{ background: COLORES[g.grupo] ?? 'var(--chart-5)' }} />
              {g.grupo}
            </span>
            <span className="flex items-baseline gap-3">
              <span className="cifra text-xs text-muted">{Math.round((g.importe / total) * 100)} %</span>
              <Importe valor={g.importe} />
            </span>
          </li>
        ))}
        {r.pasivos > 0 && (
          <li className="flex items-center justify-between gap-3 border-t border-line pt-2.5 text-sm">
            <span className="text-muted">Deudas</span>
            <Importe valor={-r.pasivos} className="text-neg" />
          </li>
        )}
      </ul>
    </div>
  )
}

function Evolucion({ r }: { r: Resumen }) {
  if (r.historico.length < 2) {
    return <Vacio>La evolución aparecerá a partir de mañana: la app guarda una foto de tu patrimonio cada día que sincroniza.</Vacio>
  }
  return (
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={r.historico} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
          <defs>
            <linearGradient id="neto" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.28} />
              <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="var(--line)" />
          <XAxis dataKey="fecha" tickFormatter={(v) => fecha(v, { day: '2-digit', month: 'short' })} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={40} />
          <YAxis tickFormatter={eurK} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} width={76} domain={['auto', 'auto']} />
          <Tooltip {...estiloTooltip} formatter={(v) => [eur(Number(v)), 'Patrimonio neto']} labelFormatter={(v) => fecha(String(v))} />
          <Area type="monotone" dataKey="neto" stroke="var(--chart-1)" strokeWidth={2} fill="url(#neto)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function Flujo({ r }: { r: Resumen }) {
  if (!r.flujo_mensual.length) return <Vacio>Importa o sincroniza movimientos para ver tus ingresos y gastos por mes.</Vacio>
  return (
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={r.flujo_mensual} margin={{ top: 8, right: 4, left: 4, bottom: 0 }} barGap={3}>
          <CartesianGrid vertical={false} stroke="var(--line)" />
          <XAxis dataKey="mes" tickFormatter={mesCorto} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis tickFormatter={eurK} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} width={68} />
          <Tooltip {...estiloTooltip} cursor={{ fill: 'var(--panel-2)' }} formatter={(v, n) => [eur(Number(v)), n === 'ingresos' ? 'Ingresos' : 'Gastos']} labelFormatter={(v) => mesCorto(String(v))} />
          <Bar dataKey="ingresos" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={22} />
          <Bar dataKey="gastos" fill="var(--chart-3)" radius={[4, 4, 0, 0]} maxBarSize={22} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function Panel() {
  const { data: r, isLoading, error } = useQuery({ queryKey: ['resumen'], queryFn: () => api.get<Resumen>('/resumen') })
  if (isLoading) return <Cargando />
  if (error) return <ErrorCarga error={error} />
  if (!r) return null
  const maxCat = Math.max(1, ...r.gasto_categorias.map((c) => c.importe))
  const { iva, irpf, trimestre } = r.fiscal

  return (
    <>
      <Cabecera titulo="Panel" subtitulo={`Situación a ${fecha(r.fecha, { day: 'numeric', month: 'long', year: 'numeric' })}`} />

      <div className="grid gap-4 lg:grid-cols-3">
        <Tarjeta className="lg:col-span-2" titulo="Patrimonio neto">
          <div className="mb-5 flex flex-wrap gap-x-10 gap-y-4">
            <Dato etiqueta="Neto" valor={eur(r.neto)} />
            <Dato etiqueta="Tienes" valor={eur(r.activos)} />
            <Dato etiqueta="Debes" valor={eur(r.pasivos)} />
          </div>
          <Evolucion r={r} />
        </Tarjeta>
        <Tarjeta titulo="En qué está">
          <Composicion r={r} />
        </Tarjeta>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Tarjeta titulo={`IVA ${trimestre}T · modelo 303`} accion={<Etiqueta tono="aviso">{iva.plazo}</Etiqueta>}>
          <Dato etiqueta={iva.resultado >= 0 ? 'A ingresar' : 'A compensar'} valor={eur(iva.resultado)} />
          <p className="mt-3 text-sm text-muted">{iva.presentado ? 'Ya presentado en Hacienda.' : `Estimado: repercutido ${eur(iva.repercutido)} menos soportado ${eur(iva.soportado)}.`}</p>
        </Tarjeta>
        <Tarjeta titulo={`IRPF ${trimestre}T · modelo 130`} accion={<Etiqueta tono={irpf.exento ? 'bien' : 'aviso'}>{irpf.exento ? 'Exento' : irpf.plazo}</Etiqueta>}>
          <Dato etiqueta="A ingresar" valor={irpf.exento ? 'No presentas' : eur(irpf.resultado)} />
          {irpf.notas.map((n) => <p key={n} className="mt-3 text-sm text-muted">{n}</p>)}
        </Tarjeta>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Tarjeta className="lg:col-span-2" titulo="Ingresos y gastos por mes"
          accion={<span className="flex gap-3 text-xs text-muted"><span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-[var(--chart-1)]" />Ingresos</span><span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-[var(--chart-3)]" />Gastos</span></span>}>
          <Flujo r={r} />
        </Tarjeta>
        <Tarjeta titulo="Gasto últimos 30 días" accion={<Link to="/cuentas" className="text-xs font-medium text-accent">Ver movimientos</Link>}>
          {r.gasto_categorias.length ? (
            <ul className="space-y-3">
              {r.gasto_categorias.slice(0, 7).map((c) => (
                <li key={c.categoria}>
                  <div className="mb-1 flex justify-between gap-2 text-sm"><span className="truncate">{c.categoria}</span><Importe valor={c.importe} /></div>
                  <div className="h-1.5 rounded-full bg-panel-2"><div className="h-full rounded-full bg-[var(--chart-3)]" style={{ width: `${(c.importe / maxCat) * 100}%` }} /></div>
                </li>
              ))}
            </ul>
          ) : <Vacio>Sin gastos en los últimos 30 días.</Vacio>}
        </Tarjeta>
      </div>

      <Tarjeta className="mt-4" titulo="Próximos pagos" accion={<Link to="/planificacion" className="text-xs font-medium text-accent">Planificación</Link>}>
        {r.proximos_pagos.length ? (
          <ul className="divide-y divide-line">
            {r.proximos_pagos.map((p) => {
              const dias = diasHasta(p.fecha)
              return (
                <li key={p.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{p.concepto}</div>
                    <div className="text-xs text-muted">{fecha(p.fecha, { day: 'numeric', month: 'long', year: 'numeric' })}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Etiqueta tono={dias < 0 ? 'mal' : dias <= 30 ? 'aviso' : 'neutro'}>{dias < 0 ? 'Vencido' : dias === 0 ? 'Hoy' : `En ${dias} días`}</Etiqueta>
                    <Importe valor={p.importe} />
                  </div>
                </li>
              )
            })}
          </ul>
        ) : <Vacio>No hay pagos previstos.</Vacio>}
      </Tarjeta>
    </>
  )
}
