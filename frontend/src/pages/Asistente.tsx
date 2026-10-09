import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowUp, RotateCcw, Sparkles } from 'lucide-react'
import { api } from '../lib/api'
import type { Aviso, EstadoAsistente, MensajeChat, RespuestaAsistente, Resumen } from '../lib/tipos'
import { Boton, Cabecera, EnDosPasos, ErrorCarga, Vacio } from '../components/ui'

const CLAVE = 'finanzas:asistente'
const TOPE_MENSAJES = 20  // los mismos que manda el servidor al modelo
const SUGERENCIAS = [
  '¿Cuánto me toca pagar este trimestre de IVA y de IRPF?',
  '¿Cuánto puedo ahorrar al mes para la boda?',
  '¿En qué he gastado más este último mes?',
  '¿Me conviene amortizar hipoteca o invertir en Indexa?',
]
/** A qué pantalla lleva cada herramienta que ha consultado el asistente. */
const HERRAMIENTAS: Record<string, { texto: string; ruta: string }> = {
  movimientos: { texto: 'movimientos', ruta: '/cuentas' },
  autonomo: { texto: 'autónomo', ruta: '/ingresos' },
  nominas: { texto: 'nóminas', ruta: '/ingresos?ver=nomina' },
  calcular_sueldo: { texto: 'calculadora de sueldo', ruta: '/ingresos?ver=nomina' },
  inmuebles: { texto: 'bienes', ruta: '/inmuebles' },
  vender_o_alquilar: { texto: 'vender o alquilar', ruta: '/inmuebles' },
  planificacion: { texto: 'plan', ruta: '/plan' },
  prevision: { texto: 'previsión', ruta: '/plan' },
  inversiones: { texto: 'inversiones', ruta: '/inversiones' },
  indexa: { texto: 'Indexa', ruta: '/inversiones' },
  gastos: { texto: 'gastos', ruta: '/gastos' },
  hacienda: { texto: 'Hacienda', ruta: '/impuestos' },
  hacienda_hoy: { texto: 'Hacienda hoy', ruta: '/impuestos' },
  ahorro_fiscal: { texto: 'ahorro fiscal', ruta: '/impuestos' },
}

function cargar(): MensajeChat[] {
  try { return (JSON.parse(sessionStorage.getItem(CLAVE) ?? '[]') as MensajeChat[]).slice(-TOPE_MENSAJES) } catch { return [] }
}

/** Preguntas que vienen de los avisos de Inicio (plazos, Sabadell, cuota…), y detrás las fijas. */
function sugerencias(avisos: Aviso[] | undefined): string[] {
  const propias: string[] = []
  for (const a of avisos ?? []) {
    const t = a.texto.toLowerCase()
    if (t.includes('plazo')) propias.push('¿Cuánto me toca de IVA este trimestre?')
    else if (t.includes('sabadell')) propias.push('¿Tengo que renovar el permiso de Sabadell?')
    else if (t.includes('cuota de autónomos')) propias.push('¿Me van a regularizar la cuota de autónomos?')
    else if (t.includes('hacienda te carga')) propias.push('¿Tengo dinero en la cuenta para lo que me carga Hacienda?')
    else if (t.includes('actualiza lo que vale')) propias.push('¿Qué rentabilidad me da el piso alquilado?')
  }
  return [...new Set([...propias, ...SUGERENCIAS])].slice(0, 7)
}

/** Un error de red o de Vercel (504) se explica en vez de enseñar «Error 504». */
const explicarError = (e: Error) =>
  /\b50[234]\b|timeout|tiempo de espera|gateway|failed to fetch/i.test(e.message)
    ? 'El asistente ha tardado demasiado y la petición se ha cortado. Prueba con una pregunta más concreta (un año, un trimestre, un cliente).'
    : e.message

// --- Markdown sencillo: títulos (##), listas (-, *, 1.) y negritas; nunca se interpreta HTML ------------------

type Bloque = { tipo: 'p' | 'h' | 'ul' | 'ol'; lineas: string[] }

function bloques(t: string): Bloque[] {
  const out: Bloque[] = []
  for (const cruda of t.split('\n')) {
    const l = cruda.trimEnd()
    const titulo = /^#{1,4}\s+(.*)$/.exec(l)
    const vineta = /^\s*[-*•]\s+(.*)$/.exec(l)
    const numero = /^\s*\d+[.)]\s+(.*)$/.exec(l)
    const ultimo = out[out.length - 1]
    if (titulo) out.push({ tipo: 'h', lineas: [titulo[1]] })
    else if (vineta && ultimo?.tipo === 'ul') ultimo.lineas.push(vineta[1])
    else if (vineta) out.push({ tipo: 'ul', lineas: [vineta[1]] })
    else if (numero && ultimo?.tipo === 'ol') ultimo.lineas.push(numero[1])
    else if (numero) out.push({ tipo: 'ol', lineas: [numero[1]] })
    else out.push({ tipo: 'p', lineas: [l] })
  }
  return out
}

function Linea({ t }: { t: string }) {
  return <>{t.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((x, j) =>
    x.startsWith('**') && x.endsWith('**') ? <strong key={j}>{x.slice(2, -2)}</strong>
      : x.startsWith('`') && x.endsWith('`') ? <code key={j} className="cifra text-[13px]">{x.slice(1, -1)}</code>
        : x)}</>
}

