import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { eur, fecha, pct } from '../lib/format'
import type { CarteraIndexa as Cartera } from '../lib/tipos'
import { Barra, Dato, ErrorCarga, Etiqueta, Importe, Tabla, Tarjeta } from './ui'

const CLASES: Record<string, string> = {
  equity: 'Renta variable', fixed_income: 'Renta fija', cash: 'Liquidez',
}
const clase = (c: string) => CLASES[c] ?? CLASES[c.split('_')[0]] ?? (c.toLowerCase().includes('equity') ? 'Renta variable'
  : c.toLowerCase().includes('fixed') || c.toLowerCase().includes('bond') ? 'Renta fija' : c.replace(/_/g, ' '))

function Cuenta({ c }: { c: Cartera }) {
  const posiciones = c.posiciones ?? []
  const rv = posiciones.filter((p) => clase(p.clase) === 'Renta variable').reduce((s, p) => s + p.peso, 0)
  return (
    <Tarjeta titulo={c.producto ? `${c.producto} · ${c.numero}` : c.nombre} accion={
      <div className="flex flex-wrap items-center gap-2">
        {c.perfil_riesgo != null && <Etiqueta tono="acento">Perfil {c.perfil_riesgo}/10</Etiqueta>}
        {c.fecha && <span className="text-xs text-muted">a {fecha(c.fecha)}</span>}
      </div>}>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4 [&>*]:min-w-0">
        <Dato etiqueta="Valor" valor={eur(c.total)} nota={c.efectivo ? `${eur(c.efectivo)} en efectivo` : undefined} />
        <Dato etiqueta="Plusvalía" valor={<Importe valor={c.plusvalia} signo />} nota={c.coste != null ? `sobre ${eur(c.coste)} de coste` : 'La API no da el coste'} />
        <Dato etiqueta="Rentabilidad anual" valor={pct(c.rentabilidad_anual)} tono={(c.rentabilidad_anual ?? 0) >= 0 ? 'pos' : 'neg'}
          nota={c.rentabilidad_total != null ? `${pct(c.rentabilidad_total)} desde el inicio` : undefined} />
        <Dato etiqueta="Volatilidad" valor={pct(c.volatilidad)}
          nota={c.rentabilidad_esperada != null ? `Esperada por Indexa: ${pct(c.rentabilidad_esperada)} al año` : undefined} />
      </div>
      {posiciones.length > 0 ? (
        <div className="mt-5">
          {rv > 0 && <p className="mb-2 text-xs text-muted">{Math.round(rv)} % renta variable · {Math.round(100 - rv)} % renta fija y liquidez</p>}
          <Tabla>
            <thead><tr><th>Fondo</th><th className="hidden md:table-cell">Tipo</th><th className="hidden w-32 sm:table-cell">Peso</th><th className="num">Valor</th><th className="num hidden sm:table-cell">Plusvalía</th></tr></thead>
            <tbody>
              {posiciones.map((p) => (
                <tr key={p.codigo || p.nombre}>
                  <td className="max-w-[280px]">
                    <div className="truncate font-medium">{p.nombre}</div>
                    <div className="cifra truncate text-xs text-muted"><span className="sm:hidden">{pct(p.peso)} · </span>{p.codigo}{p.gestora && ` · ${p.gestora}`}</div>
                  </td>
                  <td className="hidden text-muted md:table-cell">{p.clase ? clase(p.clase) : '—'}</td>
                  <td className="hidden sm:table-cell"><div className="flex items-center gap-2"><div className="flex-1"><Barra valor={p.peso} max={100} /></div><span className="cifra w-12 text-right text-xs">{pct(p.peso)}</span></div></td>
                  <td className="num"><Importe valor={p.valor} /></td>
                  <td className="num hidden sm:table-cell"><Importe valor={p.coste != null ? p.valor - p.coste : null} signo /></td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        </div>
      ) : <p className="mt-4 text-sm text-muted">Pulsa Sincronizar para traer los fondos de esta cuenta.</p>}
    </Tarjeta>
  )
}

/** Cartera de Indexa: valor, rentabilidad y fondos de cada cuenta, de la última sincronización. */
export default function CarteraIndexa() {
  const { data, error } = useQuery({ queryKey: ['indexa'], queryFn: () => api.get<Cartera[]>('/indexa') })
  if (error && !data) return <section className="mt-8"><h2 className="mb-3 text-lg font-semibold">Indexa Capital</h2><ErrorCarga error={error} /></section>
  if (!data?.length) return null
  return (
    <section className="mt-8">
      <h2 className="mb-3 text-lg font-semibold">Indexa Capital</h2>
      <div className="space-y-4">{data.map((c) => <Cuenta key={c.cuenta_id} c={c} />)}</div>
    </section>
  )
}
