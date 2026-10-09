import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { eur, pct } from '../../lib/format'
import type { Constantes, Inmueble, VenderOAlquilar } from '../../lib/tipos'
import { num } from '../../lib/utilidades'
import { Campo, Fila } from '../ui'

/** Compara vender el piso (lo que te quedaría en mano) con seguir alquilándolo. Se calcula al abrir el desplegable. */
export function VenderOSeguir({ i, constantes }: { i: Inmueble; constantes: Constantes }) {
  const [precio, setPrecio] = useState('')
  const [gastos, setGastos] = useState('')
  const [abierto, setAbierto] = useState(false)
  const p = num(precio), g = num(gastos)
  const params = new URLSearchParams()
  if (p) params.set('precio', String(p))
  if (g != null) params.set('gastos_venta_pct', String(g))
  const consulta = params.toString()
  const { data: v, isFetching, error } = useQuery({
    queryKey: ['vender', i.id, consulta], enabled: abierto, placeholderData: (prev) => prev, retry: false,
    queryFn: () => api.get<VenderOAlquilar>(`/inmuebles/${i.id}/vender${consulta ? `?${consulta}` : ''}`),
  })
  const parcial = i.porcentaje_propiedad < 100
  return (
    <details className="mt-5 rounded-xl border border-line p-4" onToggle={(e) => setAbierto((e.target as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-sm font-semibold">¿Vender o seguir alquilando?</summary>
      <div className="mt-3 grid gap-3 sm:max-w-md sm:grid-cols-2">
        <Campo etiqueta="Precio de venta del piso entero (€)" inputMode="decimal" value={precio} onChange={(e) => setPrecio(e.target.value)}
          placeholder={v ? String(Math.round(v.precio_entero)) : ''} ayuda={parcial ? `Vacío: el valor actual. Tu parte es el ${pct(i.porcentaje_propiedad, 0)}.` : 'Vacío: el valor actual.'} />
        <Campo etiqueta="Gastos de venta (%)" inputMode="decimal" value={gastos} onChange={(e) => setGastos(e.target.value)}
          placeholder={String(constantes.gastos_venta_pct)} ayuda="Agencia, certificados, cancelación de la hipoteca…" />
      </div>
      {error && <p className="mt-3 text-xs text-neg" role="alert">{error.message}</p>}
      {v && (
        <div className={`mt-4 grid gap-6 lg:grid-cols-2 ${isFetching ? 'opacity-60' : ''}`}>
          <div>
            <h4 className="mb-1 text-sm font-semibold">Si vendes</h4>
            <Fila etiqueta={parcial ? `Tu ${pct(i.porcentaje_propiedad, 0)} del precio (${v.valor_detalle})` : `Precio (${v.valor_detalle})`} valor={v.precio_venta} />
            <Fila etiqueta={`Gastos de venta (${pct(v.gastos_venta_pct)})`} valor={-v.gastos_venta} />
            <Fila etiqueta="Lo que te costó, menos lo amortizado" valor={<span className="cifra text-muted">{eur(v.valor_adquisicion)}</span>} />
            <Fila etiqueta={`IRPF de la ganancia (${eur(v.ganancia)})`} valor={-v.irpf_ganancia} />
            <Fila etiqueta="Cancelar la hipoteca" valor={-v.hipoteca_pendiente} />
            <Fila etiqueta="Te queda en mano" valor={v.en_mano} fuerte />
            <p className="mt-2 text-xs text-muted">
              La ganancia es el precio menos los gastos y lo que te costó, descontando la amortización del {pct(v.constantes.amortizacion_pct, 0)} que
              ya te has deducido ({eur(v.amortizacion_acumulada)}).
            </p>
          </div>
          <div>
            <h4 className="mb-1 text-sm font-semibold">Si sigues alquilando</h4>
            <Fila etiqueta="Te queda al año" valor={v.alquiler_flujo_anual} />
            <Fila etiqueta={`IRPF del alquiler (${pct(v.tipo_marginal, 1)} sobre ${eur(v.alquiler_tributa)})`} valor={-v.alquiler_irpf_anual} />
            <Fila etiqueta="Neto al año" valor={v.alquiler_flujo_tras_irpf} fuerte />
            <p className="mt-2 text-xs text-muted">
              {v.rentabilidad_sobre_en_mano !== null
                ? `Equivale a un ${pct(v.rentabilidad_sobre_en_mano)} al año sobre lo que sacarías vendiendo, sin contar lo que suba o baje el piso.`
                : 'Vendiendo no te quedaría dinero en mano.'}
            </p>
          </div>
          <div className="lg:col-span-2">{v.notas.map((n) => <p key={n} className="text-xs text-muted">{n}</p>)}</div>
        </div>
      )}
    </details>
  )
}
