import { useState } from 'react'
import type { TextareaHTMLAttributes } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { Facturacion } from '../lib/tipos'
import { useAccion } from '../lib/utilidades'
import { Campo, Cargando, Formulario, Selector } from './ui'

const claseTexto = 'w-full rounded-xl border border-line bg-panel px-3 py-2 text-sm text-ink placeholder:text-muted/70'

function Texto({ etiqueta, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement> & { etiqueta: string }) {
  return <label className="flex flex-col gap-1.5 text-xs font-medium text-muted sm:col-span-2">{etiqueta}<textarea rows={3} {...p} className={claseTexto} /></label>
}

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
          <Texto etiqueta="Dirección" name="direccion" defaultValue={e.direccion} />
          <Campo etiqueta="Email" name="email" type="email" defaultValue={e.email} />
          <Campo etiqueta="Teléfono" name="telefono" defaultValue={e.telefono} />
          <Campo etiqueta="IBAN para el cobro" name="iban" defaultValue={e.iban} className="sm:col-span-2" />
          <Texto etiqueta="Texto al pie (opcional)" name="pie" defaultValue={e.pie} rows={2} />
        </Formulario>
      ) : c && (
        <Formulario key={c.nombre} onEnviar={(d) => guardarCliente.mutateAsync(d)}>
          <Campo etiqueta="NIF / VAT number" name="nif" defaultValue={c.nif} />
          <Selector etiqueta="Idioma de la factura" name="idioma" defaultValue={c.idioma}>
            <option value="es">Español</option><option value="en">Inglés</option>
          </Selector>
          <Texto etiqueta="Dirección" name="direccion" defaultValue={c.direccion} />
          <Texto etiqueta="Nota en sus facturas (opcional)" name="nota_factura" defaultValue={c.nota_factura} rows={2}
            placeholder="Si la dejas vacía y la factura va sin IVA, se pone la mención del art. 69 de la Ley del IVA." />
        </Formulario>
      )}
    </div>
  )
}
