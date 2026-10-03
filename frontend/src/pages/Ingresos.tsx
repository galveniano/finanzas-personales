import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Settings2 } from 'lucide-react'
import { api } from '../lib/api'
import type { Prevision } from '../lib/tipos'
import FormSupuestos from '../components/FormSupuestos'
import LoQueGanas from '../components/LoQueGanas'
import SeccionAutonomo from '../components/SeccionAutonomo'
import SeccionNomina from '../components/SeccionNomina'
import { Boton, Cabecera, Dialogo, Tarjeta, Vacio } from '../components/ui'

const PESTANAS = [{ id: 'autonomo', texto: 'Autónomo' }, { id: 'nomina', texto: 'Nómina' }] as const

export default function Ingresos() {
  const [params, setParams] = useSearchParams()
  const ver = params.get('ver') === 'nomina' ? 'nomina' : 'autonomo'
  const [editar, setEditar] = useState(false)
  const { data: d } = useQuery({ queryKey: ['prevision'], queryFn: () => api.get<Prevision>('/prevision') })
  const sinDatos = d && !d.supuestos.nomina && !d.supuestos.clientes.length
  const botonSupuestos = <Boton variante="secundario" className="px-2.5 py-1 text-xs" onClick={() => setEditar(true)}><Settings2 size={14} />Sueldo y tarifas</Boton>

  return (
    <>
      <Cabecera titulo="Ingresos" subtitulo="Tu nómina, lo que facturas y el alquiler" />

      {d && (sinDatos
        ? <Tarjeta titulo="Lo que ganas al mes" accion={botonSupuestos}>
            <Vacio>Pon tu sueldo y lo que cobras a cada cliente en «Sueldo y tarifas» y verás lo que te queda cada mes.</Vacio>
          </Tarjeta>
        : <LoQueGanas anios={d.anios} cuota={d.gastos_autonomo_mes} origenCuota={d.origen_gastos_autonomo} accion={botonSupuestos} />)}

      <div className="mt-8 mb-4 flex gap-1 border-b border-line" role="tablist">
        {PESTANAS.map((p) => (
          <button key={p.id} role="tab" aria-selected={ver === p.id} onClick={() => setParams(p.id === 'autonomo' ? {} : { ver: p.id }, { replace: true })}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${ver === p.id ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-ink'}`}>
            {p.texto}
          </button>
        ))}
      </div>
      {ver === 'nomina' ? <SeccionNomina /> : <SeccionAutonomo />}

      <Dialogo abierto={editar} onCerrar={() => setEditar(false)} titulo="Sueldo y tarifas">
        {editar && d && <FormSupuestos s={d.supuestos} habitualBanco={d.gasto_habitual_banco} cerrar={() => setEditar(false)} />}
      </Dialogo>
    </>
  )
}
