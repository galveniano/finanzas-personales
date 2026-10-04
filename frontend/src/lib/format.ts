// useGrouping 'always': en español Intl no pone el punto de miles en 4 cifras (1234 €); para importes queda raro
const eurFmt = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', useGrouping: 'always' })
const eurCorto = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0, useGrouping: 'always' })
const compacto = new Intl.NumberFormat('es-ES', { notation: 'compact', maximumFractionDigits: 1 })

export const eur = (v: number | null | undefined) => (v == null ? '—' : eurFmt.format(v))
export const eur0 = (v: number | null | undefined) => (v == null ? '—' : eurCorto.format(v))
export const eurK = (v: number) => `${compacto.format(v)} €`

export function fecha(iso: string | null | undefined, opciones?: Intl.DateTimeFormatOptions) {
  if (!iso) return '—'
  const d = iso.length === 10 ? new Date(`${iso}T00:00:00`) : fechaServidor(iso)
  return d.toLocaleDateString('es-ES', opciones ?? { day: '2-digit', month: '2-digit', year: 'numeric' })
}

export const mesCorto = (ym: string) =>
  new Date(`${ym}-01T00:00:00`).toLocaleDateString('es-ES', { month: 'short' }).replace('.', '')

/** Fecha de hoy (YYYY-MM-DD) en la zona horaria local, no en UTC. */
export function hoyISO() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Fecha y hora del servidor (UTC). Si trae hora pero no zona, se interpreta como UTC. */
export function fechaServidor(iso: string) {
  const t = iso.replace(/^(\d{4}-\d{2}-\d{2}) (?=\d{2}:)/, '$1T')
  const sinZona = /T\d{2}:\d{2}/.test(t) && !/(Z|[+-]\d{2}:?\d{2})$/i.test(t)
  return new Date(sinZona ? `${t}Z` : t)
}

/** «12 oct, 09:30» en hora local a partir de una marca de tiempo del servidor. */
export const fechaHora = (iso: string, opciones?: Intl.DateTimeFormatOptions) =>
  fechaServidor(iso).toLocaleString('es-ES', opciones ?? { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })

export function diasHasta(iso: string) {
  const ms = new Date(`${iso}T00:00:00`).getTime() - new Date(new Date().toDateString()).getTime()
  return Math.round(ms / 86_400_000)
}
