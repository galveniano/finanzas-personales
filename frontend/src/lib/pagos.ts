import { api } from './api'
import { useAccion } from './utilidades'

/** Marcar un pago previsto como pagado (o deshacerlo). Plan, Inicio e Inversiones comparten la llamada. */
export function useMarcarPago() {
  return useAccion(({ id, pagado }: { id: number; pagado: boolean }) => api.patch(`/pagos/${id}`, { pagado }))
}

/** Borrar un pago previsto por id. */
export function useBorrarPago() {
  return useAccion((id: number) => api.del(`/pagos/${id}`), 'Pago borrado')
}
