import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, Pencil, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../lib/api'
import { diasHasta, eur, eurK, fecha, hoyISO } from '../lib/format'
import type { Planificacion as Datos, Prevision } from '../lib/tipos'
import { num, useAccion } from '../lib/utilidades'
import { Barra, BorrarEnDosPasos, Boton, Cabecera, Campo, Cargando, Dato, Dialogo, Etiqueta, ErrorCarga, Formulario, Importe, Selector, Tabla, Tarjeta, Vacio } from '../components/ui'

const nombreMes = (clave: string) => fecha(`${clave}-01`, { month: 'short', year: '2-digit' })
const cuandoVence = (dias: number) => (dias < 0 ? 'Vencido' : dias === 0 ? 'Hoy' : dias === 1 ? 'Mañana' : `${dias} días`)
const ahorroTexto = (v: number) => (v < 0 ? `Gastando unos ${eur(-v)} más de lo que entra al mes` : `Ahorrando unos ${eur(v)} al mes`)
const TIPO: Record<string, string> = { boda: 'Boda', viaje: 'Viaje', casa: 'Casa', colchon: 'Colchón', otro: 'Objetivo' }

export default function Plan() {
  const [dialogo, setDialogo] = useState<'objetivo' | 'pago' | null>(null)
  const [editando, setEditando] = useState<Datos['objetivos'][number] | null>(null)
  const { data: d, isLoading, error } = useQuery({ queryKey: ['planificacion'], queryFn: () => api.get<Datos>('/planificacion') })
  const { data: prev } = useQuery({ queryKey: ['prevision'], queryFn: () => api.get<Prevision>('/prevision') })
  const guardarObjetivo = useAccion((v: Record<string, string>) => {
    const datos = { nombre: v.nombre, tipo: v.tipo, fecha_objetivo: v.fecha_objetivo || null,
      importe_objetivo: num(v.importe_objetivo) ?? 0, ahorrado: num(v.ahorrado) ?? 0 }
    return (editando ? api.patch(`/objetivos/${editando.id}`, datos) : api.post('/objetivos', datos))
      .then(() => { setDialogo(null); setEditando(null) })
  }, 'Objetivo guardado')
  const borrarObjetivo = useAccion((id: number) => api.del(`/objetivos/${id}`), 'Objetivo borrado')
  const borrarPago = useAccion((id: number) => api.del(`/pagos/${id}`), 'Pago borrado')
  const crearPago = useAccion((v: Record<string, string>) => api.post('/pagos', {
    concepto: v.concepto, fecha: v.fecha, importe: num(v.importe),
    objetivo_id: v.objetivo_id ? Number(v.objetivo_id) : null, activo_id: v.activo_id ? Number(v.activo_id) : null,
    pagado: v.pagado === 'on',
  }).then(() => setDialogo(null)), 'Pago previsto guardado')
  const marcar = useAccion(({ id, pagado }: { id: number; pagado: boolean }) => api.patch(`/pagos/${id}`, { pagado }))

  if (isLoading) return <Cargando />
  if (error) return <ErrorCarga error={error} />
  if (!d) return null
  const sinSupuestos = prev && !prev.supuestos.nomina && !prev.supuestos.clientes.length
  const ultimo = prev?.meses[prev.meses.length - 1]
  const impuestos = prev?.meses.reduce((s, m) => s + m.total_impuestos, 0) ?? 0

  return (
    <>
      <Cabecera titulo="Plan" subtitulo="El dinero que tendrás, tus objetivos y los pagos que vienen">
        <Boton variante="secundario" onClick={() => setDialogo('pago')}><Plus size={16} />Pago previsto</Boton>
        <Boton onClick={() => setDialogo('objetivo')}><Plus size={16} />Objetivo</Boton>
      </Cabecera>

      <Tarjeta>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <Dato etiqueta="Tienes hoy" valor={eur(d.liquidez)} nota="Cuentas corrientes y de ahorro" />
          <Dato etiqueta="Pagos en 12 meses" valor={eur(d.pendiente_12_meses)}
            nota={d.financiado_hipoteca ? `Sin los ${eur(d.financiado_hipoteca)} que pone la hipoteca prevista` : 'Los de abajo'} />
          <Dato etiqueta="Impuestos en 12 meses" valor={sinSupuestos || !prev ? '—' : eur(impuestos)} nota="IVA, 130 y renta" />
          {ultimo && !sinSupuestos
            ? <Dato etiqueta={`Tendrás en ${fecha(`${ultimo.mes}-01`, { month: 'long', year: 'numeric' })}`} valor={eur(ultimo.liquidez)}
                tono={ultimo.liquidez < 0 ? 'neg' : 'pos'} nota={ahorroTexto((ultimo.liquidez - prev!.liquidez_hoy) / prev!.meses.length)} />
            : <Dato etiqueta="Tendrás en un año" valor="—" nota={<Link to="/ingresos" className="text-accent">Pon tu sueldo y tarifas</Link>} />}
        </div>
        {prev && !sinSupuestos && (
          <div className="mt-6 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={prev.meses} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--line)" />
                <XAxis dataKey="mes" tickFormatter={nombreMes} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis yAxisId="l" tickFormatter={eurK} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} width={68} />
                <YAxis yAxisId="n" orientation="right" hide />
                <Tooltip contentStyle={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, fontSize: 12 }}
                  cursor={{ fill: 'var(--panel-2)' }} labelFormatter={(v) => nombreMes(String(v))}
                  formatter={(v, n) => [eur(Number(v)), n === 'neto' ? 'Ahorro del mes' : 'Dinero disponible']} />
                <Bar yAxisId="n" dataKey="neto" fill="var(--chart-2)" radius={[4, 4, 0, 0]} maxBarSize={24} />
                <Line yAxisId="l" dataKey="liquidez" stroke="var(--chart-1)" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </Tarjeta>

      <h2 className="mt-8 mb-3 text-lg font-semibold">Objetivos</h2>
      {d.objetivos.length ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {d.objetivos.map((o) => {
            const pct = o.importe_objetivo ? Math.round((o.ahorrado / o.importe_objetivo) * 100) : 0
            return (
              <Tarjeta key={o.id}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate font-semibold">{o.nombre}</div>
                    <div className="text-xs text-muted">{o.fecha_objetivo ? fecha(o.fecha_objetivo, { day: 'numeric', month: 'long', year: 'numeric' }) : 'Sin fecha'}</div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <Etiqueta tono="acento">{TIPO[o.tipo] ?? o.tipo}</Etiqueta>
                    <Boton variante="fantasma" className="px-2 py-1" aria-label="Editar" onClick={() => { setEditando(o); setDialogo('objetivo') }}><Pencil size={14} /></Boton>
                    <BorrarEnDosPasos etiqueta={`el objetivo ${o.nombre}`} disabled={borrarObjetivo.isPending} onBorrar={() => borrarObjetivo.mutate(o.id)} />
                  </div>
                </div>
                <div className="mt-4 flex items-baseline justify-between gap-2">
                  <span className="cifra text-xl font-medium">{eur(o.ahorrado)}</span>
                  <span className="cifra text-xs text-muted">de {eur(o.importe_objetivo)} · {pct} %</span>
                </div>
                <div className="mt-2"><Barra valor={o.ahorrado} max={o.importe_objetivo} /></div>
                {o.ahorro_mensual != null && (
                  <p className="mt-3 text-sm">Aparta <strong className="cifra">{eur(o.ahorro_mensual)}</strong> al mes para llegar.</p>
                )}
              </Tarjeta>
            )
          })}
        </div>
      ) : <Vacio>Crea objetivos como la boda o un viaje y te digo cuánto apartar cada mes.</Vacio>}

      <h2 className="mt-8 mb-3 text-lg font-semibold">Pagos previstos</h2>
      <Tarjeta>
        {d.pagos.length ? (
          <ol className="relative space-y-1 border-l border-line pl-5">
            {d.pagos.map((p) => {
              const dias = diasHasta(p.fecha)
              return (
                <li key={p.id} className="relative flex flex-wrap items-center justify-between gap-3 py-2">
                  <span className={`absolute top-1/2 -left-[27px] size-3 -translate-y-1/2 rounded-full border-2 ${p.pagado ? 'border-accent bg-accent' : 'border-line bg-panel'}`} />
                  <div className="min-w-0">
                    <div className={`font-medium ${p.pagado ? 'text-muted line-through' : ''}`}>{p.concepto}</div>
                    <div className="text-xs text-muted">{fecha(p.fecha, { day: 'numeric', month: 'long', year: 'numeric' })}{(p.inmueble || p.objetivo || p.inversion) && ` · ${p.inmueble ?? p.objetivo ?? p.inversion}`}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    {!p.pagado && <Etiqueta tono={dias < 0 ? 'mal' : dias <= 30 ? 'aviso' : 'neutro'}>{cuandoVence(dias)}</Etiqueta>}
                    <Importe valor={p.importe} />
                    <Boton variante={p.pagado ? 'secundario' : 'fantasma'} className="px-2 py-1 text-xs" disabled={marcar.isPending} onClick={() => marcar.mutate({ id: p.id, pagado: !p.pagado })}>
                      <Check size={14} />{p.pagado ? 'Pagado' : 'Marcar'}
                    </Boton>
                    <BorrarEnDosPasos etiqueta={`el pago ${p.concepto}`} disabled={borrarPago.isPending} onBorrar={() => borrarPago.mutate(p.id)} />
                  </div>
                </li>
              )
            })}
          </ol>
        ) : <Vacio>Apunta aquí los plazos de la obra nueva, la señal de la boda o el viaje.</Vacio>}
      </Tarjeta>


      {prev && !sinSupuestos && (
        <details className="mt-8 rounded-2xl border border-line bg-panel p-5">
          <summary className="cursor-pointer text-[15px] font-semibold">Mes a mes</summary>
          <ul className="mt-4 divide-y divide-line sm:hidden">
            {prev.meses.map((m) => (
              <li key={m.mes} className="py-3 text-sm first:pt-0">
                <div className="mb-1.5 flex items-baseline justify-between gap-2">
                  <span className="font-medium capitalize">{nombreMes(m.mes)}</span>
                  <span className="text-xs text-muted">Liquidez <Importe valor={m.liquidez} /></span>
                </div>
                <dl className="space-y-1">
                  {m.nomina ? <div className="flex justify-between gap-3"><dt className="text-muted">Nómina</dt><dd><Importe valor={m.nomina} /></dd></div> : null}
                  {m.cobros ? <div className="flex justify-between gap-3"><dt className="text-muted">Clientes</dt><dd><Importe valor={m.cobros} /></dd></div> : null}
                  {m.alquiler ? <div className="flex justify-between gap-3"><dt className="text-muted">Alquiler</dt><dd><Importe valor={m.alquiler} /></dd></div> : null}
                  <div className="flex justify-between gap-3"><dt className="text-muted">Gastos</dt><dd><Importe valor={-m.gastos} /></dd></div>
                  {m.pagos_previstos ? <div className="flex justify-between gap-3"><dt className="text-muted">Pagos</dt><dd><Importe valor={-m.pagos_previstos} /></dd></div> : null}
                  {m.impuestos.map((i) => (
                    <div key={i.concepto} className="flex justify-between gap-3">
                      <dt className="text-muted">{i.concepto}{i.presentado && <> <Etiqueta tono="bien">Presentado</Etiqueta></>}</dt>
                      <dd><Importe valor={-i.importe} /></dd>
                    </div>
                  ))}
                  <div className="flex justify-between gap-3 font-medium"><dt>Ahorro</dt><dd><Importe valor={m.neto} /></dd></div>
                </dl>
              </li>
            ))}
          </ul>
          <div className="mt-4 hidden sm:block">
            <Tabla>
              <thead><tr><th>Mes</th><th className="num">Nómina</th><th className="num">Clientes</th><th className="num">Alquiler</th>
                <th className="num">Gastos</th><th className="num">Pagos</th><th>Impuestos</th><th className="num">Ahorro</th><th className="num">Liquidez</th></tr></thead>
              <tbody>
                {prev.meses.map((m) => (
                  <tr key={m.mes}>
                    <td className="whitespace-nowrap capitalize">{nombreMes(m.mes)}</td>
                    <td className="num"><Importe valor={m.nomina} /></td>
                    <td className="num" title={`Facturado ${eur(m.facturado)} + IVA ${eur(m.iva)} − retención ${eur(m.retenciones)}`}><Importe valor={m.cobros} /></td>
                    <td className="num"><Importe valor={m.alquiler} /></td>
                    <td className="num"><Importe valor={-m.gastos} /></td>
                    <td className="num">{m.pagos_previstos ? <Importe valor={-m.pagos_previstos} /> : ''}</td>
                    <td className="text-xs">{m.impuestos.map((i) => (
                      <div key={i.concepto} className="flex justify-between gap-2 whitespace-nowrap">
                        <span className="text-muted">{i.concepto}{i.presentado && <> <Etiqueta tono="bien">Presentado</Etiqueta></>}</span>
                        <Importe valor={-i.importe} />
                      </div>))}</td>
                    <td className="num font-medium"><Importe valor={m.neto} /></td>
                    <td className="num"><Importe valor={m.liquidez} /></td>
                  </tr>
                ))}
              </tbody>
            </Tabla>
          </div>
          <div>
            <p className="mt-3 text-xs text-muted">Clientes es lo que cobras: base más IVA menos retención. El IVA y el 130 de cada trimestre se pagan el mes siguiente; la renta, en junio.
              «Pagos» son los pagos previstos de arriba.</p>
          </div>
        </details>
      )}

      <Dialogo abierto={dialogo === 'objetivo'} onCerrar={() => { setDialogo(null); setEditando(null) }} titulo={editando ? 'Editar objetivo' : 'Nuevo objetivo'}>
        {dialogo === 'objetivo' && <Formulario key={editando?.id ?? 'nuevo'} onEnviar={(v) => guardarObjetivo.mutateAsync(v)}>
          <Campo etiqueta="Nombre" name="nombre" required placeholder="Boda" defaultValue={editando?.nombre ?? ''} />
          <Selector etiqueta="Tipo" name="tipo" defaultValue={editando?.tipo ?? 'boda'}>
            <option value="boda">Boda</option><option value="viaje">Viaje</option><option value="casa">Casa</option>
            <option value="colchon">Colchón de seguridad</option><option value="otro">Otro</option>
          </Selector>
          <Campo etiqueta="Fecha" name="fecha_objetivo" type="date" defaultValue={editando?.fecha_objetivo ?? ''} />
          <Campo etiqueta="Presupuesto (€)" name="importe_objetivo" inputMode="decimal" required defaultValue={editando?.importe_objetivo ?? ''} />
          <Campo etiqueta="Ya ahorrado (€)" name="ahorrado" inputMode="decimal" defaultValue={editando?.ahorrado ?? 0} />
        </Formulario>}
      </Dialogo>
      <Dialogo abierto={dialogo === 'pago'} onCerrar={() => setDialogo(null)} titulo="Nuevo pago previsto">
        <Formulario onEnviar={(v) => crearPago.mutateAsync(v)}>
          <Campo etiqueta="Concepto" name="concepto" required className="sm:col-span-2" placeholder="Plazo promotora" />
          <Campo etiqueta="Fecha" name="fecha" type="date" defaultValue={hoyISO()} required />
          <Campo etiqueta="Importe (€)" name="importe" inputMode="decimal" required />
          <Selector etiqueta="Inmueble" name="activo_id" defaultValue="">
            <option value="">Ninguno</option>{d.inmuebles.map((i) => <option key={i.id} value={i.id}>{i.nombre}</option>)}
          </Selector>
          <Selector etiqueta="Objetivo" name="objetivo_id" defaultValue="">
            <option value="">Ninguno</option>{d.objetivos.map((o) => <option key={o.id} value={o.id}>{o.nombre}</option>)}
          </Selector>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="pagado" className="size-4 accent-[var(--accent)]" />Ya está pagado</label>
        </Formulario>
      </Dialogo>
    </>
  )
}
