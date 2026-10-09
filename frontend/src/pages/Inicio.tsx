import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../lib/api'
import { cuandoVence, diasHasta, eur, eurK, fecha } from '../lib/format'
import { eje, estiloTooltip } from '../lib/graficas'
import type { Aviso, Resumen } from '../lib/tipos'
import { Cabecera, Cargando, Dato, ErrorCarga, Importe, Tarjeta } from '../components/ui'

const COLORES: Record<string, string> = {
  Liquidez: 'var(--chart-2)', Inversiones: 'var(--chart-1)', Inmuebles: 'var(--chart-3)', Otros: 'var(--chart-4)',
  'Vehículos': 'var(--chart-5)',
}

const NIVEL: Record<Aviso['nivel'], string> = {
  error: 'border-neg/40 bg-neg/10 text-neg', aviso: 'border-warn/40 bg-warn-soft text-warn', info: 'border-line bg-panel text-ink',
}

function Avisos({ avisos }: { avisos: Aviso[] }) {
  const [todos, setTodos] = useState(false)
  if (!avisos.length) return null
  const visibles = todos ? avisos : avisos.slice(0, 3)
  return (
    <ul className="mb-4 grid gap-2" aria-label="Avisos">
      {visibles.map((a, i) => (
        <li key={i} className={`flex items-start justify-between gap-3 rounded-xl border px-4 py-2.5 text-sm ${NIVEL[a.nivel]}`}>
          <span className="min-w-0">{a.texto}</span>
          <Link to={a.ir} className="shrink-0 text-xs font-medium underline underline-offset-2">Ver</Link>
        </li>
      ))}
      {avisos.length > 3 && (
        <li><button type="button" className="text-xs font-medium text-accent" onClick={() => setTodos(!todos)}>
          {todos ? 'Ver menos' : `Ver los ${avisos.length} avisos`}</button></li>
      )}
    </ul>
  )
}

