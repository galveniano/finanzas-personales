import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { MESES, capitalizar, eur, pct } from '../lib/format'
import type { CalculoNomina } from '../lib/tipos'
import { num } from '../lib/utilidades'
import { Campo, Casilla, Dato, Segmentos, Selector, Tabla, Tarjeta } from './ui'

const MODOS = [{ valor: 'bruto', texto: 'Bruto a neto' }, { valor: 'neto', texto: 'Neto a bruto' }] as const

/** De bruto anual a neto de cada mes, o qué bruto hace falta para cobrar un neto. */
export default function CalculadoraSueldo({ brutoInicial }: { brutoInicial: number | null }) {
  const [modo, setModo] = useState<'bruto' | 'neto'>('bruto')
  const [importe, setImporte] = useState(brutoInicial ? String(Math.round(brutoInicial)) : '35000')
  const [pagas, setPagas] = useState('14')
  const [hijos, setHijos] = useState('0')
  const [temporal, setTemporal] = useState(false)
  const [tipo, setTipo] = useState('')  // retención que quieres probar; vacía = la calculada
  const valor = num(importe)
  const tipoElegido = modo === 'bruto' ? num(tipo) : undefined
  const params = new URLSearchParams({ pagas, hijos, temporal: String(temporal), [modo === 'bruto' ? 'bruto_anual' : 'neto_mes']: String(valor ?? 0) })
  if (tipoElegido != null) params.set('tipo_irpf', String(tipoElegido))
  const { data: c, isFetching } = useQuery({
    queryKey: ['calculo-nomina', params.toString()], queryFn: () => api.get<CalculoNomina>(`/nominas/calculo?${params}`),
    enabled: !!valor && valor > 0, placeholderData: (prev) => prev,
  })

  return (
    <Tarjeta className="mt-4" titulo="Calculadora de sueldo" accion={
      <Segmentos pequeno etiqueta="Modo de cálculo" opciones={MODOS} valor={modo} onCambiar={setModo} />}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Campo etiqueta={modo === 'bruto' ? 'Bruto anual (€)' : 'Neto que quieres al mes (€)'} value={importe} onChange={(e) => setImporte(e.target.value)} inputMode="decimal" />
        <Selector etiqueta="Pagas" value={pagas} onChange={(e) => setPagas(e.target.value)}>
          <option value="14">14 (extras jun. y dic.)</option><option value="12">12 (prorrateadas)</option>
        </Selector>
        <Selector etiqueta="Hijos" value={hijos} onChange={(e) => setHijos(e.target.value)}>
          {[0, 1, 2, 3].map((h) => <option key={h} value={h}>{h === 3 ? '3 o más' : h}</option>)}
        </Selector>
        {modo === 'bruto' && (
          <Campo etiqueta="Retención que quieres (%)" value={tipo} onChange={(e) => setTipo(e.target.value)} inputMode="decimal" placeholder="La calculada"
            ayuda="Para ver qué neto queda si le pides más a la empresa." />
        )}
        <Casilla etiqueta="Contrato temporal" className="self-start pt-7" checked={temporal} onChange={(e) => setTemporal(e.target.checked)} />
      </div>

      {c && (
        <div className={isFetching ? 'opacity-60 transition' : 'transition'}>
          <div className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {modo === 'neto' && <Dato etiqueta="Bruto anual necesario" valor={eur(c.bruto_anual)} />}
            <Dato etiqueta="Neto al mes" valor={eur(c.neto_mes)} nota={c.neto_paga_extra != null ? `Pagas extra: ${eur(c.neto_paga_extra)}` : undefined} />
            <Dato etiqueta="Retención IRPF" valor={pct(c.tipo_irpf)} nota={`${eur(c.irpf_anual)} al año${tipoElegido != null ? ' · la que has puesto' : ''}`} />
            <Dato etiqueta="Seguridad Social" valor={eur(c.ss_anual)} nota="al año" />
            {modo === 'bruto' && <Dato etiqueta="Neto al año" valor={eur(c.neto_anual)} />}
          </div>
          <details className="mt-5">
            <summary className="cursor-pointer text-sm font-medium text-accent">Ver mes a mes</summary>
            <div className="mt-3">
              <Tabla>
                <thead><tr><th>Mes</th><th className="num">Bruto</th><th className="num">Seg. Social</th><th className="num">IRPF</th><th className="num">Neto</th></tr></thead>
                <tbody>
                  {c.meses.map((m, i) => (
                    <tr key={i}>
                      <td>{capitalizar(MESES[m.mes - 1])}{m.paga_extra && <span className="ml-1 text-xs text-muted">(paga extra)</span>}</td>
                      <td className="num cifra">{eur(m.bruto)}</td><td className="num cifra">{eur(m.seguridad_social)}</td>
                      <td className="num cifra">{eur(m.irpf)}</td><td className="num cifra font-medium">{eur(m.neto)}</td>
                    </tr>
                  ))}
                </tbody>
              </Tabla>
            </div>
          </details>
          <p className="mt-4 text-xs text-muted">
            Estimación con las cotizaciones de 2026 y el cálculo general de retenciones. Tu empresa puede retenerte otro tipo (puedes pedirle uno más alto), y como también
            facturas como autónomo, en la renta pagarás más de lo que te retienen en la nómina.
          </p>
        </div>
      )}
    </Tarjeta>
  )
}
