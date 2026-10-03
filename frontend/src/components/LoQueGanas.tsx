import { useState } from 'react'
import type { ReactNode } from 'react'
import { eur } from '../lib/format'
import type { RentaPrevista } from '../lib/tipos'
import { Boton, Importe, Tabla, Tarjeta } from './ui'

const GASTOS_FUENTE: Record<string, string> = {
  'Nómina': 'Seguridad Social', 'Autónomo': 'Cuota y gastos', 'Alquiler': 'Comunidad, seguro, IBI e intereses',
}

export default function LoQueGanas({ anios, cuota, origenCuota, accion }: { anios: RentaPrevista[]; cuota: number; origenCuota: string; accion?: ReactNode }) {
  const [anio, setAnio] = useState(anios[0]?.anio)
  const r = anios.find((x) => x.anio === anio) ?? anios[0]
  if (!r) return null
  const mes = (v: number) => v / 12
  return (
    <Tarjeta titulo={`Lo que ganas al mes en ${r.anio}`} accion={
      <div className="flex flex-wrap items-center gap-1">{anios.length > 1 && anios.map((x) => (
        <Boton key={x.anio} variante={x.anio === r.anio ? 'primario' : 'secundario'} className="px-2.5 py-1 text-xs" onClick={() => setAnio(x.anio)}>{x.anio}</Boton>
      ))}{accion}</div>}>
      <Tabla>
        <thead><tr><th>Fuente</th><th className="num">Bruto</th><th className="num hidden sm:table-cell">Gastos</th><th className="num hidden sm:table-cell">IRPF</th><th className="num">Neto</th></tr></thead>
        <tbody>
          {r.ingresos.fuentes.map((f) => (
            <tr key={f.fuente}>
              <td>{f.fuente}<div className="text-xs text-muted">{f.cliente ? 'Autónomo' : GASTOS_FUENTE[f.fuente]}</div></td>
              <td className="num"><Importe valor={f.bruto_mes} /></td>
              <td className="num hidden sm:table-cell"><Importe valor={-mes(f.gastos_anual)} /></td>
              <td className="num hidden sm:table-cell"><Importe valor={-mes(f.irpf_anual)} /></td>
              <td className="num font-medium"><Importe valor={f.neto_mes} /></td>
            </tr>
          ))}
          <tr className="font-semibold">
            <td>Total al mes</td>
            <td className="num"><Importe valor={r.ingresos.total.bruto_mes} /></td>
            <td className="num hidden sm:table-cell"><Importe valor={-mes(r.ingresos.total.gastos_anual)} /></td>
            <td className="num hidden sm:table-cell"><Importe valor={-mes(r.ingresos.total.irpf_anual)} /></td>
            <td className="num"><Importe valor={r.ingresos.total.neto_mes} /></td>
          </tr>
          <tr className="text-muted">
            <td>Total al año</td>
            <td className="num"><Importe valor={r.ingresos.total.bruto_anual} /></td>
            <td className="num hidden sm:table-cell"><Importe valor={-r.ingresos.total.gastos_anual} /></td>
            <td className="num hidden sm:table-cell"><Importe valor={-r.ingresos.total.irpf_anual} /></td>
            <td className="num"><Importe valor={r.ingresos.total.neto_anual} /></td>
          </tr>
        </tbody>
      </Tabla>
      <p className="mt-3 text-xs text-muted">
        Media del año (las pagas extra y el variable se reparten en 12). El IRPF es el de la renta completa, no solo lo retenido,
        repartido al tipo medio entre lo que aporta cada fuente.
        Gastos de autónomo: {eur(cuota)} al mes ({origenCuota}).
      </p>
    </Tarjeta>
  )
}

