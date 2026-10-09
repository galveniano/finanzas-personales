import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ShieldCheck } from 'lucide-react'
import { api, esDemo, SESION_CADUCADA } from '../lib/api'
import type { EstadoAuth } from '../lib/tipos'
import { cargarGsi } from '../lib/google'
import Logo from './Logo'
import { Cargando } from './ui'

function Entrar({ clientId }: { clientId: string | null }) {
  const qc = useQueryClient()
  const boton = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(clientId ? null : 'Falta configurar GOOGLE_CLIENT_ID en el servidor.')

  useEffect(() => {
    if (!clientId) return
    let vivo = true
    cargarGsi().then((g) => {
      if (!vivo || !boton.current) return
      g.accounts.id.initialize({
        client_id: clientId,
        callback: async ({ credential }) => {
          try {
            await api.post('/auth/google', { credential })
            await qc.invalidateQueries()
          } catch (e) { setError((e as Error).message) }
        },
      })
      g.accounts.id.renderButton(boton.current, { theme: 'outline', size: 'large', shape: 'pill', text: 'continue_with', locale: 'es' })
    }).catch((e: Error) => setError(e.message))
    return () => { vivo = false }
  }, [clientId, qc])

  return (
    <Centrado>
      <div className="w-full max-w-sm rounded-2xl border border-line bg-panel p-8 text-center">
        <div className="mx-auto mb-5 w-fit"><Logo grande /></div>
        <h1 className="text-xl font-semibold">Finanzas</h1>
        <p className="mt-2 text-sm text-muted">Entra con tu cuenta de Google. Solo las cuentas autorizadas pueden ver los datos.</p>
        <div ref={boton} className="mt-6 flex min-h-11 justify-center" />
        {error && <p className="mt-4 text-sm text-neg" role="alert">{error}</p>}
        <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-muted"><ShieldCheck size={14} />Conexión cifrada y sesión de 30 días</p>
      </div>
    </Centrado>
  )
}

function Centrado({ children }: { children: ReactNode }) {
  return <div className="grid min-h-screen place-items-center bg-bg px-4">{children}</div>
}

/** Si la app pide iniciar sesión (publicada en Vercel), enseña la pantalla de entrada hasta que lo hagas. */
export default function Acceso({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['auth'], queryFn: () => api.get<EstadoAuth>('/auth/estado'), enabled: !esDemo, staleTime: Infinity,
  })
  useEffect(() => {
    const caducada = () => qc.invalidateQueries({ queryKey: ['auth'] })
    window.addEventListener(SESION_CADUCADA, caducada)
    return () => window.removeEventListener(SESION_CADUCADA, caducada)
  }, [qc])

  if (esDemo) return <>{children}</>
  if (isLoading) return <Centrado><div className="w-full max-w-2xl"><Cargando /></div></Centrado>
  if (error) return <Centrado><p className="text-sm text-muted">No se puede conectar con la app: {error.message}</p></Centrado>
  if (data?.requerida && !data.email) return <Entrar clientId={data.client_id} />
  return <>{children}</>
}
