import { useQuery } from '@tanstack/react-query'
import { Pencil } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../../lib/api'
import { eur, eurK, fecha, hoyISO, pct } from '../../lib/format'
import { eje, estiloTooltip } from '../../lib/graficas'
import type { Cobro, Constantes, Contrato, GastoInmueble, Inmueble, Prevision } from '../../lib/tipos'
import { useAccion } from '../../lib/utilidades'
import type { Columna } from '../ui'
import { Barra, BorrarEnDosPasos, Boton, Dato, Etiqueta, Fila, Importe, TablaResponsive, Tarjeta } from '../ui'
import { Hipoteca } from './Hipoteca'
import { VenderOSeguir } from './VenderOSeguir'
import { BOTON_PEQ, mesLargo, mesesHasta, mesesTexto, nombreMes, TIPOS_GASTO_INMUEBLE } from './comun'
import type { Accion } from './comun'

const nombreGasto = (g: GastoInmueble) => g.concepto || TIPOS_GASTO_INMUEBLE[g.tipo] || g.tipo

const COLUMNAS_GASTOS: Columna<GastoInmueble>[] = [
  { cabecera: 'Fecha', celda: (g) => fecha(g.fecha), claseTd: 'cifra whitespace-nowrap text-muted', papel: 'subtitulo',
    celdaMovil: (g) => <><span className="cifra">{fecha(g.fecha)}</span> · {TIPOS_GASTO_INMUEBLE[g.tipo] ?? g.tipo}</> },
  { cabecera: 'Tipo', celda: (g) => TIPOS_GASTO_INMUEBLE[g.tipo] ?? g.tipo, papel: 'oculta' },
  { cabecera: 'Concepto', celda: (g) => g.concepto || <span className="text-muted">—</span>, papel: 'titulo', celdaMovil: nombreGasto },
  { cabecera: 'Importe', celda: (g) => <Importe valor={g.importe} />, num: true, fuerte: true },
]

function etiquetaBien(i: Inmueble): { texto: string; tono: 'aviso' | 'acento' | 'neutro' } {
  if (i.tipo === 'inmueble_en_construccion') return { texto: 'En construcción', tono: 'aviso' }
  if (i.tipo === 'vehiculo') return { texto: 'Coche', tono: 'neutro' }
  if (i.tipo === 'otro') return { texto: 'Otro bien', tono: 'neutro' }
  return { texto: i.uso === 'alquiler' ? 'Alquilado' : i.uso === 'vivienda_habitual' ? 'Vivienda habitual' : 'Inmueble', tono: 'acento' }
}

/** Valor del piso frente a lo que queda de hipoteca, en cada valoración (y el día de la compra). */
function Evolucion({ i }: { i: Inmueble }) {
  const puntos = [
    ...(i.fecha_compra ? [{ fecha: i.fecha_compra, valor: i.precio_compra, deuda: i.deuda_compra ?? 0 }] : []),
    ...i.valoraciones.map((v) => ({ fecha: v.fecha, valor: v.valor, deuda: v.deuda })),
  ].sort((a, b) => a.fecha.localeCompare(b.fecha))
  if (puntos.length < 2) return null
  return (
    <div className="mt-5">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2 text-xs">
        <h3 className="text-sm font-semibold">Evolución</h3>
        <ul className="flex gap-4 text-muted" aria-label="Leyenda">
          <li className="flex items-center gap-1.5"><span className="h-0.5 w-4 rounded bg-[var(--chart-1)]" aria-hidden />Valor del piso</li>
          <li className="flex items-center gap-1.5"><span className="h-0.5 w-4 rounded border-t-2 border-dashed border-[var(--chart-5)]" aria-hidden />Hipoteca pendiente</li>
        </ul>
      </div>
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={puntos} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--line)" />
            <XAxis dataKey="fecha" tickFormatter={(v) => fecha(String(v), { month: 'short', year: '2-digit' })} {...eje} minTickGap={32} />
            <YAxis tickFormatter={eurK} {...eje} width={60} domain={[0, 'auto']} />
            <Tooltip {...estiloTooltip} labelFormatter={(v) => fecha(String(v))}
              formatter={(v, n) => [eur(Number(v)), n === 'valor' ? 'Valor del piso' : 'Hipoteca pendiente']} />
            <Line type="monotone" dataKey="valor" stroke="var(--chart-1)" strokeWidth={2} dot={{ r: 3, strokeWidth: 0, fill: 'var(--chart-1)' }} />
            <Line type="monotone" dataKey="deuda" stroke="var(--chart-5)" strokeWidth={2} strokeDasharray="5 4" dot={{ r: 3, strokeWidth: 0, fill: 'var(--chart-5)' }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-xs text-muted">El piso entero según tus valoraciones (y el precio de compra); la hipoteca según su cuadro en cada fecha.</p>
    </div>
  )
}

