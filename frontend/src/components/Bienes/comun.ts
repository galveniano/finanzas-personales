// Lo que comparten las piezas de Bienes: la acción abierta en el diálogo, los textos de cada clave y helpers de fecha.
import { capitalizar, fecha, MESES } from '../../lib/format'
import type { Deuda, Inmueble } from '../../lib/tipos'

export type Accion = {
  tipo: 'nuevo' | 'editar' | 'valoracion' | 'editarValoracion' | 'hipoteca' | 'prestamo' | 'editarDeuda' | 'contrato'
    | 'editarContrato' | 'renta' | 'gasto' | 'editarGasto' | 'escritura' | 'escriturar'
  inmueble?: Inmueble; contratoId?: number; deuda?: Deuda; gastoId?: number; valoracionId?: number
}

export const TITULOS: Record<Accion['tipo'], string> = {
  nuevo: 'Nuevo bien', editar: 'Editar', valoracion: 'Nueva valoración', editarValoracion: 'Editar valoración',
  hipoteca: 'Añadir hipoteca', prestamo: 'Añadir préstamo', editarDeuda: 'Editar', contrato: 'Contrato de alquiler',
  editarContrato: 'Editar contrato', renta: 'Actualizar renta', gasto: 'Añadir gasto', editarGasto: 'Editar gasto',
  escritura: 'Gastos de escritura', escriturar: 'Escriturada',
}

export const TIPOS_GASTO_INMUEBLE: Record<string, string> = {
  ibi: 'IBI', comunidad: 'Comunidad', seguro: 'Seguro', reparacion: 'Reparación', intereses: 'Intereses hipoteca',
  suministros: 'Suministros', gestion: 'Gestión', otros: 'Otros',
}
export const TIPOS_BIEN: Record<string, string> = {
  inmueble: 'Ya es mío', inmueble_en_construccion: 'Obra nueva en construcción', vehiculo: 'Coche', otro: 'Otro bien',
}
export const USOS: Record<string, string> = { alquiler: 'Alquiler', vivienda_habitual: 'Vivienda habitual', otro: 'Otro' }
export const TIPOS_DEUDA: Record<Deuda['tipo'], string> = { hipoteca: 'Hipoteca', prestamo: 'Préstamo', otro: 'Otra deuda' }

/** Clase de los botones pequeños de las fichas. */
export const BOTON_PEQ = 'px-2.5 py-1.5 text-xs'

/** «oct 2031» a partir de una fecha ISO. */
export const mesAnio = (iso: string) => fecha(iso, { month: 'short', year: 'numeric' })
/** «Octubre» a partir de «2031-10». */
export const nombreMes = (ym: string) => capitalizar(MESES[Number(ym.slice(5, 7)) - 1])
/** «octubre de 2031» a partir de «2031-10». */
export const mesLargo = (ym: string) => fecha(`${ym}-01`, { month: 'long', year: 'numeric' })
/** Meses que faltan hasta una fecha ISO (negativo si ya pasó). */
export function mesesHasta(iso: string) {
  const hoy = new Date()
  return (Number(iso.slice(0, 4)) - hoy.getFullYear()) * 12 + Number(iso.slice(5, 7)) - (hoy.getMonth() + 1)
}
export const mesesTexto = (n: number) =>
  n >= 12 ? `${n} meses (${(n / 12).toLocaleString('es-ES', { maximumFractionDigits: 1 })} años)` : `${n} ${n === 1 ? 'mes' : 'meses'}`
