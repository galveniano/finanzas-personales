import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { api } from '../lib/api'
import { MESES } from '../lib/format'
import { ESTILO_DIA, diaISO, laborables, mesActual, moverMes } from '../lib/festivos'
import type { Facturacion, TipoDia } from '../lib/tipos'
import { useAvisos } from '../lib/utilidades'
import RejillaMes from './RejillaMes'
import { Boton, Campo } from './ui'

type Pincel = TipoDia | 'quitar'
const PINCELES: { valor: Pincel; texto: string }[] = [
  { valor: 'vacaciones', texto: 'Vacaciones' }, { valor: 'no_disponible', texto: 'No puedo' }, { valor: 'quitar', texto: 'Borrar' },
]
const MAX_DIAS_RANGO = 370

/** Días laborables (sin fines de semana ni festivos) entre dos fechas «AAAA-MM-DD», ambas incluidas. */
function laborablesEntre(desde: string, hasta: string): string[] {
  const dias: string[] = []
  let d = new Date(`${desde}T00:00:00`)
  const fin = new Date(`${hasta}T00:00:00`)
  for (let i = 0; d <= fin && i <= MAX_DIAS_RANGO; d.setDate(d.getDate() + 1), i++) {
    const mes = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    if (laborables(mes).has(d.getDate())) dias.push(diaISO(mes, d.getDate()))
  }
  return dias
}

/** Calendario donde marcas tus vacaciones y los días que no puedes trabajar; el planificador de facturas ya no los cuenta. */
export default function CalendarioDias() {
  const qc = useQueryClient()
  const avisar = useAvisos()
  const { data } = useQuery({ queryKey: ['facturacion'], queryFn: () => api.get<Facturacion>('/facturacion') })
  const marcados = data?.dias_no_disponibles ?? {}
  const [mes, setMes] = useState(mesActual())
  const [pincel, setPincel] = useState<Pincel>('vacaciones')
  const [anio, m] = mes.split('-').map(Number)

  const marcar = useMutation({
    mutationFn: ({ dias, tipo }: { dias: string[]; tipo: TipoDia | null }) => api.put<{ dias_no_disponibles: Record<string, TipoDia> }>('/facturacion/dias', { dias, tipo }),
    onMutate: ({ dias, tipo }) => {
      const antes = qc.getQueryData<Facturacion>(['facturacion'])
      if (antes) {
        const nuevos = { ...antes.dias_no_disponibles }
        for (const d of dias) { if (tipo) nuevos[d] = tipo; else delete nuevos[d] }
        qc.setQueryData(['facturacion'], { ...antes, dias_no_disponibles: nuevos })
      }
      return { antes }
    },
    onError: (e: Error, _v, ctx) => { if (ctx?.antes) qc.setQueryData(['facturacion'], ctx.antes); avisar(e.message, 'error') },
    onSettled: () => qc.invalidateQueries({ queryKey: ['facturacion'] }),
  })
  const tocar = (d: number) => {
    const clave = diaISO(mes, d)
    const tipo = pincel === 'quitar' || marcados[clave] === pincel ? null : pincel
    marcar.mutate({ dias: [clave], tipo })
  }
  // Un tramo entero (las vacaciones de agosto) con el pincel elegido, solo los días laborables
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const rangoValido = !!desde && !!hasta && hasta >= desde
  const marcarRango = () => {
    const dias = laborablesEntre(desde, hasta)
    if (!dias.length) return avisar('En ese tramo no hay días laborables', 'error')
    if (dias.length > 260) return avisar('Marca como mucho un año de cada vez', 'error')
    marcar.mutate({ dias, tipo: pincel === 'quitar' ? null : pincel })
    setMes(desde.slice(0, 7))
    setDesde('')
    setHasta('')
  }

  const delMes = Object.entries(marcados).filter(([k]) => k.startsWith(mes))
  const vacacionesAnio = Object.entries(marcados).filter(([k, v]) => k.startsWith(String(anio)) && v === 'vacaciones'
    && ![0, 6].includes(new Date(`${k}T00:00:00`).getDay())).length
  const disponibles = laborables(mes, marcados).size

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <Boton variante="fantasma" className="px-2" onClick={() => setMes(moverMes(mes, -1))} aria-label="Mes anterior"><ChevronLeft size={18} /></Boton>
        <span className="font-semibold capitalize">{MESES[m - 1]} {anio}</span>
        <Boton variante="fantasma" className="px-2" onClick={() => setMes(moverMes(mes, 1))} aria-label="Mes siguiente"><ChevronRight size={18} /></Boton>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-muted">Al tocar un día marca:</span>
        {PINCELES.map((p) => (
          <button key={p.valor} type="button" aria-pressed={pincel === p.valor} onClick={() => setPincel(p.valor)}
            className={`rounded-full border px-3 py-1 font-medium transition ${pincel === p.valor ? 'border-accent bg-accent-soft text-accent' : 'border-line text-muted'}`}>
            {p.valor !== 'quitar' && <span className={`mr-1.5 inline-block size-2 rounded-full ${ESTILO_DIA[p.valor].split(' ')[0]}`} />}{p.texto}
          </button>
        ))}
      </div>

      <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (rangoValido) marcarRango() }} aria-label="Marcar un tramo de días">
        <Campo etiqueta="Del día" type="date" value={desde} onChange={(e) => setDesde(e.target.value)} className="min-w-0 flex-1 basis-36" />
        <Campo etiqueta="al" type="date" value={hasta} min={desde || undefined} onChange={(e) => setHasta(e.target.value)} className="min-w-0 flex-1 basis-36" />
        <Boton type="submit" variante="secundario" disabled={!rangoValido || marcar.isPending}>
          {pincel === 'quitar' ? 'Borrar el tramo' : `Marcar ${pincel === 'vacaciones' ? 'vacaciones' : 'que no puedo'}`}
        </Boton>
      </form>

      <RejillaMes mes={mes} onDia={tocar}
        claseDia={(d, { festivo, finde }) => {
          const tipo = marcados[diaISO(mes, d)]
          return `rounded-lg py-2 font-medium transition ${tipo ? ESTILO_DIA[tipo] : finde || festivo ? 'text-muted/60' : 'bg-panel-2'} ${festivo ? 'ring-1 ring-[var(--chart-3)]' : ''}`
        }}
        tituloDia={(d, { festivo }) => {
          const tipo = marcados[diaISO(mes, d)]
          return [festivo, tipo === 'vacaciones' ? 'Vacaciones' : tipo === 'no_disponible' ? 'No puedes' : ''].filter(Boolean).join(' · ') || undefined
        }} />

      <dl className="grid grid-cols-3 gap-3 rounded-xl bg-panel-2 p-4 text-sm">
        <div><dt className="text-xs text-muted">Puedes trabajar</dt><dd className="cifra text-lg font-semibold">{disponibles} días</dd></div>
        <div><dt className="text-xs text-muted">Marcados este mes</dt><dd className="cifra text-lg font-semibold">{delMes.length}</dd></div>
        <div><dt className="text-xs text-muted">Vacaciones en {anio}</dt><dd className="cifra text-lg font-semibold">{vacacionesAnio} días</dd></div>
      </dl>
      <p className="text-xs text-muted">Los festivos de España y de Murcia ya no cuentan (borde de color). Los festivos locales márcalos como «No puedo».
        Al planificar una factura, estos días salen ya quitados.</p>
    </div>
  )
}
