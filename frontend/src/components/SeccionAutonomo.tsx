import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, CalendarX, Download, FileText, IdCard, Landmark, Pencil, Plus } from 'lucide-react'
import CalendarioDias from './CalendarioDias'
import CuotaTgss from './CuotaTgss'
import DatosFacturacion from './DatosFacturacion'
import { FormFactura, FormGasto } from './FormulariosAutonomo'
import PlanificadorFactura from './PlanificadorFactura'
import ResumenAnual from './ResumenAnual'
import { nombreCategoria } from './categoriasGasto'
import { api } from '../lib/api'
import { eur, eurK, fecha } from '../lib/format'
import { cursorBarra, eje, estiloTooltip } from '../lib/graficas'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Autonomo as Datos, Factura, GastoAutonomo, SugerenciaCobro } from '../lib/tipos'
import { useAccion } from '../lib/utilidades'
import type { Columna } from './ui'
import { BorrarEnDosPasos, Boton, Cargando, Dato, Dialogo, EnDosPasos, Etiqueta, ErrorCarga, Importe, Segmentos, SelectorAnio, TablaResponsive, Tarjeta, Vacio } from './ui'

/** Abre el documento de la factura en otra pestaña, para imprimirlo o guardarlo en PDF. */
function VerDocumento({ f }: { f: Factura }) {
  return (
    <a href={`/api/autonomo/facturas/${f.id}/documento`} target="_blank" rel="noopener" aria-label={`Ver la factura ${f.numero}`} title="Ver la factura"
      className="inline-flex items-center rounded-xl px-2 py-1 text-muted transition hover:bg-panel-2 hover:text-ink"><FileText size={14} /></a>
  )
}

const diaMes = (iso: string) => fecha(iso, { day: '2-digit', month: 'short' })
const diaMesNum = (iso: string | null) => fecha(iso, { day: '2-digit', month: '2-digit' })

type Filtro = 'todas' | 'pendientes' | 'cobradas'
const FILTROS = [{ valor: 'todas', texto: 'Todas' }, { valor: 'pendientes', texto: 'Pendientes' }, { valor: 'cobradas', texto: 'Cobradas' }] as const

/** Estado de cobro de una factura y, si está pendiente, los botones para darla por cobrada. */
function EstadoCobro({ f, sugerencia, cobrar, ocupado }: {
  f: Factura; sugerencia?: SugerenciaCobro; cobrar: (v: { id: number; fecha?: string }) => void; ocupado: boolean
}) {
  if (f.cobrada) return <Etiqueta tono="bien">Cobrada el {diaMesNum(f.fecha_cobro)}</Etiqueta>
  const dias = f.dias_pendiente ?? 0
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <Etiqueta tono={dias > 90 ? 'mal' : dias > 45 ? 'aviso' : 'neutro'}>Pendiente · {dias} {dias === 1 ? 'día' : 'días'}</Etiqueta>
      {sugerencia
        ? <Boton variante="secundario" className="px-2 py-0.5 text-xs" disabled={ocupado} onClick={() => cobrar({ id: f.id, fecha: sugerencia.fecha })}
            title={`Ingreso de ${eur(sugerencia.importe)} en tu cuenta`}><Landmark size={12} />Vista en el banco el {diaMesNum(sugerencia.fecha)} · Marcar</Boton>
        : <Boton variante="fantasma" className="px-2 py-0.5 text-xs" disabled={ocupado} onClick={() => cobrar({ id: f.id })}>Cobrada hoy</Boton>}
    </span>
  )
}

const COLUMNAS_GASTOS: Columna<GastoAutonomo>[] = [
  { cabecera: 'Fecha', celda: (g) => diaMes(g.fecha), claseTd: 'cifra whitespace-nowrap text-muted', papel: 'subtitulo',
    celdaMovil: (g) => <><span className="cifra">{diaMes(g.fecha)}</span> · {nombreCategoria(g.categoria)}</> },
  { cabecera: 'Proveedor', celda: (g) => g.proveedor || g.concepto, papel: 'titulo' },
  { cabecera: 'Categoría', celda: (g) => nombreCategoria(g.categoria), claseTd: 'text-muted', papel: 'oculta' },
  { cabecera: 'Base', celda: (g) => <Importe valor={g.base} />, num: true },
  { cabecera: 'IVA', celda: (g) => <Importe valor={g.cuota_iva} />, num: true },
  { cabecera: 'Deducible', celda: (g) => <span className="cifra">{g.deducible_pct} %</span>, num: true },
]

