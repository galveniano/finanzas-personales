// Tema claro / oscuro / sistema. index.css entiende data-theme="light|dark" en <html>; sin atributo manda el sistema.
// Se aplica antes del primer render (main.tsx y un script en index.html) para que no parpadee.
import { useSyncExternalStore } from 'react'

export type Tema = 'claro' | 'oscuro' | 'sistema'
export const CLAVE_TEMA = 'finanzas:tema'
export const TEMAS: readonly { valor: Tema; texto: string }[] = [
  { valor: 'claro', texto: 'Claro' }, { valor: 'oscuro', texto: 'Oscuro' }, { valor: 'sistema', texto: 'Sistema' },
]

export function leerTema(): Tema {
  try {
    const v = localStorage.getItem(CLAVE_TEMA)
    if (v === 'claro' || v === 'oscuro') return v
  } catch { /* sin almacenamiento (modo privado) */ }
  return 'sistema'
}

const oyentes = new Set<() => void>()
let actual: Tema = leerTema()

/** Pone data-theme en <html>; «sistema» lo quita y manda prefers-color-scheme. Lo recuerda en localStorage. */
export function aplicarTema(t: Tema) {
  const html = document.documentElement
  if (t === 'sistema') html.removeAttribute('data-theme')
  else html.setAttribute('data-theme', t === 'oscuro' ? 'dark' : 'light')
  try {
    if (t === 'sistema') localStorage.removeItem(CLAVE_TEMA)
    else localStorage.setItem(CLAVE_TEMA, t)
  } catch { /* sin almacenamiento */ }
  actual = t
  oyentes.forEach((f) => f())
}

/** Lo que se ve ahora mismo, resolviendo «sistema». */
export function temaEfectivo(): 'claro' | 'oscuro' {
  if (actual !== 'sistema') return actual
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'oscuro' : 'claro'
}

const suscribir = (f: () => void) => {
  oyentes.add(f)
  return () => { oyentes.delete(f) }
}

/** El tema elegido, compartido entre el menú lateral y Ajustes. */
export const useTema = () => useSyncExternalStore(suscribir, () => actual, () => 'sistema' as Tema)
