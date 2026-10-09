import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Briefcase, Building2, ChevronDown, Landmark } from 'lucide-react'
import { api } from '../lib/api'
import { cuandoVence, diasHasta, eur, eurK, fecha } from '../lib/format'
import { eje, estiloTooltip } from '../lib/graficas'
import type { Aviso, GastosResumenInicio, Linea, PuntoHistorico, Resumen } from '../lib/tipos'
import BarraTono from '../components/BarraTono'
import { Cabecera, Cargando, Dato, ErrorCarga, Etiqueta, Importe, Segmentos, Tabla, Tarjeta } from '../components/ui'

const COLORES: Record<string, string> = {
  Liquidez: 'var(--chart-2)', Inversiones: 'var(--chart-1)', Inmuebles: 'var(--chart-3)', Otros: 'var(--chart-4)',
  'Vehículos': 'var(--chart-5)',
}
// Series de la gráfica «Por tipo», en el orden en que se apilan (de abajo arriba)
const TIPOS = [
  { clave: 'liquidez', texto: 'Liquidez', color: 'var(--chart-2)' },
  { clave: 'inversiones', texto: 'Inversiones', color: 'var(--chart-1)' },
  { clave: 'inmuebles', texto: 'Inmuebles', color: 'var(--chart-3)' },
  { clave: 'vehiculos', texto: 'Vehículos', color: 'var(--chart-5)' },
  { clave: 'otros', texto: 'Otros', color: 'var(--chart-4)' },
] as const
const NOMBRE_SERIE: Record<string, string> = { ...Object.fromEntries(TIPOS.map((t) => [t.clave, t.texto])), deudas: 'Deudas', neto: 'Neto' }
const VISTAS = [{ valor: 'neto', texto: 'Neto' }, { valor: 'tipo', texto: 'Por tipo' }] as const
const RANGOS: { valor: number; texto: string }[] = [{ valor: 3, texto: '3 m' }, { valor: 12, texto: '1 a' }, { valor: 0, texto: 'Todo' }]

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

/** Patrimonio a final de cada año (o hoy, el año en curso) y cuánto ha cambiado, en total y por tipo. */
function PorAnio({ historico }: { historico: PuntoHistorico[] }) {
  const ultimos = new Map<string, PuntoHistorico>()
  for (const h of historico) ultimos.set(h.fecha.slice(0, 4), h)
  const filas = [...ultimos.entries()]
  if (filas.length < 2) return null
  const cambio = (i: number, f: (h: PuntoHistorico) => number) => (i ? <Importe valor={f(filas[i][1]) - f(filas[i - 1][1])} signo /> : '—')
  const otros = (h: PuntoHistorico) => (h.vehiculos ?? 0) + h.otros
  return (
    <div className="mt-4">
      <Tabla>
        <thead><tr>
          <th>Año</th><th className="num">Neto</th><th className="num">Cambio</th>
          <th className="num hidden md:table-cell">Liquidez</th><th className="num hidden md:table-cell">Inversiones</th>
          <th className="num hidden md:table-cell">Inmuebles</th><th className="num hidden lg:table-cell">Otros</th><th className="num hidden md:table-cell">Deudas</th>
        </tr></thead>
        <tbody>
          {filas.map(([anio, h], i) => (
            <tr key={anio}>
              <td className="cifra">{anio}</td>
              <td className="num"><Importe valor={h.neto} /></td>
              <td className="num">{cambio(i, (x) => x.neto)}</td>
              <td className="num hidden md:table-cell">{cambio(i, (x) => x.liquidez)}</td>
              <td className="num hidden md:table-cell">{cambio(i, (x) => x.inversiones)}</td>
              <td className="num hidden md:table-cell">{cambio(i, (x) => x.inmuebles)}</td>
              <td className="num hidden lg:table-cell">{cambio(i, otros)}</td>
              <td className="num hidden md:table-cell">{cambio(i, (x) => -x.deudas)}</td>
            </tr>
          ))}
        </tbody>
      </Tabla>
      <p className="mt-2 text-xs text-muted">Cambio de cada año respecto al cierre del anterior; en las deudas, en negativo si has debido más. El año en curso, hasta hoy.</p>
    </div>
  )
}

