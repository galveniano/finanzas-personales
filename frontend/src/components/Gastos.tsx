import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { eur, eurK, fecha, mesCorto } from '../lib/format'
import type { GastosRecientes, Resumen } from '../lib/tipos'
import { Dato, Importe, Tarjeta, Vacio } from './ui'

export default function ComoGastas({ g }: { g: GastosRecientes }) {
  const max = Math.max(1, ...g.categorias.map((c) => c.mes))
  return (
    <div className="mt-6 grid gap-4 lg:grid-cols-3">
      <Tarjeta className="lg:col-span-2" titulo={`Cómo gastas · media de los últimos ${g.meses} meses`}>
        <div className="mb-5 grid gap-6 sm:grid-cols-3">
          <Dato etiqueta="Entra al mes" valor={eur(g.ingresos_mes)} />
          <Dato etiqueta="Sale al mes" valor={eur(g.gastos_mes)} />
          <Dato etiqueta="Ahorras al mes" valor={eur(g.ahorro_mes)} tono={g.ahorro_mes >= 0 ? 'pos' : 'neg'}
            nota={g.tasa_ahorro !== null ? `${String(g.tasa_ahorro).replace('.', ',')} % de lo que entra` : undefined} />
        </div>
        {g.categorias.length ? (
          <ul className="space-y-2.5">
            {g.categorias.map((c) => (
              <li key={c.categoria}>
                <div className="mb-1 flex justify-between gap-2 text-sm"><span className="truncate">{c.categoria}</span><Importe valor={c.mes} /></div>
                <div className="h-1.5 rounded-full bg-panel-2"><div className="h-full rounded-full bg-accent" style={{ width: `${(c.mes / max) * 100}%` }} /></div>
              </li>
            ))}
          </ul>
        ) : <Vacio>Sincroniza el banco para ver en qué se va el dinero.</Vacio>}
        <p className="mt-3 text-xs text-muted">Sin traspasos entre tus cuentas ni aportaciones a Indexa; solo tu parte de las cuentas compartidas.</p>
      </Tarjeta>
      <Tarjeta titulo="Suscripciones y recibos fijos" accion={<span className="cifra text-sm font-semibold">{eur(g.suscripciones_mes)}/mes</span>}>
        {g.suscripciones.length ? (
          <ul className="divide-y divide-line">
            {g.suscripciones.map((x) => (
              <li key={x.concepto} className="flex items-center justify-between gap-3 py-2 text-sm">
                <span className="min-w-0"><span className="block truncate">{x.concepto}</span>
                  <span className="text-xs text-muted">{eur(x.anual)} al año · último {fecha(x.ultimo_cargo, { day: 'numeric', month: 'short' })}</span></span>
                <Importe valor={x.mes} />
              </li>
            ))}
          </ul>
        ) : <Vacio>Aparecerán los cargos que se repiten cada mes (Netflix, gimnasio, seguros…).</Vacio>}
      </Tarjeta>
    </div>
  )
}


/** Ingresos y gastos de cada mes según el banco. */
export function FlujoMensual({ flujo }: { flujo: Resumen['flujo_mensual'] }) {
  if (flujo.length < 2) return null
  return (
    <Tarjeta className="mt-4" titulo="Ingresos y gastos por mes"
      accion={<span className="flex gap-3 text-xs text-muted"><span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-[var(--chart-1)]" />Ingresos</span><span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-[var(--chart-3)]" />Gastos</span></span>}>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={flujo} margin={{ top: 8, right: 4, left: 4, bottom: 0 }} barGap={3}>
            <CartesianGrid vertical={false} stroke="var(--line)" />
            <XAxis dataKey="mes" tickFormatter={mesCorto} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tickFormatter={eurK} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} width={68} />
            <Tooltip contentStyle={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, fontSize: 12 }}
              cursor={{ fill: 'var(--panel-2)' }} formatter={(v, n) => [eur(Number(v)), n === 'ingresos' ? 'Ingresos' : 'Gastos']} labelFormatter={(v) => mesCorto(String(v))} />
            <Bar dataKey="ingresos" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={22} />
            <Bar dataKey="gastos" fill="var(--chart-3)" radius={[4, 4, 0, 0]} maxBarSize={22} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Tarjeta>
  )
}
