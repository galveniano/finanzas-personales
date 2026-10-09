// Lo que comparten las gráficas de recharts: el tooltip con los colores del tema y los ejes sin línea.

export const estiloTooltip = {
  contentStyle: { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, fontSize: 12, color: 'var(--ink)' },
  labelStyle: { color: 'var(--muted)' },
}

/** Fondo de la columna bajo el ratón (BarChart y ComposedChart). */
export const cursorBarra = { fill: 'var(--panel-2)' }

/** Para `<XAxis {...eje} />` y `<YAxis {...eje} />`. */
export const eje = { tick: { fill: 'var(--muted)', fontSize: 11 }, axisLine: false, tickLine: false }
