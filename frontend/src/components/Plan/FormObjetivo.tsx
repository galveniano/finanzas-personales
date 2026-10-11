import { useState } from 'react'
import type { Cuenta, Objetivo } from '../../lib/tipos'
import { Area, Campo, Formulario, Selector } from '../ui'

/** Alta y edición de un objetivo. Ligado a una cuenta, lo ahorrado sale de su saldo y el campo manual se apaga. */
export default function FormObjetivo({ editando, cuentas, onEnviar }: {
  editando: Objetivo | null; cuentas: Cuenta[]; onEnviar: (v: Record<string, string>) => Promise<unknown>
}) {
  const [cuenta, setCuenta] = useState(editando?.cuenta_id ? String(editando.cuenta_id) : '')
  const elegida = cuentas.find((c) => String(c.id) === cuenta)
  return (
    <Formulario onEnviar={onEnviar}>
      <Campo etiqueta="Nombre" name="nombre" required placeholder="Boda" defaultValue={editando?.nombre ?? ''} />
      <Selector etiqueta="Tipo" name="tipo" defaultValue={editando?.tipo ?? 'boda'}>
        <option value="boda">Boda</option><option value="viaje">Viaje</option><option value="casa">Casa</option>
        <option value="colchon">Colchón de seguridad</option><option value="otro">Otro</option>
      </Selector>
      <Campo etiqueta="Fecha" name="fecha_objetivo" type="date" defaultValue={editando?.fecha_objetivo ?? ''} />
      <Campo etiqueta="Presupuesto (€)" name="importe_objetivo" inputMode="decimal" required defaultValue={editando?.importe_objetivo ?? ''} />
      <Selector etiqueta="Cuenta donde lo ahorras" name="cuenta_id" value={cuenta} onChange={(e) => setCuenta(e.target.value)}>
        <option value="">Ninguna: lo apunto a mano</option>
        {cuentas.map((c) => <option key={c.id} value={c.id}>{c.nombre}{c.entidad ? ` · ${c.entidad}` : ''}</option>)}
      </Selector>
      <Campo etiqueta="Ya ahorrado (€)" name="ahorrado" inputMode="decimal" disabled={!!cuenta}
        defaultValue={editando && !editando.ahorrado_automatico ? editando.ahorrado : 0}
        ayuda={elegida ? `Se calcula solo: el saldo de ${elegida.nombre} (tu parte, ${elegida.participacion} %).` : 'Lo que ya tienes apartado para esto.'} />
      <Area etiqueta="Notas" name="notas" className="sm:col-span-2" rows={2} defaultValue={editando?.notas ?? ''} placeholder="Presupuesto del catering, enlaces, lo que quieras recordar…" />
    </Formulario>
  )
}
