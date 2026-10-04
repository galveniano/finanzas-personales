import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarPlus, Copy } from 'lucide-react'
import { api } from '../lib/api'
import { eur, fecha } from '../lib/format'
import type { AhorroFiscal, Hacienda } from '../lib/tipos'
import { num, useAccion, useAvisos } from '../lib/utilidades'
import { Boton, Campo, Dato, ErrorCarga, Cargando, Importe, Selector, Tarjeta } from './ui'

/** Lo que debes a Hacienda y aún no has pagado, y la cuenta donde lo apartas. */
function Hucha({ h }: { h: Hacienda }) {
  const elegir = useAccion((cuenta_id: number | null) => api.put('/hacienda/hucha', { cuenta_id }), 'Hucha guardada')
  const { hucha } = h
  return (
    <Tarjeta titulo="Lo que debes a Hacienda">
      {h.pendiente.lineas.length ? (
        <ul className="mb-4 divide-y divide-line text-sm">
          {h.pendiente.lineas.map((l) => (
            <li key={l.concepto} className="flex justify-between gap-3 py-1.5">
              <span>{l.concepto}{l.en_curso && <span className="text-xs text-muted"> · en curso</span>}</span>
              <Importe valor={l.importe} />
            </li>
          ))}
          <li className="flex justify-between gap-3 py-1.5 font-semibold"><span>Total hoy</span><Importe valor={h.pendiente.total} /></li>
        </ul>
      ) : <p className="mb-4 text-sm text-muted">Ahora mismo no debes nada a Hacienda.</p>}
      <Selector etiqueta="Cuenta donde lo apartas (la hucha)" value={hucha.cuenta_id ?? ''} disabled={elegir.isPending}
        onChange={(e) => elegir.mutate(e.target.value ? Number(e.target.value) : null)}>
        <option value="">Ninguna</option>
        {h.cuentas.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
      </Selector>
      <div className="mt-4 flex flex-wrap gap-x-8 gap-y-3">
        {hucha.apartado != null && <Dato etiqueta="Tienes apartado" valor={eur(hucha.apartado)} />}
        <Dato etiqueta="Te falta" valor={eur(hucha.falta)} />
        <Dato etiqueta="Aparta al mes" valor={eur(hucha.al_mes)} nota={`durante ${hucha.meses_hasta_junio} meses, hasta la renta de junio`} />
      </div>
      <p className="mt-3 text-xs text-muted">Incluye la renta de {h.renta?.anio ?? 'este año'} prevista entera ({eur(hucha.renta_prevista)}).
        El IVA que cobras no es tuyo: va al 303.</p>
    </Tarjeta>
  )
}

/** Cuota de autónomos pagada frente a la que toca por tus rendimientos reales. */
function CuotaAutonomos({ h }: { h: Hacienda }) {
  if (!h.cuota_autonomos.length) return (
    <Tarjeta titulo="Cuota de autónomos">
      <p className="text-sm text-muted">Sube tu renta (PDF) o pon tus clientes en Ingresos para comparar la cuota que pagas con la que te toca.</p>
    </Tarjeta>
  )
  return (
    <Tarjeta titulo="Cuota de autónomos" accion={<span className="text-xs text-muted">Estimación</span>}>
      <div className="grid gap-4">
        {h.cuota_autonomos.map((r) => (
          <div key={r.anio} className="text-sm">
            <div className="mb-1 font-medium">{r.anio} <span className="text-xs font-normal text-muted">· según {r.fuente}</span></div>
            <dl className="space-y-1">
              <div className="flex justify-between gap-3"><dt className="text-muted">Rendimiento para cotizar</dt><dd><Importe valor={r.rendimiento_computable_mes} /> al mes</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-muted">Te toca (tramo {r.tramo})</dt><dd><Importe valor={r.cuota_minima_anual} /> al año como mínimo</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-muted">{r.previsto ? 'Llevas camino de pagar' : 'Pagaste'}</dt><dd><Importe valor={r.cuota_pagada} /></dd></div>
              {r.a_pagar > 0 && <div className="flex justify-between gap-3 text-warn"><dt>Puede reclamarte</dt><dd><Importe valor={r.a_pagar} /></dd></div>}
              {r.a_devolver > 0 && <div className="flex justify-between gap-3 text-pos"><dt>Te devolvería</dt><dd><Importe valor={r.a_devolver} /></dd></div>}
              {r.devolucion_pluriactividad > 0 && <div className="flex justify-between gap-3 text-pos"><dt>Devolución por pluriactividad</dt><dd><Importe valor={r.devolucion_pluriactividad} /></dd></div>}
            </dl>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-muted">La Seguridad Social regulariza cada año con tu renta: si cotizaste por debajo de tu tramo te cobra la diferencia.
        Como también cotizas por la nómina, te devuelve de oficio la mitad de lo que pases del tope. Cifras orientativas: confírmalas con tu gestor.
        Para no llevarte el susto, sube la base en Importass.</p>
    </Tarjeta>
  )
}

/** Cuánto baja la renta aportando a pensiones o apuntando más gastos, y lo de la renta que la app no ve. */
function AhorroFiscalTarjeta({ h }: { h: Hacienda }) {
  const [pensiones, setPensiones] = useState('1500')
  const [ppes, setPpes] = useState('')
  const [gastos, setGastos] = useState('')
  const consulta = `pensiones=${num(pensiones) ?? 0}&ppes=${num(ppes) ?? 0}&gastos=${num(gastos) ?? 0}`
  const { data: a, error } = useQuery({ queryKey: ['ahorro', consulta], queryFn: () => api.get<AhorroFiscal>(`/hacienda/ahorro?${consulta}`),
    placeholderData: (previo) => previo })
  const guardar = useAccion((v: Record<string, unknown>) => api.put('/hacienda/supuestos', v), 'Guardado en la previsión')
  const sup = h.supuestos
  return (
    <Tarjeta titulo="Pagar menos en la renta">
      {h.renta && <p className="mb-3 text-sm">Cada euro más que ganas paga ahora un <strong className="cifra">{h.renta.tipo_marginal.toLocaleString('es-ES')} %</strong>,
        así que cada euro que te deduces te ahorra casi lo mismo.</p>}
      <div className="grid gap-3 sm:grid-cols-3">
        <Campo etiqueta="Plan de pensiones (€/año)" inputMode="decimal" value={pensiones} onChange={(e) => setPensiones(e.target.value)} ayuda="Hasta 1.500 €" />
        <Campo etiqueta="Plan de empleo de autónomos" inputMode="decimal" value={ppes} onChange={(e) => setPpes(e.target.value)} ayuda="Hasta 4.250 € más" />
        <Campo etiqueta="Gastos de la actividad de más" inputMode="decimal" value={gastos} onChange={(e) => setGastos(e.target.value)} ayuda="Equipo, software, gestoría…" />
      </div>
      {error ? <ErrorCarga error={error} /> : a ? (
        <p className="mt-3 text-sm">Tu renta de {a.anio} bajaría <strong className="cifra text-pos">{eur(a.ahorro)}</strong> (de {eur(a.cuota_sin)} a {eur(a.cuota_con)}).
          {a.reduccion_aplicada < (num(pensiones) ?? 0) + (num(ppes) ?? 0) && ' Parte de lo aportado pasa del límite y no reduce nada.'}</p>
      ) : <Cargando />}
      <div className="mt-3 flex flex-wrap gap-2">
        <Boton variante="secundario" disabled={guardar.isPending}
          onClick={() => guardar.mutate({ ...sup, aportacion_pensiones_anio: num(pensiones) ?? 0, aportacion_ppes_anio: num(ppes) ?? 0 })}>
          Contar estas aportaciones en la previsión</Boton>
      </div>

      <div className="mt-5 border-t border-line pt-4">
        <h3 className="mb-2 text-sm font-semibold">Lo de la renta que la app no ve</h3>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => {
          e.preventDefault()
          const fd = new FormData(e.currentTarget)
          const v = (k: string) => { const x = String(fd.get(k) ?? ''); return x.trim() === '' ? null : num(x) ?? null }
          guardar.mutate({ ...sup, rentas_ahorro_anio: v('ahorro'), imputacion_inmuebles_anio: v('imputacion'),
            fraccionar_renta: fd.get('fraccionar') === 'on' })
        }}>
          <Campo etiqueta="Intereses, dividendos y ventas de fondos (€/año)" name="ahorro" inputMode="decimal"
            defaultValue={sup.rentas_ahorro_anio ?? ''} placeholder={eur(h.origen.valor_rentas_ahorro)}
            ayuda={`Vacío: ${h.origen.rentas_ahorro_anio}. Tributa del 19 al 30 %.`} />
          <Campo etiqueta="Imputación de otras viviendas (€/año)" name="imputacion" inputMode="decimal"
            defaultValue={sup.imputacion_inmuebles_anio ?? ''} placeholder={eur(h.origen.valor_imputacion)}
            ayuda={`Vacío: ${h.origen.imputacion_inmuebles_anio}. El 1,1 % del valor catastral de tu parte.`} />
          <label className="flex items-center gap-2 text-sm sm:col-span-2">
            <input type="checkbox" name="fraccionar" defaultChecked={!!sup.fraccionar_renta} />
            Fracciono la renta: 60 % en junio y 40 % en noviembre
          </label>
          <div className="flex justify-end sm:col-span-2"><Boton type="submit" disabled={guardar.isPending}>Guardar</Boton></div>
        </form>
      </div>
    </Tarjeta>
  )
}

/** Próximos plazos y la dirección para verlos en Google Calendar. */
function Plazos({ h }: { h: Hacienda }) {
  const avisar = useAvisos()
  const { data: enlace } = useQuery({ queryKey: ['calendario'], queryFn: () => api.get<{ ruta: string }>('/calendario/enlace') })
  const url = enlace ? `${window.location.origin}${enlace.ruta}` : ''
  const copiar = async () => {
    try { await navigator.clipboard.writeText(url); avisar('Dirección copiada') } catch { avisar('Cópiala a mano', 'error') }
  }
  return (
    <Tarjeta titulo="Plazos">
      <ul className="divide-y divide-line text-sm">
        {h.plazos.slice(0, 6).map((p) => (
          <li key={p.fecha + p.titulo} className="flex justify-between gap-3 py-1.5">
            <span>{p.titulo}</span><span className="cifra whitespace-nowrap text-muted">{fecha(p.fecha, { day: 'numeric', month: 'short' })}</span>
          </li>
        ))}
      </ul>
      {url && <div className="mt-4 rounded-xl bg-panel-2 p-3 text-xs">
        <p className="mb-2 flex items-center gap-1.5 font-medium"><CalendarPlus size={14} />Tenlos en Google Calendar</p>
        <p className="text-muted">En Google Calendar: Otros calendarios, + , Desde URL, y pega esta dirección. Avisa 5 días antes y se actualiza solo.</p>
        <div className="mt-2 flex items-center gap-2">
          <code className="min-w-0 flex-1 truncate">{url}</code>
          <Boton variante="secundario" className="px-2 py-1 text-xs" onClick={copiar}><Copy size={13} />Copiar</Boton>
        </div>
      </div>}
    </Tarjeta>
  )
}

export default function SeccionHacienda() {
  const { data: h, error } = useQuery({ queryKey: ['hacienda'], queryFn: () => api.get<Hacienda>('/hacienda') })
  if (error) return <ErrorCarga error={error} />
  if (!h) return <Cargando />
  return (
    <section className="mt-8">
      <h2 className="mb-3 text-lg font-semibold">Lo que debes, tu cuota y cómo pagar menos</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        <Hucha h={h} />
        <CuotaAutonomos h={h} />
        <AhorroFiscalTarjeta h={h} />
        <Plazos h={h} />
      </div>
    </section>
  )
}