const enlaceBoton = 'inline-flex items-center justify-center gap-2 rounded-xl border border-line bg-panel px-3.5 py-2 text-sm font-medium transition hover:bg-panel-2'

export default function SeccionAutonomo() {
  const [anio, setAnio] = useState(() => new Date().getFullYear())
  // «Registrar factura» va en la URL (?accion=factura) para poder abrirlo desde fuera (la paleta de comandos)
  const [params, setParams] = useSearchParams()
  const formFactura = params.get('accion') === 'factura'
  const conAccion = (accion: string | null) => (prev: URLSearchParams) => {
    const p = new URLSearchParams(prev)
    if (accion) p.set('accion', accion); else p.delete('accion')
    return p
  }
  const abrirFactura = () => setParams(conAccion('factura'), { replace: true })
  const cerrarFactura = () => setParams(conAccion(null), { replace: true })
  const [dialogo, setDialogo] = useState<'gasto' | 'planificar' | 'calendario' | 'datos' | null>(null)
  const [editando, setEditando] = useState<Factura | null>(null)
  const [editandoGasto, setEditandoGasto] = useState<GastoAutonomo | null>(null)
  const [filtro, setFiltro] = useState<Filtro>('todas')
  const { data: d, isLoading, error } = useQuery({ queryKey: ['autonomo', anio], queryFn: () => api.get<Datos>(`/autonomo?anio=${anio}`) })
  const borrar = useAccion(({ tipo, id }: { tipo: string; id: number }) => api.del(`/autonomo/${tipo}/${id}`), 'Borrado')
  const cobrar = useAccion(({ id, fecha }: { id: number; fecha?: string }) => api.post(`/autonomo/facturas/${id}/cobrada`, { fecha: fecha ?? null }), 'Factura cobrada')
  const conciliar = useAccion(() => api.post<{ marcadas: number }>('/autonomo/cobros/conciliar'), 'Facturas marcadas como cobradas')
  const maxCliente = Math.max(1, ...(d?.por_cliente.map((c) => c.base) ?? [1]))
  const sugerencias = new Map((d?.sugerencias_cobro ?? []).map((s) => [s.factura_id, s]))
  const facturas = (d?.facturas ?? []).filter((f) => filtro === 'todas' || (filtro === 'cobradas') === f.cobrada)
  const deben = d?.por_cobrar
  const columnasFacturas: Columna<Factura>[] = [
    { cabecera: 'Fecha', celda: (f) => diaMes(f.fecha), claseTd: 'cifra whitespace-nowrap text-muted', papel: 'subtitulo',
      celdaMovil: (f) => <span className="cifra">{diaMes(f.fecha)} · Nº {f.numero}</span> },
    { cabecera: 'Nº', celda: (f) => f.numero, claseTd: 'cifra', papel: 'oculta' },
    { cabecera: 'Cliente', celda: (f) => <>{f.cliente}{f.tipo_iva === 0 && <span className="ml-2"><Etiqueta>No sujeta</Etiqueta></span>}</>, claseTd: 'whitespace-nowrap', papel: 'titulo' },
    { cabecera: 'Base', celda: (f) => <Importe valor={f.base} />, num: true },
    { cabecera: 'IVA', celda: (f) => <Importe valor={f.cuota_iva} />, num: true },
    { cabecera: 'Retención', celda: (f) => <Importe valor={-f.retencion} />, num: true },
    { cabecera: 'Cobras', celda: (f) => <Importe valor={f.total} />, num: true, claseTd: 'font-medium', fuerte: true },
    { cabecera: 'Cobro', celda: (f) => <EstadoCobro f={f} sugerencia={sugerencias.get(f.id)} cobrar={cobrar.mutate} ocupado={cobrar.isPending} /> },
  ]

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">{d ? `${eur(d.total_facturado)} facturados en ${anio}` : ''}</p>
        <div className="flex flex-wrap items-center gap-2">
          <SelectorAnio valor={anio} onCambiar={setAnio} />
          <a href={`/api/autonomo/libro.xlsx?anio=${anio}`} download className={enlaceBoton} title="Libro de facturas emitidas y gastos del año, en Excel, para la gestoría"><Download size={16} />Libro {anio}</a>
          <Boton variante="secundario" onClick={() => setDialogo('datos')}><IdCard size={16} />Datos de facturación</Boton>
          <Boton variante="secundario" onClick={() => setDialogo('calendario')}><CalendarX size={16} />Vacaciones</Boton>
          <Boton variante="secundario" onClick={() => setDialogo('planificar')}><CalendarDays size={16} />Generar factura</Boton>
          <Boton variante="secundario" onClick={() => setDialogo('gasto')}><Plus size={16} />Gasto</Boton>
          <Boton onClick={abrirFactura}><Plus size={16} />Factura</Boton>
        </div>
      </div>

      {isLoading ? <Cargando /> : error ? <ErrorCarga error={error} /> : d && (
        <>
          {deben && deben.facturas > 0 && (
            <Tarjeta className="mb-4" titulo="Te deben" accion={sugerencias.size > 0 && (
              <EnDosPasos className="px-2.5 py-1 text-xs" icono={<Landmark size={14} />} disabled={conciliar.isPending}
                texto={`Marcar las ${sugerencias.size} que ya veo en el banco`} textoConfirmar={`Confirmar: ${sugerencias.size} cobradas`}
                onConfirmar={() => conciliar.mutate(undefined)} />
            )}>
              <div className="grid gap-6 sm:grid-cols-3">
                <Dato etiqueta="Pendiente de cobro" valor={eur(deben.total)} nota={`${deben.facturas} ${deben.facturas === 1 ? 'factura' : 'facturas'}, de cualquier año`} />
                <Dato etiqueta="La más antigua" valor={`${deben.mas_antigua_dias} días`} tono={(deben.mas_antigua_dias ?? 0) > 90 ? 'neg' : undefined} nota="desde la fecha de la factura" />
                <Dato etiqueta="Vistas en el banco" valor={sugerencias.size} nota="ingresos que cuadran con una factura" />
              </div>
              <p className="mt-3 text-xs text-muted">
                Un ingreso «cuadra» si entra en tus cuentas desde la fecha de la factura por su total a cobrar (±1 €); un mismo ingreso no vale para dos facturas.
                Marcarlas pone como fecha de cobro la del ingreso. Si no ves aquí alguna factura, cambia el año.
              </p>
            </Tarjeta>
          )}

          {d.por_anio.length > 0 && (
            <Tarjeta titulo="Facturado y ganado neto por año">
              <div className="h-60">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={d.por_anio.map((a) => ({ ...a, etiqueta: a.previsto ? `${a.anio} (previsto)` : String(a.anio) }))}
                    margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="var(--line)" />
                    <XAxis dataKey="etiqueta" {...eje} />
                    <YAxis tickFormatter={eurK} {...eje} width={68} />
                    <Tooltip {...estiloTooltip} cursor={cursorBarra} formatter={(v, n) => [eur(Number(v)), n === 'facturado' ? 'Facturado (sin IVA)' : 'Neto tras gastos e IRPF']} />
                    <Legend formatter={(v) => (v === 'facturado' ? 'Facturado (sin IVA)' : 'Neto tras gastos e IRPF')} wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="facturado" fill="var(--chart-2)" radius={[4, 4, 0, 0]} maxBarSize={36} />
                    <Bar dataKey="neto" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={36} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-xs text-muted">Neto = facturado menos gastos deducibles y el IRPF de la actividad a tu tipo medio de la renta (el real del año si ya la subiste).
                El IVA no cuenta: lo cobras y se lo das a Hacienda. El año en curso usa la previsión del año completo (o lo ya facturado, si es más).</p>
            </Tarjeta>
          )}
          <ResumenAnual anio={anio} />

          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            <Tarjeta titulo="Por cliente">
              {d.por_cliente.length ? (
                <ul className="space-y-3">
                  {d.por_cliente.map((c) => (
                    <li key={c.cliente}>
                      <div className="mb-1 flex justify-between gap-2 text-sm"><span className="truncate">{c.cliente}</span><Importe valor={c.base} /></div>
                      <div className="h-1.5 rounded-full bg-panel-2"><div className="h-full rounded-full bg-accent" style={{ width: `${(c.base / maxCliente) * 100}%` }} /></div>
                    </li>
                  ))}
                </ul>
              ) : <Vacio>Sin facturas este año.</Vacio>}
            </Tarjeta>

            <Tarjeta className="xl:col-span-2" titulo="Facturas emitidas" accion={d.facturas.length > 0 && (
              <Segmentos pequeno etiqueta="Qué facturas ver" opciones={FILTROS} valor={filtro} onCambiar={setFiltro} />
            )}>
              {d.avisos_numeracion.length > 0 && (
                <ul className="mb-3 space-y-1 text-xs text-warn" aria-label="Avisos de numeración">
                  {d.avisos_numeracion.map((a) => <li key={a}>{a}</li>)}
                </ul>
              )}
              <TablaResponsive filas={facturas} columnas={columnasFacturas} clave={(f) => f.id}
                acciones={(f) => <><VerDocumento f={f} /><Boton variante="fantasma" className="px-2 py-1" onClick={() => setEditando(f)} aria-label={`Editar la factura ${f.numero}`}><Pencil size={14} /></Boton><BorrarEnDosPasos etiqueta={`la factura ${f.numero}`} disabled={borrar.isPending} onBorrar={() => borrar.mutate({ tipo: 'facturas', id: f.id })} /></>}
                vacio={d.facturas.length ? `No hay facturas ${filtro} en ${anio}.` : 'Registra tus facturas para ver el IVA y el IRPF de cada trimestre.'} />
            </Tarjeta>
          </div>

          <Tarjeta className="mt-4" titulo="Gastos de la actividad">
            <CuotaTgss anio={anio} />
            <TablaResponsive filas={d.gastos} columnas={COLUMNAS_GASTOS} clave={(g) => g.id}
              acciones={(g) => <><Boton variante="fantasma" className="px-2 py-1" onClick={() => setEditandoGasto(g)} aria-label={`Editar el gasto ${g.proveedor || g.concepto}`}><Pencil size={14} /></Boton><BorrarEnDosPasos etiqueta={`el gasto ${g.proveedor || g.concepto}`} disabled={borrar.isPending} onBorrar={() => borrar.mutate({ tipo: 'gastos', id: g.id })} /></>}
              vacio="Apunta la cuota de autónomos, la gestoría o el software: bajan tu IRPF y, si llevan IVA, también el 303." />
          </Tarjeta>
        </>
      )}

      <Dialogo abierto={formFactura} onCerrar={cerrarFactura} titulo="Registrar factura">
        <FormFactura clientes={d?.clientes ?? []} onHecho={cerrarFactura} />
      </Dialogo>
      <Dialogo abierto={!!editando} onCerrar={() => setEditando(null)} titulo={`Editar factura ${editando?.numero ?? ''}`}>
        {editando && <FormFactura key={editando.id} f={editando} clientes={d?.clientes ?? []} onHecho={() => setEditando(null)} />}
      </Dialogo>
      <Dialogo abierto={dialogo === 'calendario'} onCerrar={() => setDialogo(null)} titulo="Vacaciones y días que no puedes">
        <CalendarioDias />
      </Dialogo>
      <Dialogo abierto={dialogo === 'datos'} onCerrar={() => setDialogo(null)} titulo="Datos de facturación">
        <DatosFacturacion onHecho={() => setDialogo(null)} />
      </Dialogo>
      <Dialogo abierto={dialogo === 'planificar'} onCerrar={() => setDialogo(null)} titulo="Generar factura por días">
        {dialogo === 'planificar' && <PlanificadorFactura onHecho={() => setDialogo(null)} />}
      </Dialogo>
      <Dialogo abierto={dialogo === 'gasto'} onCerrar={() => setDialogo(null)} titulo="Registrar gasto">
        <FormGasto onHecho={() => setDialogo(null)} />
      </Dialogo>
      <Dialogo abierto={!!editandoGasto} onCerrar={() => setEditandoGasto(null)} titulo={`Editar gasto · ${editandoGasto?.proveedor || editandoGasto?.concepto || ''}`}>
        {editandoGasto && <FormGasto key={editandoGasto.id} g={editandoGasto} onHecho={() => setEditandoGasto(null)} />}
      </Dialogo>
    </>
  )
}
