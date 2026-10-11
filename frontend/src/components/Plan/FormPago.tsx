import { hoyISO } from '../../lib/format'
import type { Pago, Planificacion } from '../../lib/tipos'
import { Campo, Casilla, Formulario, Selector } from '../ui'

/** Alta y edición de un pago previsto. Las llamadas de capital (inversion_id) se crean desde la inversión, no aquí. */
export default function FormPago({ editando, inmuebles, objetivos, onEnviar }: {
  editando: Pago | null; inmuebles: Planificacion['inmuebles']; objetivos: Planificacion['objetivos']
  onEnviar: (v: Record<string, string>) => Promise<unknown>
}) {
  return (
    <Formulario onEnviar={onEnviar}>
      <Campo etiqueta="Concepto" name="concepto" required className="sm:col-span-2" placeholder="Plazo promotora" defaultValue={editando?.concepto ?? ''} />
      <Campo etiqueta="Fecha" name="fecha" type="date" defaultValue={editando?.fecha ?? hoyISO()} required />
      <Campo etiqueta="Importe (€)" name="importe" inputMode="decimal" required defaultValue={editando?.importe ?? ''} />
      <Selector etiqueta="Inmueble" name="activo_id" defaultValue={editando?.activo_id ?? ''}>
        <option value="">Ninguno</option>{inmuebles.map((i) => <option key={i.id} value={i.id}>{i.nombre}</option>)}
      </Selector>
      <Selector etiqueta="Objetivo" name="objetivo_id" defaultValue={editando?.objetivo_id ?? ''}>
        <option value="">Ninguno</option>{objetivos.map((o) => <option key={o.id} value={o.id}>{o.nombre}</option>)}
      </Selector>
      <Casilla etiqueta="Ya está pagado" name="pagado" defaultChecked={editando?.pagado ?? false} />
      {editando?.inversion && <p className="text-xs text-muted sm:col-span-2">Es una llamada de capital de {editando.inversion}: seguirá ligada a esa inversión.</p>}
    </Formulario>
  )
}
