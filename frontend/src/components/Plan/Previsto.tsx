import { Link } from 'react-router-dom'
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { eur, eurK } from '../../lib/format'
import { cursorBarra, eje, estiloTooltip } from '../../lib/graficas'
import type { Planificacion, Prevision } from '../../lib/tipos'
import { Dato, Tarjeta } from '../ui'
import { ahorroTexto, mesLargo, nombreMes, tieneSupuestos } from './comun'

const NOMBRES: Record<string, string> = { neto: 'Ahorro del mes', liquidez: 'Dinero disponible', liquidez_escenario: 'Con el escenario' }

/** Lo que tienes hoy, lo que vendrá y la gráfica mes a mes; con un escenario activo, su línea punteada encima. */
export default function Previsto({ d, prev, esc, meses }: { d: Planificacion; prev?: Prevision; esc?: Prevision; meses: number }) {
  const conSupuestos = !!prev && tieneSupuestos(prev)
  const ultimo = prev?.meses[prev.meses.length - 1]
  // Lo mismo que lista «Impuestos que vienen»: sin el ajuste de lo ya pagado este mes (las devoluciones sí restan)
  const impuestos = prev?.meses.reduce((s, m) => s + m.impuestos.filter((i) => i.tipo !== 'ajuste').reduce((t, i) => t + i.importe, 0), 0) ?? 0
  const financiado = prev?.meses.reduce((s, m) => s + m.financiado, 0) ?? 0
  const bajoColchon = prev?.meses.find((m) => m.bajo_colchon)
  const datos = prev?.meses.map((m, i) => ({ ...m, liquidez_escenario: esc?.meses[i]?.liquidez }))
  return (
    <Tarjeta>
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <Dato etiqueta="Tienes hoy" valor={eur(d.liquidez)} nota="Cuentas corrientes y de ahorro, tu parte" />
        <Dato etiqueta="Pagos en 12 meses" valor={eur(d.pendiente_12_meses)}
          nota={[
            'Los pagos previstos de abajo',
            d.objetivos_12_meses ? `y ${eur(d.objetivos_12_meses)} de objetivos con fecha sin pagos apuntados` : '',
            d.financiado_hipoteca ? `sin los ${eur(d.financiado_hipoteca)} que pone la hipoteca prevista` : '',
          ].filter(Boolean).join(', ')} />
        <Dato etiqueta={`Impuestos en ${meses} meses`} valor={prev ? eur(impuestos) : '—'}
          nota={conSupuestos ? 'IVA, 130, renta, autónomos e IBI, sin contar lo ya pagado este mes. Estimación' : 'Solo lo ya presentado y los tributos del año pasado'} />
        {ultimo && conSupuestos
          ? <Dato etiqueta={`Tendrás en ${mesLargo(ultimo.mes)}`} valor={eur(ultimo.liquidez)} tono={ultimo.liquidez < 0 ? 'neg' : 'pos'}
              nota={<>{ahorroTexto((ultimo.liquidez - prev!.liquidez_hoy) / prev!.meses.length)}
                {financiado > 0 && <>. De los pagos previstos, {eur(financiado)} los pone la hipoteca prevista</>}</>} />
          : <Dato etiqueta="Tendrás en un año" valor="—" nota={<Link to="/ingresos" className="text-accent">Pon tu sueldo y tarifas</Link>} />}
      </div>
      {datos && conSupuestos && (
        <div className="mt-6 h-56" role="img" aria-label={`Dinero disponible mes a mes durante ${meses} meses${esc ? ', con el escenario en línea punteada' : ''}`}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={datos} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--line)" />
              <XAxis dataKey="mes" tickFormatter={nombreMes} interval={meses > 12 ? 2 : 'preserveEnd'} {...eje} />
              <YAxis yAxisId="l" tickFormatter={eurK} {...eje} width={68} />
              <YAxis yAxisId="n" orientation="right" hide />
              <Tooltip {...estiloTooltip} cursor={cursorBarra} labelFormatter={(v) => nombreMes(String(v))}
                formatter={(v, n) => [eur(Number(v)), NOMBRES[String(n)] ?? String(n)]} />
              <Bar yAxisId="n" dataKey="neto" fill="var(--chart-2)" radius={[4, 4, 0, 0]} maxBarSize={24} />
              <Line yAxisId="l" dataKey="liquidez" stroke="var(--chart-1)" strokeWidth={2} dot={false} />
              {esc && <Line yAxisId="l" dataKey="liquidez_escenario" stroke="var(--chart-3)" strokeWidth={2} strokeDasharray="6 4" dot={false} />}
              {prev!.colchon > 0 && <ReferenceLine yAxisId="l" y={prev!.colchon} stroke="var(--neg)" strokeDasharray="4 4"
                label={{ value: 'Colchón', fill: 'var(--muted)', fontSize: 11, position: 'insideTopLeft' }} />}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
      {esc && conSupuestos && <p className="mt-2 text-xs text-muted">La línea punteada es el escenario «¿Y si…?»; la continua, la previsión con tus supuestos de hoy.</p>}
      {bajoColchon && (
        <p className="mt-4 rounded-xl bg-panel-2 px-4 py-3 text-sm">
          En {mesLargo(bajoColchon.mes)} bajarías a {eur(bajoColchon.liquidez)}, por debajo de tu colchón de {eur(prev!.colchon)}.
        </p>
      )}
    </Tarjeta>
  )
}
