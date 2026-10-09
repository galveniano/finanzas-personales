import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Briefcase, Building } from 'lucide-react'
import { api } from '../../lib/api'
import { eur, fecha } from '../../lib/format'
import type { Inmueble, Movimiento } from '../../lib/tipos'
import { num, useAccion } from '../../lib/utilidades'
import { Boton, Campo, Dialogo, Formulario, Importe, Selector, Vacio } from '../ui'
import { APUNTADO, conceptoLimpio } from './comun'

type Modo = 'menu' | 'actividad' | 'piso'
const TITULOS: Record<Modo, string> = { menu: 'Apuntar este gasto', actividad: 'Gasto de la actividad', piso: 'Gasto del piso' }

const redondear = (v: number) => Math.round(v * 100) / 100

/** Un cargo del banco pasa a ser un gasto deducible del autónomo (Ingresos › Autónomo), con la base sin IVA. */
function GastoActividad({ m, onCerrar }: { m: Movimiento; onCerrar: () => void }) {
  const total = Math.abs(m.importe)
  const [iva, setIva] = useState('21')
  const [base, setBase] = useState(String(redondear(total / 1.21)))
  const guardar = useAccion(async (d: Record<string, string>) => {
    await api.post('/autonomo/gastos', {
      fecha: d.fecha, proveedor: d.proveedor, concepto: d.concepto ?? '', categoria: d.categoria,
      base: num(d.base) ?? 0, tipo_iva: num(d.tipo_iva) ?? 21, deducible_pct: num(d.deducible_pct) ?? 100,
    })
    await api.patch(`/movimientos/${m.id}`, { nota: `${APUNTADO}gasto de la actividad` })
    onCerrar()
  }, 'Gasto apuntado en Ingresos › Autónomo')
  return (
    <Formulario onEnviar={(d) => guardar.mutateAsync(d)} textoBoton="Apuntar gasto">
      <Campo etiqueta="Fecha" name="fecha" type="date" defaultValue={m.fecha} required />
      <Campo etiqueta="Proveedor" name="proveedor" defaultValue={conceptoLimpio(m.concepto)} required />
      <Campo etiqueta="Concepto" name="concepto" defaultValue={m.concepto} className="sm:col-span-2" />
      <Selector etiqueta="Categoría" name="categoria" defaultValue="otros">
        <option value="cuota_reta">Cuota de autónomos</option><option value="gestoria">Gestoría</option>
        <option value="software">Software y suscripciones</option><option value="equipos">Equipos</option>
        <option value="formacion">Formación</option><option value="suministros">Suministros</option><option value="otros">Otros</option>
      </Selector>
      <Campo etiqueta="% deducible" name="deducible_pct" defaultValue="100" inputMode="decimal" ayuda="Por ejemplo, 30 % para suministros de casa." />
      <Campo etiqueta="IVA (%)" name="tipo_iva" value={iva} inputMode="decimal"
        onChange={(e) => { setIva(e.target.value); setBase(String(redondear(total / (1 + (num(e.target.value) ?? 0) / 100)))) }} />
      <Campo etiqueta="Base (€)" name="base" value={base} inputMode="decimal" onChange={(e) => setBase(e.target.value)}
        ayuda={`Los ${eur(total)} del cargo sin el IVA; si el tique dice otra base, corrígela.`} />
    </Formulario>
  )
}

/** Un cargo del banco pasa a ser un gasto del piso alquilado (Bienes): baja el rendimiento del alquiler. */
function GastoPiso({ m, onCerrar }: { m: Movimiento; onCerrar: () => void }) {
  const { data, isLoading } = useQuery({ queryKey: ['inmuebles'], queryFn: () => api.get<{ inmuebles: Inmueble[] }>('/inmuebles') })
  const pisos = data?.inmuebles.filter((i) => i.tipo === 'inmueble') ?? []
  const guardar = useAccion(async (d: Record<string, string>) => {
    const piso = pisos.find((p) => String(p.id) === d.inmueble_id)
    if (!piso) throw new Error('Elige el inmueble')
    await api.post(`/inmuebles/${piso.id}/gastos`, { fecha: d.fecha, tipo: d.tipo, importe: num(d.importe) ?? 0, concepto: d.concepto ?? '' })
    await api.patch(`/movimientos/${m.id}`, { nota: `${APUNTADO}gasto del piso ${piso.nombre}` })
    onCerrar()
  }, 'Gasto apuntado en Bienes')
  if (isLoading) return <p className="text-sm text-muted">Cargando tus inmuebles…</p>
  if (!pisos.length) return <Vacio>Primero da de alta el piso en Bienes; después podrás apuntarle gastos desde aquí.</Vacio>
  return (
    <Formulario onEnviar={(d) => guardar.mutateAsync(d)} textoBoton="Apuntar gasto">
      <Selector etiqueta="Inmueble" name="inmueble_id" required>
        {pisos.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
      </Selector>
      <Selector etiqueta="Tipo de gasto" name="tipo" defaultValue="otros">
        <option value="ibi">IBI</option><option value="comunidad">Comunidad</option><option value="seguro">Seguro</option>
        <option value="reparacion">Reparación</option><option value="intereses">Intereses hipoteca</option>
        <option value="suministros">Suministros</option><option value="gestion">Gestión</option><option value="otros">Otros</option>
      </Selector>
      <Campo etiqueta="Fecha" name="fecha" type="date" defaultValue={m.fecha} required />
      <Campo etiqueta="Importe (€)" name="importe" defaultValue={Math.abs(m.importe)} inputMode="decimal" required />
      <Campo etiqueta="Concepto" name="concepto" defaultValue={m.concepto} className="sm:col-span-2" />
    </Formulario>
  )
}

/** Menú de un gasto de la lista: apuntarlo como gasto de la actividad o del piso, con el formulario prellenado. */
export default function Apuntar({ m, onCerrar }: { m: Movimiento | null; onCerrar: () => void }) {
  const [modo, setModo] = useState<Modo>('menu')
  const cerrar = () => { onCerrar(); setModo('menu') }
  return (
    <Dialogo abierto={!!m} onCerrar={cerrar} titulo={TITULOS[modo]}>
      {m && modo === 'menu' && (
        <div className="space-y-4 text-sm">
          <p className="text-muted"><span className="font-medium text-ink">{m.concepto}</span> · {fecha(m.fecha)} · <Importe valor={m.importe} signo /></p>
          {m.nota.startsWith(APUNTADO) && <p className="rounded-xl bg-warn-soft px-3 py-2 text-xs text-warn">Ya lo apuntaste: {m.nota.slice(APUNTADO.length)}. Si lo apuntas otra vez, saldrá dos veces.</p>}
          <div className="grid gap-2 sm:grid-cols-2">
            <Boton variante="secundario" onClick={() => setModo('actividad')}><Briefcase size={16} />Es gasto de la actividad</Boton>
            <Boton variante="secundario" onClick={() => setModo('piso')}><Building size={16} />Es gasto del piso</Boton>
          </div>
          <p className="text-xs text-muted">Los gastos de la actividad bajan tu IRPF (y el 303 si llevan IVA); los del piso, el rendimiento del alquiler. El movimiento se queda aquí con una nota para que no lo apuntes dos veces.</p>
        </div>
      )}
      {m && modo === 'actividad' && <GastoActividad m={m} onCerrar={cerrar} />}
      {m && modo === 'piso' && <GastoPiso m={m} onCerrar={cerrar} />}
    </Dialogo>
  )
}
