import { useState } from 'react'
import { eur, pct } from '../lib/format'
import type { Prevision, RentaPrevista } from '../lib/tipos'
import { Etiqueta, Fila, Importe, Tarjeta } from './ui'

const esCero = (v: number | null | undefined) => v == null || Math.abs(v) < 0.005

/** Importe con, debajo, lo que la app calculaba para compararlo. */
function Comparado({ valor, estimado }: { valor: number; estimado: number | undefined }) {
  return (
    <span className="text-right">
      <Importe valor={valor} />
      {estimado !== undefined && <span className="block text-xs font-normal text-muted">la app estimaba {eur(estimado)}</span>}
    </span>
  )
}

/** `estimada`: la renta del mismo año que la app preveía antes de presentarla (solo si sigue en la previsión). */
export function RentaPresentada({ r, estimada }: { r: NonNullable<Prevision['renta_presentada']>; estimada?: RentaPrevista }) {
  const c = r.casillas
  const fila = (etiqueta: string, valor: number | undefined, fuerte = false) => valor === undefined ? null : <Fila etiqueta={etiqueta} valor={valor} fuerte={fuerte} />
  return (
    <Tarjeta titulo={`Renta ${r.anio} (presentada)`} accion={<Etiqueta tono="bien">Presentada</Etiqueta>}>
      <div>
        {fila('Trabajo (nómina)', c.rendimiento_trabajo)}
        {fila('Actividad (autónomo)', c.rendimiento_actividad)}
        {fila('Alquiler', c.rendimiento_alquiler)}
        {c.cuota !== undefined && (
          <Fila etiqueta={`Cuota${c.base_general ? ` (${pct(Math.round((c.cuota / c.base_general) * 1000) / 10, 1)} de media)` : ''}`} fuerte
            valor={<Comparado valor={c.cuota} estimado={estimada?.cuota} />} />
        )}
        {fila('Retenido en la nómina', c.retenciones_trabajo !== undefined ? -c.retenciones_trabajo : undefined)}
        {fila('Pagos del 130', c.pagos_130 !== undefined ? -c.pagos_130 : undefined)}
        <Fila etiqueta={esCero(r.resultado) ? 'Sin pagar ni devolver' : r.resultado > 0 ? 'Pagaste' : 'Te devolvieron'} fuerte
          valor={<Comparado valor={Math.abs(r.resultado)} estimado={estimada ? Math.abs(estimada.resultado) : undefined} />} />
      </div>
      {c.gastos_actividad !== undefined && <p className="mt-3 text-xs text-muted">
        Gastos de la actividad: {eur(c.gastos_actividad)} al año{c.ss_autonomo !== undefined && `, de ellos ${eur(c.ss_autonomo)} de cuota de autónomos`}.</p>}
      {estimada && <p className="mt-2 text-xs text-muted">«La app estimaba» es lo que preveía para {r.anio} con tu nómina, tus facturas y el alquiler; la diferencia son deducciones y datos que no ve.</p>}
    </Tarjeta>
  )
}


export function RentaEstimada({ r }: { r: RentaPrevista }) {
  const [actual] = useState(() => new Date().getFullYear())
  const aPresentar = r.anio < actual  // la del año pasado: se presenta entre abril y junio
  const hayImputacion = !esCero(r.imputacion_inmuebles)
  const hayReduccion = !esCero(r.reduccion_pensiones)
  const hayAhorro = !esCero(r.base_ahorro) || !esCero(r.cuota_ahorro)
  const notas: string[] = []
  if (hayReduccion) notas.push('La reducción por pensiones es lo que apuntas en «Pagar menos en la renta», con sus límites.')
  if (hayAhorro) notas.push('Intereses, dividendos y ventas de fondos tributan aparte, del 19 al 30 %.')
  return (
    <Tarjeta titulo={`Renta ${r.anio} (estimada)`} accion={<span className="flex flex-wrap justify-end gap-1.5">
      {aPresentar && <Etiqueta tono="acento">A presentar en junio</Etiqueta>}
      <Etiqueta tono={r.resultado > 0 && !esCero(r.resultado) ? 'aviso' : 'bien'}>{esCero(r.resultado) ? 'Sin pagar ni devolver' : r.resultado > 0 ? 'A pagar' : 'A devolver'}</Etiqueta>
    </span>}>
      <div>
        <Fila etiqueta="Trabajo (nómina)" valor={r.rendimiento_trabajo} />
        <Fila etiqueta="Actividad (autónomo)" valor={r.rendimiento_actividad} />
        <Fila etiqueta="Alquiler" valor={r.rendimiento_alquiler} />
        {hayImputacion && <Fila etiqueta="Imputación de otras viviendas" valor={r.imputacion_inmuebles} />}
        <Fila etiqueta="Base general" valor={r.base} fuerte />
        {hayReduccion && <>
          <Fila etiqueta="Reducción por planes de pensiones" valor={-r.reduccion_pensiones} />
          <Fila etiqueta="Base liquidable" valor={r.base_liquidable} className="font-medium" />
        </>}
        {hayAhorro && <>
          <Fila etiqueta="Cuota de la base general" valor={r.cuota - r.cuota_ahorro} />
          <Fila etiqueta={`Cuota del ahorro (sobre ${eur(r.base_ahorro)})`} valor={r.cuota_ahorro} />
        </>}
        <Fila etiqueta={`Cuota (${pct(r.tipo_medio)} de media)`} valor={r.cuota} fuerte />
        <Fila etiqueta="Retenido en la nómina" valor={-r.retenciones_nomina} />
        <Fila etiqueta="Retenido en facturas" valor={-r.retenciones_facturas} />
        <Fila etiqueta="Pagos del 130" valor={-r.pagos_130} />
        <Fila etiqueta={esCero(r.resultado) ? 'Sin pagar ni devolver' : `${r.resultado > 0 ? 'A pagar' : 'A devolver'} en junio de ${r.anio + 1}`} valor={Math.abs(r.resultado)} fuerte />
      </div>
      {notas.length > 0 && <p className="mt-3 text-xs text-muted">{notas.join(' ')}</p>}
    </Tarjeta>
  )
}
