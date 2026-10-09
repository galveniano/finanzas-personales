import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../lib/api'
import { eur, eurK, fecha } from '../lib/format'
import { eje, estiloTooltip } from '../lib/graficas'
import type { CarteraIndexa as Cartera, EvolucionInversiones, Inversiones as Privadas } from '../lib/tipos'
import CarteraIndexa from '../components/CarteraIndexa'
import InversionesPrivadas from '../components/InversionesPrivadas'
import { Cabecera, Dato, ErrorCarga, Importe, Tarjeta, Vacio } from '../components/ui'

function Evolucion() {
  const { data, error } = useQuery({ queryKey: ['inversiones-evolucion'], queryFn: () => api.get<EvolucionInversiones>('/inversiones/evolucion?meses=12') })
  if (error && !data) return <ErrorCarga error={error} />
  if (!data) return null
  const puntos = data.puntos
  return (
    <Tarjeta titulo="Evolución en 12 meses" accion={data.cambio != null && (
      <span className="text-sm"><Importe valor={data.cambio} signo /> <span className="text-xs text-muted">desde {fecha(puntos[0].fecha, { day: 'numeric', month: 'short' })}</span></span>)}>
      {puntos.length < 2 ? <p className="text-sm text-muted">La evolución aparece a partir de mañana: cada día se guarda una foto de tus inversiones con el resto del patrimonio.</p> : (
        <div className="h-52">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={puntos} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
              <defs>
                <linearGradient id="inversiones" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.28} />
                  <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="var(--line)" />
              <XAxis dataKey="fecha" tickFormatter={(v) => fecha(v, { day: '2-digit', month: 'short' })} {...eje} minTickGap={40} />
              <YAxis tickFormatter={eurK} {...eje} width={76} domain={['auto', 'auto']} />
              <Tooltip {...estiloTooltip} formatter={(v) => [eur(Number(v)), 'Inversiones']} labelFormatter={(v) => fecha(String(v))} />
              <Area type="monotone" dataKey="inversiones" stroke="var(--chart-1)" strokeWidth={2} fill="url(#inversiones)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
      <p className="mt-3 text-xs text-muted">Indexa más el NAV de los fondos privados, según la foto diaria del patrimonio: sube también cuando aportas, no solo cuando el mercado va bien.</p>
    </Tarjeta>
  )
}

/** Lo mandado a Indexa desde el banco frente a lo que vale hoy: una estimación de cuánto ha crecido tu dinero. */
function AportacionesBanco({ cuentas }: { cuentas: Cartera[] }) {
  const aportaciones = cuentas.map((c) => c.aportado_banco).filter((a) => a != null)
  const aportado = aportaciones.reduce((s, a) => s + a.total, 0)
  const ultimoAnio = aportaciones.reduce((s, a) => s + a.ultimos_12_meses, 0)
  const primera = aportaciones.map((a) => a.primera_fecha).filter((f) => f != null).sort()[0]
  const vale = cuentas.reduce((s, c) => s + (c.total ?? 0), 0)
  return (
    <Tarjeta className="mt-4" titulo="Aportaciones desde el banco">
      {aportado > 0 ? <>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4 [&>*]:min-w-0">
          <Dato etiqueta="Has aportado" valor={eur(aportado)} nota={primera ? `desde ${fecha(primera, { month: 'short', year: 'numeric' })}` : undefined} />
          <Dato etiqueta="Últimos 12 meses" valor={eur(ultimoAnio)} nota={`${eur(ultimoAnio / 12)} al mes`} />
          <Dato etiqueta="Vale hoy" valor={eur(vale)} />
          <Dato etiqueta="Diferencia" valor={<Importe valor={vale - aportado} signo />} tono={vale - aportado >= 0 ? 'pos' : 'neg'}
            nota={aportado ? `${((vale - aportado) / aportado * 100).toLocaleString('es-ES', { maximumFractionDigits: 1 })} % sobre lo aportado` : undefined} />
        </div>
        <p className="mt-3 text-xs text-muted">
          Suma de los cargos de la categoría «Inversión (Indexa)» en tus cuentas, con tu parte. Es una estimación: no descuenta reembolsos ni lo que aportaste
          antes de que el banco trajera movimientos; con varias cuentas de Indexa, cada traspaso va a la cuenta cuyo número lleva el concepto (si no, a la primera).
        </p>
      </> : (
        <Vacio>Cuando haya traspasos a Indexa con la categoría «Inversión (Indexa)» en tus cuentas, aquí verás cuánto has aportado y cuánto ha crecido. Si ya los hay, clasifícalos así en <Link to="/cuentas" className="text-accent">Cuentas</Link>.</Vacio>
      )}
    </Tarjeta>
  )
}

export default function Inversiones() {
  const indexa = useQuery({ queryKey: ['indexa'], queryFn: () => api.get<Cartera[]>('/indexa') })
  const privadas = useQuery({ queryKey: ['inversiones'], queryFn: () => api.get<Privadas>('/inversiones') })
  const cuentas = indexa.data ?? []
  const enIndexa = cuentas.reduce((s, c) => s + (c.total ?? 0), 0)
  const enPrivadas = privadas.data?.totales.nav ?? 0
  const total = enIndexa + enPrivadas
  // La plusvalía total solo se conoce si Indexa da el coste de todas las cuentas con dinero
  const plusIndexa = cuentas.every((c) => !c.total || c.plusvalia != null) ? cuentas.reduce((s, c) => s + (c.plusvalia ?? 0), 0) : null
  const plusPrivadas = privadas.data ? privadas.data.totales.nav + privadas.data.totales.distribuido - privadas.data.totales.desembolsado : 0
  const plusvalia = plusIndexa != null ? plusIndexa + plusPrivadas : null
  const cargado = indexa.data && privadas.data
  const nada = cargado && !cuentas.length && !privadas.data!.inversiones.length
  const partes = [enIndexa > 0 && `Indexa ${eur(enIndexa)}`, enPrivadas > 0 && `private equity ${eur(enPrivadas)}`].filter(Boolean).join(' · ')

  return (
    <>
      <Cabecera titulo="Inversiones" subtitulo={!cargado ? undefined : nada ? 'Indexa Capital y private equity' : <>
        <strong className="cifra text-ink">{eur(total)}</strong> invertidos{partes && ` (${partes})`}
        {plusvalia != null && <> · <Importe valor={plusvalia} signo /> de plusvalía</>}
      </>} />
      {indexa.error && !indexa.data && <ErrorCarga error={indexa.error} />}
      {nada ? (
        <Tarjeta titulo="Todavía no hay inversiones">
          <ol className="list-decimal space-y-2 pl-5 text-sm text-muted">
            <li>Si inviertes en Indexa Capital, pon tu token en <Link to="/ajustes" className="text-accent">Ajustes</Link> y sincroniza: aparecerán tus carteras con sus fondos y rentabilidad.</li>
            <li>Si tienes fondos de private equity (Concrescenta y similares), añádelos abajo con el compromiso y las llamadas de capital.</li>
          </ol>
        </Tarjeta>
      ) : cargado && <Evolucion />}
      <CarteraIndexa />
      {cuentas.length > 0 && <AportacionesBanco cuentas={cuentas} />}
      <InversionesPrivadas />
    </>
  )
}