/** Para la obra nueva: cuánto falta por poner hasta el último plazo y si la previsión del Plan llega. */
function Llegada({ i }: { i: Inmueble }) {
  const { data: prev } = useQuery({ queryKey: ['prevision'], queryFn: () => api.get<Prevision>('/prevision') })
  const pendientes = i.pagos.filter((p) => !p.pagado)
  if (!pendientes.length) return null
  const ultimo = pendientes.reduce((a, b) => (a.fecha > b.fecha ? a : b))
  const financia = i.hipotecas.filter((h) => h.futura).reduce((s, h) => s + h.capital_inicial, 0)
  const falta = Math.max(0, pendientes.reduce((s, p) => s + p.importe, 0) - financia)
  const meses = Math.max(1, mesesHasta(ultimo.fecha))
  const mes = ultimo.fecha.slice(0, 7)
  const previsto = prev?.meses.find((m) => m.mes === mes)
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold">¿Llego a la entrega?</h3>
      <div className="grid grid-cols-2 gap-4 [&>*]:min-w-0">
        <Dato etiqueta="Último plazo" valor={mesLargo(mes)} nota={ultimo.concepto} />
        <Dato etiqueta="Te falta poner" valor={eur(falta)} nota={financia ? `Sin los ${eur(financia)} que pone la hipoteca prevista` : 'Los plazos pendientes'} />
      </div>
      <p className="mt-3 text-sm">Aparta <strong className="cifra">{eur(falta / meses)}</strong> al mes hasta entonces ({mesesTexto(meses)}).</p>
      {prev && (previsto
        ? <p className={`mt-1 text-sm ${previsto.liquidez < 0 ? 'font-medium text-neg' : ''}`}>
            Según el Plan tendrás {eur(previsto.liquidez)} en {mesLargo(mes)}{previsto.liquidez < 0 ? ': no llegas, revisa el Plan.' : ', con estos plazos ya descontados.'}
          </p>
        : <p className="mt-1 text-xs text-muted">Queda más allá de los {prev.meses.length} meses que cubre el Plan.</p>)}
      <p className="mt-1 text-xs text-muted">Estimación con los plazos apuntados y la previsión del Plan.</p>
    </div>
  )
}

function LineaCobro({ c }: { c: Cobro }) {
  const mes = nombreMes(c.mes)
  const esteMes = c.mes === hoyISO().slice(0, 7)
  const dia = (iso: string) => Number(iso.slice(8, 10))
  if (!c.fecha) {
    const tranquilo = esteMes && Number(hoyISO().slice(8, 10)) < 10
    return <li className={tranquilo ? 'text-muted' : 'text-warn'}>{mes}: aún no ha llegado</li>
  }
  if (!c.cuadra) return <li className="text-warn">{mes}: llegaron {eur(c.importe)} el {dia(c.fecha)} (la renta es {eur(c.renta)})</li>
  return <li className="text-muted">{mes}: cobrado el {dia(c.fecha)} ({eur(c.importe)})</li>
}

function BloqueContrato({ c, i, abrir }: { c: Contrato; i: Inmueble; abrir: (a: Accion) => void }) {
  const borrar = useAccion((id: number) => api.del(`/contratos/${id}`), 'Contrato borrado')
  const borrarCambio = useAccion((id: number) => api.del(`/rentas/${id}`), 'Cambio de renta borrado')
  const terminado = !!c.fecha_fin && c.fecha_fin < hoyISO()
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="min-w-0 truncate text-sm font-semibold">Alquiler{c.inquilino && ` · ${c.inquilino}`}{terminado && <> <Etiqueta>Terminado</Etiqueta></>}</h3>
        <span className="flex shrink-0 items-center gap-3">
          {!terminado && <button className="text-xs font-medium text-accent" onClick={() => abrir({ tipo: 'renta', inmueble: i, contratoId: c.id })}>Actualizar renta</button>}
          <button className="text-xs font-medium text-accent" onClick={() => abrir({ tipo: 'editarContrato', inmueble: i, contratoId: c.id })}>Editar</button>
          <BorrarEnDosPasos etiqueta="el contrato" disabled={borrar.isPending} onBorrar={() => borrar.mutate(c.id)} />
        </span>
      </div>
      <p className="text-xs text-muted">Reducción en la renta: {c.reduccion_pct} %{c.fecha_fin && ` · ${terminado ? 'terminó' : 'termina'} el ${fecha(c.fecha_fin)}`}</p>
      <div className={`cifra text-2xl font-medium ${terminado ? 'text-muted' : ''}`}>{eur(c.renta_actual)}<span className="text-sm text-muted"> /mes</span></div>
      {c.cobros.length > 0 && (
        <>
          <ul className="mt-2 space-y-0.5 text-xs" aria-label="Cobros del inquilino">{[...c.cobros].reverse().map((x) => <LineaCobro key={x.mes} c={x} />)}</ul>
          <p className="mt-1 text-xs text-muted">Cruzado con los ingresos de tus cuentas: la renta (±1 €) o la categoría «Alquiler cobrado».</p>
        </>
      )}
      <ol className="mt-2 space-y-1 text-xs text-muted">
        <li>Desde {fecha(c.fecha_inicio)}: {eur(c.renta_inicial)}</li>
        {c.cambios.map((x) => (
          <li key={x.id} className="flex items-center gap-2">
            <span>Desde {fecha(x.desde)}: {eur(x.renta)}</span>
            <BorrarEnDosPasos etiqueta={`la subida del ${fecha(x.desde)}`} disabled={borrarCambio.isPending} onBorrar={() => borrarCambio.mutate(x.id)} />
          </li>
        ))}
      </ol>
    </div>
  )
}

