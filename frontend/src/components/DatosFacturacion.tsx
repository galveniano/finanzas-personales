import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Pencil } from 'lucide-react'
import { api } from '../lib/api'
import type { Facturacion } from '../lib/tipos'
import { useAccion } from '../lib/utilidades'
import { Area, BorrarEnDosPasos, Boton, Campo, Cargando, Formulario, Selector } from './ui'

/** Tus datos y los de cada cliente, para que salgan en el documento de la factura. */
export default function DatosFacturacion({ onHecho }: { onHecho: () => void }) {
  const { data } = useQuery({ queryKey: ['facturacion'], queryFn: () => api.get<Facturacion>('/facturacion') })
  const [parte, setParte] = useState<'tuyos' | string>('tuyos')
  const [nuevoNombre, setNuevoNombre] = useState<string | null>(null)  // null: no se está renombrando
  const ruta = `/facturacion/clientes/${encodeURIComponent(parte)}`
  const guardarEmisor = useAccion((d: Record<string, string>) => api.put('/facturacion/emisor', d).then(onHecho), 'Datos guardados')
  const guardarCliente = useAccion((d: Record<string, string>) => api.put(ruta, d).then(onHecho), 'Cliente guardado')
  const renombrar = useAccion((nuevo: string) => api.patch(ruta, { nuevo_nombre: nuevo }).then(() => { setParte(nuevo.trim()); setNuevoNombre(null) }), 'Cliente renombrado')
  const borrar = useAccion(() => api.del(ruta).then(() => setParte('tuyos')), 'Cliente borrado')
  if (!data) return <Cargando />
  const e = data.emisor, c = data.clientes.find((x) => x.nombre === parte)

  return (
    <div className="space-y-4">
      <Selector etiqueta="Datos de" value={parte} onChange={(ev) => { setParte(ev.target.value); setNuevoNombre(null) }}>
        <option value="tuyos">Tus datos (emisor)</option>
        {data.clientes.map((x) => <option key={x.nombre} value={x.nombre}>{x.nombre}</option>)}
      </Selector>
      {parte === 'tuyos' ? (
        <>
          <Formulario key="tuyos" onEnviar={(d) => guardarEmisor.mutateAsync(d)}>
            <Campo etiqueta="Nombre y apellidos" name="nombre" defaultValue={e.nombre} required />
            <Campo etiqueta="NIF" name="nif" defaultValue={e.nif} required />
            <Area etiqueta="Dirección" name="direccion" defaultValue={e.direccion} className="sm:col-span-2" />
            <Campo etiqueta="Email" name="email" type="email" defaultValue={e.email} />
            <Campo etiqueta="Teléfono" name="telefono" defaultValue={e.telefono} />
            <Campo etiqueta="IBAN para el cobro" name="iban" defaultValue={e.iban} className="sm:col-span-2" />
            <Area etiqueta="Texto al pie (opcional)" name="pie" defaultValue={e.pie} rows={2} className="sm:col-span-2" />
          </Formulario>
          <p className="text-xs text-muted">Un cliente nace al registrar su primera factura o al ponerlo en «Sueldo y tarifas»; elígelo arriba para completar su NIF y su dirección.</p>
        </>
      ) : c && (
        <>
          <Formulario key={c.nombre} onEnviar={(d) => guardarCliente.mutateAsync(d)}>
            <Campo etiqueta="NIF / VAT number" name="nif" defaultValue={c.nif} maxLength={20} />
            <Selector etiqueta="Idioma de la factura" name="idioma" defaultValue={c.idioma}>
              <option value="es">Español</option><option value="en">Inglés</option>
            </Selector>
            <Area etiqueta="Dirección" name="direccion" defaultValue={c.direccion} className="sm:col-span-2" />
            <Area etiqueta="Nota en sus facturas (opcional)" name="nota_factura" defaultValue={c.nota_factura} rows={2} className="sm:col-span-2"
              placeholder="Si la dejas vacía y la factura va sin IVA, se pone la mención del art. 69 de la Ley del IVA." />
          </Formulario>
          <div className="flex flex-wrap items-end justify-between gap-3 border-t border-line pt-4">
            {nuevoNombre == null ? (
              <Boton variante="secundario" className="px-2.5 py-1 text-xs" onClick={() => setNuevoNombre(c.nombre)}><Pencil size={14} />Renombrar</Boton>
            ) : (
              <form className="flex min-w-0 flex-1 flex-wrap items-end gap-2" onSubmit={(ev) => { ev.preventDefault(); if (nuevoNombre.trim()) renombrar.mutate(nuevoNombre) }}>
                <Campo etiqueta="Nombre nuevo" value={nuevoNombre} onChange={(ev) => setNuevoNombre(ev.target.value)} maxLength={120} className="min-w-0 flex-1 basis-48" autoFocus />
                <Boton type="submit" className="px-2.5 py-1.5 text-xs" disabled={renombrar.isPending || !nuevoNombre.trim() || nuevoNombre.trim() === c.nombre}>Renombrar</Boton>
                <Boton type="button" variante="fantasma" className="px-2.5 py-1.5 text-xs" onClick={() => setNuevoNombre(null)}>Cancelar</Boton>
              </form>
            )}
            <span title={c.facturas ? `Tiene ${c.facturas} ${c.facturas === 1 ? 'factura' : 'facturas'}: no se puede borrar` : undefined}>
              <BorrarEnDosPasos etiqueta={`el cliente ${c.nombre}`} texto="Borrar" disabled={!!c.facturas || borrar.isPending} onBorrar={() => borrar.mutate(undefined)} />
            </span>
          </div>
          <p className="text-xs text-muted">
            {c.facturas
              ? `Tiene ${c.facturas} ${c.facturas === 1 ? 'factura' : 'facturas'}, así que no se puede borrar; si cambió de nombre, renómbralo y se actualizan sus facturas`
              : 'Sin facturas se puede borrar; si está en «Sueldo y tarifas», se quita también de ahí'}
            . Al renombrarlo también cambia en «Sueldo y tarifas» y en sus días planificados.
          </p>
        </>
      )}
    </div>
  )
}
