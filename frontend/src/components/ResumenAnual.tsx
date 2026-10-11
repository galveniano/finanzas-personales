import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { eur } from '../lib/format'
import type { ResumenAnual as Datos } from '../lib/tipos'
import type { Columna } from './ui'
import { Dato, Etiqueta, Fila, Importe, TablaResponsive, Tarjeta, Vacio } from './ui'

type Tercero = Datos['terceros_347'][number]

const COLUMNAS_347: Columna<Tercero>[] = [
  { cabecera: 'Quién', celda: (t) => <>{t.nombre}{t.con_retencion && <span className="ml-2"><Etiqueta>Va en el 190</Etiqueta></span>}</>, papel: 'titulo' },
  { cabecera: 'NIF', celda: (t) => t.nif || <span className="text-muted">Sin NIF</span>, claseTd: 'cifra text-muted', papel: 'subtitulo',
    celdaMovil: (t) => `${t.tipo === 'cliente' ? 'Cliente' : 'Proveedor'} · ${t.nif || 'sin NIF'}` },
  { cabecera: 'Tipo', celda: (t) => (t.tipo === 'cliente' ? 'Cliente' : 'Proveedor'), claseTd: 'text-muted', papel: 'oculta' },
  { cabecera: 'Operaciones', celda: (t) => t.operaciones, num: true, claseTd: 'cifra' },
  { cabecera: 'Importe (con IVA)', celda: (t) => <Importe valor={t.importe} />, num: true, claseTd: 'font-medium', fuerte: true },
]

/** Lo del año que hace falta para el 390 (resumen anual del IVA) y para saber si toca el 347. */
export default function ResumenAnual({ anio }: { anio: number }) {
  const { data: d } = useQuery({ queryKey: ['autonomo', 'anual', anio], queryFn: () => api.get<Datos>(`/autonomo/anual?anio=${anio}`) })
  if (!d) return null
  const conBase = d.repercutido.filter((r) => r.base > 0)
  const diferencia = d.presentado_303 != null ? d.presentado_303 - d.calculado_303 : null
  return (
    <Tarjeta className="mt-4" titulo={`Resumen de ${anio}`} accion={<span className="text-xs text-muted">Para el 390 y el 347</span>}>
      {!d.facturas && !d.gastos ? <Vacio>Sin facturas ni gastos en {anio}: no hay nada que resumir.</Vacio> : (
        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted">IVA repercutido por tipo</h3>
            {conBase.length ? conBase.map((r) => (
              <Fila key={r.tipo} etiqueta={r.tipo === 0 ? 'Sin IVA (0 %, no sujetas)' : `Al ${r.tipo} % · base ${eur(r.base)}`} valor={r.cuota} />
            )) : <p className="text-sm text-muted">Sin facturas este año.</p>}
            <Fila etiqueta={`Total repercutido · base ${eur(d.base_total)}`} valor={d.iva_repercutido} fuerte />
            <Fila etiqueta={`IVA soportado deducible · base ${eur(d.base_soportada)}`} valor={d.iva_soportado} />
            <Fila etiqueta="Retenciones que te han hecho en las facturas" valor={d.retenciones} />
          </div>
          <div className="grid gap-6 sm:grid-cols-2">
            <Dato etiqueta="303 presentados" valor={d.presentado_303 != null ? eur(d.presentado_303) : '—'}
              nota={d.presentado_303 != null ? `${d.trimestres.filter((t) => t.presentado != null).length} de 4 trimestres` : 'Ninguno subido a Hacienda'} />
            <Dato etiqueta="Calculado con facturas" valor={eur(d.calculado_303)}
              nota={diferencia == null ? 'Repercutido menos soportado' : Math.abs(diferencia) < 1 ? 'Cuadra con lo presentado' : `${diferencia > 0 ? 'Presentaste' : 'Calculas'} ${eur(Math.abs(diferencia))} de más`} />
            <div className="sm:col-span-2">
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted">347 · más de {eur(d.umbral_347)} con un mismo tercero</h3>
              <TablaResponsive filas={d.terceros_347} columnas={COLUMNAS_347} clave={(t) => `${t.tipo}-${t.nombre}`}
                vacio="Nadie pasa del umbral: no te toca el 347 por lo que hay aquí." />
            </div>
          </div>
        </div>
      )}
      <p className="mt-3 text-xs text-muted">
        Es lo que necesitas para el 390 de enero y para saber si te toca el 347 (operaciones con terceros). Sale de las facturas y los gastos
        apuntados aquí, IVA incluido en el 347. Las operaciones con retención las declara tu cliente en el 190 y no van en tu 347. Es orientativo.
      </p>
    </Tarjeta>
  )
}
