// Festivos y días laborables para planificar facturas. Los de cada municipio no van: márcalos como «no puedo».

import type { TipoDia } from './tipos'

/** Color de un día de vacaciones o que no puedes trabajar. */
export const ESTILO_DIA: Record<TipoDia, string> = {
  vacaciones: 'bg-[var(--chart-2)] text-panel',
  no_disponible: 'bg-[var(--chart-3)] text-panel',
}

export const DIAS_SEMANA = ['L', 'M', 'X', 'J', 'V', 'S', 'D']

const dos = (n: number) => String(n).padStart(2, '0')

/** «2026-10-05» del día d del mes «2026-10». */
export const diaISO = (mes: string, d: number) => `${mes}-${dos(d)}`

export function mesActual(): string {
  const h = new Date()
  return `${h.getFullYear()}-${dos(h.getMonth() + 1)}`
}

/** Domingo de Pascua (algoritmo anónimo gregoriano). */
function pascua(anio: number): Date {
  const a = anio % 19, b = Math.floor(anio / 100), c = anio % 100, d = Math.floor(b / 4), e = b % 4
  const f = Math.floor((b + 8) / 25), g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30
  const i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7, m = Math.floor((a + 11 * h + 22 * l) / 451)
  const mes = Math.floor((h + l - 7 * m + 114) / 31), dia = ((h + l - 7 * m + 114) % 31) + 1
  return new Date(anio, mes - 1, dia)
}

/** Festivos nacionales y de la Región de Murcia, por «MM-DD». */
export function festivos(anio: number): Map<string, string> {
  const f = new Map<string, string>([
    ['01-01', 'Año Nuevo'], ['01-06', 'Reyes'], ['03-19', 'San José'], ['05-01', 'Día del Trabajo'], ['06-09', 'Día de la Región'],
    ['08-15', 'Asunción'], ['10-12', 'Fiesta Nacional'], ['11-01', 'Todos los Santos'], ['12-06', 'Constitución'],
    ['12-08', 'Inmaculada'], ['12-25', 'Navidad'],
  ])
  const p = pascua(anio)
  for (const [delta, nombre] of [[-3, 'Jueves Santo'], [-2, 'Viernes Santo']] as const) {
    const d = new Date(p); d.setDate(p.getDate() + delta)
    f.set(`${dos(d.getMonth() + 1)}-${dos(d.getDate())}`, nombre)
  }
  return f
}

export const festivoDe = (fest: Map<string, string>, mes: string, d: number) => fest.get(`${mes.slice(5)}-${dos(d)}`)

/** Días de lunes a viernes que no son festivo; sin los que marques en `fuera` («AAAA-MM-DD»). */
export function laborables(mes: string, fuera: Record<string, unknown> = {}): Set<number> {
  const [anio, m] = mes.split('-').map(Number)
  const fest = festivos(anio), dias = new Set<number>()
  for (let d = 1; d <= new Date(anio, m, 0).getDate(); d++) {
    const dow = new Date(anio, m - 1, d).getDay()
    if (dow !== 0 && dow !== 6 && !festivoDe(fest, mes, d) && !(diaISO(mes, d) in fuera)) dias.add(d)
  }
  return dias
}

export function moverMes(mes: string, delta: number): string {
  const [anio, m] = mes.split('-').map(Number)
  const d = new Date(anio, m - 1 + delta, 1)
  return `${d.getFullYear()}-${dos(d.getMonth() + 1)}`
}
