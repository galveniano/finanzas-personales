import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { eur } from '../lib/format'
import type { Prevision } from '../lib/tipos'
import { Boton, Campo, Importe, Selector, useAccion } from '../components/ui'

const DIAS_SEMANA = ['L', 'M', 'X', 'J', 'V', 'S', 'D']
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

/** Domingo de Pascua (algoritmo anónimo gregoriano). */
function pascua(anio: number): Date {
  const a = anio % 19, b = Math.floor(anio / 100), c = anio % 100, d = Math.floor(b / 4), e = b % 4
  const f = Math.floor((b + 8) / 25), g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30
  const i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7, m = Math.floor((a + 11 * h + 22 * l) / 451)
  const mes = Math.floor((h + l - 7 * m + 114) / 31), dia = ((h + l - 7 * m + 114) % 31) + 1
  return new Date(anio, mes - 1, dia)
}

/** Festivos nacionales y de la Región de Murcia (sin los locales de cada municipio). */
function festivos(anio: number): Map<string, string> {
  const f = new Map<string, string>([
    ['01-01', 'Año Nuevo'], ['01-06', 'Reyes'], ['03-19', 'San José'], ['05-01', 'Día del Trabajo'], ['06-09', 'Día de la Región'],
    ['08-15', 'Asunción'], ['10-12', 'Fiesta Nacional'], ['11-01', 'Todos los Santos'], ['12-06', 'Constitución'],
    ['12-08', 'Inmaculada'], ['12-25', 'Navidad'],
  ])
  const p = pascua(anio)
  for (const [delta, nombre] of [[-3, 'Jueves Santo'], [-2, 'Viernes Santo']] as const) {
    const d = new Date(p); d.setDate(p.getDate() + delta)
    f.set(`${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`, nombre)
  }
  return f
}

function laborables(mes: string): Set<number> {
  const [anio, m] = mes.split('-').map(Number)
  const fest = festivos(anio), dias = new Set<number>()
  for (let d = 1; d <= new Date(anio, m, 0).getDate(); d++) {
    const dow = new Date(anio, m - 1, d).getDay()
    if (dow !== 0 && dow !== 6 && !fest.has(`${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`)) dias.add(d)
  }
  return dias
}

function mesActual(): string {
  const h = new Date()
  return `${h.getFullYear()}-${String(h.getMonth() + 1).padStart(2, '0')}`
}

