import { eur } from '../lib/format'
import type { Prevision, RentaPrevista } from '../lib/tipos'
import { Etiqueta, Importe, Tarjeta } from './ui'

export function RentaPresentada({ r }: { r: NonNullable<Prevision['renta_presentada']> }) {
  const c = r.casillas
  const fila = (etiqueta: string, valor: number | undefined, fuerte = false) => valor === undefined ? null : (
    <div className={`flex justify-between ${fuerte ? 'border-t border-line pt-1.5 font-medium' : ''}`}><dt className={fuerte ? '' : 'text-muted'}>{etiqueta}</dt><dd><Importe valor={valor} /></dd></div>)
  return (
    <Tarjeta titulo={`Renta ${r.anio} (presentada)`} accion={<Etiqueta tono="bien">Presentada</Etiqueta>}>
      <dl className="space-y-1.5 text-sm">
        {fila('Trabajo (nómina)', c.rendimiento_trabajo)}
        {fila('Actividad (autónomo)', c.rendimiento_actividad)}
        {fila('Alquiler', c.rendimiento_alquiler)}
        {fila(`Cuota${c.base_general ? ` (${String(Math.round((c.cuota / c.base_general) * 1000) / 10).replace('.', ',')} % de media)` : ''}`, c.cuota, true)}
        {fila('Retenido en la nómina', c.retenciones_trabajo !== undefined ? -c.retenciones_trabajo : undefined)}
        {fila('Pagos del 130', c.pagos_130 !== undefined ? -c.pagos_130 : undefined)}
        <div className="flex justify-between border-t border-line pt-1.5 font-semibold"><dt>{r.resultado >= 0 ? 'Pagaste' : 'Te devolvieron'}</dt><dd><Importe valor={Math.abs(r.resultado)} /></dd></div>
      </dl>
      {c.gastos_actividad !== undefined && <p className="mt-3 text-xs text-muted">
        Gastos de la actividad: {eur(c.gastos_actividad)} al año{c.ss_autonomo !== undefined && `, de ellos ${eur(c.ss_autonomo)} de cuota de autónomos`}.</p>}
    </Tarjeta>
  )
}


export function RentaEstimada({ r }: { r: RentaPrevista }) {
  return (
    <Tarjeta titulo={`Renta ${r.anio} (estimada)`} accion={<Etiqueta tono={r.resultado > 0 ? 'aviso' : 'bien'}>{r.resultado > 0 ? 'A pagar' : 'A devolver'}</Etiqueta>}>
      <dl className="space-y-1.5 text-sm">
        <div className="flex justify-between"><dt className="text-muted">Trabajo (nómina)</dt><dd><Importe valor={r.rendimiento_trabajo} /></dd></div>
        <div className="flex justify-between"><dt className="text-muted">Actividad (autónomo)</dt><dd><Importe valor={r.rendimiento_actividad} /></dd></div>
        <div className="flex justify-between"><dt className="text-muted">Alquiler</dt><dd><Importe valor={r.rendimiento_alquiler} /></dd></div>
        <div className="flex justify-between border-t border-line pt-1.5 font-medium"><dt>Cuota ({String(r.tipo_medio).replace('.', ',')} % de media)</dt><dd><Importe valor={r.cuota} /></dd></div>
        <div className="flex justify-between"><dt className="text-muted">Retenido en la nómina</dt><dd><Importe valor={-r.retenciones_nomina} /></dd></div>
        <div className="flex justify-between"><dt className="text-muted">Retenido en facturas</dt><dd><Importe valor={-r.retenciones_facturas} /></dd></div>
        <div className="flex justify-between"><dt className="text-muted">Pagos del 130</dt><dd><Importe valor={-r.pagos_130} /></dd></div>
        <div className="flex justify-between border-t border-line pt-1.5 font-semibold"><dt>{r.resultado >= 0 ? 'A pagar' : 'A devolver'} en junio de {r.anio + 1}</dt><dd><Importe valor={Math.abs(r.resultado)} /></dd></div>
      </dl>
    </Tarjeta>
  )
}
