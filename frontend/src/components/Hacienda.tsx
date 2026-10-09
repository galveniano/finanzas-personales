import { useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarPlus, Copy, Landmark, Percent, Receipt } from 'lucide-react'
import { api } from '../lib/api'
import { eur, eur0, fecha, hoyISO, pct } from '../lib/format'
import type { AhorroFiscal, Hacienda, LineaPendiente, PlazoHacienda } from '../lib/tipos'
import { num, useAccion, useAvisos } from '../lib/utilidades'
import { Boton, Campo, Casilla, Dato, Etiqueta, ErrorCarga, Cargando, Fila, Importe, Selector, Tarjeta } from './ui'

const ICONO: Record<LineaPendiente['tipo'], typeof Receipt> = { iva: Receipt, '130': Percent, renta: Landmark }
const QUE_ES: Record<LineaPendiente['tipo'], string> = {
  iva: 'IVA (303): el IVA que cobras en tus facturas menos el deducible de tus gastos. No es tuyo: se ingresa al cerrar el trimestre.',
  '130': 'IRPF (130): el pago a cuenta del trimestre, el 20 % del rendimiento acumulado del año menos las retenciones y lo ya pagado.',
  renta: 'Renta: lo que te saldría a pagar en junio por lo que llevas ganado este año, la del año pasado si aún no la has presentado y los plazos pendientes de una renta ya presentada.',
}

/** Desplegable discreto con el mismo aspecto en todas las tarjetas. */
function Explicacion({ resumen, children }: { resumen: string; children: ReactNode }) {
  return (
    <details className="mt-3 text-xs text-muted">
      <summary className="cursor-pointer font-medium">{resumen}</summary>
      <div className="mt-2 space-y-1.5">{children}</div>
    </details>
  )
}

