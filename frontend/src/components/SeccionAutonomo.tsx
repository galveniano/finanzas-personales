import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, Pencil, Plus } from 'lucide-react'
import PlanificadorFactura from './PlanificadorFactura'
import { api } from '../lib/api'
import { eur, eurK, fecha, hoyISO } from '../lib/format'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Autonomo as Datos, Factura } from '../lib/tipos'
import { num, opc, useAccion } from '../lib/utilidades'
import { BorrarEnDosPasos, Boton, Campo, Cargando, Dialogo, Etiqueta, ErrorCarga, Formulario, Importe, Selector, Tabla, Tarjeta, Vacio } from './ui'

function FormFactura({ clientes, onHecho, f }: { clientes: string[]; onHecho: () => void; f?: Factura }) {
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
      <Campo etiqueta="Número" name="numero" required defaultValue={f?.numero} />
      <label className="flex flex-col gap-1.5 text-xs font-medium text-muted">Cliente
        <input name="cliente" list="clientes" required defaultValue={f?.cliente} className="w-full rounded-xl border border-line bg-panel px-3 py-2 text-sm text-ink" />
        <datalist id="clientes">{clientes.map((c) => <option key={c} value={c} />)}</datalist>
      </label>
      <Campo etiqueta="Fecha" name="fecha" type="date" defaultValue={f?.fecha ?? hoyISO()} required />
      <Campo etiqueta="Base imponible (€)" name="base" inputMode="decimal" required defaultValue={f ? String(f.base) : undefined} />
      {tipo === 'nacional' && <>
        <Campo etiqueta="IVA %" name="tipo_iva" defaultValue={f && f.tipo_iva ? String(f.tipo_iva) : '21'} inputMode="decimal" />
        <Campo etiqueta="Retención IRPF %" name="tipo_retencion" defaultValue={f && f.tipo_iva ? String(f.tipo_retencion) : '15'} inputMode="decimal" />
      </>}
      <Campo etiqueta="Concepto" name="concepto" placeholder="Consultoría" defaultValue={f?.concepto} />
      <Campo etiqueta="Cobrada el" name="fecha_cobro" type="date" defaultValue={f?.fecha_cobro ?? ''} />
    </Formulario>
  )
}

function FormGasto({ onHecho }: { onHecho: () => void }) {
  const crear = useAccion((d: Record<string, string>) => api.post('/autonomo/gastos', {
    ...d, base: num(d.base), tipo_iva: num(d.tipo_iva) ?? 0, deducible_pct: num(d.deducible_pct) ?? 100,
  }).then(onHecho), 'Gasto registrado')
  return (
    <Formulario onEnviar={(d) => crear.mutateAsync(d)}>
      <Campo etiqueta="Fecha" name="fecha" type="date" defaultValue={hoyISO()} required />
      <Campo etiqueta="Proveedor" name="proveedor" />
      <Selector etiqueta="Categoría" name="categoria" defaultValue="otros">
        <option value="cuota_reta">Cuota de autónomos</option><option value="gestoria">Gestoría</option>
        <option value="software">Software y suscripciones</option><option value="equipos">Equipos</option>
        <option value="formacion">Formación</option><option value="suministros">Suministros</option><option value="otros">Otros</option>
      </Selector>
      <Campo etiqueta="Concepto" name="concepto" />
      <Campo etiqueta="Base (€)" name="base" inputMode="decimal" required />
      <Campo etiqueta="IVA %" name="tipo_iva" defaultValue="21" inputMode="decimal" ayuda="La cuota de autónomos va sin IVA (0)." />
      <Campo etiqueta="% deducible" name="deducible_pct" defaultValue="100" inputMode="decimal" ayuda="Por ejemplo, 30 % para suministros de casa." />
    </Formulario>
  )
}

const anioActual = () => new Date().getFullYear()

