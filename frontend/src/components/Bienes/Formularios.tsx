import { api } from '../../lib/api'
import { eur, hoyISO, pct } from '../../lib/format'
import type { Constantes, Inmueble } from '../../lib/tipos'
import { num, opc, useAccion } from '../../lib/utilidades'
import { Area, Campo, Formulario, Selector } from '../ui'
import { TIPOS_BIEN, TIPOS_GASTO_INMUEBLE, USOS } from './comun'
import type { Accion } from './comun'

function Opciones({ de }: { de: Record<string, string> }) {
  return <>{Object.entries(de).map(([valor, texto]) => <option key={valor} value={valor}>{texto}</option>)}</>
}

/** Campos de un bien (alta y edición comparten casi todo). */
function CamposBien({ i }: { i?: Inmueble }) {
  const v = (x: number | undefined) => (x ? String(x) : '')
  return (
    <>
      <Campo etiqueta="Fecha de compra" name="fecha_compra" type="date" defaultValue={i?.fecha_compra ?? ''} />
      <Campo etiqueta="Precio (€)" name="precio_compra" inputMode="decimal" defaultValue={v(i?.precio_compra)} />
      <Campo etiqueta="Gastos de compra (€)" name="gastos_compra" inputMode="decimal" defaultValue={v(i?.gastos_compra)} ayuda="Impuestos, notaría, registro." />
      <Campo etiqueta="% de propiedad" name="porcentaje_propiedad" inputMode="decimal" defaultValue={String(i?.porcentaje_propiedad ?? 100)} />
      <Campo etiqueta="Valor catastral (€)" name="valor_catastral" inputMode="decimal" defaultValue={v(i?.valor_catastral)} />
      <Campo etiqueta="Catastral construcción (€)" name="valor_catastral_construccion" inputMode="decimal" defaultValue={v(i?.valor_catastral_construccion)} ayuda="Viene en el recibo del IBI; sirve para la amortización del alquiler." />
      <Area etiqueta="Notas" name="notas" rows={2} defaultValue={i?.notas ?? ''} className="sm:col-span-2" />
    </>
  )
}

const datosBien = (d: Record<string, string>) => ({
  nombre: d.nombre, tipo: d.tipo, uso: d.uso, fecha_compra: d.fecha_compra || null,
  precio_compra: num(d.precio_compra) ?? 0, gastos_compra: num(d.gastos_compra) ?? 0, valor_catastral: num(d.valor_catastral) ?? 0,
  valor_catastral_construccion: num(d.valor_catastral_construccion) ?? 0, porcentaje_propiedad: num(d.porcentaje_propiedad) ?? 100, notas: d.notas,
})

/** Campos comunes de una deuda (hipoteca o préstamo). `d` rellena los valores al editar. */
function CamposDeuda({ d, bienes, conBien }: { d?: Accion['deuda']; bienes: Inmueble[]; conBien: boolean }) {
  return (
    <>
      <Campo etiqueta="Capital prestado (€)" name="capital_inicial" inputMode="decimal" required defaultValue={d ? String(d.capital_inicial) : ''} />
      <Campo etiqueta="Interés anual %" name="tipo_interes_anual" inputMode="decimal" required defaultValue={d ? String(d.tipo_interes_anual) : ''} />
      <Campo etiqueta="Fecha de firma" name="fecha_inicio" type="date" required defaultValue={d?.fecha_inicio ?? ''} />
      <Campo etiqueta="Plazo (meses)" name="plazo_meses" type="number" min={1} required defaultValue={d ? String(d.plazo_meses) : ''} />
      <Campo etiqueta="Pendiente real (€, opcional)" name="pendiente" inputMode="decimal" defaultValue={d?.saldo_pendiente_manual != null ? String(d.saldo_pendiente_manual) : ''}
        ayuda="El del último recibo. Manda sobre el cálculo teórico; útil con interés variable." />
      <Campo etiqueta="Pendiente a fecha" name="saldo_fecha" type="date" defaultValue={d?.saldo_fecha ?? hoyISO()} ayuda="Desde ese día baja con cada cuota." />
      {conBien && (
        <Selector etiqueta="Ligado a" name="activo_id" defaultValue={d?.activo_id ? String(d.activo_id) : ''} className="sm:col-span-2">
          <option value="">Ningún bien</option>
          {bienes.map((b) => <option key={b.id} value={b.id}>{b.nombre}</option>)}
        </Selector>
      )}
    </>
  )
}

