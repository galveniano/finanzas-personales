// Sincronizar bancos desde cualquier sitio (barra superior, paleta, Ajustes) avisando con el resultado real:
// el servidor responde 200 aunque falle, con `ok` y el mensaje de cada fuente.
import { api } from './api'
import type { RespuestaSync, ResultadoSync } from './tipos'
import { useAccion, useAvisos } from './utilidades'

const NOMBRE: Record<string, string> = { sabadell: 'Sabadell', indexa: 'Indexa' }

export function useSincronizar(ruta: '/sync' | '/sync/sabadell' | '/sync/indexa') {
  const avisar = useAvisos()
  return useAccion(async () => {
    const r = await api.post<RespuestaSync | ResultadoSync>(ruta)
    const resultados = 'resultados' in r ? r.resultados : [r]
    if (!resultados.length) avisar('No hay ningún banco configurado: mira Ajustes', 'error')
    for (const x of resultados) avisar(`${NOMBRE[x.fuente] ?? x.fuente}: ${x.mensaje}`, x.ok ? 'ok' : 'error')
  })
}
