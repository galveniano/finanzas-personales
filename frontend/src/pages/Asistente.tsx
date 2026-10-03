import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowUp, RotateCcw, Sparkles } from 'lucide-react'
import { api } from '../lib/api'
import type { MensajeChat } from '../lib/tipos'
import { Boton, Cabecera, Vacio } from '../components/ui'

const CLAVE = 'finanzas:asistente'
const SUGERENCIAS = [
  '¿Cuánto me toca pagar este trimestre de IVA y de IRPF?',
  '¿Cuánto puedo ahorrar al mes para la boda?',
  '¿En qué he gastado más este último mes?',
  '¿Me conviene amortizar hipoteca o invertir en Indexa?',
]

function cargar(): MensajeChat[] {
  try { return JSON.parse(sessionStorage.getItem(CLAVE) ?? '[]') } catch { return [] }
}

/** Texto con **negritas** y saltos de línea, sin interpretar HTML. */
function Texto({ t }: { t: string }) {
  return <>{t.split('\n').map((linea, i) => (
    <p key={i} className={linea.trim() ? 'min-h-[1em]' : 'h-2'}>
      {linea.split(/(\*\*[^*]+\*\*)/g).map((x, j) => x.startsWith('**') && x.endsWith('**') ? <strong key={j}>{x.slice(2, -2)}</strong> : x)}
    </p>
  ))}</>
}

export default function Asistente() {
  const [mensajes, setMensajes] = useState<MensajeChat[]>(cargar)
  const [texto, setTexto] = useState('')
  const [pensando, setPensando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fin = useRef<HTMLDivElement>(null)
  const { data: estado } = useQuery({ queryKey: ['asistente'], queryFn: () => api.get<{ disponible: boolean }>('/asistente/estado') })

  useEffect(() => {
    try { sessionStorage.setItem(CLAVE, JSON.stringify(mensajes)) } catch { /* sin almacenamiento */ }
    fin.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [mensajes, pensando])

  const enviar = async (pregunta: string) => {
    if (!pregunta.trim() || pensando) return
    const nuevos: MensajeChat[] = [...mensajes, { role: 'user', content: pregunta.trim() }]
    setMensajes(nuevos)
    setTexto('')
    setError(null)
    setPensando(true)
    try {
      const r = await api.post<{ respuesta: string }>('/asistente', { mensajes: nuevos })
      setMensajes([...nuevos, { role: 'assistant', content: r.respuesta }])
    } catch (e) {
      setError((e as Error).message)
      setMensajes(mensajes)  // la pregunta vuelve a la caja para reintentar
      setTexto(pregunta)
    } finally {
      setPensando(false)
    }
  }

  return (
    <>
      <Cabecera titulo="Asistente" subtitulo="Pregunta lo que quieras sobre tus finanzas: ve todos los datos de la app">
        {mensajes.length > 0 && <Boton variante="secundario" onClick={() => setMensajes([])}><RotateCcw size={15} />Nueva conversación</Boton>}
      </Cabecera>
      {estado && !estado.disponible ? (
        <Vacio>Para activar el asistente añade tu clave de la API de Anthropic como <code>ANTHROPIC_API_KEY</code> en la configuración (en Vercel, en Environment Variables) y vuelve a desplegar.</Vacio>
      ) : (
        <div className="flex min-h-[60vh] flex-col rounded-2xl border border-line bg-panel">
          <div className="flex-1 space-y-4 p-5">
            {mensajes.length === 0 && (
              <div className="py-6 text-center">
                <Sparkles className="mx-auto mb-3 text-accent" size={28} />
                <p className="text-sm text-muted">Algunas ideas para empezar:</p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {SUGERENCIAS.map((s) => (
                    <button key={s} onClick={() => enviar(s)} className="rounded-full border border-line px-3 py-1.5 text-sm hover:border-accent hover:text-accent">{s}</button>
                  ))}
                </div>
              </div>
            )}
            {mensajes.map((m, i) => (
              <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex'}>
                <div className={`max-w-[85%] space-y-1 rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${m.role === 'user' ? 'bg-accent text-panel' : 'bg-panel-2'}`}>
                  <Texto t={m.content} />
                </div>
              </div>
            ))}
            {pensando && <div className="flex"><div className="animate-pulse rounded-2xl bg-panel-2 px-4 py-2.5 text-sm text-muted">Mirando tus datos…</div></div>}
            {error && <p className="text-sm text-neg">{error}</p>}
            <div ref={fin} />
          </div>
          <form className="flex gap-2 border-t border-line p-3" onSubmit={(e) => { e.preventDefault(); enviar(texto) }}>
            <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={1} placeholder="Escribe tu pregunta…"
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar(texto) } }}
              className="min-w-0 flex-1 resize-none rounded-xl border border-line bg-bg px-3 py-2 text-sm" aria-label="Pregunta" />
            <Boton type="submit" disabled={!texto.trim() || pensando} aria-label="Enviar"><ArrowUp size={16} /></Boton>
          </form>
        </div>
      )}
      <p className="mt-3 text-xs text-muted">Usa Claude a través de la API de Anthropic: tus datos se envían para responder y no se usan para entrenar. Puede equivocarse; confirma lo importante con tu gestor.</p>
    </>
  )
}