function Texto({ t }: { t: string }) {
  return <>{bloques(t).map((b, i) => {
    if (b.tipo === 'h') return <h3 key={i} className="mt-2 font-semibold first:mt-0"><Linea t={b.lineas[0]} /></h3>
    if (b.tipo === 'ul' || b.tipo === 'ol') {
      const Lista = b.tipo === 'ul' ? 'ul' : 'ol'
      return <Lista key={i} className={`ml-5 space-y-0.5 ${b.tipo === 'ul' ? 'list-disc' : 'list-decimal'}`}>{b.lineas.map((l, j) => <li key={j}><Linea t={l} /></li>)}</Lista>
    }
    const linea = b.lineas[0]
    return <p key={i} className={linea.trim() ? 'min-h-[1em]' : 'h-2'}><Linea t={linea} /></p>
  })}</>
}

function HaMirado({ consultas }: { consultas: string[] }) {
  const distintas = [...new Set(consultas)]
  if (!distintas.length) return null
  return (
    <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">
      Ha mirado:
      {distintas.map((c) => {
        const h = HERRAMIENTAS[c]
        return h
          ? <Link key={c} to={h.ruta} className="rounded-full border border-line px-2 py-0.5 hover:border-accent hover:text-accent">{h.texto}</Link>
          : <span key={c} className="rounded-full border border-line px-2 py-0.5">{c}</span>
      })}
    </p>
  )
}

export default function Asistente() {
  const [mensajes, setMensajes] = useState<MensajeChat[]>(cargar)
  const [texto, setTexto] = useState('')
  const [pensando, setPensando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fin = useRef<HTMLDivElement>(null)
  const { data: estado, error: errorEstado } = useQuery({ queryKey: ['asistente'], queryFn: () => api.get<EstadoAsistente>('/asistente/estado') })
  const { data: resumen } = useQuery({ queryKey: ['resumen'], queryFn: () => api.get<Resumen>('/resumen'), enabled: mensajes.length === 0 })

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
      // Al modelo solo van papel y texto; las consultas de cada respuesta se quedan en la pantalla
      const r = await api.post<RespuestaAsistente>('/asistente', { mensajes: nuevos.map(({ role, content }) => ({ role, content })) })
      const respuesta: MensajeChat = { role: 'assistant', content: r.respuesta, consultas: r.consultas }
      setMensajes([...nuevos, respuesta].slice(-TOPE_MENSAJES))
    } catch (e) {
      setError(explicarError(e as Error))
      setMensajes(mensajes)  // la pregunta vuelve a la caja para reintentar
      setTexto(pregunta)
    } finally {
      setPensando(false)
    }
  }

  return (
    <>
      <Cabecera titulo="Asistente" subtitulo="Pregunta lo que quieras sobre tus finanzas: ve todos los datos de la app">
        {mensajes.length > 0 && (
          <EnDosPasos icono={<RotateCcw size={15} />} texto="Nueva conversación" textoConfirmar="¿Borrar la conversación? Confirmar"
            onConfirmar={() => { setMensajes([]); setError(null) }} />
        )}
      </Cabecera>
      {errorEstado && !estado ? (
        <ErrorCarga error={errorEstado} />
      ) : estado && !estado.disponible ? (
        <Vacio>Para activar el asistente pon tu clave de OpenAI o de Claude en <Link to="/ajustes" className="font-medium text-accent">Ajustes → Asistente (IA)</Link>.</Vacio>
      ) : (
        <div className="flex min-h-[60vh] flex-col rounded-2xl border border-line bg-panel">
          <div className="flex-1 space-y-4 p-5">
            {mensajes.length === 0 && (
              <div className="py-6 text-center">
                <Sparkles className="mx-auto mb-3 text-accent" size={28} />
                <p className="text-sm text-muted">Algunas ideas para empezar:</p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {sugerencias(resumen?.avisos).map((s) => (
                    <button key={s} onClick={() => enviar(s)} className="rounded-full border border-line px-3 py-1.5 text-sm hover:border-accent hover:text-accent">{s}</button>
                  ))}
                </div>
              </div>
            )}
            {mensajes.map((m, i) => (
              <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex'}>
                <div className="max-w-[85%] min-w-0">
                  <div className={`space-y-1 rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${m.role === 'user' ? 'bg-accent text-panel' : 'bg-panel-2'}`}>
                    <Texto t={m.content} />
                  </div>
                  {m.role === 'assistant' && m.consultas && <HaMirado consultas={m.consultas} />}
                </div>
              </div>
            ))}
            {pensando && <div className="flex"><div className="animate-pulse rounded-2xl bg-panel-2 px-4 py-2.5 text-sm text-muted">Mirando tus datos…</div></div>}
            {error && <p className="text-sm text-neg" role="alert">{error}</p>}
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
      <p className="mt-3 text-xs text-muted">Usa {estado?.proveedor_nombre ?? 'un modelo de IA'} a través de su API: tus datos se envían para responder y no se usan para entrenar. Puede equivocarse; confirma lo importante con tu gestor.</p>
    </>
  )
}