export default function SeccionAutonomo() {
  const [actual] = useState(anioActual)
  const [anio, setAnio] = useState(actual)
  const [dialogo, setDialogo] = useState<'factura' | 'gasto' | 'planificar' | null>(null)
  const [editando, setEditando] = useState<Factura | null>(null)
  const { data: d, isLoading, error } = useQuery({ queryKey: ['autonomo', anio], queryFn: () => api.get<Datos>(`/autonomo?anio=${anio}`) })
  const borrar = useAccion(({ tipo, id }: { tipo: string; id: number }) => api.del(`/autonomo/${tipo}/${id}`), 'Borrado')
  const maxCliente = Math.max(1, ...(d?.por_cliente.map((c) => c.base) ?? [1]))

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">{d ? `${eur(d.total_facturado)} facturados en ${anio}` : ''}</p>
        <div className="flex flex-wrap items-center gap-2">
          <Selector value={anio} onChange={(e) => setAnio(Number(e.target.value))} aria-label="Año" className="!w-28">
            {[actual + 1, actual, actual - 1, actual - 2].map((a) => <option key={a} value={a}>{a}</option>)}
          </Selector>
          <Boton variante="secundario" onClick={() => setDialogo('planificar')}><CalendarDays size={16} />Planificar</Boton>
          <Boton variante="secundario" onClick={() => setDialogo('gasto')}><Plus size={16} />Gasto</Boton>
          <Boton onClick={() => setDialogo('factura')}><Plus size={16} />Factura</Boton>
        </div>
      </div>

      {isLoading ? <Cargando /> : error ? <ErrorCarga error={error} /> : d && (
        <>
          {d.por_anio.length > 0 && (
            <Tarjeta titulo="Facturado y ganado neto por año">
              <div className="h-60">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={d.por_anio.map((a) => ({ ...a, etiqueta: a.previsto ? `${a.anio} (previsto)` : String(a.anio) }))}
                    margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="var(--line)" />
                    <XAxis dataKey="etiqueta" tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tickFormatter={eurK} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} width={68} />
                    <Tooltip contentStyle={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, fontSize: 12 }}
                      cursor={{ fill: 'var(--panel-2)' }} formatter={(v, n) => [eur(Number(v)), n === 'facturado' ? 'Facturado (sin IVA)' : 'Neto tras gastos e IRPF']} />
                    <Legend formatter={(v) => (v === 'facturado' ? 'Facturado (sin IVA)' : 'Neto tras gastos e IRPF')} wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="facturado" fill="var(--chart-2)" radius={[4, 4, 0, 0]} maxBarSize={36} />
                    <Bar dataKey="neto" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={36} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-xs text-muted">Neto = facturado menos gastos deducibles y el IRPF de la actividad a tu tipo medio de la renta (el real del año si ya la subiste).
                El IVA no cuenta: lo cobras y se lo das a Hacienda. El año en curso usa la previsión del año completo (o lo ya facturado, si es más).</p>
            </Tarjeta>
          )}
          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            <Tarjeta titulo="Por cliente">
              {d.por_cliente.length ? (
                <ul className="space-y-3">
                  {d.por_cliente.map((c) => (
                    <li key={c.cliente}>
                      <div className="mb-1 flex justify-between gap-2 text-sm"><span className="truncate">{c.cliente}</span><Importe valor={c.base} /></div>
                      <div className="h-1.5 rounded-full bg-panel-2"><div className="h-full rounded-full bg-accent" style={{ width: `${(c.base / maxCliente) * 100}%` }} /></div>
                    </li>
                  ))}
                </ul>
              ) : <Vacio>Sin facturas este año.</Vacio>}
            </Tarjeta>

            <Tarjeta className="xl:col-span-2" titulo="Facturas emitidas">
              {d.facturas.length ? (<>
                <ul className="divide-y divide-line sm:hidden">
                  {d.facturas.map((f) => (
                    <li key={f.id} className="py-3 text-sm first:pt-0 last:pb-0">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="truncate font-medium">{f.cliente}{f.tipo_iva === 0 && <span className="ml-2"><Etiqueta>No sujeta</Etiqueta></span>}</div>
                          <div className="cifra text-xs text-muted">{fecha(f.fecha, { day: '2-digit', month: 'short' })} · Nº {f.numero}</div>
                        </div>
                        <span className="flex"><Boton variante="fantasma" className="px-2 py-1" onClick={() => setEditando(f)} aria-label={`Editar la factura ${f.numero}`}><Pencil size={14} /></Boton><BorrarEnDosPasos etiqueta={`la factura ${f.numero}`} disabled={borrar.isPending} onBorrar={() => borrar.mutate({ tipo: 'facturas', id: f.id })} /></span>
                      </div>
                      <dl className="mt-2 space-y-1">
                        <div className="flex justify-between gap-3"><dt className="text-muted">Base</dt><dd><Importe valor={f.base} /></dd></div>
                        <div className="flex justify-between gap-3"><dt className="text-muted">IVA</dt><dd><Importe valor={f.cuota_iva} /></dd></div>
                        <div className="flex justify-between gap-3"><dt className="text-muted">Retención</dt><dd><Importe valor={-f.retencion} /></dd></div>
                        <div className="flex justify-between gap-3 font-medium"><dt>Cobras</dt><dd><Importe valor={f.total} /></dd></div>
                      </dl>
                    </li>
                  ))}
                </ul>
                <div className="hidden sm:block">
                <Tabla>
                  <thead><tr><th>Fecha</th><th>Nº</th><th>Cliente</th><th className="num">Base</th><th className="num">IVA</th><th className="num">Retención</th><th className="num">Cobras</th><th /></tr></thead>
                  <tbody>
                    {d.facturas.map((f) => (
                      <tr key={f.id}>
                        <td className="cifra whitespace-nowrap text-muted">{fecha(f.fecha, { day: '2-digit', month: 'short' })}</td>
                        <td className="cifra">{f.numero}</td>
                        <td className="whitespace-nowrap">{f.cliente}{f.tipo_iva === 0 && <span className="ml-2"><Etiqueta>No sujeta</Etiqueta></span>}</td>
                        <td className="num"><Importe valor={f.base} /></td>
                        <td className="num"><Importe valor={f.cuota_iva} /></td>
                        <td className="num"><Importe valor={-f.retencion} /></td>
                        <td className="num font-medium"><Importe valor={f.total} /></td>
                        <td className="whitespace-nowrap text-right"><Boton variante="fantasma" className="px-2 py-1" onClick={() => setEditando(f)} aria-label={`Editar la factura ${f.numero}`}><Pencil size={14} /></Boton><BorrarEnDosPasos etiqueta={`la factura ${f.numero}`} disabled={borrar.isPending} onBorrar={() => borrar.mutate({ tipo: 'facturas', id: f.id })} /></td>
                      </tr>
                    ))}
                  </tbody>
                </Tabla>
                </div>
              </>) : <Vacio>Registra tus facturas para ver el IVA y el IRPF de cada trimestre.</Vacio>}
            </Tarjeta>
          </div>

          <Tarjeta className="mt-4" titulo="Gastos de la actividad">
            {d.gastos.length ? (<>
              <ul className="divide-y divide-line sm:hidden">
                {d.gastos.map((g) => (
                  <li key={g.id} className="py-3 text-sm first:pt-0 last:pb-0">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate font-medium">{g.proveedor || g.concepto}</div>
                        <div className="text-xs text-muted"><span className="cifra">{fecha(g.fecha, { day: '2-digit', month: 'short' })}</span> · {g.categoria.replace('_', ' ')}</div>
                      </div>
                      <BorrarEnDosPasos etiqueta={`el gasto ${g.proveedor || g.concepto}`} disabled={borrar.isPending} onBorrar={() => borrar.mutate({ tipo: 'gastos', id: g.id })} />
                    </div>
                    <dl className="mt-2 space-y-1">
                      <div className="flex justify-between gap-3"><dt className="text-muted">Base</dt><dd><Importe valor={g.base} /></dd></div>
                      <div className="flex justify-between gap-3"><dt className="text-muted">IVA</dt><dd><Importe valor={g.cuota_iva} /></dd></div>
                      <div className="flex justify-between gap-3"><dt className="text-muted">Deducible</dt><dd><span className="cifra">{g.deducible_pct} %</span></dd></div>
                    </dl>
                  </li>
                ))}
              </ul>
              <div className="hidden sm:block">
              <Tabla>
                <thead><tr><th>Fecha</th><th>Proveedor</th><th>Categoría</th><th className="num">Base</th><th className="num">IVA</th><th className="num">Deducible</th><th /></tr></thead>
                <tbody>
                  {d.gastos.map((g) => (
                    <tr key={g.id}>
                      <td className="cifra whitespace-nowrap text-muted">{fecha(g.fecha, { day: '2-digit', month: 'short' })}</td>
                      <td>{g.proveedor || g.concepto}</td>
                      <td className="text-muted">{g.categoria.replace('_', ' ')}</td>
                      <td className="num"><Importe valor={g.base} /></td>
                      <td className="num"><Importe valor={g.cuota_iva} /></td>
                      <td className="num cifra">{g.deducible_pct} %</td>
                      <td className="text-right"><BorrarEnDosPasos etiqueta={`el gasto ${g.proveedor || g.concepto}`} disabled={borrar.isPending} onBorrar={() => borrar.mutate({ tipo: 'gastos', id: g.id })} /></td>
                    </tr>
                  ))}
                </tbody>
              </Tabla>
              </div>
            </>) : <Vacio>Apunta la cuota de autónomos, la gestoría o el software: bajan tu IRPF y, si llevan IVA, también el 303.</Vacio>}
          </Tarjeta>
        </>
      )}

      <Dialogo abierto={dialogo === 'factura'} onCerrar={() => setDialogo(null)} titulo="Registrar factura">
        <FormFactura clientes={d?.clientes ?? []} onHecho={() => setDialogo(null)} />
      </Dialogo>
      <Dialogo abierto={!!editando} onCerrar={() => setEditando(null)} titulo={`Editar factura ${editando?.numero ?? ''}`}>
        {editando && <FormFactura key={editando.id} f={editando} clientes={d?.clientes ?? []} onHecho={() => setEditando(null)} />}
      </Dialogo>
      <Dialogo abierto={dialogo === 'planificar'} onCerrar={() => setDialogo(null)} titulo="Planificar factura por días">
        {dialogo === 'planificar' && <PlanificadorFactura onHecho={() => setDialogo(null)} />}
      </Dialogo>
      <Dialogo abierto={dialogo === 'gasto'} onCerrar={() => setDialogo(null)} titulo="Registrar gasto">
        <FormGasto onHecho={() => setDialogo(null)} />
      </Dialogo>
    </>
  )
}
