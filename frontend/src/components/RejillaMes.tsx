import { useMemo } from 'react'
import { DIAS_SEMANA, festivoDe, festivos } from '../lib/festivos'

type Contexto = { festivo?: string; finde: boolean }

/** Rejilla de un mes («AAAA-MM»): cabecera de L a D, huecos hasta el primer día y un botón por día.
 *  Cada día llega con su festivo (si lo es) y si cae en fin de semana, para pintarlo y titularlo. */
export default function RejillaMes({ mes, claseDia, tituloDia, onDia, presionado }: {
  mes: string
  claseDia: (d: number, ctx: Contexto) => string
  tituloDia?: (d: number, ctx: Contexto) => string | undefined
  onDia: (d: number) => void
  presionado?: (d: number) => boolean
}) {
  const [anio, m] = mes.split('-').map(Number)
  const fest = useMemo(() => festivos(anio), [anio])
  const huecos = (new Date(anio, m - 1, 1).getDay() + 6) % 7
  const total = new Date(anio, m, 0).getDate()
  return (
    <div className="grid grid-cols-7 gap-1 text-center text-xs">
      {DIAS_SEMANA.map((d) => <div key={d} className="py-1 font-medium text-muted">{d}</div>)}
      {Array.from({ length: huecos }, (_, i) => <div key={`h${i}`} />)}
      {Array.from({ length: total }, (_, i) => i + 1).map((d) => {
        const ctx = { festivo: festivoDe(fest, mes, d), finde: [0, 6].includes(new Date(anio, m - 1, d).getDay()) }
        return (
          <button key={d} type="button" title={tituloDia?.(d, ctx)} onClick={() => onDia(d)} aria-pressed={presionado?.(d)}
            className={claseDia(d, ctx)}>
            {d}
          </button>
        )
      })}
    </div>
  )
}
