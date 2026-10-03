import { useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { api } from '../lib/api'
import { eur, fecha, hoyISO } from '../lib/format'
import type { Inmueble } from '../lib/tipos'
import { Barra, Boton, Cabecera, Campo, Cargando, Dato, Dialogo, Etiqueta, ErrorCarga, Formulario, Importe, Selector, Tabla, Tarjeta, Vacio, num, opc, useAccion } from '../components/ui'

type Accion = { tipo: 'valoracion' | 'hipoteca' | 'contrato' | 'renta' | 'gasto' | 'nuevo'; inmueble?: Inmueble; contratoId?: number }

function Fila({ etiqueta, valor, fuerte }: { etiqueta: ReactNode; valor: number; fuerte?: boolean }) {
  return (
    <div className={`flex justify-between gap-3 py-1.5 text-sm ${fuerte ? 'border-t border-line pt-2.5 font-semibold' : ''}`}>
      <span className={fuerte ? '' : 'text-muted'}>{etiqueta}</span><Importe valor={valor} />
    </div>
  )
}

function Ficha({ i, abrir }: { i: Inmueble; abrir: (a: Accion) => void }) {
  const enObra = i.tipo === 'inmueble_en_construccion'
  const totalObra = i.pagos.reduce((s, p) => s + p.importe, 0)
  const pagado = i.pagos.filter((p) => p.pagado).reduce((s, p) => s + p.importe, 0)
  const r = i.rendimiento
  return (
    <Tarjeta className="mb-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">{i.nombre}</h2>
            <Etiqueta tono={enObra ? 'aviso' : 'acento'}>{enObra ? 'En construcción' : i.uso === 'alquiler' ? 'Alquilado' : i.uso === 'vivienda_habitual' ? 'Vivienda habitual' : 'Inmueble'}</Etiqueta>
          </div>
          <p className="mt-1 text-xs text-muted">
            {i.fecha_compra ? `Comprado el ${fecha(i.fecha_compra)} por ${eur(i.precio_compra)}` : enObra ? `Precio ${eur(i.precio_compra)}` : 'Sin fecha de compra'}
            {i.valor_catastral > 0 && ` · catastral ${eur(i.valor_catastral)}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {!enObra && <Boton variante="secundario" className="px-2.5 py-1.5 text-xs" onClick={() => abrir({ tipo: 'valoracion', inmueble: i })}>Valorar</Boton>}
          <Boton variante="secundario" className="px-2.5 py-1.5 text-xs" onClick={() => abrir({ tipo: 'hipoteca', inmueble: i })}>Hipoteca</Boton>
          {!enObra && <Boton variante="secundario" className="px-2.5 py-1.5 text-xs" onClick={() => abrir({ tipo: 'contrato', inmueble: i })}>Contrato</Boton>}
          <Boton variante="secundario" className="px-2.5 py-1.5 text-xs" onClick={() => abrir({ tipo: 'gasto', inmueble: i })}>Gasto</Boton>
        </div>
      </div>

      <div className="mt-5 grid gap-6 sm:grid-cols-3">
        <Dato etiqueta={enObra ? 'Pagado' : 'Valor'} valor={eur(i.valor)} nota={i.valor_detalle} />
        <Dato etiqueta="Hipoteca pendiente" valor={eur(i.deuda)} />
        <Dato etiqueta="Es tuyo" valor={eur(i.equity)} tono={i.equity >= 0 ? undefined : 'neg'} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2 [&>*]:min-w-0">
        {enObra && (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Pagos a la promotora</h3>
            <div className="mb-1 flex justify-between text-xs text-muted"><span>{eur(pagado)} pagado</span><span>{eur(totalObra)} en total</span></div>
            <Barra valor={pagado} max={totalObra} />
            <ul className="mt-3 divide-y divide-line">
              {i.pagos.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <span className="min-w-0"><span className="block truncate">{p.concepto}</span><span className="text-xs text-muted">{fecha(p.fecha)}</span></span>
                  <span className="flex items-center gap-2"><Etiqueta tono={p.pagado ? 'bien' : 'neutro'}>{p.pagado ? 'Pagado' : 'Pendiente'}</Etiqueta><Importe valor={p.importe} /></span>
                </li>
              ))}
              {!i.pagos.length && <li className="py-2 text-sm text-muted">Añade los plazos en Planificación.</li>}
            </ul>
          </div>
        )}

        {i.hipotecas.map((h) => (
          <div key={h.id}>
            <h3 className="mb-2 text-sm font-semibold">{h.nombre} · {h.entidad}</h3>
            <div className="mb-1 flex justify-between text-xs text-muted"><span>{eur(h.capital_inicial - h.pendiente)} amortizado</span><span>{eur(h.capital_inicial)}</span></div>
            <Barra valor={h.capital_inicial - h.pendiente} max={h.capital_inicial} />
            <Fila etiqueta="Cuota mensual" valor={h.cuota} />
            <Fila etiqueta={`Interés ${String(h.tipo_interes_anual).replace('.', ',')} %, intereses este año`} valor={h.intereses_anio} />
            <Fila etiqueta="Pendiente hoy" valor={h.pendiente} fuerte />
          </div>
        ))}

        {i.contratos.map((c) => (
          <div key={c.id}>
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">Alquiler{c.inquilino && ` · ${c.inquilino}`}</h3>
              <button className="text-xs font-medium text-accent" onClick={() => abrir({ tipo: 'renta', inmueble: i, contratoId: c.id })}>Actualizar renta</button>
            </div>
            <div className="cifra text-2xl font-medium">{eur(c.renta_actual)}<span className="text-sm text-muted"> /mes</span></div>
            <ol className="mt-2 space-y-1 text-xs text-muted">
              <li>Desde {fecha(c.fecha_inicio)}: {eur(c.renta_inicial)}</li>
              {c.cambios.map((x) => <li key={x.desde}>Desde {fecha(x.desde)}: {eur(x.renta)}</li>)}
            </ol>
          </div>
        ))}

        {r && (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Para la renta {r.anio} (estimado)</h3>
            <Fila etiqueta="Ingresos del alquiler" valor={r.ingresos} />
            <Fila etiqueta="Intereses y reparaciones" valor={-r.gastos_limitados} />
            <Fila etiqueta="IBI, comunidad, seguro…" valor={-r.gastos_otros} />
            <Fila etiqueta="Amortización 3 %" valor={-r.amortizacion} />
            <Fila etiqueta="Rendimiento neto" valor={r.rendimiento_neto} fuerte />
            <Fila etiqueta={`Reducción ${r.reduccion_pct} %`} valor={-r.reduccion} />
            <Fila etiqueta="Tributa" valor={r.rendimiento_reducido} fuerte />
            {r.notas.map((n) => <p key={n} className="mt-2 text-xs text-warn">{n}</p>)}
          </div>
        )}
      </div>

      {i.gastos.length > 0 && (
        <details className="mt-5">
          <summary className="cursor-pointer text-sm font-medium text-accent">Gastos registrados ({i.gastos.length})</summary>
          <div className="mt-3">
            <Tabla>
              <thead><tr><th>Fecha</th><th>Tipo</th><th>Concepto</th><th className="num">Importe</th></tr></thead>
              <tbody>{i.gastos.map((g) => <tr key={g.id}><td className="cifra text-muted">{fecha(g.fecha)}</td><td className="capitalize">{g.tipo}</td><td>{g.concepto}</td><td className="num"><Importe valor={g.importe} /></td></tr>)}</tbody>
            </Tabla>
          </div>
        </details>
      )}
    </Tarjeta>
  )
}

function Formularios({ a, cerrar }: { a: Accion; cerrar: () => void }) {
  const id = a.inmueble?.id
  const usePost = (ruta: string, msg: string) => useAccion((d: object) => api.post(ruta, d).then(cerrar), msg)
  const valoracion = usePost(`/inmuebles/${id}/valoraciones`, 'Valoración guardada')
  const hipoteca = usePost(`/inmuebles/${id}/hipotecas`, 'Hipoteca guardada')
  const contrato = usePost(`/inmuebles/${id}/contratos`, 'Contrato guardado')
  const renta = usePost(`/contratos/${a.contratoId}/rentas`, 'Renta actualizada')
  const gasto = usePost(`/inmuebles/${id}/gastos`, 'Gasto guardado')
  const nuevo = usePost('/inmuebles', 'Inmueble creado')

  switch (a.tipo) {
    case 'valoracion':
      return <Formulario onEnviar={(d) => valoracion.mutateAsync({ fecha: d.fecha, valor: num(d.valor) })}>
        <Campo etiqueta="Fecha" name="fecha" type="date" defaultValue={hoyISO()} required />
        <Campo etiqueta="Valor estimado (€)" name="valor" inputMode="decimal" required ayuda="Por ejemplo, el de un portal inmobiliario o una tasación." />
      </Formulario>
    case 'hipoteca':
      return <Formulario onEnviar={(d) => hipoteca.mutateAsync({ nombre: d.nombre, entidad: d.entidad, capital_inicial: num(d.capital_inicial),
        tipo_interes_anual: num(d.tipo_interes_anual), fecha_inicio: d.fecha_inicio, plazo_meses: Number(d.plazo_meses), saldo_pendiente_manual: num(d.pendiente) ?? null })}>
        <Campo etiqueta="Nombre" name="nombre" defaultValue="Hipoteca" />
        <Campo etiqueta="Entidad" name="entidad" defaultValue="Banco Sabadell" />
        <Campo etiqueta="Capital prestado (€)" name="capital_inicial" inputMode="decimal" required />
        <Campo etiqueta="Interés anual %" name="tipo_interes_anual" inputMode="decimal" required />
        <Campo etiqueta="Fecha de firma" name="fecha_inicio" type="date" required />
        <Campo etiqueta="Plazo (meses)" name="plazo_meses" type="number" required />
        <Campo etiqueta="Pendiente real hoy (opcional)" name="pendiente" inputMode="decimal" className="sm:col-span-2" ayuda="Si lo pones, manda sobre el cálculo teórico. Útil con interés variable." />
      </Formulario>
    case 'contrato':
      return <Formulario onEnviar={(d) => contrato.mutateAsync({ inquilino: d.inquilino, fecha_inicio: d.fecha_inicio, fecha_fin: opc(d.fecha_fin),
        renta_mensual: num(d.renta_mensual), reduccion_pct: num(d.reduccion_pct) ?? 60 })}>
        <Campo etiqueta="Inquilino" name="inquilino" />
        <Campo etiqueta="Renta inicial (€/mes)" name="renta_mensual" inputMode="decimal" required />
        <Campo etiqueta="Inicio del contrato" name="fecha_inicio" type="date" required />
        <Campo etiqueta="Fin (si ya terminó)" name="fecha_fin" type="date" />
        <Campo etiqueta="Reducción IRPF %" name="reduccion_pct" defaultValue="60" className="sm:col-span-2" ayuda="60 % para contratos firmados antes del 26/05/2023." />
      </Formulario>
    case 'renta':
      return <Formulario onEnviar={(d) => renta.mutateAsync({ desde: d.desde, renta_mensual: num(d.renta_mensual) })}>
        <Campo etiqueta="Desde" name="desde" type="date" required />
        <Campo etiqueta="Nueva renta (€/mes)" name="renta_mensual" inputMode="decimal" required />
      </Formulario>
    case 'gasto':
      return <Formulario onEnviar={(d) => gasto.mutateAsync({ fecha: d.fecha, tipo: d.tipo, importe: num(d.importe), concepto: d.concepto })}>
        <Campo etiqueta="Fecha" name="fecha" type="date" defaultValue={hoyISO()} required />
        <Selector etiqueta="Tipo" name="tipo" defaultValue="ibi">
          <option value="ibi">IBI</option><option value="comunidad">Comunidad</option><option value="seguro">Seguro</option>
          <option value="reparacion">Reparación</option><option value="intereses">Intereses hipoteca</option>
          <option value="suministros">Suministros</option><option value="gestion">Gestión</option><option value="otros">Otros</option>
        </Selector>
        <Campo etiqueta="Importe (€)" name="importe" inputMode="decimal" required />
        <Campo etiqueta="Concepto" name="concepto" />
      </Formulario>
    case 'nuevo':
      return <Formulario onEnviar={(d) => nuevo.mutateAsync({ nombre: d.nombre, tipo: d.tipo, uso: d.uso, fecha_compra: opc(d.fecha_compra),
        precio_compra: num(d.precio_compra) ?? 0, gastos_compra: num(d.gastos_compra) ?? 0, valor_catastral: num(d.valor_catastral) ?? 0,
        valor_catastral_construccion: num(d.valor_catastral_construccion) ?? 0, porcentaje_propiedad: num(d.porcentaje_propiedad) ?? 100 })}>
        <Campo etiqueta="Nombre" name="nombre" required placeholder="Piso alquilado" />
        <Selector etiqueta="Estado" name="tipo" defaultValue="inmueble">
          <option value="inmueble">Ya es mío</option><option value="inmueble_en_construccion">Obra nueva en construcción</option>
        </Selector>
        <Selector etiqueta="Uso" name="uso" defaultValue="alquiler">
          <option value="alquiler">Alquiler</option><option value="vivienda_habitual">Vivienda habitual</option><option value="otro">Otro</option>
        </Selector>
        <Campo etiqueta="Fecha de compra" name="fecha_compra" type="date" />
        <Campo etiqueta="Precio (€)" name="precio_compra" inputMode="decimal" />
        <Campo etiqueta="Gastos de compra (€)" name="gastos_compra" inputMode="decimal" ayuda="Impuestos, notaría, registro." />
        <Campo etiqueta="Valor catastral (€)" name="valor_catastral" inputMode="decimal" />
        <Campo etiqueta="Catastral construcción (€)" name="valor_catastral_construccion" inputMode="decimal" ayuda="Viene en el recibo del IBI." />
        <Campo etiqueta="% de propiedad" name="porcentaje_propiedad" defaultValue="100" />
      </Formulario>
  }
}

const TITULOS: Record<Accion['tipo'], string> = {
  valoracion: 'Nueva valoración', hipoteca: 'Añadir hipoteca', contrato: 'Contrato de alquiler',
  renta: 'Actualizar renta', gasto: 'Añadir gasto', nuevo: 'Nuevo inmueble',
}

export default function Inmuebles() {
  const [accion, setAccion] = useState<Accion | null>(null)
  const { data, isLoading, error } = useQuery({ queryKey: ['inmuebles'], queryFn: () => api.get<{ anio: number; inmuebles: Inmueble[] }>('/inmuebles') })
  return (
    <>
      <Cabecera titulo="Inmuebles" subtitulo="El piso alquilado, la casa nueva y sus hipotecas">
        <Boton onClick={() => setAccion({ tipo: 'nuevo' })}><Plus size={16} />Inmueble</Boton>
      </Cabecera>
      {isLoading ? <Cargando /> : error ? <ErrorCarga error={error} /> :
        data?.inmuebles.length ? data.inmuebles.map((i) => <Ficha key={i.id} i={i} abrir={setAccion} />)
          : <Vacio>Añade el piso alquilado y la casa de obra nueva.</Vacio>}
      <Dialogo abierto={!!accion} onCerrar={() => setAccion(null)} titulo={accion ? `${TITULOS[accion.tipo]}${accion.inmueble ? ` · ${accion.inmueble.nombre}` : ''}` : ''}>
        {accion && <Formularios a={accion} cerrar={() => setAccion(null)} />}
      </Dialogo>
    </>
  )
}
