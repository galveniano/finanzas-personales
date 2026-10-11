import { useState } from 'react'
import { api } from '../lib/api'
import { hoyISO } from '../lib/format'
import type { Factura, GastoAutonomo } from '../lib/tipos'
import { num, opc, useAccion } from '../lib/utilidades'
import { CATEGORIAS_GASTO } from './categoriasGasto'
import { Campo, Formulario, Selector } from './ui'

/** Registrar una factura o, con `f`, corregirla. */
export function FormFactura({ clientes, onHecho, f }: { clientes: string[]; onHecho: () => void; f?: Factura }) {
  // Extranjero solo cuando no lleva ni IVA ni retención (una factura nacional con IVA 0 sigue siendo nacional)
  const [tipo, setTipo] = useState<'nacional' | 'extranjero'>(f && f.tipo_iva === 0 && f.tipo_retencion === 0 ? 'extranjero' : 'nacional')
  const crear = useAccion((d: Record<string, string>) => {
    const datos = {
      numero: d.numero, cliente: d.cliente, fecha: d.fecha, concepto: d.concepto, base: num(d.base),
      tipo_iva: tipo === 'extranjero' ? 0 : num(d.tipo_iva) ?? 21,
      tipo_retencion: tipo === 'extranjero' ? 0 : num(d.tipo_retencion) ?? 15,
      fecha_cobro: opc(d.fecha_cobro) ?? null,
    }
    return (f ? api.put(`/autonomo/facturas/${f.id}`, datos) : api.post('/autonomo/facturas', datos)).then(onHecho)
  }, f ? 'Factura actualizada' : 'Factura registrada')
  return (
    <Formulario onEnviar={(d) => crear.mutateAsync(d)}>
      <Selector etiqueta="Tipo de cliente" value={tipo} onChange={(e) => setTipo(e.target.value as typeof tipo)} className="sm:col-span-2">
        <option value="nacional">Empresa española (IVA y retención)</option>
        <option value="extranjero">Empresa de fuera de España (sin IVA ni retención)</option>
      </Selector>
      <Campo etiqueta="Número" name="numero" required maxLength={40} defaultValue={f?.numero} />
      <Campo etiqueta="Cliente" name="cliente" list="clientes" required maxLength={120} defaultValue={f?.cliente} />
      <datalist id="clientes">{clientes.map((c) => <option key={c} value={c} />)}</datalist>
      <Campo etiqueta="Fecha" name="fecha" type="date" defaultValue={f?.fecha ?? hoyISO()} required />
      <Campo etiqueta="Base imponible (€)" name="base" inputMode="decimal" required defaultValue={f ? String(f.base) : undefined} />
      {tipo === 'nacional' && <>
        {/* String(…) y no «f.tipo_iva ? …»: un 0 es un valor, no «sin valor» */}
        <Campo etiqueta="IVA %" name="tipo_iva" defaultValue={f ? String(f.tipo_iva) : '21'} inputMode="decimal" />
        <Campo etiqueta="Retención IRPF %" name="tipo_retencion" defaultValue={f ? String(f.tipo_retencion) : '15'} inputMode="decimal" />
      </>}
      <Campo etiqueta="Concepto" name="concepto" placeholder="Consultoría" defaultValue={f?.concepto} />
      <Campo etiqueta="Cobrada el" name="fecha_cobro" type="date" defaultValue={f?.fecha_cobro ?? ''} ayuda="Vacío: pendiente de cobro." />
      {f?.con_detalle && (
        <p className="text-xs text-muted sm:col-span-2">Esta factura salió del calendario, con horas y días. Si cambias la base, el documento deja de enseñar ese desglose.</p>
      )}
    </Formulario>
  )
}

/** Apuntar un gasto de la actividad o, con `g`, corregirlo. */
export function FormGasto({ onHecho, g }: { onHecho: () => void; g?: GastoAutonomo }) {
  const guardar = useAccion((d: Record<string, string>) => {
    const datos = { ...d, base: num(d.base), tipo_iva: num(d.tipo_iva) ?? 0, deducible_pct: num(d.deducible_pct) ?? 100 }
    return (g ? api.put(`/autonomo/gastos/${g.id}`, datos) : api.post('/autonomo/gastos', datos)).then(onHecho)
  }, g ? 'Gasto actualizado' : 'Gasto registrado')
  return (
    <Formulario onEnviar={(d) => guardar.mutateAsync(d)}>
      <Campo etiqueta="Fecha" name="fecha" type="date" defaultValue={g?.fecha ?? hoyISO()} required />
      <Campo etiqueta="Proveedor" name="proveedor" maxLength={120} defaultValue={g?.proveedor} />
      <Selector etiqueta="Categoría" name="categoria" defaultValue={g?.categoria ?? 'otros'}>
        {Object.entries(CATEGORIAS_GASTO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </Selector>
      <Campo etiqueta="Concepto" name="concepto" defaultValue={g?.concepto} />
      <Campo etiqueta="Base (€)" name="base" inputMode="decimal" required defaultValue={g ? String(g.base) : undefined} />
      <Campo etiqueta="IVA %" name="tipo_iva" defaultValue={g ? String(g.tipo_iva) : '21'} inputMode="decimal" ayuda="La cuota de autónomos va sin IVA (0)." />
      <Campo etiqueta="% deducible" name="deducible_pct" defaultValue={g ? String(g.deducible_pct) : '100'} inputMode="decimal" ayuda="Por ejemplo, 30 % para suministros de casa." />
    </Formulario>
  )
}
