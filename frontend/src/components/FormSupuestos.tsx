import { useState } from 'react'
import { Plus } from 'lucide-react'
import { api } from '../lib/api'
import { MESES } from '../lib/format'
import type { SupuestosPrevision } from '../lib/tipos'
import { num, useAccion } from '../lib/utilidades'
import { Boton, Campo, Formulario, Selector } from './ui'

export default function FormSupuestos({ s, habitualBanco, cerrar }: { s: SupuestosPrevision; habitualBanco: number | null; cerrar: () => void }) {
  const [clientes, setClientes] = useState(Math.max(1, s.clientes.length))
  const guardar = useAccion((d: Record<string, string>) => api.put('/prevision/supuestos', {
    nomina: num(d.bruto_anual) ? {
      empresa: d.empresa, bruto_anual: num(d.bruto_anual), variable_pct: num(d.variable_pct) ?? 0,
      mes_variable: Number(d.mes_variable), pagas: Number(d.pagas),
    } : null,
    clientes: Array.from({ length: clientes }, (_, i) => ({
      nombre: d[`c${i}_nombre`], tarifa_hora: num(d[`c${i}_tarifa`]), horas_dia: num(d[`c${i}_horas`]) ?? 8,
      dias_mes: num(d[`c${i}_dias`]) ?? null, iva: num(d[`c${i}_iva`]) ?? 0, retencion: num(d[`c${i}_ret`]) ?? 0,
    })).filter((c) => c.nombre && c.tarifa_hora),
    gastos_autonomo_mes: num(d.gastos_autonomo_mes) ?? 0,
    gasto_habitual_mes: num(d.gasto_habitual_mes) ?? null,
    meses_sin_facturar: MESES.map((_, i) => i + 1).filter((m) => d[`sin_${m}`]),
  }).then(cerrar), 'Guardado')
  const n = s.nomina
  return (
    <Formulario onEnviar={(d) => guardar.mutateAsync(d)}>
      <h3 className="text-sm font-semibold sm:col-span-2">Nómina</h3>
      <Campo etiqueta="Empresa" name="empresa" defaultValue={n?.empresa ?? ''} />
      <Campo etiqueta="Bruto anual fijo (€)" name="bruto_anual" inputMode="decimal" defaultValue={n?.bruto_anual ?? ''} />
      <Campo etiqueta="Variable (% del fijo)" name="variable_pct" inputMode="decimal" defaultValue={n?.variable_pct ?? 0} />
      <Selector etiqueta="Mes en que cobras el variable" name="mes_variable" defaultValue={n?.mes_variable ?? 3}>
        {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
      </Selector>
      <Selector etiqueta="Pagas" name="pagas" defaultValue={n?.pagas ?? 14}>
        <option value={14}>14 (extras en junio y diciembre)</option><option value={12}>12 (prorrateadas)</option>
      </Selector>

      <h3 className="mt-2 text-sm font-semibold sm:col-span-2">Clientes como autónomo</h3>
      {Array.from({ length: clientes }, (_, i) => {
        const c = s.clientes[i]
        return (
          <div key={i} className="grid gap-3 rounded-xl border border-line p-3 sm:col-span-2 sm:grid-cols-3">
            <Campo etiqueta="Cliente" name={`c${i}_nombre`} defaultValue={c?.nombre ?? ''} className="sm:col-span-3" />
            <Campo etiqueta="€ por hora" name={`c${i}_tarifa`} inputMode="decimal" defaultValue={c?.tarifa_hora ?? ''} />
            <Campo etiqueta="Horas al día" name={`c${i}_horas`} inputMode="decimal" defaultValue={c?.horas_dia ?? 8} />
            <Campo etiqueta="Días al mes" name={`c${i}_dias`} inputMode="decimal" defaultValue={c?.dias_mes ?? ''} placeholder="Como el último mes" ayuda="Vacío: los del último mes facturado." />
            <Campo etiqueta="IVA %" name={`c${i}_iva`} inputMode="decimal" defaultValue={c?.iva ?? 21} ayuda="0 si es de fuera de España." />
            <Campo etiqueta="Retención %" name={`c${i}_ret`} inputMode="decimal" defaultValue={c?.retencion ?? 15} ayuda="15 %, o 7 % los primeros años." />
          </div>
        )
      })}
      <div className="sm:col-span-2">
        <Boton type="button" variante="secundario" onClick={() => setClientes(clientes + 1)}><Plus size={14} />Otro cliente</Boton>
      </div>
      <fieldset className="sm:col-span-2">
        <legend className="mb-2 text-xs font-medium text-muted">Meses que no facturas (vacaciones)</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {MESES.map((m, i) => (
            <label key={m} className="flex items-center gap-1.5 text-sm capitalize">
              <input type="checkbox" name={`sin_${i + 1}`} defaultChecked={s.meses_sin_facturar.includes(i + 1)} />{m.slice(0, 3)}
            </label>
          ))}
        </div>
      </fieldset>

      <h3 className="mt-2 text-sm font-semibold sm:col-span-2">Gastos</h3>
      <Campo etiqueta="Gastos deducibles como autónomo (€/mes)" name="gastos_autonomo_mes" inputMode="decimal"
        defaultValue={s.gastos_autonomo_mes} ayuda="Cuota de autónomos, gestoría, software… Solo para calcular el 130 y la renta. Con 0 se usa la cuota de autónomos que aparezca en el banco." />
      <Campo etiqueta="Gasto habitual (€/mes)" name="gasto_habitual_mes" inputMode="decimal" defaultValue={s.gasto_habitual_mes ?? ''}
        placeholder={habitualBanco ? `${Math.round(habitualBanco)} según el banco` : ''}
        ayuda="Lo que sale de tus cuentas cada mes. Vacío: la media de los últimos 3 meses del banco." />
    </Formulario>
  )
}

