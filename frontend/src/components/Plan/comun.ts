// Lo que comparten las piezas de Plan: nombres de mes, tipos de objetivo y frases repetidas.
import { eur, fecha } from '../../lib/format'
import type { Escenario, Prevision } from '../../lib/tipos'

export const nombreMes = (clave: string) => fecha(`${clave}-01`, { month: 'short', year: '2-digit' })
export const mesLargo = (clave: string) => fecha(`${clave}-01`, { month: 'long', year: 'numeric' })

export const TIPO_OBJETIVO: Record<string, string> = { boda: 'Boda', viaje: 'Viaje', casa: 'Casa', colchon: 'Colchón', otro: 'Objetivo' }

export const ahorroTexto = (v: number) => (v < 0 ? `Gastando unos ${eur(-v)} más de lo que entra al mes` : `Ahorrando unos ${eur(v)} al mes`)

/** Hay sueldo o tarifas: la previsión sabe lo que entra (como `tiene_supuestos` en el backend). */
export const tieneSupuestos = (p: Prevision) => !!(p.supuestos.nomina || p.supuestos.clientes.length)

/** Parámetros de /prevision con los meses y, si lo hay, el escenario. */
export function rutaPrevision(meses: number, escenario: Escenario | null) {
  const q = new URLSearchParams({ meses: String(meses) })
  for (const [k, v] of Object.entries(escenario ?? {})) if (v != null) q.set(k, String(v))
  return `/prevision?${q}`
}
