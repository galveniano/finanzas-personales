// Atajos de teclado globales: «g» + letra salta a una pantalla, «/» y Ctrl/Cmd+K abren la paleta, «?» la ayuda.
// Se ignoran mientras escribes en un campo o hay un <dialog> abierto.
import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

export interface Destino { ruta: string; texto: string; tecla?: string }

/** Pantallas y secciones a las que se salta con «g» + tecla; también son la lista de la paleta. */
export const DESTINOS: readonly Destino[] = [
  { ruta: '/', texto: 'Inicio', tecla: 'i' },
  { ruta: '/cuentas', texto: 'Cuentas', tecla: 'c' },
  { ruta: '/gastos', texto: 'Gastos', tecla: 'g' },
  { ruta: '/ingresos', texto: 'Ingresos › Autónomo', tecla: 'n' },
  { ruta: '/ingresos?ver=nomina', texto: 'Ingresos › Nómina' },
  { ruta: '/impuestos', texto: 'Impuestos', tecla: 't' },
  { ruta: '/inmuebles', texto: 'Bienes', tecla: 'b' },
  { ruta: '/plan', texto: 'Plan', tecla: 'p' },
  { ruta: '/inversiones', texto: 'Inversiones', tecla: 'v' },
  { ruta: '/ajustes', texto: 'Ajustes', tecla: 'a' },
  { ruta: '/asistente', texto: 'Asistente' },
]

export const esMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/i.test(navigator.userAgent)
/** Cómo se escribe la tecla de la paleta en esta máquina: ⌘ K o Ctrl K. */
export const TECLA_MOD = esMac ? '⌘' : 'Ctrl'

export const AYUDA_ATAJOS: readonly { teclas: string[]; texto: string }[] = [
  { teclas: [TECLA_MOD, 'K'], texto: 'Buscar o ejecutar una acción' },
  { teclas: ['/'], texto: 'Buscar' },
  { teclas: ['?'], texto: 'Esta ayuda' },
  ...DESTINOS.filter((d) => d.tecla).map((d) => ({ teclas: ['g', d.tecla!], texto: `Ir a ${d.texto}` })),
  { teclas: ['Esc'], texto: 'Cerrar' },
]

const ESPERA_G_MS = 1500

/** La pulsación va a un campo de texto (no hay que robársela). */
export function enCampo(e: KeyboardEvent): boolean {
  const t = e.target
  if (!(t instanceof HTMLElement)) return false
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) || t.isContentEditable
}

export const hayDialogo = () => !!document.querySelector('dialog[open]')

export function useAtajos({ onBuscar, onAyuda }: { onBuscar: () => void; onAyuda: () => void }) {
  const navigate = useNavigate()
  const g = useRef(0)  // cuándo se pulsó la «g» (0 = nada pendiente)
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        onBuscar()
        return
      }
      if (e.ctrlKey || e.metaKey || e.altKey || enCampo(e) || hayDialogo()) { g.current = 0; return }
      if (e.key === '/') { e.preventDefault(); onBuscar(); return }
      if (e.key === '?') { e.preventDefault(); onAyuda(); return }
      const k = e.key.toLowerCase()
      if (g.current && Date.now() - g.current < ESPERA_G_MS) {
        g.current = 0
        const destino = DESTINOS.find((d) => d.tecla === k)
        if (destino) { e.preventDefault(); navigate(destino.ruta) }
        return
      }
      g.current = k === 'g' ? Date.now() : 0
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [navigate, onBuscar, onAyuda])
}