/** Fecha (AAAA-MM-DD) de hace `meses` meses, para recortar el histórico. */
function hastaHaceMeses(meses: number) {
  const d = new Date()
  d.setMonth(d.getMonth() - meses)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function Evolucion({ historico }: { historico: PuntoHistorico[] }) {
  const [vista, setVista] = useState<'neto' | 'tipo'>('neto')
  const [rango, setRango] = useState<number>(12)
  if (historico.length < 2) return <p className="text-xs text-muted">La evolución aparece a partir de mañana: cada día se guarda una foto de tu patrimonio.</p>
  const corte = rango ? hastaHaceMeses(rango) : ''
  const puntos = historico.filter((h) => h.fecha >= corte).map((h) => ({ ...h, vehiculos: h.vehiculos ?? 0, deudas: -h.deudas }))
  const dias = puntos.length > 1 ? (Date.parse(puntos[puntos.length - 1].fecha) - Date.parse(puntos[0].fecha)) / 86_400_000 : 0
  const tick = (v: string) => fecha(v, dias > 365 ? { month: 'short', year: '2-digit' } : { day: '2-digit', month: 'short' })
  const selectores = (
    <div className="flex flex-wrap gap-2">
      <Segmentos pequeno etiqueta="Qué ver" opciones={VISTAS} valor={vista} onCambiar={setVista} />
      <Segmentos pequeno etiqueta="Periodo" opciones={RANGOS} valor={rango} onCambiar={setRango} />
    </div>
  )
  if (puntos.length < 2) {
    return <>
      {selectores}
      <p className="mt-3 text-xs text-muted">Aún no hay dos fotos en este periodo: elige uno más largo.</p>
    </>
  }
  return (
    <>
      {selectores}
      <div className="mt-3 h-60">
        <ResponsiveContainer width="100%" height="100%">
          {vista === 'neto' ? (
            <AreaChart data={puntos} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
              <defs>
                <linearGradient id="neto" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.28} />
                  <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="var(--line)" />
              <XAxis dataKey="fecha" tickFormatter={tick} {...eje} minTickGap={40} />
              <YAxis tickFormatter={eurK} {...eje} width={76} domain={['auto', 'auto']} />
              <Tooltip {...estiloTooltip} formatter={(v) => [eur(Number(v)), 'Patrimonio neto']} labelFormatter={(v) => fecha(String(v))} />
              <Area type="monotone" dataKey="neto" stroke="var(--chart-1)" strokeWidth={2} fill="url(#neto)" />
            </AreaChart>
          ) : (
            <ComposedChart data={puntos} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--line)" />
              <XAxis dataKey="fecha" tickFormatter={tick} {...eje} minTickGap={40} />
              <YAxis tickFormatter={eurK} {...eje} width={76} domain={['auto', 'auto']} />
              <Tooltip {...estiloTooltip} formatter={(v, n) => [eur(Math.abs(Number(v))), NOMBRE_SERIE[String(n)] ?? String(n)]} labelFormatter={(v) => fecha(String(v))} />
              {TIPOS.map((t) => (
                <Area key={t.clave} type="monotone" dataKey={t.clave} stackId="tienes" stroke={t.color} fill={t.color} fillOpacity={0.55} strokeWidth={1} />
              ))}
              {/* Las deudas, como área por debajo de cero: así el neto es lo que sobresale */}
              <Area type="monotone" dataKey="deudas" stackId="debes" stroke="var(--neg)" fill="var(--neg)" fillOpacity={0.3} strokeWidth={1} />
              <Line type="monotone" dataKey="neto" stroke="var(--ink)" strokeWidth={2} dot={false} strokeDasharray="5 3" />
            </ComposedChart>
          )}
        </ResponsiveContainer>
      </div>
      {vista === 'tipo' && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
          {TIPOS.map((t) => <span key={t.clave} className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm" style={{ background: t.color }} />{t.texto}</span>)}
          <span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-neg/50" />Deudas (bajo cero)</span>
          <span className="flex items-center gap-1.5"><i className="h-0.5 w-3 border-t-2 border-dashed border-ink" />Neto</span>
        </div>
      )}
    </>
  )
}

