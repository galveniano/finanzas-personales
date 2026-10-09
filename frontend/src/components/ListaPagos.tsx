import { useState } from 'react'
import type { ReactNode } from 'react'
import { Check, Pencil } from 'lucide-react'
import { cuandoVence, diasHasta, fecha } from '../lib/format'
import type { Pago } from '../lib/tipos'
import LineaTiempo from './LineaTiempo'
import type { ItemLinea } from './LineaTiempo'
import { BorrarEnDosPasos, Boton, Etiqueta, Importe, Segmentos, Vacio } from './ui'

const FILTROS = [{ valor: 'pendientes', texto: 'Pendientes' }, { valor: 'todos', texto: 'Todos' }] as const
type Filtro = typeof FILTROS[number]['valor']

/** Pagos previstos con su vencimiento, si ya se han visto cargados en el banco, marcar pagado, editar y borrar.
 *  Los pendientes van primero; los ya pagados, plegados debajo (o todos en orden con el filtro «Todos»).
 *  `compacto` (para Inicio): solo los pendientes, sin filtro, sin raya, y solo con el botón de marcar.
 *  `acciones` va arriba a la izquierda (p. ej. «Marcar los vistos en el banco»). */
export default function ListaPagos({ pagos, onMarcar, onBorrar, onEditar, compacto, ocupado, acciones, vacio }: {
  pagos: Pago[]
  onMarcar: (pago: Pago, pagado: boolean) => void
  onBorrar: (pago: Pago) => void
  onEditar?: (pago: Pago) => void
  compacto?: boolean
  ocupado?: boolean
  acciones?: ReactNode
  vacio?: ReactNode
}) {
  const [filtro, setFiltro] = useState<Filtro>('pendientes')
  const pendientes = pagos.filter((p) => !p.pagado)
  const pagados = pagos.filter((p) => p.pagado)

  const item = (p: Pago): ItemLinea => {
    const dias = diasHasta(p.fecha)
    const visto = p.visto_en_banco
    const enlace = p.inmueble ?? p.objetivo ?? p.inversion
    const cuando = compacto
      ? `${cuandoVence(dias)} · ${fecha(p.fecha, { day: 'numeric', month: 'short' })}`
      : fecha(p.fecha, { day: 'numeric', month: 'long', year: 'numeric' })
    return {
      clave: p.id, marcado: p.pagado, apagado: p.pagado, principal: p.concepto,
      secundario: (
        <>
          {cuando}{enlace && !compacto && ` · ${enlace}`}
          {visto && <> · <span className="text-accent">Visto en el banco el {fecha(visto.fecha, { day: 'numeric', month: 'short' })}</span></>}
        </>
      ),
      derecha: (
        <>
          {!p.pagado && !compacto && (visto
            ? <Etiqueta tono="acento">En el banco</Etiqueta>
            : <Etiqueta tono={dias < 0 ? 'mal' : dias <= 30 ? 'aviso' : 'neutro'}>{cuandoVence(dias)}</Etiqueta>)}
          <Importe valor={p.importe} />
          <Boton variante={p.pagado ? 'secundario' : visto ? 'primario' : 'fantasma'} className="px-2 py-1 text-xs" disabled={ocupado}
            onClick={() => onMarcar(p, !p.pagado)} aria-pressed={p.pagado}
            aria-label={p.pagado ? `Desmarcar ${p.concepto} como pagado` : `Marcar ${p.concepto} como pagado`}>
            <Check size={14} />{compacto ? null : p.pagado ? 'Pagado' : visto ? 'Marcar pagado' : 'Marcar'}
          </Boton>
          {onEditar && !compacto && (
            <Boton variante="fantasma" className="px-2 py-1" disabled={ocupado} onClick={() => onEditar(p)} aria-label={`Editar ${p.concepto}`} title="Editar">
              <Pencil size={14} />
            </Boton>
          )}
          {!compacto && <BorrarEnDosPasos etiqueta={`el pago ${p.concepto}`} disabled={ocupado} onBorrar={() => onBorrar(p)} />}
        </>
      ),
    }
  }

  if (!pagos.length) return <Vacio>{vacio ?? 'No hay pagos previstos.'}</Vacio>
  if (compacto) {
    return pendientes.length ? <LineaTiempo compacto items={pendientes.map(item)} /> : <p className="text-sm text-muted">Todo pagado.</p>
  }
  const lista = filtro === 'todos' ? pagos : pendientes
  return (
    <>
      {(acciones || pagados.length > 0) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">{acciones}</div>
          {pagados.length > 0 && <Segmentos pequeno etiqueta="Qué pagos ver" opciones={FILTROS} valor={filtro} onCambiar={setFiltro} />}
        </div>
      )}
      {lista.length
        ? <LineaTiempo items={lista.map(item)} />
        : <Vacio>Todo pagado: no queda ningún pago pendiente.</Vacio>}
      {filtro === 'pendientes' && pagados.length > 0 && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-muted">Ya pagados ({pagados.length})</summary>
          <div className="mt-3"><LineaTiempo items={pagados.map(item)} /></div>
        </details>
      )}
    </>
  )
}
