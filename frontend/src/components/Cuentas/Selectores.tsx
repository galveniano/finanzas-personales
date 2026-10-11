import type { SelectHTMLAttributes } from 'react'
import type { Categoria } from '../../lib/tipos'
import { Selector } from '../ui'

/** Selector discreto para una celda: sin borde ni fondo hasta pasar el ratón. */
export function SelectorEnLinea({ className, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <Selector {...p} className={`max-w-[170px] rounded-lg! border-transparent! bg-transparent! px-1.5! py-1! hover:border-line! ${className ?? ''}`} />
}

/** Las opciones de categoría de un selector, con la de «sin categoría» delante. */
export function OpcionesCategoria({ categorias, sinCategoria = 'Sin categoría' }: { categorias: Categoria[]; sinCategoria?: string }) {
  return (
    <>
      <option value="">{sinCategoria}</option>
      {categorias.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
    </>
  )
}
