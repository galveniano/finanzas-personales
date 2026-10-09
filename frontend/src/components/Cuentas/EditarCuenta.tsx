import { useState } from 'react'
import { api } from '../../lib/api'
import type { Cuenta } from '../../lib/tipos'
import { num, useAccion } from '../../lib/utilidades'
import { Campo, Formulario, Selector } from '../ui'
import { esManual } from './comun'

const FIJAS = [100, 50, 0]

/** Nombre, entidad, tipo, IBAN, saldo (si no la sincroniza el banco) y de quién es la cuenta. */
export default function EditarCuenta({ c, onCerrar }: { c: Cuenta; onCerrar: () => void }) {
  const manual = esManual(c)
  const [titularidad, setTitularidad] = useState(FIJAS.includes(c.participacion) ? String(c.participacion) : 'otro')
  const guardar = useAccion(async (d: Record<string, string>) => {
    const participacion = titularidad === 'otro' ? num(d.participacion) : Number(titularidad)
    if (participacion == null || participacion < 0 || participacion > 100) throw new Error('La parte tuya tiene que estar entre 0 y 100 %')
    const cuerpo: Record<string, unknown> = { nombre: d.nombre, entidad: d.entidad ?? '', tipo: d.tipo, iban: d.iban ?? '', participacion }
    if (manual) {
      const saldo = num(d.saldo)
      if (saldo != null && saldo !== c.saldo) cuerpo.saldo = saldo
    }
    await api.patch(`/cuentas/${c.id}`, cuerpo)
    onCerrar()
  }, 'Cuenta actualizada')
  return (
    <Formulario onEnviar={(d) => guardar.mutateAsync(d)}>
      <Campo etiqueta="Nombre" name="nombre" defaultValue={c.nombre} required />
      <Campo etiqueta="Entidad" name="entidad" defaultValue={c.entidad} placeholder="Banco Sabadell" />
      <Selector etiqueta="Tipo" name="tipo" defaultValue={c.tipo}>
        <option value="corriente">Corriente</option><option value="ahorro">Ahorro</option><option value="tarjeta">Tarjeta de crédito</option>
        {c.tipo === 'inversion' && <option value="inversion">Inversión</option>}
      </Selector>
      <Campo etiqueta="IBAN" name="iban" defaultValue={c.iban} placeholder="ES00 0081 0000 0000 0000 0000" ayuda="Con espacios o sin ellos, da igual." />
      {manual
        ? <Campo etiqueta="Saldo actual (€)" name="saldo" defaultValue={c.saldo_fecha ? c.saldo : ''} inputMode="decimal" placeholder="0,00"
            ayuda="Al guardarlo queda fechado hoy. Los extractos y lo que apuntes a mano lo van actualizando." />
        : <Campo etiqueta="Saldo" value={c.ultima_sincronizacion ? 'Lo pone el banco al sincronizar' : 'Lo pone la sincronización'} readOnly className="text-muted" />}
      <Selector etiqueta="De quién es" value={titularidad} onChange={(e) => setTitularidad(e.target.value)}>
        <option value="100">Mía</option>
        <option value="50">Compartida a medias</option>
        <option value="0">No es mía (se ve, pero no cuenta)</option>
        <option value="otro">Otro porcentaje…</option>
      </Selector>
      {titularidad === 'otro' && (
        <Campo etiqueta="Parte tuya (%)" name="participacion" defaultValue={c.participacion} inputMode="decimal" required
          ayuda="Solo esa parte del saldo y de los movimientos cuenta en tu patrimonio y en tus gastos." />
      )}
    </Formulario>
  )
}
