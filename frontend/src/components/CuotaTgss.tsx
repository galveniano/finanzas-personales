import { useQuery } from '@tanstack/react-query'
import { Landmark } from 'lucide-react'
import { api } from '../lib/api'
import { eur } from '../lib/format'
import type { CargosTgss } from '../lib/tipos'
import { useAccion } from '../lib/utilidades'
import { Boton } from './ui'

/** Cargos de la cuota de autónomos que están en el banco y aún no son gasto de la actividad: un botón los apunta. */
export default function CuotaTgss({ anio }: { anio: number }) {
  const { data: d } = useQuery({ queryKey: ['autonomo', 'cuota-tgss', anio], queryFn: () => api.get<CargosTgss>(`/autonomo/cuota-tgss?anio=${anio}`) })
  const apuntar = useAccion(() => api.post<{ n: number }>(`/autonomo/cuota-tgss?anio=${anio}`), 'Cuota de autónomos apuntada como gasto')
  if (!d?.n) return null
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-warn-soft px-4 py-3 text-sm">
      <div className="min-w-0">
        <p className="text-warn">Hay {d.n} {d.n === 1 ? 'cargo' : 'cargos'} de la cuota de autónomos en el banco sin apuntar como gasto ({eur(d.total)}).</p>
        <p className="mt-0.5 text-xs text-muted">El 130 estimado con facturas solo descuenta los gastos apuntados. Se apuntan sin IVA y deducibles al 100 %.</p>
      </div>
      <Boton variante="secundario" className="px-2.5 py-1 text-xs" disabled={apuntar.isPending} onClick={() => apuntar.mutate(undefined)}>
        <Landmark size={14} />Apuntar
      </Boton>
    </div>
  )
}