export function Ficha({ i, anio, constantes, abrir }: { i: Inmueble; anio: number; constantes: Constantes; abrir: (a: Accion) => void }) {
  const enObra = i.tipo === 'inmueble_en_construccion'
  const inmueble = i.tipo === 'inmueble'
  const conHipoteca = inmueble || enObra
  const ren = i.rentabilidad
  const r = i.rendimiento
  const apuntado = i.pagos.reduce((s, p) => s + p.importe, 0)
  const pagado = i.pagos.filter((p) => p.pagado).reduce((s, p) => s + p.importe, 0)
  const totalObra = Math.max(i.precio_compra, apuntado)
  const borrarGasto = useAccion((id: number) => api.del(`/gastos-inmueble/${id}`), 'Gasto borrado')
  const borrarValoracion = useAccion((id: number) => api.del(`/valoraciones/${id}`), 'Valoración borrada')
  const borrar = useAccion(() => api.del(`/inmuebles/${i.id}`), `${i.nombre} borrado`)
  const etiqueta = etiquetaBien(i)
  const parcial = i.porcentaje_propiedad < 100
  return (
    <Tarjeta className="mb-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">{i.nombre}</h2>
            <Etiqueta tono={etiqueta.tono}>{etiqueta.texto}</Etiqueta>
            {parcial && <Etiqueta>Tuyo al {pct(i.porcentaje_propiedad, 0)}</Etiqueta>}
          </div>
          <p className="mt-1 text-xs text-muted">
            {i.fecha_compra ? `Comprado el ${fecha(i.fecha_compra)} por ${eur(i.precio_compra)}` : enObra ? `Precio ${eur(i.precio_compra)}` : 'Sin fecha de compra'}
            {i.valor_catastral > 0 && ` · catastral ${eur(i.valor_catastral)}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {!enObra && <Boton variante="secundario" className={BOTON_PEQ} onClick={() => abrir({ tipo: 'valoracion', inmueble: i })}>Valorar</Boton>}
          {conHipoteca && <Boton variante="secundario" className={BOTON_PEQ} onClick={() => abrir({ tipo: 'hipoteca', inmueble: i })}>Hipoteca</Boton>}
          {inmueble && <Boton variante="secundario" className={BOTON_PEQ} onClick={() => abrir({ tipo: 'contrato', inmueble: i })}>Contrato</Boton>}
          {conHipoteca && <Boton variante="secundario" className={BOTON_PEQ} onClick={() => abrir({ tipo: 'gasto', inmueble: i })}>Gasto</Boton>}
          {enObra && <Boton variante="secundario" className={BOTON_PEQ} onClick={() => abrir({ tipo: 'escritura', inmueble: i })}>Gastos de escritura</Boton>}
          {enObra && <Boton className={BOTON_PEQ} onClick={() => abrir({ tipo: 'escriturar', inmueble: i })}>Escriturada</Boton>}
          <Boton variante="fantasma" className="px-2 py-1.5 text-xs" onClick={() => abrir({ tipo: 'editar', inmueble: i })} aria-label={`Editar ${i.nombre}`}><Pencil size={14} /></Boton>
          <BorrarEnDosPasos etiqueta={`${i.nombre} con sus hipotecas, contratos y gastos`} disabled={borrar.isPending} onBorrar={() => borrar.mutate(undefined)} />
        </div>
      </div>

      <div className={`mt-5 grid gap-6 sm:grid-cols-2 ${i.plusvalia_latente != null ? 'lg:grid-cols-4' : 'lg:grid-cols-3'} [&>*]:min-w-0`}>
        <Dato etiqueta={enObra ? 'Pagado' : 'Valor'} valor={eur(i.valor)} nota={parcial && !enObra ? `${i.valor_detalle} · tu parte` : i.valor_detalle} />
        {conHipoteca && <Dato etiqueta="Hipoteca pendiente" valor={eur(i.deuda)} />}
        {conHipoteca && <Dato etiqueta="Es tuyo" valor={eur(i.equity)} tono={i.equity >= 0 ? undefined : 'neg'} />}
        {i.plusvalia_latente != null && (
          <Dato etiqueta="Plusvalía latente" valor={eur(i.plusvalia_latente)} tono={i.plusvalia_latente >= 0 ? 'pos' : 'neg'}
            nota={`Valor menos lo que costó (${eur(i.coste)}${parcial ? ', tu parte' : ''}), sin impuestos`} />
        )}
      </div>
      {i.notas && <p className="mt-3 text-xs text-muted">{i.notas}</p>}
      {inmueble && <Evolucion i={i} />}

      <div className="mt-6 grid gap-6 lg:grid-cols-2 [&>*]:min-w-0">
        {enObra && (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Pagos a la promotora</h3>
            <div className="mb-1 flex justify-between text-xs text-muted"><span>{eur(pagado)} pagado</span><span>{eur(totalObra)} en total</span></div>
            <Barra valor={pagado} max={totalObra} />
            {i.precio_compra > apuntado && <p className="mt-1 text-xs text-warn">Quedan {eur(i.precio_compra - apuntado)} del precio por apuntar como plazos en Plan.</p>}
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
        {enObra && <Llegada i={i} />}

        {i.hipotecas.map((h) => <Hipoteca key={h.id} h={h} anio={anio} inmueble={i} abrir={abrir} />)}
        {i.contratos.map((c) => <BloqueContrato key={c.id} c={c} i={i} abrir={abrir} />)}

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
            <Fila etiqueta={`Amortización ${pct(constantes.amortizacion_pct, 0)}`} valor={-r.amortizacion} />
            <Fila etiqueta="Rendimiento neto" valor={r.rendimiento_neto} fuerte />
            <Fila etiqueta={`Reducción ${r.reduccion_pct} %`} valor={-r.reduccion} />
            <Fila etiqueta="Tributa" valor={r.rendimiento_reducido} fuerte />
            {r.notas.map((n) => <p key={n} className="mt-2 text-xs text-warn">{n}</p>)}
          </div>
        )}
      </div>

      {inmueble && i.contratos.length > 0 && <VenderOSeguir i={i} constantes={constantes} />}

      {!enObra && i.pagos.length > 0 && (
        <details className="mt-5">
          <summary className="cursor-pointer text-sm font-medium text-accent">Pagos previstos ({i.pagos.length})</summary>
          <ul className="mt-2 divide-y divide-line">
            {i.pagos.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                <span className="min-w-0"><span className="block truncate">{p.concepto}</span><span className="text-xs text-muted">{fecha(p.fecha)}</span></span>
                <span className="flex items-center gap-2"><Etiqueta tono={p.pagado ? 'bien' : 'neutro'}>{p.pagado ? 'Pagado' : 'Pendiente'}</Etiqueta><Importe valor={p.importe} /></span>
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-muted">Se editan en Plan.</p>
        </details>
      )}
      {i.gastos.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm font-medium text-accent">Gastos registrados ({i.gastos.length})</summary>
          <div className="mt-3">
            <TablaResponsive filas={i.gastos} columnas={COLUMNAS_GASTOS} clave={(g) => g.id}
              acciones={(g) => <>
                <Boton variante="fantasma" className="px-2 py-1" onClick={() => abrir({ tipo: 'editarGasto', inmueble: i, gastoId: g.id })} aria-label={`Editar el gasto ${nombreGasto(g)}`}><Pencil size={14} /></Boton>
                <BorrarEnDosPasos etiqueta={`el gasto ${nombreGasto(g)}`} disabled={borrarGasto.isPending} onBorrar={() => borrarGasto.mutate(g.id)} />
              </>} />
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
                <span className="flex items-center gap-1"><Importe valor={v.valor} className="mr-1" />
                  <Boton variante="fantasma" className="px-2 py-1" onClick={() => abrir({ tipo: 'editarValoracion', inmueble: i, valoracionId: v.id })} aria-label={`Editar la valoración del ${fecha(v.fecha)}`}><Pencil size={14} /></Boton>
                  <BorrarEnDosPasos etiqueta="la valoración" disabled={borrarValoracion.isPending} onBorrar={() => borrarValoracion.mutate(v.id)} /></span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Tarjeta>
  )
}