function LineasGrupo({ lineas }: { lineas: Linea[] }) {
  return (
    <ul className="mt-1 mb-2 space-y-1 pl-4.5 text-xs">
      {lineas.map((l, i) => (
        <li key={i} className="flex items-baseline justify-between gap-3">
          <span className="min-w-0 truncate"><span className="text-ink">{l.nombre}</span>{l.detalle && <span className="text-muted"> · {l.detalle}</span>}</span>
          <Importe valor={l.importe} className="text-xs" />
        </li>
      ))}
    </ul>
  )
}

/** Reparto del patrimonio; cada grupo se despliega para ver qué lo forma. */
function Composicion({ r }: { r: Resumen }) {
  const total = r.activos || 1
  const resumen = r.grupos.filter((g) => g.importe > 0).map((g) => `${g.grupo} ${Math.round((g.importe / total) * 100)} %`).join(', ')
  const grupo = (nombre: string, color: string, importe: number, lineas: Linea[], porcentaje?: number) => (
    <li key={nombre}>
      <details className="group">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 py-1 text-sm">
          <span className="flex min-w-0 items-center gap-2">
            <span className="size-2.5 shrink-0 rounded-sm" style={{ background: color }} />
            <span className="truncate">{nombre}</span>
            <ChevronDown size={14} className="shrink-0 text-muted transition group-open:rotate-180" aria-hidden />
          </span>
          <span className="flex shrink-0 items-baseline gap-3">
            {porcentaje != null && <span className="cifra text-xs text-muted">{porcentaje} %</span>}
            <Importe valor={importe} className={importe < 0 ? 'text-neg' : undefined} />
          </span>
        </summary>
        <LineasGrupo lineas={lineas} />
      </details>
    </li>
  )
  return (
    <div className="space-y-4">
      <div className="flex h-3 overflow-hidden rounded-full bg-panel-2" role="img" aria-label={`Reparto de lo que tienes: ${resumen || 'nada todavía'}`}>
        {r.grupos.filter((g) => g.importe > 0).map((g) => (
          <div key={g.grupo} style={{ width: `${(g.importe / total) * 100}%`, background: COLORES[g.grupo] ?? 'var(--chart-5)' }} title={g.grupo} />
        ))}
      </div>
      <ul className="space-y-1.5">
        {r.grupos.map((g) => grupo(g.grupo, COLORES[g.grupo] ?? 'var(--chart-5)', g.importe,
          r.lineas_activo.filter((l) => l.grupo === g.grupo), Math.round((g.importe / total) * 100)))}
        {r.pasivos > 0 && (
          <li className="border-t border-line pt-1.5">
            <ul>{grupo('Deudas', 'var(--neg)', -r.pasivos, r.lineas_pasivo)}</ul>
          </li>
        )}
      </ul>
      <p className="text-xs text-muted">Toca un grupo para ver qué lo forma y de cuándo es cada valoración.</p>
    </div>
  )
}

function Paso({ n, icono: Icono, titulo, texto, a, enlace }: { n: number; icono: typeof Landmark; titulo: string; texto: string; a: string; enlace: string }) {
  return (
    <li className="flex gap-4 rounded-2xl border border-line bg-panel p-5">
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent" aria-hidden><Icono size={20} /></span>
      <div className="min-w-0">
        <div className="text-xs font-medium uppercase tracking-wider text-muted">Paso {n}</div>
        <div className="mt-0.5 font-semibold">{titulo}</div>
        <p className="mt-1 text-sm text-muted">{texto}</p>
        <Link to={a} className="mt-2 inline-block text-sm font-medium text-accent">{enlace} →</Link>
      </div>
    </li>
  )
}

