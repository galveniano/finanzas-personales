import type { ReactNode } from 'react'

export interface ItemLinea {
  clave: string | number
  marcado: boolean          // punto relleno (pagado, presentado…)
  principal: ReactNode      // línea principal
  secundario?: ReactNode    // línea pequeña gris debajo
  derecha?: ReactNode       // etiquetas, importe y botones
  apagado?: boolean         // tachado y en gris (ya pagado)
}

/** Lista vertical con un punto por elemento sobre una raya (impuestos que vienen, pagos previstos…).
 *  `compacto`: sin raya ni puntos, solo líneas separadas, para una tarjeta pequeña. */
export default function LineaTiempo({ items, compacto }: { items: ItemLinea[]; compacto?: boolean }) {
  return (
    <ol className={compacto ? 'divide-y divide-line' : 'relative space-y-1 border-l border-line pl-5'}>
      {items.map((i) => (
        <li key={i.clave} className={`relative flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2 ${compacto ? 'first:pt-0 last:pb-0' : ''}`}>
          {!compacto && (
            <span aria-hidden="true" className={`absolute top-1/2 -left-[27px] size-3 -translate-y-1/2 rounded-full border-2 ${i.marcado ? 'border-accent bg-accent' : 'border-line bg-panel'}`} />
          )}
          <div className="min-w-0 flex-1">
            <div className={`truncate font-medium ${i.apagado ? 'text-muted line-through' : ''}`}>{i.principal}</div>
            {i.secundario && <div className="text-xs text-muted">{i.secundario}</div>}
          </div>
          {i.derecha && <div className="ml-auto flex flex-wrap items-center justify-end gap-2">{i.derecha}</div>}
        </li>
      ))}
    </ol>
  )
}
