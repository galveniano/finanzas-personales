/** Barra de progreso como `Barra` de ui.tsx, pero con tono: acento por defecto, aviso o neg (p. ej. al pasarse de
 *  un presupuesto). Candidata a fundirse con `Barra` añadiéndole la prop `tono`. */
export default function BarraTono({ valor, max, tono = 'acento', etiqueta, fina }: {
  valor: number; max: number; tono?: 'acento' | 'aviso' | 'neg'; etiqueta?: string; fina?: boolean
}) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (valor / max) * 100)) : 0
  const color = { acento: 'bg-accent', aviso: 'bg-warn', neg: 'bg-neg' }[tono]
  return (
    <div className={`${fina ? 'h-1.5' : 'h-2'} overflow-hidden rounded-full bg-panel-2`} role="progressbar" aria-label={etiqueta}
      aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`h-full rounded-full transition-[width] ${color}`} style={{ width: `${pct}%` }} />
    </div>
  )
}