/** Patrimonio a final de cada año (o hoy, el año en curso) y cuánto ha cambiado. */
function PorAnio({ r }: { r: Resumen }) {
  const ultimos = new Map<string, Resumen['historico'][number]>()
  for (const h of r.historico) ultimos.set(h.fecha.slice(0, 4), h)
  const filas = [...ultimos.entries()]
  if (filas.length < 2) return null
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full text-sm">
        <thead><tr className="text-left text-xs text-muted"><th className="py-1 font-medium">Año</th><th className="num font-medium">Neto</th><th className="num font-medium">Cambio</th></tr></thead>
        <tbody>
          {filas.map(([anio, h], i) => (
            <tr key={anio} className="border-t border-line">
              <td className="py-1.5">{anio}</td>
              <td className="num"><Importe valor={h.neto} /></td>
              <td className="num">{i ? <Importe valor={h.neto - filas[i - 1][1].neto} signo /> : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
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
  if (r.historico.length < 2) return <p className="text-xs text-muted">La evolución aparece a partir de mañana: cada día se guarda una foto de tu patrimonio.</p>
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
          <XAxis dataKey="fecha" tickFormatter={(v) => fecha(v, { day: '2-digit', month: 'short' })} {...eje} minTickGap={40} />
          <YAxis tickFormatter={eurK} {...eje} width={76} domain={['auto', 'auto']} />
          <Tooltip {...estiloTooltip} formatter={(v) => [eur(Number(v)), 'Patrimonio neto']} labelFormatter={(v) => fecha(String(v))} />
          <Area type="monotone" dataKey="neto" stroke="var(--chart-1)" strokeWidth={2} fill="url(#neto)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function Inicio() {
  const { data: r, isLoading, error } = useQuery({ queryKey: ['resumen'], queryFn: () => api.get<Resumen>('/resumen') })
  if (isLoading) return <Cargando />
  if (error) return <ErrorCarga error={error} />
  if (!r) return null
  const { iva, irpf, trimestre, renta } = r.fiscal
  // Un 303 a compensar no se resta del 130: ese saldo se usa en trimestres siguientes
  const hacienda = Math.max(iva.resultado, 0) + (irpf.exento ? 0 : irpf.resultado)

  return (
    <>
      <Cabecera titulo="Inicio" subtitulo={`Situación a ${fecha(r.fecha, { day: 'numeric', month: 'long', year: 'numeric' })}`} />
      <Avisos avisos={r.avisos} />

      <div className="grid gap-4 lg:grid-cols-3">
        <Tarjeta className="lg:col-span-2" titulo="Patrimonio neto">
          <div className="mb-5 flex flex-wrap gap-x-10 gap-y-4">
            <Dato etiqueta="Neto" valor={eur(r.neto)} />
            <Dato etiqueta="Tienes" valor={eur(r.activos)} />
            <Dato etiqueta="Debes" valor={eur(r.pasivos)} />
          </div>
          <Evolucion r={r} />
          <PorAnio r={r} />
        </Tarjeta>
        <Tarjeta titulo="En qué está">
          <Composicion r={r} />
        </Tarjeta>
      </div>

      <Tarjeta className="mt-4" titulo="Disponible de verdad" accion={<Link to="/impuestos" className="text-xs font-medium text-accent">Hucha</Link>}>
        <div className="flex flex-wrap gap-x-10 gap-y-4">
          <Dato etiqueta="En tus cuentas" valor={eur(r.liquidez)} />
          <Dato etiqueta="Debes a Hacienda" valor={eur(r.hacienda_pendiente.total)} />
          <Dato etiqueta="Disponible" valor={eur(r.disponible)} />
        </div>
        {r.hacienda_pendiente.lineas.length > 0 && (
          <p className="mt-3 text-xs text-muted">
            {r.hacienda_pendiente.lineas.map((l) => `${l.concepto} ${eur(l.importe)}`).join(' · ')}. Estimado: el IVA cobrado
            y la renta que se va generando no son tuyos hasta que pagas.
          </p>
        )}
      </Tarjeta>

      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <Tarjeta titulo="Ganas al mes" accion={<Link to="/ingresos" className="text-xs font-medium text-accent">Ingresos</Link>}>
          {renta ? <>
            <Dato etiqueta="Neto" valor={eur(renta.neto_mes)} />
            <p className="mt-3 text-sm text-muted">De {eur(renta.bruto_mes)} brutos con nómina, clientes y alquiler, ya restados Seguridad Social, gastos e IRPF.</p>
          </> : <p className="text-sm text-muted">Pon tu sueldo y tus clientes en <Link to="/ingresos" className="text-accent">Ingresos</Link>.</p>}
        </Tarjeta>
        <Tarjeta titulo="Hacienda" accion={<Link to="/impuestos" className="text-xs font-medium text-accent">Impuestos</Link>}>
          <Dato etiqueta={`${trimestre}T ${r.fiscal.anio} · ${iva.plazo}`} valor={eur(hacienda)} />
          <p className="mt-1 text-xs text-muted">IVA {eur(iva.resultado)} · IRPF {irpf.exento ? 'exento' : eur(irpf.resultado)}{iva.presentado && irpf.presentado ? ' · presentado' : ''}</p>
          {renta && <p className="mt-3 border-t border-line pt-3 text-sm">
            Renta {renta.anio}: {Math.abs(renta.resultado) < 0.005 ? 'sin pagar ni devolver' : <>
              <strong className="cifra">{eur(Math.abs(renta.resultado))}</strong> {renta.resultado > 0 ? `a pagar en junio de ${renta.anio + 1}` : 'a devolver'}</>}</p>}
        </Tarjeta>
        <Tarjeta titulo="Próximos pagos" accion={<Link to="/plan" className="text-xs font-medium text-accent">Plan</Link>}>
          {r.proximos_pagos.length ? (
            <ul className="divide-y divide-line">
              {r.proximos_pagos.slice(0, 3).map((p) => {
                const dias = diasHasta(p.fecha)
                return (
                  <li key={p.id} className="flex items-center justify-between gap-3 py-2 text-sm first:pt-0">
                    <div className="min-w-0">
                      <div className="truncate">{p.concepto}</div>
                      <div className="text-xs text-muted">{cuandoVence(dias)}</div>
                    </div>
                    <Importe valor={p.importe} />
                  </li>
                )
              })}
            </ul>
          ) : <p className="text-sm text-muted">No hay pagos previstos.</p>}
        </Tarjeta>
      </div>
    </>
  )
}
