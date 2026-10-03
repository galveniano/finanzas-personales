const eurFmt = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' })
const eurCorto = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
const compacto = new Intl.NumberFormat('es-ES', { notation: 'compact', maximumFractionDigits: 1 })

export const eur = (v: number | null | undefined) => (v == null ? '—' : eurFmt.format(v))
export const eur0 = (v: number | null | undefined) => (v == null ? '—' : eurCorto.format(v))
export const eurK = (v: number) => `${compacto.format(v)} €`

export function fecha(iso: string | null | undefined, opciones?: Intl.DateTimeFormatOptions) {
  if (!iso) return '—'
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso)
  return d.toLocaleDateString('es-ES', opciones ?? { day: '2-digit', month: '2-digit', year: 'numeric' })
}

export const mesCorto = (ym: string) =>
  new Date(`${ym}-01T00:00:00`).toLocaleDateString('es-ES', { month: 'short' }).replace('.', '')

export const hoyISO = () => new Date().toISOString().slice(0, 10)

export function diasHasta(iso: string) {
  const ms = new Date(`${iso}T00:00:00`).getTime() - new Date(new Date().toDateString()).getTime()
  return Math.round(ms / 86_400_000)
}
