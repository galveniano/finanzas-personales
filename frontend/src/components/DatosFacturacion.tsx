import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { Facturacion } from '../lib/tipos'
import { useAccion } from '../lib/utilidades'
import { Area, Campo, Cargando, Formulario, Selector } from './ui'

/** Tus datos y los de cada cliente, para que salgan en el documento de la factura. */
export default function DatosFacturacion({ onHecho }: { onHecho: () => void }) {
  const { data } = useQuery({ queryKey: ['facturacion'], queryFn: () => api.get<Facturacion>('/facturacion') })
  const [parte, setParte] = useState<'tuyos' | string>('tuyos')
  const guardarEmisor = useAccion((d: Record<string, string>) => api.put('/facturacion/emisor', d).then(onHecho), 'Datos guardados')
  const guardarCliente = useAccion((d: Record<string, string>) => api.put(`/facturacion/clientes/${encodeURIComponent(parte)}`, d).then(onHecho), 'Cliente guardado')
  if (!data) return <Cargando />
  const e = data.emisor, c = data.clientes.find((x) => x.nombre === parte)

  return (
    <div className="space-y-4">
      <Selector etiqueta="Datos de" value={parte} onChange={(ev) => setParte(ev.target.value)}>
        <option value="tuyos">Tus datos (emisor)</option>
        {data.clientes.map((x) => <option key={x.nombre} value={x.nombre}>{x.nombre}</option>)}
      </Selector>
      {parte === 'tuyos' ? (
        <Formulario key="tuyos" onEnviar={(d) => guardarEmisor.mutateAsync(d)}>
          <Campo etiqueta="Nombre y apellidos" name="nombre" defaultValue={e.nombre} required />
          <Campo etiqueta="NIF" name="nif" defaultValue={e.nif} required />
          <Area etiqueta="Dirección" name="direccion" defaultValue={e.direccion} className="sm:col-span-2" />
          <Campo etiqueta="Email" name="email" type="email" defaultValue={e.email} />
          <Campo etiqueta="Teléfono" name="telefono" defaultValue={e.telefono} />
          <Campo etiqueta="IBAN para el cobro" name="iban" defaultValue={e.iban} className="sm:col-span-2" />
          <Area etiqueta="Texto al pie (opcional)" name="pie" defaultValue={e.pie} rows={2} className="sm:col-span-2" />
        </Formulario>
      ) : c && (
        <Formulario key={c.nombre} onEnviar={(d) => guardarCliente.mutateAsync(d)}>
          <Campo etiqueta="NIF / VAT number" name="nif" defaultValue={c.nif} />
          <Selector etiqueta="Idioma de la factura" name="idioma" defaultValue={c.idioma}>
            <option value="es">Español</option><option value="en">Inglés</option>
          </Selector>
          <Area etiqueta="Dirección" name="direccion" defaultValue={c.direccion} className="sm:col-span-2" />
          <Area etiqueta="Nota en sus facturas (opcional)" name="nota_factura" defaultValue={c.nota_factura} rows={2} className="sm:col-span-2"
            placeholder="Si la dejas vacía y la factura va sin IVA, se pone la mención del art. 69 de la Ley del IVA." />
        </Formulario>
      )}
    </div>
  )
}
