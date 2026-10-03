import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, Plus } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../lib/api'
import { diasHasta, eur, eurK, fecha, hoyISO, mesCorto } from '../lib/format'
import type { Planificacion as Datos } from '../lib/tipos'
import { Barra, Boton, Cabecera, Campo, Cargando, Dato, Dialogo, Etiqueta, ErrorCarga, Formulario, Importe, Selector, Tarjeta, Vacio, num, useAccion } from '../components/ui'

const TIPO: Record<string, string> = { boda: 'Boda', viaje: 'Viaje', casa: 'Casa', colchon: 'Colchón', otro: 'Objetivo' }

function pagosPorMes(d: Datos) {
  const meses = new Map<string, number>()
  for (const p of d.pagos) {
    if (p.pagado) continue
    const k = p.fecha.slice(0, 7)
    meses.set(k, (meses.get(k) ?? 0) + p.importe)
  }
  return [...meses.entries()].sort().map(([mes, importe]) => ({ mes, importe }))
}

export default function Planificacion() {
  const [dialogo, setDialogo] = useState<'objetivo' | 'pago' | null>(null)
  const { data: d, isLoading, error } = useQuery({ queryKey: ['planificacion'], queryFn: () => api.get<Datos>('/planificacion') })
  const crearObjetivo = useAccion((v: Record<string, string>) => api.post('/objetivos', {
    nombre: v.nombre, tipo: v.tipo, fecha_objetivo: v.fecha_objetivo || null,
    importe_objetivo: num(v.importe_objetivo) ?? 0, ahorrado: num(v.ahorrado) ?? 0,
  }).then(() => setDialogo(null)), 'Objetivo creado')
  const crearPago = useAccion((v: Record<string, string>) => api.post('/pagos', {
    concepto: v.concepto, fecha: v.fecha, importe: num(v.importe),
    objetivo_id: v.objetivo_id ? Number(v.objetivo_id) : null, activo_id: v.activo_id ? Number(v.activo_id) : null,
    pagado: v.pagado === 'on',
  }).then(() => setDialogo(null)), 'Pago previsto guardado')
  const marcar = useAccion(({ id, pagado }: { id: number; pagado: boolean }) => api.patch(`/pagos/${id}`, { pagado }))

  if (isLoading) return <Cargando />
  if (error) return <ErrorCarga error={error} />
  if (!d) return null
  const porMes = pagosPorMes(d)
  const margen = d.liquidez - d.pendiente_12_meses

  return (
    <>
      <Cabecera titulo="Planificación" subtitulo="Bodas, viajes, la casa nueva y lo que viene">
        <Boton variante="secundario" onClick={() => setDialogo('pago')}><Plus size={16} />Pago previsto</Boton>
        <Boton onClick={() => setDialogo('objetivo')}><Plus size={16} />Objetivo</Boton>
      </Cabecera>

      <Tarjeta>
        <div className="grid gap-6 sm:grid-cols-3">
          <Dato etiqueta="Liquidez hoy" valor={eur(d.liquidez)} nota="Cuentas corrientes y de ahorro" />
          <Dato etiqueta="Pagos en 12 meses" valor={eur(d.pendiente_12_meses)} />
          <Dato etiqueta="Margen" valor={eur(margen)} tono={margen < 0 ? 'neg' : 'pos'}
            nota={margen < 0 ? 'Con lo que tienes hoy no llegas: cuenta con lo que ahorres estos meses.' : 'Te sobra aunque no ahorres nada más.'} />
        </div>
        {porMes.length > 0 && (
          <div className="mt-6 h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={porMes} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--line)" />
                <XAxis dataKey="mes" tickFormatter={(m) => `${mesCorto(m)} ${m.slice(2, 4)}`} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={eurK} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} width={68} />
                <Tooltip contentStyle={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, fontSize: 12 }}
                  cursor={{ fill: 'var(--panel-2)' }} formatter={(v) => [eur(Number(v)), 'Pagos pendientes']} labelFormatter={(m) => `${mesCorto(String(m))} ${String(m).slice(0, 4)}`} />
                <Bar dataKey="importe" fill="var(--chart-3)" radius={[4, 4, 0, 0]} maxBarSize={36} />
              </BarChart>
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
                  <Etiqueta tono="acento">{TIPO[o.tipo] ?? o.tipo}</Etiqueta>
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
                    {!p.pagado && <Etiqueta tono={dias < 0 ? 'mal' : dias <= 30 ? 'aviso' : 'neutro'}>{dias < 0 ? 'Vencido' : `${dias} días`}</Etiqueta>}
                    <Importe valor={p.importe} />
                    <Boton variante={p.pagado ? 'secundario' : 'fantasma'} className="px-2 py-1 text-xs" onClick={() => marcar.mutate({ id: p.id, pagado: !p.pagado })}>
                      <Check size={14} />{p.pagado ? 'Pagado' : 'Marcar'}
                    </Boton>
                  </div>
                </li>
              )
            })}
          </ol>
        ) : <Vacio>Apunta aquí los plazos de la obra nueva, la señal de la boda o el viaje.</Vacio>}
      </Tarjeta>

      <Dialogo abierto={dialogo === 'objetivo'} onCerrar={() => setDialogo(null)} titulo="Nuevo objetivo">
        <Formulario onEnviar={(v) => crearObjetivo.mutateAsync(v)}>
          <Campo etiqueta="Nombre" name="nombre" required placeholder="Boda" />
          <Selector etiqueta="Tipo" name="tipo" defaultValue="boda">
            <option value="boda">Boda</option><option value="viaje">Viaje</option><option value="casa">Casa</option>
            <option value="colchon">Colchón de seguridad</option><option value="otro">Otro</option>
          </Selector>
          <Campo etiqueta="Fecha" name="fecha_objetivo" type="date" />
          <Campo etiqueta="Presupuesto (€)" name="importe_objetivo" inputMode="decimal" required />
          <Campo etiqueta="Ya ahorrado (€)" name="ahorrado" inputMode="decimal" defaultValue="0" />
        </Formulario>
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