/** Lo que debes a Hacienda y aún no has pagado, y la cuenta donde lo apartas. */
function Hucha({ h }: { h: Hacienda }) {
  const elegir = useAccion((cuenta_id: number | null) => api.put('/hacienda/hucha', { cuenta_id }), 'Hucha guardada')
  const { hucha } = h
  const tipos = [...new Set(h.pendiente.lineas.map((l) => l.tipo))]
  return (
    <Tarjeta titulo="Lo que debes a Hacienda">
      {h.pendiente.lineas.length ? (
        <div className="mb-4 divide-y divide-line">
          {h.pendiente.lineas.map((l) => {
            const Icono = ICONO[l.tipo]
            return (
              <Fila key={l.concepto} valor={l.importe} etiqueta={
                <span className="flex min-w-0 items-center gap-2"><Icono size={14} className="shrink-0" aria-hidden />
                  <span className="min-w-0 truncate">{l.concepto}{l.en_curso && <span className="text-xs text-muted"> · en curso</span>}</span></span>} />
            )
          })}
          <Fila etiqueta="Total hoy" valor={h.pendiente.total} fuerte />
        </div>
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
      <p className="mt-3 text-xs text-muted">«Te falta» incluye la renta de {h.renta?.anio ?? 'este año'} prevista entera ({eur(hucha.renta_prevista)}) menos lo apartado.
        Son estimaciones a partir de tus facturas y la previsión.</p>
      {tipos.length > 0 && (
        <Explicacion resumen="Qué es cada línea">
          {tipos.map((t) => <p key={t}>{QUE_ES[t]}</p>)}
          {h.pendiente.lineas.some((l) => l.en_curso) && <p>«En curso»: solo cuenta la parte del trimestre (o del año, en la renta) que ya ha pasado; la cifra crece día a día.</p>}
        </Explicacion>
      )}
    </Tarjeta>
  )
}

/** Cuota de autónomos pagada frente a la que toca por tus rendimientos reales. */
function CuotaAutonomos({ h }: { h: Hacienda }) {
  const [anioActual] = useState(() => new Date().getFullYear())
  if (!h.cuota_autonomos.length) return (
    <Tarjeta titulo="Cuota de autónomos">
      <p className="text-sm text-muted">Sube tu renta (PDF) o pon tus clientes en Ingresos para comparar la cuota que pagas con la que te toca.</p>
    </Tarjeta>
  )
  return (
    <Tarjeta titulo="Cuota de autónomos" accion={<span className="text-xs text-muted">Estimación</span>}>
      <div className="grid gap-5">
        {h.cuota_autonomos.map((r) => {
          const alMes = r.a_pagar / Math.max(r.meses_hasta_regularizacion, 1)
          return (
            <div key={r.anio} className="text-sm">
              <div className="mb-1 font-medium">{r.anio} <span className="text-xs font-normal text-muted">· según {r.fuente}</span></div>
              <div>
                <Fila etiqueta="Rendimiento para cotizar" valor={<><Importe valor={r.rendimiento_computable_mes} /> al mes</>} />
                <Fila etiqueta={`Base mínima de tu tramo (${r.tramo})`} valor={<><Importe valor={r.base_minima} /> al mes</>} />
                <Fila etiqueta="Te toca" valor={<><Importe valor={r.cuota_minima_anual} /> al año como mínimo</>} />
                <Fila etiqueta={r.previsto ? 'Llevas camino de pagar' : 'Pagaste'} valor={r.cuota_pagada} />
                {r.cuota_pagada > 0 && <Fila etiqueta="Base por la que cotizas" valor={<><Importe valor={r.base_cotizada_mes} /> al mes</>} />}
                {r.a_pagar > 0 && <Fila etiqueta="Puede reclamarte" valor={r.a_pagar} className="text-warn" />}
                {r.a_devolver > 0 && <Fila etiqueta="Te devolvería" valor={r.a_devolver} className="text-pos" />}
                {r.devolucion_pluriactividad > 0 && <Fila etiqueta="Devolución por pluriactividad" valor={r.devolucion_pluriactividad} className="text-pos" />}
              </div>
              {r.a_pagar > 0 && (
                <p className="mt-2 rounded-xl bg-warn-soft p-3 text-xs text-warn">
                  {r.anio >= anioActual
                    ? <>Sube la base a <strong className="cifra">{eur(r.base_minima)}</strong> en Importass y evitas una regularización de <strong className="cifra">{eur(r.a_pagar)}</strong>,
                      o deja la base y aparta <strong className="cifra">{eur(alMes)}</strong> al mes en la hucha hasta que la Seguridad Social regularice {r.anio} (hacia noviembre de {r.anio + 1}).</>
                    : <>La base de {r.anio} ya no se puede cambiar: aparta <strong className="cifra">{eur(alMes)}</strong> al mes en la hucha para la regularización, que llegará hacia noviembre de {r.anio + 1}.</>}
                </p>
              )}
            </div>
          )
        })}
      </div>
      <p className="mt-3 text-xs text-muted">La base por la que cotizas sale de la cuota que pagas (al {pct(h.cuota_autonomos[0].tipo)} de tipo); si no vemos cargos de la cuota en el banco, cuenta como si no pagaras nada. La Seguridad Social regulariza cada año con tu renta:
        si cotizaste por debajo de la base mínima de tu tramo te cobra la diferencia. Como también cotizas por la nómina, te devuelve de oficio la mitad de lo que pases del tope.
        Cifras orientativas: confírmalas con tu gestor.</p>
    </Tarjeta>
  )
}

/** Cuánto baja la renta aportando a pensiones o apuntando más gastos, y lo de la renta que la app no ve. */
function AhorroFiscalTarjeta({ h }: { h: Hacienda }) {
  const sup = h.supuestos
  const [pensiones, setPensiones] = useState(() => String(sup.aportacion_pensiones_anio || ''))
  const [ppes, setPpes] = useState(() => String(sup.aportacion_ppes_anio || ''))
  const [gastos, setGastos] = useState('')
  const consulta = `pensiones=${num(pensiones) ?? 0}&ppes=${num(ppes) ?? 0}&gastos=${num(gastos) ?? 0}`
  const { data: a, error } = useQuery({ queryKey: ['ahorro', consulta], queryFn: () => api.get<AhorroFiscal>(`/hacienda/ahorro?${consulta}`),
    placeholderData: (previo) => previo })
  const guardar = useAccion((v: Record<string, unknown>) => api.put('/hacienda/supuestos', v), 'Guardado en la previsión')
  const sinCambios = (num(pensiones) ?? 0) === (sup.aportacion_pensiones_anio ?? 0) && (num(ppes) ?? 0) === (sup.aportacion_ppes_anio ?? 0)
  const aportado = (num(pensiones) ?? 0) + (num(ppes) ?? 0)
  return (
    <Tarjeta titulo="Pagar menos en la renta">
      {h.renta && <p className="mb-3 text-sm">Cada euro más que ganas paga ahora un <strong className="cifra">{pct(h.renta.tipo_marginal)}</strong>,
        así que cada euro que te deduces te ahorra casi lo mismo.</p>}
      <div className="grid gap-3 sm:grid-cols-3">
        <Campo etiqueta="Plan de pensiones (€/año)" inputMode="decimal" value={pensiones} onChange={(e) => setPensiones(e.target.value)}
          ayuda={a ? `Hasta ${eur0(a.limites.pensiones)}` : 'Según el límite legal'} />
        <Campo etiqueta="Plan de empleo de autónomos" inputMode="decimal" value={ppes} onChange={(e) => setPpes(e.target.value)}
          ayuda={a ? `Hasta ${eur0(a.limites.ppes)} más, y entre los dos no más del ${pct(a.limites.pct_rendimientos, 0)} de lo que ganas trabajando` : 'Según el límite legal'} />
        <Campo etiqueta="Gastos de la actividad de más" inputMode="decimal" value={gastos} onChange={(e) => setGastos(e.target.value)} ayuda="Equipo, software, gestoría…" />
      </div>
      {error ? <ErrorCarga error={error} /> : a ? (
        <p className="mt-3 text-sm">
          {Math.abs(a.ahorro) < 0.005
            ? <>Tu renta de {a.anio} se queda en <strong className="cifra">{eur(a.cuota_sin)}</strong>: es lo que ya cuenta la previsión.</>
            : a.ahorro > 0
              ? <>Tu renta de {a.anio} bajaría <strong className="cifra text-pos">{eur(a.ahorro)}</strong> (de {eur(a.cuota_sin)} a {eur(a.cuota_con)}).</>
              : <>Tu renta de {a.anio} subiría <strong className="cifra text-neg">{eur(-a.ahorro)}</strong> (de {eur(a.cuota_sin)} a {eur(a.cuota_con)}): aportas menos de lo que tienes guardado.</>}
          {a.reduccion_aplicada < aportado - 0.005 && ' Parte de lo aportado pasa del límite y no reduce nada.'}
        </p>
      ) : <Cargando />}
      <div className="mt-3 flex flex-wrap gap-2">
        <Boton variante="secundario" disabled={guardar.isPending || sinCambios}
          onClick={() => guardar.mutate({ ...sup, aportacion_pensiones_anio: num(pensiones) ?? 0, aportacion_ppes_anio: num(ppes) ?? 0 })}>
          {sinCambios ? 'Ya cuentan en la previsión' : 'Contar estas aportaciones en la previsión'}</Boton>
      </div>
      <p className="mt-3 text-xs text-muted">La cuota de partida es la de la renta estimada de arriba, con lo que ya tienes guardado{a && a.reduccion_guardada > 0 ? ` (${eur(a.reduccion_guardada)} de reducción)` : ''}.
        Estimación con la escala general del IRPF.</p>

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
          <Casilla etiqueta="Fracciono la renta: 60 % en junio y 40 % en noviembre" name="fraccionar" defaultChecked={!!sup.fraccionar_renta} className="sm:col-span-2" />
          <div className="flex justify-end sm:col-span-2"><Boton type="submit" disabled={guardar.isPending}>Guardar</Boton></div>
        </form>
      </div>
    </Tarjeta>
  )
}

function ListaPlazos({ plazos }: { plazos: PlazoHacienda[] }) {
  return (
    <ul className="divide-y divide-line text-sm">
      {plazos.map((p) => (
        <li key={p.fecha + p.titulo} title={p.detalle || undefined} className="flex items-start justify-between gap-3 py-1.5">
          <span className="min-w-0">
            <span className={`flex flex-wrap items-center gap-x-2 gap-y-1 ${p.vencido ? 'text-neg' : ''}`}>
              <span className="truncate">{p.titulo}</span>
              {p.presentado && <Etiqueta tono="bien">Presentado</Etiqueta>}
              {p.vencido && <Etiqueta tono="mal">Sin presentar</Etiqueta>}
            </span>
            {p.detalle && <span className="block truncate text-xs text-muted">{p.detalle}</span>}
          </span>
          <span className={`cifra whitespace-nowrap ${p.vencido ? 'text-neg' : 'text-muted'}`}>{fecha(p.fecha, { day: 'numeric', month: 'short' })}</span>
        </li>
      ))}
    </ul>
  )
}

/** Todos los plazos del año (los pasados y los lejanos, plegados) y la dirección para verlos en Google Calendar. */
function Plazos({ h }: { h: Hacienda }) {
  const avisar = useAvisos()
  const { data: enlace } = useQuery({ queryKey: ['calendario'], queryFn: () => api.get<{ ruta: string }>('/calendario/enlace') })
  const url = enlace ? `${window.location.origin}${enlace.ruta}` : ''
  const copiar = async () => {
    try { await navigator.clipboard.writeText(url); avisar('Dirección copiada') } catch { avisar('Cópiala a mano', 'error') }
  }
  const hoy = hoyISO()
  const pasados = h.plazos.filter((p) => p.fecha < hoy)
  const proximos = h.plazos.filter((p) => p.fecha >= hoy)
  const sinPresentar = pasados.filter((p) => p.vencido).length
  return (
    <Tarjeta titulo="Plazos">
      {pasados.length > 0 && (
        <details className="mb-2">
          <summary className={`cursor-pointer text-xs font-medium ${sinPresentar ? 'text-neg' : 'text-muted'}`}>
            Ya pasados este año ({pasados.length}){sinPresentar > 0 && `, ${sinPresentar} sin presentar`}</summary>
          <ListaPlazos plazos={pasados} />
        </details>
      )}
      {proximos.length ? <ListaPlazos plazos={proximos.slice(0, 6)} /> : <p className="text-sm text-muted">No hay más plazos a la vista.</p>}
      {proximos.length > 6 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-medium text-muted">Más adelante ({proximos.length - 6})</summary>
          <ListaPlazos plazos={proximos.slice(6)} />
        </details>
      )}
      <p className="mt-3 text-xs text-muted">«Presentado» sale de las declaraciones que subes; si estás exento del 130, con el 303 basta.</p>
      {url && <div className="mt-4 rounded-xl bg-panel-2 p-3 text-xs">
        <p className="mb-2 flex items-center gap-1.5 font-medium"><CalendarPlus size={14} />Tenlos en Google Calendar</p>
        <p className="text-muted">En Google Calendar: Otros calendarios, + , Desde URL, y pega esta dirección. Trae los plazos de Hacienda, tus pagos previstos y las llamadas de capital
          (también tus objetivos con fecha y cuándo caduca el permiso del banco), avisa unos días antes y se actualiza solo.</p>
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
  return (
    <section className="mt-8 scroll-mt-4" id="hucha">
      <h2 className="mb-3 text-lg font-semibold">Lo que debes, tu cuota y cómo pagar menos</h2>
      {error ? <ErrorCarga error={error} /> : !h ? <Cargando /> : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Hucha h={h} />
          <CuotaAutonomos h={h} />
          <AhorroFiscalTarjeta h={h} />
          <Plazos h={h} />
        </div>
      )}
    </section>
  )
}
