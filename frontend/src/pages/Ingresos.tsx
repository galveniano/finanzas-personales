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
import { Boton, Cabecera, Dialogo, ErrorCarga, Pestanas, Tarjeta, Vacio } from '../components/ui'

const PESTANAS = [{ id: 'autonomo', texto: 'Autónomo' }, { id: 'nomina', texto: 'Nómina' }] as const

export default function Ingresos() {
  const [params, setParams] = useSearchParams()
  // ?ver=nomina abre esa pestaña; ?accion=factura abre «Registrar factura» (en Autónomo) desde fuera
  const ver = params.get('accion') === 'factura' ? 'autonomo' : params.get('ver') === 'nomina' ? 'nomina' : 'autonomo'
  const [editar, setEditar] = useState(false)
  const { data: d, error } = useQuery({ queryKey: ['prevision'], queryFn: () => api.get<Prevision>('/prevision') })
  const sinDatos = d && !d.supuestos.nomina && !d.supuestos.clientes.length
  const botonSupuestos = <Boton variante="secundario" className="px-2.5 py-1 text-xs" onClick={() => setEditar(true)}><Settings2 size={14} />Sueldo y tarifas</Boton>

  return (
    <>
      <Cabecera titulo="Ingresos" subtitulo="Tu nómina, lo que facturas y el alquiler" />

      {error && !d && <ErrorCarga error={error} />}
      {d && (sinDatos
        ? <Tarjeta titulo="Lo que ganas al mes" accion={botonSupuestos}>
            <Vacio>Pon tu sueldo y lo que cobras a cada cliente en «Sueldo y tarifas» y verás lo que te queda cada mes.</Vacio>
          </Tarjeta>
        : <LoQueGanas anios={d.anios} cuota={d.gastos_autonomo_mes} origenCuota={d.origen_gastos_autonomo} accion={botonSupuestos} />)}

      <Pestanas className="mt-8 mb-4" pestanas={PESTANAS} activa={ver} onCambiar={(id) => setParams(id === 'autonomo' ? {} : { ver: id }, { replace: true })} />
      {ver === 'nomina' ? <SeccionNomina /> : <SeccionAutonomo />}

      <Dialogo abierto={editar} onCerrar={() => setEditar(false)} titulo="Sueldo y tarifas">
        {editar && d && <FormSupuestos s={d.supuestos} habitualBanco={d.gasto_habitual_banco} cerrar={() => setEditar(false)} />}
      </Dialogo>
    </>
  )
}
