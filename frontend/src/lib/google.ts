// Google Identity Services: https://developers.google.com/identity/gsi/web
export interface Gsi {
  accounts: {
    id: {
      initialize: (o: { client_id: string; callback: (r: { credential: string }) => void }) => void
      renderButton: (el: HTMLElement, o: Record<string, unknown>) => void
    }
    oauth2: {
      initTokenClient: (o: {
        client_id: string; scope: string; prompt?: string
        callback: (r: { access_token?: string; error?: string; error_description?: string }) => void
        error_callback?: (e: { type: string; message?: string }) => void
      }) => { requestAccessToken: () => void }
    }
  }
}
declare global { interface Window { google?: Gsi } }

export function cargarGsi(): Promise<Gsi> {
  return new Promise((ok, mal) => {
    if (window.google) return ok(window.google)
    const s = document.createElement('script')
    s.src = 'https://accounts.google.com/gsi/client'
    s.async = true
    s.onload = () => (window.google ? ok(window.google) : mal(new Error('Google no ha cargado')))
    s.onerror = () => mal(new Error('No se puede cargar el inicio de sesión de Google'))
    document.head.appendChild(s)
  })
}

/** Pide a Google permiso de solo lectura de Drive. El token dura una hora y no se guarda. */
export async function permisoDrive(clientId: string): Promise<string> {
  const g = await cargarGsi()
  return new Promise((ok, mal) => {
    g.accounts.oauth2.initTokenClient({
      client_id: clientId, scope: 'https://www.googleapis.com/auth/drive.readonly',
      callback: (r) => (r.access_token ? ok(r.access_token) : mal(new Error(r.error_description || r.error || 'Permiso denegado'))),
      error_callback: (e) => mal(new Error(e.type === 'popup_closed' ? 'Has cerrado la ventana de Google' : e.message || 'Permiso denegado')),
    }).requestAccessToken()
  })
}
