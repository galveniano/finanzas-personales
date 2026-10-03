import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import { eur, fecha, hoyISO } from '../lib/format'
import type { Autonomo as Datos, Fuente } from '../lib/tipos'
import { Boton, Cabecera, Campo, Cargando, Dialogo, Etiqueta, ErrorCarga, Formulario, Importe, Selector, Tabla, Tarjeta, Vacio, num, opc, useAccion } from '../components/ui'

function BorrarEnDosPasos({ onBorrar }: { onBorrar: () => void }) {
  const [seguro, setSeguro] = useState(false)
  return seguro
    ? <Boton variante="peligro" className="px-2 py-1 text-xs" onClick={onBorrar} onBlur={() => setSeguro(false)} autoFocus>Confirmar</Boton>
    : <Boton variante="fantasma" className="px-2 py-1" onClick={() => setSeguro(true)} aria-label="Borrar"><Trash2 size={14} /></Boton>
}

function FormFactura({ clientes, onHecho }: { clientes: string[]; onHecho: () => void }) {
  const [tipo, setTipo] = useState<'nacional' | 'extranjero'>('nacional')
  const crear = useAccion((d: Record<string, string>) => api.post('/autonomo/facturas', {
    numero: d.numero, cliente: d.cliente, fecha: d.fecha, concepto: d.concepto, base: num(d.base),
    tipo_iva: tipo === 'extranjero' ? 0 : num(d.tipo_iva) ?? 21,
    tipo_retencion: tipo === 'extranjero' ? 0 : num(d.tipo_retencion) ?? 15,
    fecha_cobro: opc(d.fecha_cobro),
  }).then(onHecho), 'Factura registrada')
  return (
    <Formulario onEnviar={(d) => crear.mutateAsync(d)}>
      <Selector etiqueta="Tipo de cliente" value={tipo} onChange={(e) => setTipo(e.target.value as typeof tipo)} className="sm:col-span-2">
        <option value="nacional">Empresa española (IVA y retención)</option>
        <option value="extranjero">Empresa de fuera de España (sin IVA ni retención)</option>
      </Selector>
      <Campo etiqueta="Número" name="numero" required />
      <label className="flex flex-col gap-1.5 text-xs font-medium text-muted">Cliente
        <input name="cliente" list="clientes" required className="w-full rounded-xl border border-line bg-panel px-3 py-2 text-sm text-ink" />
        <datalist id="clientes">{clientes.map((c) => <option key={c} value={c} />)}</datalist>
      </label>
      <Campo etiqueta="Fecha" name="fecha" type="date" defaultValue={hoyISO()} required />
      <Campo etiqueta="Base imponible (€)" name="base" inputMode="decimal" required />
      {tipo === 'nacional' && <>
        <Campo etiqueta="IVA %" name="tipo_iva" defaultValue="21" inputMode="decimal" />
        <Campo etiqueta="Retención IRPF %" name="tipo_retencion" defaultValue="15" inputMode="decimal" />
      </>}
      <Campo etiqueta="Concepto" name="concepto" placeholder="Consultoría" />
      <Campo etiqueta="Cobrada el" name="fecha_cobro" type="date" />
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

/** Resultado de un modelo: lo presentado manda; si las facturas dan otra cifra, se enseña debajo. */
function Modelo({ nombre, valor, fuente, estimado, exento }: { nombre: string; valor: number; fuente: Fuente; estimado: number | null; exento?: boolean }) {
  const distinto = fuente === 'presentado' && estimado !== null && Math.abs(estimado - valor) >= 1
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <dt className="flex items-center gap-1.5 text-muted">{nombre}
          {fuente === 'presentado' ? <Etiqueta tono="bien">Presentado</Etiqueta> : <Etiqueta>Estimado</Etiqueta>}</dt>
        <dd className="font-semibold">{exento ? <Etiqueta tono="bien">Exento</Etiqueta> : <Importe valor={valor} />}</dd>
      </div>
      {distinto && <p className="mt-0.5 text-right text-xs text-muted">Con tus facturas saldría <Importe valor={estimado} /></p>}
    </div>
  )
}

export default function Autonomo() {
  const actual = new Date().getFullYear()
  const [anio, setAnio] = useState(actual)
  const [dialogo, setDialogo] = useState<'factura' | 'gasto' | null>(null)
  const { data: d, isLoading, error } = useQuery({ queryKey: ['autonomo', anio], queryFn: () => api.get<Datos>(`/autonomo?anio=${anio}`) })
  const borrar = useAccion(({ tipo, id }: { tipo: string; id: number }) => api.del(`/autonomo/${tipo}/${id}`), 'Borrado')
  const trimActual = anio === actual ? Math.floor(new Date().getMonth() / 3) + 1 : 0
  const maxCliente = Math.max(1, ...(d?.por_cliente.map((c) => c.base) ?? [1]))

  return (
    <>
      <Cabecera titulo="Autónomo" subtitulo={d ? (d.ingresos_declarados !== null
        ? `${eur(d.ingresos_declarados)} de ingresos declarados en ${anio} (130 hasta el ${d.ultimo_130}T)`
        : `${eur(d.total_facturado)} facturados en ${anio}`) : undefined}>
        <Selector value={anio} onChange={(e) => setAnio(Number(e.target.value))} aria-label="Año" className="w-28">
          {[actual + 1, actual, actual - 1, actual - 2].map((a) => <option key={a} value={a}>{a}</option>)}
        </Selector>
        <Boton variante="secundario" onClick={() => setDialogo('gasto')}><Plus size={16} />Gasto</Boton>
        <Boton onClick={() => setDialogo('factura')}><Plus size={16} />Factura</Boton>
      </Cabecera>

      {isLoading ? <Cargando /> : error ? <ErrorCarga error={error} /> : d && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {d.trimestres.map((t) => (
              <Tarjeta key={t.trimestre} className={t.trimestre === trimActual ? 'ring-2 ring-accent' : ''}
                titulo={`${t.trimestre}º trimestre`} accion={<span className="text-xs text-muted">{t.plazo}</span>}>
                <dl className="space-y-2 text-sm">
                  <Modelo nombre="IVA (303)" valor={t.iva_resultado} fuente={t.iva_fuente} estimado={t.iva_estimado} />
                  <Modelo nombre="IRPF (130)" valor={t.irpf_resultado} fuente={t.irpf_fuente} estimado={t.irpf_estimado} exento={t.exento_130} />
                  {t.ingresos_acumulados !== null
                    ? <div className="flex justify-between gap-2 border-t border-line pt-2 text-xs"><dt className="text-muted">Ingresos acumulados (130)</dt><dd><Importe valor={t.ingresos_acumulados} /></dd></div>
                    : <div className="flex justify-between gap-2 border-t border-line pt-2 text-xs"><dt className="text-muted">Facturado</dt><dd><Importe valor={t.base} /></dd></div>}
                  <div className="flex justify-between gap-2 border-t border-line pt-2 text-xs"><dt className="text-muted">Retenciones acumuladas</dt><dd><Importe valor={t.retenciones_acumuladas} /></dd></div>
                </dl>
              </Tarjeta>
            ))}
          </div>
          {(d.pagado_iva !== 0 || d.pagado_irpf !== 0) && (
            <p className="mt-3 text-sm text-muted">Presentado en Hacienda en {anio}: <Importe valor={d.pagado_iva} /> de IVA y <Importe valor={d.pagado_irpf} /> de IRPF.
              Lo que aún no has presentado se estima con tus facturas y gastos.</p>)}
          {d.trimestres[3].notas.map((n) => <p key={n} className="mt-3 text-sm text-muted">{n}</p>)}

          <div className="mt-6 grid gap-4 lg:grid-cols-3">
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

            <Tarjeta className="lg:col-span-2" titulo="Facturas emitidas">
              {d.facturas.length ? (
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
                        <td className="text-right"><BorrarEnDosPasos onBorrar={() => borrar.mutate({ tipo: 'facturas', id: f.id })} /></td>
                      </tr>
                    ))}
                  </tbody>
                </Tabla>
              ) : <Vacio>Registra tus facturas para ver el IVA y el IRPF de cada trimestre.</Vacio>}
            </Tarjeta>
          </div>

          <Tarjeta className="mt-4" titulo="Gastos de la actividad">
            {d.gastos.length ? (
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
                      <td className="text-right"><BorrarEnDosPasos onBorrar={() => borrar.mutate({ tipo: 'gastos', id: g.id })} /></td>
                    </tr>
                  ))}
                </tbody>
              </Tabla>
            ) : <Vacio>Apunta la cuota de autónomos, la gestoría o el software: bajan tu IRPF y, si llevan IVA, también el 303.</Vacio>}
          </Tarjeta>
        </>
      )}

      <Dialogo abierto={dialogo === 'factura'} onCerrar={() => setDialogo(null)} titulo="Registrar factura">
        <FormFactura clientes={d?.clientes ?? []} onHecho={() => setDialogo(null)} />
      </Dialogo>
      <Dialogo abierto={dialogo === 'gasto'} onCerrar={() => setDialogo(null)} titulo="Registrar gasto">
        <FormGasto onHecho={() => setDialogo(null)} />
      </Dialogo>
    </>
  )
}
