import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../lib/api'
import { eur, eurK, fecha, hoyISO } from '../lib/format'
import type { Nominas as Datos } from '../lib/tipos'
import { Boton, Cabecera, Campo, Cargando, Dato, Dialogo, ErrorCarga, Formulario, Importe, Tabla, Tarjeta, Vacio, num, useAccion } from '../components/ui'

export default function Nominas() {
  const [abierto, setAbierto] = useState(false)
  const { data: d, isLoading, error } = useQuery({ queryKey: ['nominas'], queryFn: () => api.get<Datos>('/nominas') })
  const crear = useAccion((v: Record<string, string>) => api.post('/nominas', {
    empresa: v.empresa, fecha: v.fecha, bruto: num(v.bruto), retencion_irpf: num(v.retencion_irpf),
    seguridad_social: num(v.seguridad_social), neto: num(v.neto),
  }).then(() => setAbierto(false)), 'Nómina registrada')

  if (isLoading) return <Cargando />
  if (error) return <ErrorCarga error={error} />
  if (!d) return null
  const t = d.totales
  const tipoMedio = t.bruto ? (t.retencion_irpf / t.bruto) * 100 : 0
  const delAnio = d.nominas.filter((n) => n.fecha.startsWith(String(d.anio))).slice().reverse()

  return (
    <>
      <Cabecera titulo="Nóminas" subtitulo={`Trabajo por cuenta ajena en ${d.anio}`}>
        <Boton onClick={() => setAbierto(true)}><Plus size={16} />Nómina</Boton>
      </Cabecera>
      <Tarjeta>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <Dato etiqueta="Bruto acumulado" valor={eur(t.bruto)} />
          <Dato etiqueta="Retenido IRPF" valor={eur(t.retencion_irpf)} nota={`${tipoMedio.toFixed(2).replace('.', ',')} % de media`} />
          <Dato etiqueta="Seguridad Social" valor={eur(t.seguridad_social)} />
          <Dato etiqueta="Neto cobrado" valor={eur(t.neto)} />
        </div>
      </Tarjeta>

      {delAnio.length > 1 && (
        <Tarjeta className="mt-4" titulo="Bruto y retención por mes">
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={delAnio} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--line)" />
                <XAxis dataKey="fecha" tickFormatter={(v) => fecha(v, { month: 'short' })} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={eurK} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} width={68} />
                <Tooltip contentStyle={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, fontSize: 12 }}
                  cursor={{ fill: 'var(--panel-2)' }} formatter={(v, n) => [eur(Number(v)), n === 'neto' ? 'Neto' : 'IRPF']} labelFormatter={(v) => fecha(String(v), { month: 'long' })} />
                <Bar dataKey="neto" stackId="a" fill="var(--chart-1)" maxBarSize={28} />
                <Bar dataKey="retencion_irpf" stackId="a" fill="var(--chart-3)" radius={[4, 4, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Tarjeta>
      )}

      <Tarjeta className="mt-4" titulo="Todas las nóminas">
        {d.nominas.length ? (
          <Tabla>
            <thead><tr><th>Mes</th><th>Empresa</th><th className="num">Bruto</th><th className="num">IRPF</th><th className="num">SS</th><th className="num">Neto</th></tr></thead>
            <tbody>
              {d.nominas.map((n) => (
                <tr key={n.id}>
                  <td className="whitespace-nowrap capitalize">{fecha(n.fecha, { month: 'long', year: 'numeric' })}</td>
                  <td className="text-muted">{n.empresa}</td>
                  <td className="num"><Importe valor={n.bruto} /></td>
                  <td className="num"><Importe valor={n.retencion_irpf} /></td>
                  <td className="num"><Importe valor={n.seguridad_social} /></td>
                  <td className="num font-medium"><Importe valor={n.neto} /></td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        ) : <Vacio>Registra tus nóminas de Indra para saber cuánto te han retenido y estimar la renta.</Vacio>}
      </Tarjeta>

      <Dialogo abierto={abierto} onCerrar={() => setAbierto(false)} titulo="Registrar nómina">
        <Formulario onEnviar={(v) => crear.mutateAsync(v)}>
          <Campo etiqueta="Empresa" name="empresa" defaultValue="Indra" />
          <Campo etiqueta="Fecha" name="fecha" type="date" defaultValue={hoyISO()} required />
          <Campo etiqueta="Bruto (€)" name="bruto" inputMode="decimal" required />
          <Campo etiqueta="Retención IRPF (€)" name="retencion_irpf" inputMode="decimal" required />
          <Campo etiqueta="Seguridad Social (€)" name="seguridad_social" inputMode="decimal" required />
          <Campo etiqueta="Neto (€)" name="neto" inputMode="decimal" required />
        </Formulario>
      </Dialogo>
    </>
  )
}
