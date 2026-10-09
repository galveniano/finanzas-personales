import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { eur, fecha, fechaHora, pct } from '../lib/format'
import type { CarteraIndexa as Cartera } from '../lib/tipos'
import { Barra, Dato, ErrorCarga, Etiqueta, Importe, Tabla, Tarjeta } from './ui'

const CLASES: Record<string, string> = {
  equity: 'Renta variable', fixed_income: 'Renta fija', cash: 'Liquidez',
}
const clase = (c: string) => CLASES[c] ?? CLASES[c.split('_')[0]] ?? (c.toLowerCase().includes('equity') ? 'Renta variable'
  : c.toLowerCase().includes('fixed') || c.toLowerCase().includes('bond') ? 'Renta fija' : c.replace(/_/g, ' '))
const precio = (v: number | null) => (v == null ? '—' : v.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 4 }))

function Cuenta({ c }: { c: Cartera }) {
  const posiciones = c.posiciones ?? []
  const rv = posiciones.filter((p) => clase(p.clase) === 'Renta variable').reduce((s, p) => s + p.peso, 0)
  const total = c.total ?? 0
  const efectivo = c.efectivo ?? 0
  const efectivoAlto = total > 0 && efectivo / total > 0.01
  const conTitulos = posiciones.some((p) => p.titulos != null || p.precio != null)
  // Sin coste de la API, la plusvalía se estima con lo que has mandado desde el banco
  const aportado = c.aportado_banco && c.aportado_banco.total > 0 ? c.aportado_banco.total : null
  const plusvalia = c.plusvalia != null ? { valor: c.plusvalia, nota: `sobre ${eur(c.coste)} de coste` }
    : aportado != null ? { valor: total - aportado, nota: `estimada: ${eur(total)} de valor menos ${eur(aportado)} aportados desde el banco` }
    : { valor: null, nota: 'La API no da el coste y no hay traspasos desde el banco' }
  return (
    <Tarjeta titulo={c.producto ? `${c.producto} · ${c.numero}` : c.nombre} accion={
      <div className="flex flex-wrap items-center gap-2">
        {c.perfil_riesgo != null && <Etiqueta tono="acento">Perfil {c.perfil_riesgo}/10</Etiqueta>}
        {efectivoAlto && <Etiqueta tono="aviso">{eur(efectivo)} sin invertir ({pct((efectivo / total) * 100, 1)})</Etiqueta>}
        {c.ultima_sincronizacion ? <span className="text-xs text-muted">sincronizada {fechaHora(c.ultima_sincronizacion)}</span>
          : c.fecha && <span className="text-xs text-muted">a {fecha(c.fecha)}</span>}
      </div>}>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5 [&>*]:min-w-0">
        <Dato etiqueta="Valor" valor={eur(total)} nota={efectivo ? `${eur(efectivo)} en efectivo` : undefined} />
        <Dato etiqueta="Plusvalía" valor={<Importe valor={plusvalia.valor} signo />} nota={plusvalia.nota} />
        <Dato etiqueta="Rentabilidad anual" valor={pct(c.rentabilidad_anual)} tono={(c.rentabilidad_anual ?? 0) >= 0 ? 'pos' : 'neg'}
          nota={c.rentabilidad_total != null ? `${pct(c.rentabilidad_total)} desde el inicio (TWR, la de la cartera)` : 'TWR, la de la cartera'} />
        <Dato etiqueta="Rentabilidad de tu dinero" valor={pct(c.rentabilidad_dinero)} tono={c.rentabilidad_dinero == null ? undefined : c.rentabilidad_dinero >= 0 ? 'pos' : 'neg'}
          nota="MWR: cuenta cuándo aportaste cada euro; por eso difiere de la anual" />
        <Dato etiqueta="Volatilidad" valor={pct(c.volatilidad)}
          nota={c.rentabilidad_esperada != null ? `Esperada por Indexa: ${pct(c.rentabilidad_esperada)} al año` : undefined} />
      </div>
      {posiciones.length > 0 ? (
        <div className="mt-5">
          {rv > 0 && <p className="mb-2 text-xs text-muted">{Math.round(rv)} % renta variable · {Math.round(100 - rv)} % renta fija y liquidez</p>}
          <Tabla>
            <thead><tr>
              <th>Fondo</th><th className="hidden md:table-cell">Tipo</th><th className="hidden w-32 sm:table-cell">Peso</th>
              {conTitulos && <><th className="num hidden xl:table-cell">Títulos</th><th className="num hidden xl:table-cell">Precio</th></>}
              <th className="num">Valor</th><th className="num hidden sm:table-cell">Plusvalía</th>
            </tr></thead>
            <tbody>
              {posiciones.map((p) => (
                <tr key={p.codigo || p.nombre}>
                  <td className="max-w-[280px]">
                    <div className="truncate font-medium">{p.nombre}</div>
                    <div className="cifra truncate text-xs text-muted"><span className="sm:hidden">{pct(p.peso)} · </span>{p.codigo}{p.gestora && ` · ${p.gestora}`}</div>
                  </td>
                  <td className="hidden text-muted md:table-cell">{p.clase ? clase(p.clase) : '—'}</td>
                  <td className="hidden sm:table-cell"><div className="flex items-center gap-2"><div className="flex-1"><Barra valor={p.peso} max={100} /></div><span className="cifra w-12 text-right text-xs">{pct(p.peso)}</span></div></td>
                  {conTitulos && <>
                    <td className="num cifra hidden text-muted xl:table-cell">{p.titulos == null ? '—' : p.titulos.toLocaleString('es-ES', { maximumFractionDigits: 4 })}</td>
                    <td className="num cifra hidden text-muted xl:table-cell">{precio(p.precio)}{p.precio != null && p.fecha ? <span className="block text-[10px]">{fecha(p.fecha, { day: '2-digit', month: 'short' })}</span> : null}</td>
                  </>}
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