const datosDeuda = (d: Record<string, string>, conBien: boolean) => {
  const pendiente = num(d.pendiente)
  return {
    nombre: d.nombre, entidad: d.entidad, capital_inicial: num(d.capital_inicial), tipo_interes_anual: num(d.tipo_interes_anual),
    fecha_inicio: d.fecha_inicio, plazo_meses: Number(d.plazo_meses),
    saldo_pendiente_manual: pendiente ?? null, saldo_fecha: pendiente != null ? (opc(d.saldo_fecha) ?? null) : null,
    ...(conBien ? { activo_id: d.activo_id ? Number(d.activo_id) : null } : {}),
  }
}

export function Formularios({ a, cerrar, bienes, constantes }: { a: Accion; cerrar: () => void; bienes: Inmueble[]; constantes?: Constantes }) {
  const id = a.inmueble?.id
  const usePost = (ruta: string, msg: string) => useAccion((d: object) => api.post(ruta, d).then(cerrar), msg)
  const usePatch = (ruta: string, msg: string) => useAccion((d: object) => api.patch(ruta, d).then(cerrar), msg)
  const valoracion = usePost(`/inmuebles/${id}/valoraciones`, 'Valoración guardada')
  const editarValoracion = usePatch(`/valoraciones/${a.valoracionId}`, 'Valoración guardada')
  const hipoteca = usePost(`/inmuebles/${id}/hipotecas`, 'Hipoteca guardada')
  const prestamo = usePost('/deudas', 'Préstamo guardado')
  const editarDeuda = usePatch(`/deudas/${a.deuda?.id}`, 'Cambios guardados')
  const contrato = usePost(`/inmuebles/${id}/contratos`, 'Contrato guardado')
  const editarContrato = usePatch(`/contratos/${a.contratoId}`, 'Contrato guardado')
  const renta = usePost(`/contratos/${a.contratoId}/rentas`, 'Renta actualizada')
  const gasto = usePost(`/inmuebles/${id}/gastos`, 'Gasto guardado')
  const editarGasto = usePatch(`/gastos-inmueble/${a.gastoId}`, 'Gasto guardado')
  const nuevo = usePost('/inmuebles', 'Bien creado')
  const editar = usePatch(`/inmuebles/${id}`, 'Cambios guardados')
  const escritura = usePost(`/inmuebles/${id}/gastos-escritura`, 'Gastos de escritura añadidos a Plan')
  const escriturar = usePost(`/inmuebles/${id}/escriturar`, 'Escriturada: ya es tu vivienda')
  const i = a.inmueble
  const c = i?.contratos.find((x) => x.id === a.contratoId)
  const g = i?.gastos.find((x) => x.id === a.gastoId)
  const v = i?.valoraciones.find((x) => x.id === a.valoracionId)
  const d = a.deuda

  switch (a.tipo) {
    case 'valoracion':
    case 'editarValoracion':
      return <Formulario onEnviar={(f) => (v ? editarValoracion : valoracion).mutateAsync({ fecha: f.fecha, valor: num(f.valor) })}>
        <Campo etiqueta="Fecha" name="fecha" type="date" defaultValue={v?.fecha ?? hoyISO()} required />
        <Campo etiqueta="Valor estimado del piso entero (€)" name="valor" inputMode="decimal" required defaultValue={v ? String(v.valor) : ''}
          ayuda="Por ejemplo, el de un portal inmobiliario o una tasación." />
      </Formulario>
    case 'hipoteca':
      return <Formulario onEnviar={(f) => hipoteca.mutateAsync(datosDeuda(f, false))}>
        <Campo etiqueta="Nombre" name="nombre" defaultValue="Hipoteca" />
        <Campo etiqueta="Entidad" name="entidad" defaultValue="Banco Sabadell" />
        <CamposDeuda bienes={bienes} conBien={false} />
      </Formulario>
    case 'prestamo':
      return <Formulario onEnviar={(f) => prestamo.mutateAsync({ ...datosDeuda(f, true), tipo: f.tipo })}>
        <Campo etiqueta="Nombre" name="nombre" required placeholder="Préstamo del coche" />
        <Campo etiqueta="Entidad" name="entidad" placeholder="Financiera" />
        <Selector etiqueta="Tipo" name="tipo" defaultValue="prestamo" className="sm:col-span-2">
          <option value="prestamo">Préstamo</option><option value="otro">Otra deuda</option>
        </Selector>
        <CamposDeuda bienes={bienes} conBien />
      </Formulario>
    case 'editarDeuda':
      return <Formulario onEnviar={(f) => editarDeuda.mutateAsync(datosDeuda(f, d?.tipo !== 'hipoteca'))}>
        <Campo etiqueta="Nombre" name="nombre" required defaultValue={d?.nombre} />
        <Campo etiqueta="Entidad" name="entidad" defaultValue={d?.entidad} />
        <CamposDeuda d={d} bienes={bienes} conBien={d?.tipo !== 'hipoteca'} />
        <p className="text-xs text-muted sm:col-span-2">Si cambias el interés o el pendiente real, el cuadro, la cuota y los intereses del año se recalculan desde ahí.</p>
      </Formulario>
    case 'contrato':
      return <Formulario onEnviar={(f) => contrato.mutateAsync({ inquilino: f.inquilino, fecha_inicio: f.fecha_inicio, fecha_fin: opc(f.fecha_fin),
        renta_mensual: num(f.renta_mensual), reduccion_pct: num(f.reduccion_pct) ?? null })}>
        <Campo etiqueta="Inquilino" name="inquilino" />
        <Campo etiqueta="Renta inicial (€/mes)" name="renta_mensual" inputMode="decimal" required />
        <Campo etiqueta="Inicio del contrato" name="fecha_inicio" type="date" required />
        <Campo etiqueta="Fin (si ya terminó)" name="fecha_fin" type="date" />
        <Campo etiqueta="Reducción IRPF %" name="reduccion_pct" className="sm:col-span-2" ayuda="Vacío: 60 % si el contrato es anterior al 26/05/2023 y 50 % si es posterior." />
      </Formulario>
    case 'editarContrato':
      return <Formulario onEnviar={(f) => editarContrato.mutateAsync({ inquilino: f.inquilino, fecha_inicio: f.fecha_inicio, fecha_fin: f.fecha_fin || null,
        renta_mensual: num(f.renta_mensual), ...(num(f.reduccion_pct) !== undefined ? { reduccion_pct: num(f.reduccion_pct) } : {}) })}>
        <Campo etiqueta="Inquilino" name="inquilino" defaultValue={c?.inquilino} />
        <Campo etiqueta="Renta inicial (€/mes)" name="renta_mensual" inputMode="decimal" required defaultValue={c ? String(c.renta_inicial) : ''}
          ayuda="La del contrato; las subidas van en «Actualizar renta»." />
        <Campo etiqueta="Inicio del contrato" name="fecha_inicio" type="date" required defaultValue={c?.fecha_inicio} />
        <Campo etiqueta="Fin (si ya terminó)" name="fecha_fin" type="date" defaultValue={c?.fecha_fin ?? ''} />
        <Campo etiqueta="Reducción IRPF %" name="reduccion_pct" defaultValue={c ? String(c.reduccion_pct) : ''} className="sm:col-span-2" />
      </Formulario>
    case 'renta':
      return <Formulario onEnviar={(f) => renta.mutateAsync({ desde: f.desde, renta_mensual: num(f.renta_mensual) })}>
        <Campo etiqueta="Desde" name="desde" type="date" required defaultValue={hoyISO()} />
        <Campo etiqueta="Nueva renta (€/mes)" name="renta_mensual" inputMode="decimal" required defaultValue={c ? String(c.renta_actual) : ''} />
      </Formulario>
    case 'gasto':
    case 'editarGasto':
      return <Formulario onEnviar={(f) => (g ? editarGasto : gasto).mutateAsync({ fecha: f.fecha, tipo: f.tipo, importe: num(f.importe), concepto: f.concepto })}>
        <Campo etiqueta="Fecha" name="fecha" type="date" defaultValue={g?.fecha ?? hoyISO()} required />
        <Selector etiqueta="Tipo" name="tipo" defaultValue={g?.tipo ?? 'ibi'}><Opciones de={TIPOS_GASTO_INMUEBLE} /></Selector>
        <Campo etiqueta="Importe (€)" name="importe" inputMode="decimal" required defaultValue={g ? String(g.importe) : ''} />
        <Campo etiqueta="Concepto" name="concepto" defaultValue={g?.concepto ?? ''} />
      </Formulario>
    case 'escritura':
      return <Formulario onEnviar={(f) => escritura.mutateAsync({ fecha: f.fecha, precio: num(f.precio) ?? null })}>
        <Campo etiqueta="Fecha prevista de la escritura" name="fecha" type="date" required />
        <Campo etiqueta="Precio sin IVA (€)" name="precio" inputMode="decimal" defaultValue={i?.precio_compra ? String(i.precio_compra) : ''} />
        <p className="text-xs text-muted sm:col-span-2">
          Te apunto en Plan un pago con el AJD de Murcia ({pct(constantes?.ajd_pct ?? 1.5, 1)} del precio) y unos {eur(constantes?.notaria ?? 1200)} de
          notaría, registro y gestoría. Es una estimación.
        </p>
      </Formulario>
    case 'escriturar': {
      const pagado = (i?.pagos ?? []).filter((p) => p.pagado && !p.concepto.startsWith('Escritura')).reduce((s, p) => s + p.importe, 0)
      return <Formulario textoBoton="Ya está escriturada" onEnviar={(f) => escriturar.mutateAsync({ fecha: f.fecha, precio_total: num(f.precio_total) ?? null })}>
        <Campo etiqueta="Fecha de la escritura" name="fecha" type="date" required defaultValue={hoyISO()} />
        <Campo etiqueta="Precio total (€, opcional)" name="precio_total" inputMode="decimal" placeholder={String(Math.round(pagado))}
          ayuda="Vacío: la suma de los plazos pagados a la promotora, sin los gastos de escritura." />
        <ul className="list-disc space-y-1 pl-5 text-xs text-muted sm:col-span-2">
          <li>Pasa a ser tu vivienda habitual, comprada en esa fecha.</li>
          <li>Los plazos previstos hasta esa fecha se marcan como pagados; los «Escritura…» pasan a gastos de compra.</li>
          <li>Si la hipoteca prevista empezaba más tarde, empieza ese día y ya cuenta como deuda.</li>
        </ul>
      </Formulario>
    }
    case 'editar':
      return <Formulario onEnviar={(f) => editar.mutateAsync(datosBien(f))}>
        <Campo etiqueta="Nombre" name="nombre" required defaultValue={i?.nombre} />
        <Selector etiqueta="Qué es" name="tipo" defaultValue={i?.tipo}><Opciones de={TIPOS_BIEN} /></Selector>
        <Selector etiqueta="Uso" name="uso" defaultValue={i?.uso} className="sm:col-span-2"><Opciones de={USOS} /></Selector>
        <CamposBien i={i} />
      </Formulario>
    case 'nuevo':
      return <Formulario textoBoton="Crear" onEnviar={(f) => nuevo.mutateAsync(datosBien(f))}>
        <Campo etiqueta="Nombre" name="nombre" required placeholder="Piso alquilado" />
        <Selector etiqueta="Qué es" name="tipo" defaultValue="inmueble"><Opciones de={TIPOS_BIEN} /></Selector>
        <Selector etiqueta="Uso" name="uso" defaultValue="alquiler" className="sm:col-span-2"><Opciones de={USOS} /></Selector>
        <CamposBien />
      </Formulario>
  }
}