/** Calcula una factura con la tarifa del cliente y los días que marques; la crea o la usa en la previsión. */
export default function PlanificadorFactura({ onHecho }: { onHecho: () => void }) {
  const { data: p } = useQuery({ queryKey: ['prevision'], queryFn: () => api.get<Prevision>('/prevision') })
  const clientes = p?.supuestos.clientes ?? []
  const [cliente, setCliente] = useState(0)
  const [mes, setMes] = useState(mesActual())
  const [marcados, setMarcados] = useState<Set<number>>(() => laborables(mesActual()))
  const [numero, setNumero] = useState('')
  const c = clientes[cliente]
  const [tarifa, setTarifa] = useState<number | null>(null)
  const [horas, setHoras] = useState<number | null>(null)
  const t = tarifa ?? c?.tarifa_hora ?? 0, h = horas ?? c?.horas_dia ?? 8
  const iva = c?.iva ?? 21, ret = c?.retencion ?? 15

  const [anio, m] = mes.split('-').map(Number)
  const fest = useMemo(() => festivos(anio), [anio])
  const huecos = (new Date(anio, m - 1, 1).getDay() + 6) % 7
  const total = new Date(anio, m, 0).getDate()
  const dias = marcados.size
  const base = Math.round(t * h * dias * 100) / 100
  const cuotaIva = Math.round(base * iva) / 100, retencion = Math.round(base * ret) / 100
  const planificado = c ? p?.supuestos.dias_planificados?.[c.nombre]?.[mes] : undefined

  const cambiarMes = (nuevo: string) => { setMes(nuevo); setMarcados(laborables(nuevo)) }
  const alternar = (d: number) => setMarcados((s) => { const n = new Set(s); if (n.has(d)) n.delete(d); else n.add(d); return n })
  const prever = useAccion(() => api.put('/prevision/dias', { cliente: c.nombre, mes, dias }), 'Días guardados en la previsión')
  const crear = useAccion(() => api.post('/autonomo/facturas', {
    numero, cliente: c.nombre, fecha: `${mes}-${String(total).padStart(2, '0')}`, base, tipo_iva: iva, tipo_retencion: ret,
    concepto: `${String(dias)} días × ${String(h).replace('.', ',')} h × ${eur(t)}/h (${MESES[m - 1]} ${anio})`,
  }).then(onHecho), 'Factura registrada')

  if (!clientes.length) return <p className="text-sm text-muted">Añade tus clientes y su tarifa en Previsión › Supuestos para planificar facturas.</p>

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Selector etiqueta="Cliente" value={cliente} onChange={(e) => { setCliente(Number(e.target.value)); setTarifa(null); setHoras(null) }}>
          {clientes.map((x, i) => <option key={x.nombre} value={i}>{x.nombre}</option>)}
        </Selector>
        <Campo etiqueta="Mes" type="month" value={mes} onChange={(e) => e.target.value && cambiarMes(e.target.value)} />
        <Campo etiqueta="€ por hora" inputMode="decimal" value={t} onChange={(e) => setTarifa(Number(e.target.value.replace(',', '.')) || 0)} />
        <Campo etiqueta="Horas al día" inputMode="decimal" value={h} onChange={(e) => setHoras(Number(e.target.value.replace(',', '.')) || 0)} />
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between text-xs text-muted">
          <span>Toca los días para marcarlos o quitarlos. Los festivos de España y de Murcia vienen quitados.</span>
          <span className="flex gap-2">
            <button type="button" className="font-medium text-accent" onClick={() => setMarcados(laborables(mes))}>Laborables</button>
            <button type="button" className="font-medium text-accent" onClick={() => setMarcados(new Set())}>Ninguno</button>
          </span>
        </div>
        <div className="grid grid-cols-7 gap-1 text-center text-xs">
          {DIAS_SEMANA.map((d) => <div key={d} className="py-1 font-medium text-muted">{d}</div>)}
          {Array.from({ length: huecos }, (_, i) => <div key={`h${i}`} />)}
          {Array.from({ length: total }, (_, i) => i + 1).map((d) => {
            const on = marcados.has(d)
            const nombreFestivo = fest.get(`${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`)
            return (
              <button key={d} type="button" title={nombreFestivo} onClick={() => alternar(d)} aria-pressed={on}
                className={`rounded-lg py-2 font-medium transition ${on ? 'bg-accent text-panel' : 'bg-panel-2 text-muted'} ${nombreFestivo ? 'ring-1 ring-[var(--chart-3)]' : ''}`}>
                {d}
              </button>
            )
          })}
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 rounded-xl bg-panel-2 p-4 text-sm sm:grid-cols-4">
        <div><dt className="text-xs text-muted">Días</dt><dd className="cifra text-lg font-semibold">{dias}</dd></div>
        <div><dt className="text-xs text-muted">Base</dt><dd className="text-lg font-semibold"><Importe valor={base} /></dd></div>
        <div><dt className="text-xs text-muted">IVA {iva} % · retención {ret} %</dt><dd><Importe valor={cuotaIva - retencion} signo /></dd></div>
        <div><dt className="text-xs text-muted">Te ingresan</dt><dd className="text-lg font-semibold"><Importe valor={base + cuotaIva - retencion} /></dd></div>
      </dl>
      {planificado !== undefined && <p className="text-xs text-muted">En la previsión tienes {planificado} días para este mes.</p>}

      <div className="flex flex-wrap items-end justify-end gap-3">
        <Boton variante="secundario" disabled={!c || prever.isPending} onClick={() => prever.mutate(undefined)}>Usar en la previsión</Boton>
        <Campo etiqueta="Número de factura" value={numero} onChange={(e) => setNumero(e.target.value)} className="w-40" />
        <Boton disabled={!numero || !dias || crear.isPending} onClick={() => crear.mutate(undefined)}>Crear factura</Boton>
      </div>
    </div>
  )
}
