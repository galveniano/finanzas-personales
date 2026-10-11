import { api } from '../../lib/api'
import { eur, fecha, hoyISO } from '../../lib/format'
import type { Categoria, Cuenta, Movimiento } from '../../lib/tipos'
import { num, useAccion } from '../../lib/utilidades'
import { Area, BorrarEnDosPasos, Campo, Formulario, Selector } from '../ui'
import { OpcionesCategoria } from './Selectores'

/** Apuntar un movimiento a mano en una cuenta manual o de extracto, o editar (y borrar) uno ya apuntado. */
export function FormMovimiento({ cuentas, categorias, editar, onCerrar }: {
  cuentas: Cuenta[]; categorias: Categoria[]; editar?: Movimiento | null; onCerrar: () => void
}) {
  const guardar = useAccion(async (d: Record<string, string>) => {
    const importe = Math.abs(num(d.importe) ?? 0)
    if (!importe) throw new Error('Pon el importe')
    const cuerpo = {
      fecha: d.fecha, concepto: d.concepto, importe: d.sentido === 'entra' ? importe : -importe,
      categoria_id: d.categoria_id ? Number(d.categoria_id) : null, nota: d.nota ?? '',
    }
    if (editar) await api.put(`/movimientos/${editar.id}`, cuerpo)
    else await api.post('/movimientos', { cuenta_id: Number(d.cuenta_id), ...cuerpo })
    onCerrar()
  }, editar ? 'Movimiento guardado' : 'Movimiento apuntado')
  const borrar = useAccion((id: number) => api.del(`/movimientos/${id}`).then(onCerrar), 'Movimiento borrado')
  return (
    <div className="space-y-4">
      <Formulario onEnviar={(d) => guardar.mutateAsync(d)} textoBoton={editar ? 'Guardar' : 'Apuntar'}>
        {editar
          ? <Campo etiqueta="Cuenta" value={editar.cuenta} readOnly className="sm:col-span-2" />
          : (
            <Selector etiqueta="Cuenta" name="cuenta_id" required className="sm:col-span-2" defaultValue={cuentas[0]?.id}>
              {cuentas.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </Selector>
          )}
        <Campo etiqueta="Fecha" name="fecha" type="date" required defaultValue={editar?.fecha ?? hoyISO()} />
        <Selector etiqueta="Sentido" name="sentido" defaultValue={editar && editar.importe > 0 ? 'entra' : 'sale'}>
          <option value="sale">Sale de la cuenta (gasto)</option>
          <option value="entra">Entra en la cuenta (ingreso)</option>
        </Selector>
        <Campo etiqueta="Concepto" name="concepto" required defaultValue={editar?.concepto} placeholder="Alquiler, cena, Bizum a…" className="sm:col-span-2" />
        <Campo etiqueta="Importe (€)" name="importe" required inputMode="decimal" defaultValue={editar ? Math.abs(editar.importe) : ''} placeholder="0,00" />
        <Selector etiqueta="Categoría" name="categoria_id" defaultValue={editar?.categoria_id ?? ''}>
          <OpcionesCategoria categorias={categorias} sinCategoria={editar ? 'Sin categoría' : 'Automática (según las reglas)'} />
        </Selector>
        <Area etiqueta="Nota" name="nota" rows={2} defaultValue={editar?.nota} className="sm:col-span-2" placeholder="Para qué fue, con quién, si te lo devuelven…" />
      </Formulario>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span>El saldo de la cuenta se ajusta solo con lo que apuntes.</span>
        {editar && <BorrarEnDosPasos texto="Borrar movimiento" etiqueta="el movimiento" onBorrar={() => borrar.mutate(editar.id)} disabled={borrar.isPending} />}
      </div>
    </div>
  )
}

/** La nota de cualquier movimiento, también de los que vienen del banco. */
export function NotaMovimiento({ m, onCerrar }: { m: Movimiento; onCerrar: () => void }) {
  const guardar = useAccion((d: Record<string, string>) => api.patch(`/movimientos/${m.id}`, { nota: d.nota ?? '' }).then(onCerrar), 'Nota guardada')
  return (
    <Formulario onEnviar={(d) => guardar.mutateAsync(d)}>
      <p className="text-sm text-muted sm:col-span-2">
        <span className="font-medium text-ink">{m.concepto}</span> · {fecha(m.fecha)} · <span className="cifra">{eur(m.importe)}</span>
      </p>
      <Area etiqueta="Nota" name="nota" defaultValue={m.nota} className="sm:col-span-2" autoFocus placeholder="Para qué fue, con quién, si te lo devuelven…" />
    </Formulario>
  )
}
