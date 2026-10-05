import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText } from 'lucide-react'
import { api } from '../lib/api'
import { eur } from '../lib/format'
import { DIAS_SEMANA, ESTILO_DIA, MESES, diaISO, festivoDe, festivos, laborables, mesActual } from '../lib/festivos'
import type { Facturacion, Prevision } from '../lib/tipos'
import { num, useAccion } from '../lib/utilidades'
import { Boton, Campo, Importe, Selector } from './ui'

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

const ultimoDia = (mes: string) => { const [a, m] = mes.split('-').map(Number); return diaISO(mes, new Date(a, m, 0).getDate()) }

/** Calcula una factura con la tarifa del cliente y los días que marques; la crea con su documento o la usa en la previsión. */
export default function PlanificadorFactura({ onHecho }: { onHecho: () => void }) {
  const { data: p } = useQuery({ queryKey: ['prevision'], queryFn: () => api.get<Prevision>('/prevision') })
  const { data: fac } = useQuery({ queryKey: ['facturacion'], queryFn: () => api.get<Facturacion>('/facturacion') })
  const noDisp = useMemo(() => fac?.dias_no_disponibles ?? {}, [fac])
  const clientes = p?.supuestos.clientes ?? []
  const [cliente, setCliente] = useState(0)
  const [mes, setMes] = useState(mesActual())
  // null = los laborables del mes sin tus vacaciones ni los días que no puedes
  const [elegidos, setElegidos] = useState<Set<number> | null>(null)
  const marcados = elegidos ?? laborables(mes, noDisp)
  const c = clientes[cliente]
  const datosCliente = fac?.clientes.find((x) => x.nombre === c?.nombre)
  const ingles = datosCliente?.idioma === 'en'
  // Texto tal cual lo escribes (admite «,» y vacío); null = lo sugerido
  const [tarifa, setTarifa] = useState<string | null>(null)
  const [horas, setHoras] = useState<string | null>(null)
  const [numero, setNumero] = useState<string | null>(null)
  const [fechaFactura, setFechaFactura] = useState<string | null>(null)
  const [concepto, setConcepto] = useState<string | null>(null)
  const [creada, setCreada] = useState<{ id: number; numero: string } | null>(null)
  const t = tarifa != null ? num(tarifa) ?? 0 : c?.tarifa_hora ?? 0
  const h = horas != null ? num(horas) ?? 0 : c?.horas_dia ?? 8
  const comoTexto = (v: number) => String(v).replace('.', ',')
  const iva = c?.iva ?? 21, ret = c?.retencion ?? 15

  const [anio, m] = mes.split('-').map(Number)
  const fest = useMemo(() => festivos(anio), [anio])
  const { data: sugerido } = useQuery({
    queryKey: ['facturacion', 'numero', anio],
    queryFn: () => api.get<{ numero: string }>(`/facturacion/siguiente-numero?anio=${anio}`),
  })
  const huecos = (new Date(anio, m - 1, 1).getDay() + 6) % 7
  const total = new Date(anio, m, 0).getDate()
  const dias = marcados.size
  const horasTotales = Math.round(h * dias * 100) / 100
  const base = Math.round(t * horasTotales * 100) / 100
  const cuotaIva = Math.round(base * iva) / 100, retencion = Math.round(base * ret) / 100
  const planificado = c ? p?.supuestos.dias_planificados?.[c.nombre]?.[mes] : undefined
  const conceptoSugerido = ingles ? `Consulting services – ${MONTHS[m - 1]} ${anio}` : `Servicios de consultoría – ${MESES[m - 1]} de ${anio}`
  const numeroFactura = numero ?? sugerido?.numero ?? ''

  const cambiarMes = (nuevo: string) => { setMes(nuevo); setElegidos(null); setFechaFactura(null); setConcepto(null); setNumero(null) }
  const alternar = (d: number) => {
    const n = new Set(marcados)
    if (n.has(d)) n.delete(d); else n.add(d)
    setElegidos(n)
  }
  const prever = useAccion(() => api.put('/prevision/dias', { cliente: c.nombre, mes, dias }), 'Días guardados en la previsión')
  const crear = useAccion(() => api.post<{ ok: boolean; id: number }>('/autonomo/facturas', {
    numero: numeroFactura, cliente: c.nombre, fecha: fechaFactura ?? ultimoDia(mes), base, tipo_iva: iva, tipo_retencion: ret,
    concepto: concepto ?? conceptoSugerido,
    detalle: { horas: horasTotales, precio_hora: t, dias: [...marcados].sort((a, b) => a - b).map((d) => diaISO(mes, d)) },
  }).then((r) => setCreada({ id: r.id, numero: numeroFactura })), 'Factura creada')

  if (!clientes.length) return <p className="text-sm text-muted">Añade tus clientes y su tarifa en Ingresos › Sueldo y tarifas para planificar facturas.</p>

  if (creada) return (
    <div className="space-y-4 text-sm">
      <p>La factura {creada.numero} está registrada.{fac?.emisor.nif ? '' : ' Rellena «Datos de facturación» para que tu nombre y NIF salgan en el documento.'}</p>
      <div className="flex flex-wrap justify-end gap-3">
        <Boton variante="secundario" onClick={onHecho}>Cerrar</Boton>
        <a href={`/api/autonomo/facturas/${creada.id}/documento`} target="_blank" rel="noopener"
          className="inline-flex items-center gap-2 rounded-xl bg-accent px-3.5 py-2 font-medium text-panel hover:opacity-90"><FileText size={16} />Abrir la factura</a>
      </div>
    </div>
  )

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Selector etiqueta="Cliente" value={cliente} onChange={(e) => { setCliente(Number(e.target.value)); setTarifa(null); setHoras(null); setConcepto(null) }}>
          {clientes.map((x, i) => <option key={x.nombre} value={i}>{x.nombre}</option>)}
        </Selector>
        <Campo etiqueta="Mes" type="month" value={mes} onChange={(e) => e.target.value && cambiarMes(e.target.value)} />
        <Campo etiqueta="€ por hora" type="text" inputMode="decimal" value={tarifa ?? comoTexto(t)} onChange={(e) => setTarifa(e.target.value)} />
        <Campo etiqueta="Horas al día" type="text" inputMode="decimal" value={horas ?? comoTexto(h)} onChange={(e) => setHoras(e.target.value)} />
      </div>

      <div>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-muted">
          <span className="min-w-0 flex-1 basis-60">Toca los días para marcarlos o quitarlos. Los festivos, tus vacaciones y los días que no puedes vienen quitados.</span>
          <span className="flex shrink-0 gap-3">
            <button type="button" className="font-medium text-accent" onClick={() => setElegidos(null)}>Laborables</button>
            <button type="button" className="font-medium text-accent" onClick={() => setElegidos(new Set())}>Ninguno</button>
          </span>
        </div>
        <div className="grid grid-cols-7 gap-1 text-center text-xs">
          {DIAS_SEMANA.map((d) => <div key={d} className="py-1 font-medium text-muted">{d}</div>)}
          {Array.from({ length: huecos }, (_, i) => <div key={`h${i}`} />)}
          {Array.from({ length: total }, (_, i) => i + 1).map((d) => {
            const on = marcados.has(d)
            const nombreFestivo = festivoDe(fest, mes, d)
            const tipo = noDisp[diaISO(mes, d)]
            const titulo = [nombreFestivo, tipo === 'vacaciones' ? 'Vacaciones' : tipo ? 'No puedes' : ''].filter(Boolean).join(' · ')
            return (
              <button key={d} type="button" title={titulo || undefined} onClick={() => alternar(d)} aria-pressed={on}
                className={`rounded-lg py-2 font-medium transition ${on ? 'bg-accent text-panel' : tipo ? `${ESTILO_DIA[tipo]} opacity-60` : 'bg-panel-2 text-muted'} ${nombreFestivo ? 'ring-1 ring-[var(--chart-3)]' : ''}`}>
                {d}
              </button>
            )
          })}
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 rounded-xl bg-panel-2 p-4 text-sm sm:grid-cols-4">
        <div><dt className="text-xs text-muted">Días · horas</dt><dd className="cifra text-lg font-semibold">{dias} · {comoTexto(horasTotales)}</dd></div>
        <div><dt className="text-xs text-muted">Base</dt><dd className="text-lg font-semibold"><Importe valor={base} /></dd></div>
        <div><dt className="text-xs text-muted">IVA {iva} % · retención {ret} %</dt><dd><Importe valor={cuotaIva - retencion} signo /></dd></div>
        <div><dt className="text-xs text-muted">Te ingresan</dt><dd className="text-lg font-semibold"><Importe valor={base + cuotaIva - retencion} /></dd></div>
      </dl>
      {planificado !== undefined && <p className="text-xs text-muted">En la previsión tienes {planificado} días para este mes.</p>}

      <div className="grid gap-4 sm:grid-cols-2">
        <Campo etiqueta="Número de factura" value={numeroFactura} onChange={(e) => setNumero(e.target.value)} />
        <Campo etiqueta="Fecha de la factura" type="date" value={fechaFactura ?? ultimoDia(mes)} onChange={(e) => setFechaFactura(e.target.value)} />
        <Campo etiqueta="Concepto" value={concepto ?? conceptoSugerido} onChange={(e) => setConcepto(e.target.value)} className="sm:col-span-2" />
      </div>
      <div className="flex flex-wrap justify-end gap-3">
        <Boton variante="secundario" disabled={!c || prever.isPending} onClick={() => prever.mutate(undefined)}>Usar en la previsión</Boton>
        <Boton disabled={!numeroFactura || !dias || crear.isPending} onClick={() => crear.mutate(undefined)}>Crear factura de {eur(base)}</Boton>
      </div>
    </div>
  )
}
