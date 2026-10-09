import { Link } from 'react-router-dom'
import { cuandoVence, diasHasta, fecha } from '../../lib/format'
import type { Prevision } from '../../lib/tipos'
import LineaTiempo from '../LineaTiempo'
import { Etiqueta, Importe, Tarjeta, Vacio } from '../ui'
import { mesLargo } from './comun'

/** Los impuestos de la previsión con su plazo, en orden, sin los ajustes internos ni los de importe cero. */
export default function ImpuestosQueVienen({ prev, meses }: { prev: Prevision; meses: number }) {
  const proximos = prev.meses.flatMap((m) => m.impuestos.filter((i) => i.tipo !== 'ajuste' && i.importe).map((i) => ({ ...i, mes: m.mes })))
  return (
    <>
      <div className="mt-8 mb-3 flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-semibold">Impuestos que vienen</h2>
        <Link to="/impuestos" className="text-sm text-accent">Ver en Impuestos</Link>
      </div>
      <Tarjeta>
        {proximos.length ? (
          <LineaTiempo items={proximos.map((i, n) => {
            const dias = i.vence ? diasHasta(i.vence) : null
            return {
              clave: `${i.mes}-${n}`, marcado: i.importe < 0, principal: i.concepto,
              secundario: i.vence
                ? `${i.presentado && i.tipo === 'renta' ? 'Se carga el' : 'Hasta el'} ${fecha(i.vence, { day: 'numeric', month: 'long', year: 'numeric' })}`
                : `Hacia ${mesLargo(i.mes)} (fecha aproximada)`,
              derecha: (
                <>
                  {i.presentado ? <Etiqueta tono="bien">Presentado</Etiqueta> : <Etiqueta tono="neutro">Estimado</Etiqueta>}
                  {dias != null && dias <= 30 && <Etiqueta tono={dias < 0 ? 'mal' : 'aviso'}>{cuandoVence(dias)}</Etiqueta>}
                  <Importe valor={-i.importe} />
                </>
              ),
            }
          })} />
        ) : <Vacio>No hay impuestos previstos en los próximos {meses} meses.</Vacio>}
        <p className="mt-3 text-xs text-muted">El IVA (303) y el IRPF (130) de cada trimestre, la renta de junio, la regularización de la cuota de autónomos
          (con la devolución por pluriactividad restada) y los tributos que pagaste el año pasado, como el IBI o el de circulación.
          Lo no presentado sale de la previsión y es una estimación. La cuota mensual de autónomos va en los gastos.</p>
      </Tarjeta>
    </>
  )
}