/** Sin cuentas ni bienes todavía: en vez de ceros, los tres pasos para empezar. */
function EmpezarAqui() {
  return (
    <Tarjeta titulo="Empieza por aquí">
      <p className="mb-4 text-sm text-muted">Tu patrimonio sale de lo que haya en tus cuentas y de los bienes que registres. Tres pasos y esta pantalla cobra vida.</p>
      <ol className="grid gap-3 md:grid-cols-3">
        <Paso n={1} icono={Landmark} titulo="Conecta el banco" a="/ajustes" enlace="Ir a Ajustes"
          texto="Conecta Sabadell (o importa un extracto en Cuentas) para tener saldos y movimientos al día." />
        <Paso n={2} icono={Briefcase} titulo="Pon tu sueldo y tarifas" a="/ingresos" enlace="Ir a Ingresos"
          texto="Con tu nómina y lo que cobras a cada cliente se estima lo que ganas, los impuestos y la renta." />
        <Paso n={3} icono={Building2} titulo="Crea tus bienes" a="/inmuebles" enlace="Ir a Bienes"
          texto="El piso, la hipoteca, la casa en obra, el coche… lo que tienes y lo que debes por ello." />
      </ol>
    </Tarjeta>
  )
}

function TarjetaHacienda({ r }: { r: Resumen }) {
  const { iva, irpf, trimestre, renta } = r.fiscal
  // Un 303 a compensar no se resta del 130: ese saldo se usa en trimestres siguientes
  const aPagar = Math.max(iva.resultado, 0) + (irpf.exento ? 0 : irpf.resultado)
  const estado = (x: { presentado: boolean; previsto: boolean }) => (x.presentado ? 'presentado' : x.previsto ? 'previsto' : 'estimado')
  const estados = [estado(iva), ...(irpf.exento ? [] : [estado(irpf)])]
  const global = estados.every((e) => e === 'presentado') ? 'presentado' : estados.includes('estimado') ? 'estimado' : 'previsto'
  const ETIQUETA = { presentado: { texto: 'Presentado', tono: 'bien' }, previsto: { texto: 'Previsto', tono: 'acento' }, estimado: { texto: 'Estimado', tono: 'neutro' } } as const
  const detalle = (x: 'iva' | 'irpf') => (estados.every((e) => e === estados[0]) ? '' : ` (${estado(x === 'iva' ? iva : irpf)})`)
  return (
    <Tarjeta titulo="Hacienda" accion={<Link to="/impuestos" className="text-xs font-medium text-accent">Impuestos</Link>}>
      <Dato etiqueta={`${trimestre}T ${r.fiscal.anio} · ${iva.plazo}`} valor={eur(aPagar)} nota={<Etiqueta tono={ETIQUETA[global].tono}>{ETIQUETA[global].texto}</Etiqueta>} />
      <p className="mt-2 text-xs text-muted">
        IVA {iva.resultado < 0 ? `${eur(-iva.resultado)} a compensar` : eur(iva.resultado)}{detalle('iva')} · IRPF {irpf.exento ? 'exento' : eur(irpf.resultado)}{irpf.exento ? '' : detalle('irpf')}.
        {iva.resultado < 0 && ' El IVA a compensar no se resta del 130: se descuenta en trimestres siguientes.'}
      </p>
      {renta && <p className="mt-3 border-t border-line pt-3 text-sm">
        Renta {renta.anio}: {Math.abs(renta.resultado) < 0.005 ? 'sin pagar ni devolver' : <>
          <strong className="cifra">{eur(Math.abs(renta.resultado))}</strong> {renta.resultado > 0 ? `a pagar en junio de ${renta.anio + 1}` : 'a devolver'}</>}</p>}
      <p className="mt-3 text-xs text-muted">Aquí, solo el trimestre que toca. «Debes a Hacienda», arriba, es la estimación acumulada de todo lo pendiente (IVA, 130 y renta).</p>
    </Tarjeta>
  )
}

