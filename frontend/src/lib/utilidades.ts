import { createContext, useContext } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

/** Convierte '1.234,56', '1.500' o '1234.56' a número; vacío → undefined. */
export function num(v: string | undefined): number | undefined {
  if (v == null) return undefined
  const s = v.replace(/[\s€]/g, '')
  if (s === '') return undefined
  // «1.500» sin coma es 1500 (punto de miles); «1234.56» o «1.5» siguen siendo decimales
  const t = s.includes(',') ? s.replace(/\./g, '').replace(',', '.')
    : /^-?\d{1,3}(\.\d{3})+$/.test(s) ? s.replace(/\./g, '') : s
  const n = Number(t)
  return Number.isFinite(n) ? n : undefined
}
export const opc = (v: string | undefined) => (v && v.trim() !== '' ? v : undefined)

export type Avisar = (texto: string, tipo?: 'ok' | 'error') => void
export const AvisosCtx = createContext<Avisar>(() => {})
export const useAvisos = () => useContext(AvisosCtx)

/** Mutación que, al terminar, refresca los datos y avisa. */
export function useAccion<T>(fn: (v: T) => Promise<unknown>, mensajeOk?: string) {
  const qc = useQueryClient()
  const avisar = useAvisos()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries()
      if (mensajeOk) avisar(mensajeOk)
    },
    onError: (e: Error) => avisar(e.message, 'error'),
  })
}
