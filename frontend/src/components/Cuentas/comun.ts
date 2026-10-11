// Lo que comparten las piezas de la página Cuentas (sin componentes: ver Selectores.tsx).
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import type { Categoria, Cuenta } from '../../lib/tipos'

export const ORIGEN: Record<string, { texto: string; tono: 'acento' | 'neutro' | 'bien' }> = {
  enable_banking: { texto: 'Sincronizada', tono: 'bien' },
  indexa: { texto: 'Indexa API', tono: 'bien' },
  csv: { texto: 'Extracto', tono: 'neutro' },
  manual: { texto: 'Manual', tono: 'neutro' },
}
export const TIPO_CUENTA: Record<string, string> = { corriente: 'Corriente', ahorro: 'Ahorro', tarjeta: 'Tarjeta', inversion: 'Inversión' }

/** Cuentas cuyo saldo y movimientos se escriben a mano o con extractos (las sincronizadas las lleva el banco). */
export const esManual = (c: Cuenta) => c.origen === 'manual' || c.origen === 'csv'

/** Con lo que empieza la nota que deja «Apuntar desde un movimiento», para verlo y no apuntarlo dos veces. */
export const APUNTADO = 'Apuntado como '

/** Todas las cuentas, también las ocultas (`activa: false`), para poder recuperarlas. */
export const useCuentas = () => useQuery({ queryKey: ['cuentas', 'todas'], queryFn: () => api.get<Cuenta[]>('/cuentas?todas=true') })
export const useCategorias = () => useQuery({ queryKey: ['categorias'], queryFn: () => api.get<Categoria[]>('/categorias') })

/** «COMPRA TARJ. 5402 NETFLIX.COM 12/09» → «Netflix Com»: el concepto sin números ni palabras de relleno, para
 *  proponerlo como proveedor (el mismo criterio que `patron_de` en el backend). */
export function conceptoLimpio(concepto: string) {
  const t = concepto.replace(/[\d/.,:*#-]+/g, ' ')
    .replace(/\b(compra|tarj|tarjeta|pago|recibo|adeudo|cargo|en|de|a|sepa|contactless|transferencia|bizum|traspaso)\b/gi, ' ')
    .replace(/\s+/g, ' ').trim()
  return t ? t.toLowerCase().replace(/(^|\s)\S/g, (x) => x.toUpperCase()) : concepto
}

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** Desde y hasta de cada atajo de periodo de la lista de movimientos ('' = sin límite). */
export function rangosPeriodo(): Record<string, [string, string]> {
  const hoy = new Date(), y = hoy.getFullYear(), m = hoy.getMonth()
  return {
    mes: [iso(new Date(y, m, 1)), iso(new Date(y, m + 1, 0))],
    mes_pasado: [iso(new Date(y, m - 1, 1)), iso(new Date(y, m, 0))],
    anio: [iso(new Date(y, 0, 1)), iso(new Date(y, 11, 31))],
    doce: [iso(new Date(y, m - 11, 1)), ''],
    todo: ['', ''],
  }
}
