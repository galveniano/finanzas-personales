import { eur, pct } from '../lib/format'
import type { Prevision, RentaPrevista } from '../lib/tipos'
import { Etiqueta, Fila, Tarjeta } from './ui'

const esCero = (v: number) => Math.abs(v) < 0.005

export function RentaPresentada({ r }: { r: NonNullable<Prevision['renta_presentada']> }) {
  const c = r.casillas
  const fila = (etiqueta: string, valor: number | undefined, fuerte = false) => valor === undefined ? null : <Fila etiqueta={etiqueta} valor={valor} fuerte={fuerte} />
  return (
    <Tarjeta titulo={`Renta ${r.anio} (presentada)`} accion={<Etiqueta tono="bien">Presentada</Etiqueta>}>
      <div>
        {fila('Trabajo (nómina)', c.rendimiento_trabajo)}
        {fila('Actividad (autónomo)', c.rendimiento_actividad)}
        {fila('Alquiler', c.rendimiento_alquiler)}
        {fila(`Cuota${c.base_general ? ` (${pct(Math.round((c.cuota / c.base_general) * 1000) / 10, 1)} de media)` : ''}`, c.cuota, true)}
        {fila('Retenido en la nómina', c.retenciones_trabajo !== undefined ? -c.retenciones_trabajo : undefined)}
        {fila('Pagos del 130', c.pagos_130 !== undefined ? -c.pagos_130 : undefined)}
        <Fila etiqueta={esCero(r.resultado) ? 'Sin pagar ni devolver' : r.resultado > 0 ? 'Pagaste' : 'Te devolvieron'} valor={Math.abs(r.resultado)} fuerte />
      </div>
      {c.gastos_actividad !== undefined && <p className="mt-3 text-xs text-muted">
        Gastos de la actividad: {eur(c.gastos_actividad)} al año{c.ss_autonomo !== undefined && `, de ellos ${eur(c.ss_autonomo)} de cuota de autónomos`}.</p>}
    </Tarjeta>
  )
}


export function RentaEstimada({ r }: { r: RentaPrevista }) {
  return (
    <Tarjeta titulo={`Renta ${r.anio} (estimada)`} accion={<Etiqueta tono={r.resultado > 0 && !esCero(r.resultado) ? 'aviso' : 'bien'}>{esCero(r.resultado) ? 'Sin pagar ni devolver' : r.resultado > 0 ? 'A pagar' : 'A devolver'}</Etiqueta>}>
      <div>
        <Fila etiqueta="Trabajo (nómina)" valor={r.rendimiento_trabajo} />
        <Fila etiqueta="Actividad (autónomo)" valor={r.rendimiento_actividad} />
        <Fila etiqueta="Alquiler" valor={r.rendimiento_alquiler} />
        <Fila etiqueta={`Cuota (${pct(r.tipo_medio)} de media)`} valor={r.cuota} fuerte />
        <Fila etiqueta="Retenido en la nómina" valor={-r.retenciones_nomina} />
        <Fila etiqueta="Retenido en facturas" valor={-r.retenciones_facturas} />
        <Fila etiqueta="Pagos del 130" valor={-r.pagos_130} />
        <Fila etiqueta={esCero(r.resultado) ? 'Sin pagar ni devolver' : `${r.resultado > 0 ? 'A pagar' : 'A devolver'} en junio de ${r.anio + 1}`} valor={Math.abs(r.resultado)} fuerte />
      </div>
    </Tarjeta>
  )
}
