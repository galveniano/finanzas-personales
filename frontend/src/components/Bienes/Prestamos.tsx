import { useQuery } from '@tanstack/react-query'
import { Pencil } from 'lucide-react'
import { api } from '../../lib/api'
import { eur, fecha, pct } from '../../lib/format'
import type { Prestamo } from '../../lib/tipos'
import { useAccion } from '../../lib/utilidades'
import { BorrarEnDosPasos, Boton, Cargando, Dato, ErrorCarga, Etiqueta, Tarjeta, Vacio } from '../ui'
import { CuadroYSimulador } from './Hipoteca'
import { mesAnio, TIPOS_DEUDA } from './comun'
import type { Accion } from './comun'

/** Préstamos y otras deudas sin inmueble (el del coche, uno personal…). Las hipotecas van en su piso. */
export function Prestamos({ abrir }: { abrir: (a: Accion) => void }) {
  const { data, isLoading, error } = useQuery({ queryKey: ['deudas'], queryFn: () => api.get<Prestamo[]>('/deudas') })
  const borrar = useAccion((id: number) => api.del(`/deudas/${id}`), 'Préstamo borrado')
  const lista = (data ?? []).filter((d) => d.tipo !== 'hipoteca')
  const pendiente = lista.reduce((s, d) => s + d.pendiente, 0)
  const cuotas = lista.filter((d) => !d.futura && d.pendiente > 0).reduce((s, d) => s + d.cuota, 0)
  return (
    <section className="mt-8">
      <div className="mb-3 min-w-0">
        <h2 className="text-lg font-semibold">Préstamos y otras deudas</h2>
        {lista.length > 0 && <p className="text-sm text-muted">{eur(pendiente)} pendientes · {eur(cuotas)} al mes en cuotas</p>}
      </div>
      {isLoading ? <Cargando /> : error ? <ErrorCarga error={error} /> : lista.length ? (
        <div className="grid gap-4 md:grid-cols-2">
          {lista.map((d) => (
            <Tarjeta key={d.id}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate font-semibold">{d.nombre}</div>
                  <div className="truncate text-xs text-muted">{d.entidad || 'Sin entidad'}{d.activo && ` · ${d.activo}`}</div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Etiqueta tono={d.futura ? 'acento' : 'neutro'}>{d.futura ? 'Empieza pronto' : TIPOS_DEUDA[d.tipo]}</Etiqueta>
                  <Boton variante="fantasma" className="px-2 py-1" onClick={() => abrir({ tipo: 'editarDeuda', deuda: d })} aria-label={`Editar ${d.nombre}`}><Pencil size={14} /></Boton>
                  <BorrarEnDosPasos etiqueta={`el préstamo ${d.nombre}`} disabled={borrar.isPending} onBorrar={() => borrar.mutate(d.id)} />
                </div>
              </div>
              <div className="mt-4 grid grid-cols-3 gap-4 [&>*]:min-w-0">
                <Dato etiqueta="Pendiente" valor={eur(d.futura ? d.capital_inicial : d.pendiente)} />
                <Dato etiqueta="Cuota" valor={eur(d.cuota)} nota={pct(d.tipo_interes_anual, 3) + ' anual'} />
                {d.futura
                  ? <Dato etiqueta="Empieza" valor={fecha(d.fecha_inicio, { month: 'short', year: 'numeric' })} nota={`${d.plazo_meses} meses`} />
                  : <Dato etiqueta="Acaba" valor={d.fin ? mesAnio(d.fin) : '—'} nota={`Quedan ${d.cuotas_restantes} cuotas`} />}
              </div>
              <p className="mt-3 text-xs text-muted">
                {eur(d.capital_inicial)} desde el {fecha(d.fecha_inicio)} en {d.plazo_meses} meses
                {d.saldo_fecha ? `; pendiente real a ${fecha(d.saldo_fecha)}: ${eur(d.saldo_pendiente_manual)}` : '; según el cuadro de la firma'}.
                Se resta de tu patrimonio.
              </p>
              {!d.futura && d.pendiente > 0 && <CuadroYSimulador d={d} />}
            </Tarjeta>
          ))}
        </div>
      ) : <Vacio>Si tienes un préstamo del coche u otra deuda sin inmueble, añádela con «Añadir préstamo»: se resta de tu patrimonio y aquí ves cuánto queda.</Vacio>}
    </section>
  )
}