function TarjetaEsteMes({ g }: { g: GastosResumenInicio }) {
  const sinDatos = g.este_mes === 0 && g.media_mes === 0
  const pasado = g.media_mes > 0 && g.proyeccion > g.media_mes * 1.1
  return (
    <Tarjeta titulo="Este mes" accion={<Link to="/gastos" className="text-xs font-medium text-accent">Gastos</Link>}>
      {sinDatos ? <p className="text-sm text-muted">Cuando haya movimientos del banco verás aquí lo que llevas gastado este mes.</p> : <>
        <Dato etiqueta={`Llevas en ${g.dia} ${g.dia === 1 ? 'día' : 'días'}`} valor={eur(g.este_mes)} tono={pasado ? 'neg' : undefined} />
        <div className="mt-3">
          <BarraTono valor={g.este_mes} max={Math.max(g.proyeccion, g.media_mes, 1)} tono={pasado ? 'neg' : 'acento'} etiqueta="Gastado sobre lo previsto del mes" />
        </div>
        <p className={`mt-2 text-sm ${pasado ? 'text-neg' : 'text-muted'}`}>
          A este ritmo acabarás en <strong className="cifra">{eur(g.proyeccion)}</strong> (media {eur(g.media_mes)}){pasado ? ': por encima de lo normal.' : '.'}
        </p>
        <p className="mt-2 text-xs text-muted">Gasto del día a día, sin impuestos ni pagos previstos. La media es la de los 3 últimos meses completos y el final del mes, una estimación.</p>
      </>}
    </Tarjeta>
  )
}

export default function Inicio() {
  const { data: r, isLoading, error } = useQuery({ queryKey: ['resumen'], queryFn: () => api.get<Resumen>('/resumen') })
  if (isLoading) return <Cargando />
  if (error) return <ErrorCarga error={error} />
  if (!r) return null
  const { renta } = r.fiscal
  const vacio = r.lineas_activo.length === 0

  return (
    <>
      <Cabecera titulo="Inicio" subtitulo={`Situación a ${fecha(r.fecha, { day: 'numeric', month: 'long', year: 'numeric' })}`} />
      <Avisos avisos={r.avisos} />

      {vacio ? <EmpezarAqui /> : (
        <div className="grid gap-4 lg:grid-cols-3">
          <Tarjeta className="lg:col-span-2" titulo="Patrimonio neto">
            <div className="mb-5 flex flex-wrap gap-x-10 gap-y-4">
              <Dato etiqueta="Neto" valor={eur(r.neto)} />
              <Dato etiqueta="Tienes" valor={eur(r.activos)} />
              <Dato etiqueta="Debes" valor={eur(r.pasivos)} />
            </div>
            <Evolucion historico={r.historico} />
            <PorAnio historico={r.historico} />
          </Tarjeta>
          <Tarjeta titulo="En qué está">
            <Composicion r={r} />
          </Tarjeta>
        </div>
      )}

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

      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <TarjetaEsteMes g={r.gastos} />
        <Tarjeta titulo="Ganas al mes" accion={<Link to="/ingresos" className="text-xs font-medium text-accent">Ingresos</Link>}>
          {renta ? <>
            <Dato etiqueta="Neto" valor={eur(renta.neto_mes)} />
            <p className="mt-3 text-sm text-muted">De {eur(renta.bruto_mes)} brutos con nómina, clientes y alquiler, ya restados Seguridad Social, gastos e IRPF.</p>
          </> : <p className="text-sm text-muted">Pon tu sueldo y tus clientes en <Link to="/ingresos" className="text-accent">Ingresos</Link>.</p>}
        </Tarjeta>
        <TarjetaHacienda r={r} />
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
