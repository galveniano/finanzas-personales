import type { SimpleIcon } from 'simple-icons'
import {
  siApple, siApplemusic, siAppletv, siAudible, siClaude, siCrunchyroll, siCursor, siDazn, siDeezer, siDropbox,
  siDuolingo, siFigma, siGithub, siGlovo, siGoogle, siHbomax, siMovistar, siMubi, siNetflix, siNotion,
  siOrange, siParamountplus, siPatreon, siPerplexity, siPlaystation, siSpotify, siStrava, siTidal, siTwitch,
  siUber, siVodafone, siYoutube, siZoom,
} from 'simple-icons'
import { Briefcase, Building2, Car, HeartPulse, Home, Plug, Repeat, ShoppingBag, Smartphone, Store, Tv, Utensils, Zap } from 'lucide-react'

// Logos de las marcas (simple-icons, CC0) que van dentro del frontal: no se pide nada a webs de fuera.
// La clave es la que da el servidor (finanzas/gastos.py, SERVICIOS); las que no tienen logo salen con su inicial.
const LOGOS: Record<string, SimpleIcon> = {
  apple: siApple, applemusic: siApplemusic, appletv: siAppletv, audible: siAudible, claude: siClaude,
  crunchyroll: siCrunchyroll, cursor: siCursor, dazn: siDazn, deezer: siDeezer, dropbox: siDropbox,
  duolingo: siDuolingo, figma: siFigma, github: siGithub, glovo: siGlovo, google: siGoogle, googleone: siGoogle,
  hbomax: siHbomax, movistar: siMovistar, movistarplus: siMovistar, mubi: siMubi, netflix: siNetflix,
  notion: siNotion, orange: siOrange, paramountplus: siParamountplus, patreon: siPatreon,
  perplexity: siPerplexity, playstation: siPlaystation, spotify: siSpotify, strava: siStrava, tidal: siTidal,
  twitch: siTwitch, uber: siUber, vodafone: siVodafone, youtube: siYoutube, zoom: siZoom,
}

// Recibos que no son de una marca conocida: un icono según la categoría
const POR_CATEGORIA: Record<string, typeof Repeat> = {
  'Cuota hipoteca': Home, 'Cuota autónomos': Briefcase, Suministros: Zap, 'Ocio y suscripciones': Tv,
  Supermercado: ShoppingBag, Restaurantes: Utensils, Transporte: Car, Compras: ShoppingBag,
  'Luz, gas y agua': Plug, 'Teléfono e internet': Smartphone, Seguros: HeartPulse, Comunidad: Building2,
}

/** Texto blanco o negro según lo claro que sea el color de fondo. */
function tinta(hex: string) {
  const n = parseInt(hex.replace('#', ''), 16)
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255]
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.62 ? '#111111' : '#ffffff'
}

export default function IconoServicio({ icono, color, nombre, categoria, grupo, sitio = false, tamano = 36 }: {
  icono: string | null; color: string | null; nombre: string; categoria?: string | null; grupo?: string
  /** Un comercio, no un cargo que se repite: sin categoría con icono sale una tienda */
  sitio?: boolean; tamano?: number
}) {
  const logo = icono ? LOGOS[icono] : undefined
  const estilo = { width: tamano, height: tamano }
  if (color) {
    const fondo = color
    return (
      <span aria-hidden className="grid shrink-0 place-items-center rounded-xl" style={{ ...estilo, background: fondo, color: tinta(fondo) }}>
        {logo
          ? <svg viewBox="0 0 24 24" width={tamano * 0.55} height={tamano * 0.55} fill="currentColor"><path d={logo.path} /></svg>
          : <span className="font-semibold" style={{ fontSize: tamano * 0.42 }}>{nombre.replace(/[^\p{L}\p{N}]/gu, '').slice(0, 1).toUpperCase()}</span>}
      </span>
    )
  }
  const Icono = POR_CATEGORIA[categoria ?? ''] ?? POR_CATEGORIA[grupo ?? ''] ?? (sitio ? Store : Repeat)
  return (
    <span aria-hidden className="grid shrink-0 place-items-center rounded-xl bg-panel-2 text-muted" style={estilo}>
      <Icono size={tamano * 0.5} />
    </span>
  )
}
