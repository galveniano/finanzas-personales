import type { ReactNode } from 'react'
import { eur } from '../../lib/format'
import type { MesPrevision, Prevision } from '../../lib/tipos'
import { Etiqueta, Importe, Tabla } from '../ui'
import { nombreMes } from './comun'

type Fila = { etiqueta: ReactNode; valor: ReactNode }
type Col = {
  cabecera: string
  celda: (m: MesPrevision) => ReactNode   // la celda de la tabla
  filas?: (m: MesPrevision) => Fila[]     // en móvil, si una celda se abre en varias líneas (impuestos, pagos)
  vacia?: (m: MesPrevision) => boolean    // en móvil no sale
  titulo?: (m: MesPrevision) => string | undefined
  num?: boolean
  fuerte?: boolean
  claseTd?: (m: MesPrevision) => string | undefined
}

const presentado = (i: MesPrevision['impuestos'][number]) => <>{i.concepto}{i.presentado && <> <Etiqueta tono="bien">Presentado</Etiqueta></>}</>
const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ') || undefined

function columnas(prev: Prevision): Col[] {
  return [
    { cabecera: 'Nómina', num: true, celda: (m) => <Importe valor={m.nomina} />, vacia: (m) => !m.nomina },
    {
      cabecera: 'Clientes', num: true, celda: (m) => <Importe valor={m.cobros} />, vacia: (m) => !m.cobros,
      titulo: (m) => `Facturado ${eur(m.facturado)} + IVA ${eur(m.iva)} − retención ${eur(m.retenciones)}`
        + (prev.dias_fuera[m.mes] ? ` · ${prev.dias_fuera[m.mes]} días de vacaciones` : ''),
    },
    { cabecera: 'Alquiler', num: true, celda: (m) => <Importe valor={m.alquiler} />, vacia: (m) => !m.alquiler },
    { cabecera: 'Gastos', num: true, celda: (m) => <Importe valor={-m.gastos} /> },
    {
      cabecera: 'Pagos', num: true, vacia: (m) => !(m.pagos_previstos + m.total_objetivos + m.financiado),
      titulo: (m) => m.objetivos.map((o) => `${o.concepto}: ${eur(o.importe)}`).join('\n') || undefined,
      celda: (m) => (
        <>
          {m.pagos_previstos + m.total_objetivos ? <Importe valor={-(m.pagos_previstos + m.total_objetivos)} /> : null}
          {m.financiado > 0 && <div className="text-xs whitespace-nowrap text-muted">la hipoteca pone {eur(m.financiado)}</div>}
        </>
      ),
      filas: (m) => [
        ...(m.pagos_previstos ? [{ etiqueta: 'Pagos', valor: <Importe valor={-m.pagos_previstos} /> }] : []),
        ...m.objetivos.map((o) => ({ etiqueta: o.concepto, valor: <Importe valor={-o.importe} /> })),
        ...(m.financiado > 0 ? [{ etiqueta: 'La hipoteca pone', valor: <Importe valor={m.financiado} /> }] : []),
      ],
    },
    {
      cabecera: 'Impuestos', vacia: (m) => !m.impuestos.length, claseTd: () => 'text-xs',
      celda: (m) => m.impuestos.map((i) => (
        <div key={i.concepto} className="flex justify-between gap-2 whitespace-nowrap">
          <span className="text-muted">{presentado(i)}</span><Importe valor={-i.importe} />
        </div>
      )),
      filas: (m) => m.impuestos.map((i) => ({ etiqueta: presentado(i), valor: <Importe valor={-i.importe} /> })),
    },
    { cabecera: 'Ahorro', num: true, fuerte: true, celda: (m) => <Importe valor={m.neto} /> },
    {
      cabecera: 'Liquidez', num: true, celda: (m) => <Importe valor={m.liquidez} />,
      claseTd: (m) => (m.bajo_colchon ? 'bg-panel-2' : undefined), titulo: (m) => (m.bajo_colchon ? 'Por debajo de tu colchón' : undefined),
    },
  ]
}

/** La previsión mes a mes: tabla en escritorio y lista en móvil, las dos a partir de las mismas columnas
 *  (en móvil la liquidez va en la cabecera del mes y las celdas vacías no salen). */
export default function MesAMes({ prev }: { prev: Prevision }) {
  const cols = columnas(prev)
  const ya = prev.meses[0]?.ya_este_mes
  return (
    <details className="mt-8 rounded-2xl border border-line bg-panel p-5">
      <summary className="cursor-pointer text-[15px] font-semibold">Mes a mes</summary>
      <ul className="mt-4 divide-y divide-line sm:hidden">
        {prev.meses.map((m) => (
          <li key={m.mes} className="py-3 text-sm first:pt-0">
            <div className="mb-1.5 flex items-baseline justify-between gap-2">
              <span className="font-medium capitalize">{nombreMes(m.mes)}</span>
              <span className={`text-xs ${m.bajo_colchon ? 'text-neg' : 'text-muted'}`}>Liquidez <Importe valor={m.liquidez} /></span>
            </div>
            <dl className="space-y-1">
              {cols.filter((c) => c.cabecera !== 'Liquidez' && !c.vacia?.(m)).flatMap((c) =>
                (c.filas?.(m) ?? [{ etiqueta: c.cabecera, valor: c.celda(m) }]).map((f, i) => (
                  <div key={`${c.cabecera}-${i}`} className={cx('flex justify-between gap-3', c.fuerte && 'font-medium')}>
                    <dt className={c.fuerte ? undefined : 'text-muted'}>{f.etiqueta}</dt><dd>{f.valor}</dd>
                  </div>
                )))}
            </dl>
          </li>
        ))}
      </ul>
      <div className="mt-4 hidden sm:block">
        <Tabla>
          <thead><tr><th>Mes</th>{cols.map((c) => <th key={c.cabecera} className={c.num ? 'num' : undefined}>{c.cabecera}</th>)}</tr></thead>
          <tbody>
            {prev.meses.map((m) => (
              <tr key={m.mes}>
                <td className="whitespace-nowrap capitalize">{nombreMes(m.mes)}</td>
                {cols.map((c) => (
                  <td key={c.cabecera} className={cx(c.num && 'num', c.fuerte && 'font-medium', c.claseTd?.(m))} title={c.titulo?.(m)}>{c.celda(m)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </Tabla>
      </div>
      <p className="mt-3 text-xs text-muted">Clientes es lo que cobras: base más IVA menos retención, con los días de vacaciones del calendario ya descontados.
        El IVA y el 130 de cada trimestre se pagan el mes siguiente; la renta, en junio; la regularización de autónomos, hacia noviembre del año siguiente.
        «Pagos» son los pagos previstos de arriba (los vencidos sin marcar, en el mes en curso) y los objetivos con fecha que no tienen pagos apuntados,
        ya sin lo que pone una hipoteca prevista. Todo son estimaciones.</p>
      {ya && (
        <p className="mt-2 text-xs text-muted">Este mes ya han pasado por tus cuentas {eur(ya.nomina + ya.cobros + ya.alquiler)} de ingresos,
          {' '}{eur(ya.gastos)} de gastos y {eur(ya.impuestos)} de impuestos. Ya están en el saldo de hoy, así que el mes en curso solo cuenta lo que falta.</p>
      )}
    </details>
  )
}
