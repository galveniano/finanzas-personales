import { Pencil } from 'lucide-react'
import { Link } from 'react-router-dom'
import { eur, fecha } from '../../lib/format'
import type { Objetivo, Planificacion } from '../../lib/tipos'
import { Barra, BorrarEnDosPasos, Boton, Etiqueta, Tarjeta, Vacio } from '../ui'
import { TIPO_OBJETIVO, mesLargo } from './comun'

/** Lo que piden los objetivos al mes frente a lo que ahorra la previsión. */
function Sintesis({ s }: { s: Planificacion['sintesis'] }) {
  const piden = s.ahorro_objetivos_mes
  const ahorra = s.ahorro_prevision_mes
  if (!piden) return null
  if (ahorra == null) {
    return (
      <p className="mb-3 rounded-xl bg-panel-2 px-4 py-3 text-sm">
        Tus objetivos piden <strong className="cifra">{eur(piden)}</strong> al mes.{' '}
        <Link to="/ingresos" className="text-accent">Pon tu sueldo y tarifas</Link> para saber si llegas.
      </p>
    )
  }
  const llegas = ahorra >= piden
  return (
    <div className="mb-3">
      <p className={`rounded-xl px-4 py-3 text-sm ${llegas ? 'bg-accent-soft text-pos' : 'bg-warn-soft text-warn'}`}>
        Tus objetivos piden <strong className="cifra">{eur(piden)}</strong> al mes y la previsión{' '}
        {ahorra < 0
          ? <>no ahorra: gastas <strong className="cifra">{eur(-ahorra)}</strong> más de lo que entra al mes.</>
          : <>ahorra <strong className="cifra">{eur(ahorra)}</strong> al mes{llegas ? ': vas bien.' : <>: faltan <strong className="cifra">{eur(piden - ahorra)}</strong> al mes.</>}</>}
      </p>
      <p className="mt-1.5 text-xs text-muted">Media de los {s.meses} meses de la previsión, sin contar lo que gastarías en los propios objetivos. Es una estimación.</p>
    </div>
  )
}

function Llegada({ o }: { o: Objetivo }) {
  const l = o.llegas_en
  if (!l) return null
  if (l.a_tiempo) return <p className="mt-2 text-sm text-pos">Llegas en {mesLargo(l.mes!)} con el ahorro previsto.</p>
  if (l.a_tiempo === false) {
    return <p className="mt-2 text-sm text-neg">No llegas: faltarán {eur(l.faltara)}{l.mes && <> (lo tendrías en {mesLargo(l.mes)})</>}.</p>
  }
  return <p className="mt-2 text-sm text-muted">{l.mes ? `Lo tendrías en ${mesLargo(l.mes)} con el ahorro previsto.` : 'Con el ahorro previsto no llegas.'}</p>
}

export default function Objetivos({ d, onNuevo, onEditar, onBorrar, borrando }: {
  d: Planificacion; onNuevo: () => void; onEditar: (o: Objetivo) => void; onBorrar: (o: Objetivo) => void; borrando: boolean
}) {
  return (
    <>
      <h2 className="mt-8 mb-3 text-lg font-semibold">Objetivos</h2>
      <Sintesis s={d.sintesis} />
      {d.objetivos.length ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {d.objetivos.map((o) => {
            const pct = o.importe_objetivo ? Math.round((o.ahorrado / o.importe_objetivo) * 100) : 0
            const conseguido = o.importe_objetivo > 0 && o.ahorrado >= o.importe_objetivo
            return (
              <Tarjeta key={o.id}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate font-semibold">{o.nombre}</div>
                    <div className="text-xs text-muted">{o.fecha_objetivo ? fecha(o.fecha_objetivo, { day: 'numeric', month: 'long', year: 'numeric' }) : 'Sin fecha'}</div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {conseguido ? <Etiqueta tono="bien">Conseguido</Etiqueta> : <Etiqueta tono="acento">{TIPO_OBJETIVO[o.tipo] ?? o.tipo}</Etiqueta>}
                    <Boton variante="fantasma" className="px-2 py-1" aria-label={`Editar ${o.nombre}`} title="Editar" onClick={() => onEditar(o)}><Pencil size={14} /></Boton>
                    <BorrarEnDosPasos etiqueta={`el objetivo ${o.nombre}`} disabled={borrando} onBorrar={() => onBorrar(o)} />
                  </div>
                </div>
                <div className="mt-4 flex items-baseline justify-between gap-2">
                  <span className="cifra text-xl font-medium">{eur(o.ahorrado)}</span>
                  <span className="cifra text-xs text-muted">de {eur(o.importe_objetivo)} · {pct} %</span>
                </div>
                <div className="mt-2"><Barra valor={o.ahorrado} max={o.importe_objetivo} /></div>
                {o.ahorrado_automatico && <p className="mt-2 text-xs text-muted">Lo ahorrado es el saldo de {o.cuenta} (tu parte).</p>}
                {o.ahorro_mensual != null && !conseguido && (
                  <p className="mt-3 text-sm">Aparta <strong className="cifra">{eur(o.ahorro_mensual)}</strong> al mes para llegar.</p>
                )}
                <Llegada o={o} />
                {o.notas && <p className="mt-2 line-clamp-3 text-xs whitespace-pre-line text-muted" title={o.notas}>{o.notas}</p>}
              </Tarjeta>
            )
          })}
        </div>
      ) : (
        <Vacio>
          Crea objetivos como la boda o un viaje y te digo cuánto apartar cada mes.{' '}
          <button type="button" className="cursor-pointer text-accent" onClick={onNuevo}>Crear el primero</button>
        </Vacio>
      )}
    </>
  )
}
