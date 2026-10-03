// Cliente de la API del backend. En la vista previa publicada (sin backend) las lecturas
// salen de window.__DEMO__ y las escrituras no hacen nada.
declare global {
  interface Window { __DEMO__?: Record<string, unknown> }
}

export const esDemo = typeof window !== 'undefined' && !!window.__DEMO__

export class ApiError extends Error {}

/** Se lanza cuando la sesión de Google caduca o no existe; Acceso vuelve a pedir entrar. */
export const SESION_CADUCADA = 'finanzas:sesion-caducada'

async function peticion<T>(metodo: string, ruta: string, cuerpo?: unknown): Promise<T> {
  if (esDemo) {
    if (metodo === 'GET') {
      const clave = ruta.split('?')[0]
      const datos = window.__DEMO__![ruta] ?? window.__DEMO__![clave]
      if (datos === undefined) throw new ApiError('Sin datos de ejemplo para esta vista')
      return structuredClone(datos) as T
    }
    throw new ApiError('Esto es una vista previa: aquí no se guarda nada.')
  }
  const init: RequestInit = { method: metodo, headers: {} }
  if (cuerpo instanceof FormData) init.body = cuerpo
  else if (cuerpo !== undefined) {
    init.body = JSON.stringify(cuerpo)
    init.headers = { 'Content-Type': 'application/json' }
  }
  const r = await fetch(`/api${ruta}`, init)
  if (r.status === 401 && !ruta.startsWith('/auth/')) window.dispatchEvent(new Event(SESION_CADUCADA))
  if (!r.ok) {
    let detalle = `Error ${r.status}`
    try {
      const j = await r.json()
      if (typeof j.detail === 'string') detalle = j.detail
      else if (Array.isArray(j.detail)) detalle = 'Revisa los campos del formulario.'
    } catch { /* respuesta sin JSON */ }
    throw new ApiError(detalle)
  }
  return r.json() as Promise<T>
}

export const api = {
  get: <T,>(ruta: string) => peticion<T>('GET', ruta),
  post: <T = { ok: boolean },>(ruta: string, cuerpo?: unknown) => peticion<T>('POST', ruta, cuerpo),
  patch: <T = { ok: boolean },>(ruta: string, cuerpo?: unknown) => peticion<T>('PATCH', ruta, cuerpo),
  put: <T = { ok: boolean },>(ruta: string, cuerpo?: unknown) => peticion<T>('PUT', ruta, cuerpo),
  del: <T = { ok: boolean },>(ruta: string) => peticion<T>('DELETE', ruta),
}
