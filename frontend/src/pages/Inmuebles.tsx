import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Pencil, Plus } from 'lucide-react'
import { api } from '../lib/api'
import { eur, fecha, hoyISO, pct } from '../lib/format'
import type { Inmueble, VenderOAlquilar } from '../lib/tipos'
import { num, opc, useAccion } from '../lib/utilidades'
import { Barra, BorrarEnDosPasos, Boton, Cabecera, Campo, Cargando, Dato, Dialogo, Etiqueta, ErrorCarga, Fila, Formulario, Importe, Selector, Tabla, Tarjeta, Vacio } from '../components/ui'

type Accion = { tipo: 'valoracion' | 'hipoteca' | 'contrato' | 'renta' | 'gasto' | 'nuevo' | 'editar' | 'escritura' | 'editarContrato'; inmueble?: Inmueble; contratoId?: number }

function Ficha({ i, abrir }: { i: Inmueble; abrir: (a: Accion) => void }) {
  const enObra = i.tipo === 'inmueble_en_construccion'
  const coche = i.tipo === 'vehiculo'
  const ren = i.rentabilidad
  const totalObra = i.pagos.reduce((s, p) => s + p.importe, 0)
  const pagado = i.pagos.filter((p) => p.pagado).reduce((s, p) => s + p.importe, 0)
  const r = i.rendimiento
  const borrarHipoteca = useAccion((id: number) => api.del(`/deudas/${id}`), 'Hipoteca borrada')
  const borrarContrato = useAccion((id: number) => api.del(`/contratos/${id}`), 'Contrato borrado')
  const borrarGasto = useAccion((id: number) => api.del(`/gastos-inmueble/${id}`), 'Gasto borrado')
  const borrarValoracion = useAccion((id: number) => api.del(`/valoraciones/${id}`), 'Valoración borrada')
  const borrar = useAccion(() => api.del(`/inmuebles/${i.id}`), `${i.nombre} borrado`)
  return (
    <Tarjeta className="mb-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">{i.nombre}</h2>
            <Etiqueta tono={enObra ? 'aviso' : 'acento'}>{coche ? 'Coche' : enObra ? 'En construcción' : i.uso === 'alquiler' ? 'Alquilado' : i.uso === 'vivienda_habitual' ? 'Vivienda habitual' : 'Inmueble'}</Etiqueta>
          </div>
          <p className="mt-1 text-xs text-muted">
            {i.fecha_compra ? `Comprado el ${fecha(i.fecha_compra)} por ${eur(i.precio_compra)}` : enObra ? `Precio ${eur(i.precio_compra)}` : 'Sin fecha de compra'}
            {i.valor_catastral > 0 && ` · catastral ${eur(i.valor_catastral)}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {!enObra && <Boton variante="secundario" className="px-2.5 py-1.5 text-xs" onClick={() => abrir({ tipo: 'valoracion', inmueble: i })}>Valorar</Boton>}
          {!coche && <Boton variante="secundario" className="px-2.5 py-1.5 text-xs" onClick={() => abrir({ tipo: 'hipoteca', inmueble: i })}>Hipoteca</Boton>}
          {!enObra && !coche && <Boton variante="secundario" className="px-2.5 py-1.5 text-xs" onClick={() => abrir({ tipo: 'contrato', inmueble: i })}>Contrato</Boton>}
          {!coche && <Boton variante="secundario" className="px-2.5 py-1.5 text-xs" onClick={() => abrir({ tipo: 'gasto', inmueble: i })}>Gasto</Boton>}
          {enObra && <Boton variante="secundario" className="px-2.5 py-1.5 text-xs" onClick={() => abrir({ tipo: 'escritura', inmueble: i })}>Gastos de escritura</Boton>}
          <Boton variante="fantasma" className="px-2 py-1.5 text-xs" onClick={() => abrir({ tipo: 'editar', inmueble: i })} aria-label={`Editar ${i.nombre}`}><Pencil size={14} /></Boton>
          <BorrarEnDosPasos etiqueta={`${i.nombre} con sus hipotecas, contratos y gastos`} disabled={borrar.isPending} onBorrar={() => borrar.mutate(undefined)} />
        </div>
      </div>

      <div className="mt-5 grid gap-6 sm:grid-cols-3">
        <Dato etiqueta={enObra ? 'Pagado' : 'Valor'} valor={eur(i.valor)} nota={i.valor_detalle} />
        {!coche && <Dato etiqueta="Hipoteca pendiente" valor={eur(i.deuda)} />}
        {!coche && <Dato etiqueta="Es tuyo" valor={eur(i.equity)} tono={i.equity >= 0 ? undefined : 'neg'} />}
      </div>
      {i.notas && <p className="mt-3 text-xs text-muted">{i.notas}</p>}

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
              {!i.pagos.length && <li className="py-2 text-sm text-muted">Añade los plazos en Plan.</li>}
            </ul>
          </div>
        )}

        {i.hipotecas.map((h) => (
          <div key={h.id}>
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">{h.nombre} · {h.entidad}{h.futura && <> <Etiqueta tono="acento">Prevista</Etiqueta></>}</h3>
              <BorrarEnDosPasos etiqueta={`la hipoteca ${h.nombre}`} disabled={borrarHipoteca.isPending} onBorrar={() => borrarHipoteca.mutate(h.id)} />
            </div>
            <div className="mb-1 flex justify-between text-xs text-muted"><span>{eur(h.capital_inicial - h.pendiente)} amortizado</span><span>{eur(h.capital_inicial)}</span></div>
            <Barra valor={h.capital_inicial - h.pendiente} max={h.capital_inicial} />
            <Fila etiqueta="Cuota mensual" valor={h.cuota} />
            <Fila etiqueta={`Interés ${pct(h.tipo_interes_anual, 3)}, intereses este año`} valor={h.intereses_anio} />
            {h.futura
              ? <p className="mt-2 text-xs text-muted">Empieza el {fecha(h.fecha_inicio)}. Hasta entonces no cuenta como deuda; sus cuotas ya cuentan en el Plan.</p>
              : <Fila etiqueta="Pendiente hoy" valor={h.pendiente} fuerte />}
          </div>
        ))}

        {i.contratos.map((c) => (
          <div key={c.id}>
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">Alquiler{c.inquilino && ` · ${c.inquilino}`}</h3>
              <span className="flex items-center gap-3">
                <button className="text-xs font-medium text-accent" onClick={() => abrir({ tipo: 'renta', inmueble: i, contratoId: c.id })}>Actualizar renta</button>
                <button className="text-xs font-medium text-accent" onClick={() => abrir({ tipo: 'editarContrato', inmueble: i, contratoId: c.id })}>Editar</button>
                <BorrarEnDosPasos etiqueta="el contrato" disabled={borrarContrato.isPending} onBorrar={() => borrarContrato.mutate(c.id)} />
              </span>
            </div>
            <p className="text-xs text-muted">Reducción en la renta: {c.reduccion_pct} %{c.fecha_fin && ` · terminó el ${fecha(c.fecha_fin)}`}</p>
            <div className="cifra text-2xl font-medium">{eur(c.renta_actual)}<span className="text-sm text-muted"> /mes</span></div>
            <ol className="mt-2 space-y-1 text-xs text-muted">
              <li>Desde {fecha(c.fecha_inicio)}: {eur(c.renta_inicial)}</li>
              {c.cambios.map((x) => <li key={x.desde}>Desde {fecha(x.desde)}: {eur(x.renta)}</li>)}
            </ol>
          </div>
        ))}

        {ren && (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Rentabilidad del alquiler</h3>
            <div className="mb-3 flex flex-wrap gap-x-8 gap-y-2">
              <Dato etiqueta="Bruta" valor={pct(ren.bruta)} />
              <Dato etiqueta="Neta" valor={pct(ren.neta)} />
              <Dato etiqueta="Sobre lo que pusiste" valor={pct(ren.sobre_aportado)} />
            </div>
            <Fila etiqueta="Renta al año" valor={ren.renta_anual} />
            <Fila etiqueta="Gastos (últimos 12 meses)" valor={-ren.gastos_anuales} />
            <Fila etiqueta="Cuotas de hipoteca al año" valor={-ren.cuotas_anuales} />
            <Fila etiqueta="Te queda al año" valor={ren.flujo_caja_anual} fuerte />
            <p className="mt-2 text-xs text-muted">Bruta y neta sobre lo que costó ({eur(ren.coste)}); sobre el valor actual la neta es {pct(ren.neta_sobre_valor)}.
              «Sobre lo que pusiste» descuenta los intereses y compara con tu dinero sin la hipoteca ({eur(ren.aportado)}).</p>
          </div>
        )}

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

      {i.contratos.length > 0 && <VenderOSeguir i={i} />}

      {i.gastos.length > 0 && (
        <details className="mt-5">
          <summary className="cursor-pointer text-sm font-medium text-accent">Gastos registrados ({i.gastos.length})</summary>
          <div className="mt-3">
            <Tabla>
              <thead><tr><th>Fecha</th><th>Tipo</th><th>Concepto</th><th className="num">Importe</th><th /></tr></thead>
              <tbody>{i.gastos.map((g) => <tr key={g.id}><td className="cifra text-muted">{fecha(g.fecha)}</td><td className="capitalize">{g.tipo}</td><td>{g.concepto}</td>
                <td className="num"><Importe valor={g.importe} /></td>
                <td className="text-right"><BorrarEnDosPasos etiqueta={`el gasto ${g.concepto || g.tipo}`} disabled={borrarGasto.isPending} onBorrar={() => borrarGasto.mutate(g.id)} /></td></tr>)}</tbody>
            </Tabla>
          </div>
        </details>
      )}
      {i.valoraciones.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm font-medium text-accent">Valoraciones ({i.valoraciones.length})</summary>
          <ul className="mt-2 divide-y divide-line">
            {i.valoraciones.map((v) => (
              <li key={v.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                <span className="cifra text-muted">{fecha(v.fecha)}</span>
                <span className="flex items-center gap-2"><Importe valor={v.valor} />
                  <BorrarEnDosPasos etiqueta="la valoración" disabled={borrarValoracion.isPending} onBorrar={() => borrarValoracion.mutate(v.id)} /></span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Tarjeta>
  )
}

function VenderOSeguir({ i }: { i: Inmueble }) {
  const [precio, setPrecio] = useState('')
  const [abierto, setAbierto] = useState(false)
  const p = num(precio)
  const { data: v, isFetching } = useQuery({
    queryKey: ['vender', i.id, p ?? null], enabled: abierto,
    queryFn: () => api.get<VenderOAlquilar>(`/inmuebles/${i.id}/vender${p ? `?precio=${p}` : ''}`),
  })
  return (
    <details className="mt-5 rounded-xl border border-line p-4" onToggle={(e) => setAbierto((e.target as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-sm font-semibold">¿Vender o seguir alquilando?</summary>
      <div className="mt-3 max-w-xs">
        <Campo etiqueta="Precio de venta (€)" name="precio" inputMode="decimal" value={precio} onChange={(e) => setPrecio(e.target.value)}
          placeholder={v ? String(Math.round(v.precio_venta)) : ''} ayuda="Vacío: el valor actual." />
      </div>
      {v && (
        <div className={`mt-4 grid gap-6 lg:grid-cols-2 ${isFetching ? 'opacity-60' : ''}`}>
          <div>
            <h4 className="mb-1 text-sm font-semibold">Si vendes</h4>
            <Fila etiqueta={`Precio (${v.valor_detalle})`} valor={v.precio_venta} />
            <Fila etiqueta="Gastos de venta (3 %)" valor={-v.gastos_venta} />
            <Fila etiqueta={`IRPF de la ganancia (${eur(v.ganancia)})`} valor={-v.irpf_ganancia} />
            <Fila etiqueta="Cancelar la hipoteca" valor={-v.hipoteca_pendiente} />
            <Fila etiqueta="Te queda en mano" valor={v.en_mano} fuerte />
            <p className="mt-2 text-xs text-muted">La ganancia descuenta la amortización que ya te has deducido ({eur(v.amortizacion_acumulada)}).</p>
          </div>
          <div>
            <h4 className="mb-1 text-sm font-semibold">Si sigues alquilando</h4>
            <Fila etiqueta="Te queda al año" valor={v.alquiler_flujo_anual} />
            <Fila etiqueta="IRPF del alquiler" valor={-v.alquiler_irpf_anual} />
            <Fila etiqueta="Neto al año" valor={v.alquiler_flujo_tras_irpf} fuerte />
            <p className="mt-2 text-xs text-muted">
              {v.rentabilidad_sobre_en_mano !== null
                ? `Equivale a un ${pct(v.rentabilidad_sobre_en_mano)} al año sobre lo que sacarías vendiendo, sin contar lo que suba o baje el piso.`
                : 'Vendiendo no te quedaría dinero en mano.'}
            </p>
          </div>
          <div className="lg:col-span-2">{v.notas.map((n) => <p key={n} className="text-xs text-muted">{n}</p>)}</div>
        </div>
      )}
    </details>
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
  const escritura = usePost(`/inmuebles/${id}/gastos-escritura`, 'Gastos de escritura añadidos a Plan')
  const editar = useAccion((d: object) => api.patch(`/inmuebles/${id}`, d).then(cerrar), 'Cambios guardados')
  const editarContrato = useAccion((d: object) => api.patch(`/contratos/${a.contratoId}`, d).then(cerrar), 'Contrato guardado')
  const i = a.inmueble
  const c = i?.contratos.find((x) => x.id === a.contratoId)

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
        renta_mensual: num(d.renta_mensual), reduccion_pct: num(d.reduccion_pct) ?? null })}>
        <Campo etiqueta="Inquilino" name="inquilino" />
        <Campo etiqueta="Renta inicial (€/mes)" name="renta_mensual" inputMode="decimal" required />
        <Campo etiqueta="Inicio del contrato" name="fecha_inicio" type="date" required />
        <Campo etiqueta="Fin (si ya terminó)" name="fecha_fin" type="date" />
        <Campo etiqueta="Reducción IRPF %" name="reduccion_pct" className="sm:col-span-2" ayuda="Vacío: 60 % si el contrato es anterior al 26/05/2023 y 50 % si es posterior." />
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
    case 'editarContrato':
      return <Formulario onEnviar={(d) => editarContrato.mutateAsync({ inquilino: d.inquilino, fecha_fin: d.fecha_fin || null,
        ...(num(d.reduccion_pct) !== undefined ? { reduccion_pct: num(d.reduccion_pct) } : {}) })}>
        <Campo etiqueta="Inquilino" name="inquilino" defaultValue={c?.inquilino} />
        <Campo etiqueta="Fin (si ya terminó)" name="fecha_fin" type="date" defaultValue={c?.fecha_fin ?? ''} />
        <Campo etiqueta="Reducción IRPF %" name="reduccion_pct" defaultValue={c ? String(c.reduccion_pct) : ''} className="sm:col-span-2" />
      </Formulario>
    case 'escritura':
      return <Formulario onEnviar={(d) => escritura.mutateAsync({ fecha: d.fecha, precio: num(d.precio) ?? null })}>
        <Campo etiqueta="Fecha prevista de la escritura" name="fecha" type="date" required />
        <Campo etiqueta="Precio sin IVA (€)" name="precio" inputMode="decimal" defaultValue={i?.precio_compra ? String(i.precio_compra) : ''} />
        <p className="text-xs text-muted sm:col-span-2">Te apunto en Plan un pago con el AJD de Murcia (1,5 % del precio) y unos 1.200 € de notaría, registro y gestoría.</p>
      </Formulario>
    case 'editar':
      return <Formulario onEnviar={(d) => editar.mutateAsync({ nombre: d.nombre, uso: d.uso, fecha_compra: d.fecha_compra || null,
        precio_compra: num(d.precio_compra) ?? 0, gastos_compra: num(d.gastos_compra) ?? 0, valor_catastral: num(d.valor_catastral) ?? 0,
        valor_catastral_construccion: num(d.valor_catastral_construccion) ?? 0, porcentaje_propiedad: num(d.porcentaje_propiedad) ?? 100, notas: d.notas })}>
        <Campo etiqueta="Nombre" name="nombre" required defaultValue={i?.nombre} />
        <Selector etiqueta="Uso" name="uso" defaultValue={i?.uso}>
          <option value="alquiler">Alquiler</option><option value="vivienda_habitual">Vivienda habitual</option><option value="otro">Otro</option>
        </Selector>
        <Campo etiqueta="Fecha de compra" name="fecha_compra" type="date" defaultValue={i?.fecha_compra ?? ''} />
        <Campo etiqueta="Precio (€)" name="precio_compra" inputMode="decimal" defaultValue={String(i?.precio_compra ?? '')} />
        <Campo etiqueta="Gastos de compra (€)" name="gastos_compra" inputMode="decimal" defaultValue={String(i?.gastos_compra ?? '')} />
        <Campo etiqueta="Valor catastral (€)" name="valor_catastral" inputMode="decimal" defaultValue={String(i?.valor_catastral ?? '')} />
        <Campo etiqueta="Catastral construcción (€)" name="valor_catastral_construccion" inputMode="decimal" defaultValue={String(i?.valor_catastral_construccion ?? '')} />
        <Campo etiqueta="% de propiedad" name="porcentaje_propiedad" defaultValue={String(i?.porcentaje_propiedad ?? 100)} />
        <Campo etiqueta="Notas" name="notas" defaultValue={i?.notas} className="sm:col-span-2" />
      </Formulario>
    case 'nuevo':
      return <Formulario onEnviar={(d) => nuevo.mutateAsync({ nombre: d.nombre, tipo: d.tipo, uso: d.uso, fecha_compra: opc(d.fecha_compra),
        precio_compra: num(d.precio_compra) ?? 0, gastos_compra: num(d.gastos_compra) ?? 0, valor_catastral: num(d.valor_catastral) ?? 0,
        valor_catastral_construccion: num(d.valor_catastral_construccion) ?? 0, porcentaje_propiedad: num(d.porcentaje_propiedad) ?? 100 })}>
        <Campo etiqueta="Nombre" name="nombre" required placeholder="Piso alquilado" />
        <Selector etiqueta="Estado" name="tipo" defaultValue="inmueble">
          <option value="inmueble">Ya es mío</option><option value="inmueble_en_construccion">Obra nueva en construcción</option><option value="vehiculo">Coche</option>
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
  renta: 'Actualizar renta', gasto: 'Añadir gasto', nuevo: 'Nuevo inmueble o coche',
  editar: 'Editar', escritura: 'Gastos de escritura', editarContrato: 'Editar contrato',
}

export default function Inmuebles() {
  const [accion, setAccion] = useState<Accion | null>(null)
  const { data, isLoading, error } = useQuery({ queryKey: ['inmuebles'], queryFn: () => api.get<{ anio: number; inmuebles: Inmueble[] }>('/inmuebles') })
  return (
    <>
      <Cabecera titulo="Bienes" subtitulo="Pisos, la casa nueva, hipotecas y coche">
        <Boton onClick={() => setAccion({ tipo: 'nuevo' })}><Plus size={16} />Añadir</Boton>
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
