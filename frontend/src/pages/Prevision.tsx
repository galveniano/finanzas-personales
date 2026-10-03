import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Settings2 } from 'lucide-react'
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../lib/api'
import { eur, eurK, fecha } from '../lib/format'
import type { GastosRecientes, Prevision as Datos, RentaPrevista, SupuestosPrevision } from '../lib/tipos'
import { Boton, Cabecera, Campo, Cargando, Dato, Dialogo, Etiqueta, ErrorCarga, Formulario, Importe, Selector, Tabla, Tarjeta, Vacio, num, useAccion } from '../components/ui'

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
const nombreMes = (clave: string) => fecha(`${clave}-01`, { month: 'short', year: '2-digit' })

function FormSupuestos({ s, habitualBanco, cerrar }: { s: SupuestosPrevision; habitualBanco: number | null; cerrar: () => void }) {
  const [clientes, setClientes] = useState(Math.max(1, s.clientes.length))
  const guardar = useAccion((d: Record<string, string>) => api.put('/prevision/supuestos', {
    nomina: num(d.bruto_anual) ? {
      empresa: d.empresa, bruto_anual: num(d.bruto_anual), variable_pct: num(d.variable_pct) ?? 0,
      mes_variable: Number(d.mes_variable), pagas: Number(d.pagas),
    } : null,
    clientes: Array.from({ length: clientes }, (_, i) => ({
      nombre: d[`c${i}_nombre`], tarifa_hora: num(d[`c${i}_tarifa`]), horas_dia: num(d[`c${i}_horas`]) ?? 8,
      dias_mes: num(d[`c${i}_dias`]) ?? null, iva: num(d[`c${i}_iva`]) ?? 0, retencion: num(d[`c${i}_ret`]) ?? 0,
    })).filter((c) => c.nombre && c.tarifa_hora),
    gastos_autonomo_mes: num(d.gastos_autonomo_mes) ?? 0,
    gasto_habitual_mes: num(d.gasto_habitual_mes) ?? null,
    meses_sin_facturar: MESES.map((_, i) => i + 1).filter((m) => d[`sin_${m}`]),
  }).then(cerrar), 'Previsión actualizada')
  const n = s.nomina
  return (
    <Formulario onEnviar={(d) => guardar.mutateAsync(d)}>
      <h3 className="text-sm font-semibold sm:col-span-2">Nómina</h3>
      <Campo etiqueta="Empresa" name="empresa" defaultValue={n?.empresa ?? ''} />
      <Campo etiqueta="Bruto anual fijo (€)" name="bruto_anual" inputMode="decimal" defaultValue={n?.bruto_anual ?? ''} />
      <Campo etiqueta="Variable (% del fijo)" name="variable_pct" inputMode="decimal" defaultValue={n?.variable_pct ?? 0} />
      <Selector etiqueta="Mes en que cobras el variable" name="mes_variable" defaultValue={n?.mes_variable ?? 3}>
        {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
      </Selector>
      <Selector etiqueta="Pagas" name="pagas" defaultValue={n?.pagas ?? 14}>
        <option value={14}>14 (extras en junio y diciembre)</option><option value={12}>12 (prorrateadas)</option>
      </Selector>

      <h3 className="mt-2 text-sm font-semibold sm:col-span-2">Clientes como autónomo</h3>
      {Array.from({ length: clientes }, (_, i) => {
        const c = s.clientes[i]
        return (
          <div key={i} className="grid gap-3 rounded-xl border border-line p-3 sm:col-span-2 sm:grid-cols-3">
            <Campo etiqueta="Cliente" name={`c${i}_nombre`} defaultValue={c?.nombre ?? ''} className="sm:col-span-3" />
            <Campo etiqueta="€ por hora" name={`c${i}_tarifa`} inputMode="decimal" defaultValue={c?.tarifa_hora ?? ''} />
            <Campo etiqueta="Horas al día" name={`c${i}_horas`} inputMode="decimal" defaultValue={c?.horas_dia ?? 8} />
            <Campo etiqueta="Días al mes" name={`c${i}_dias`} inputMode="decimal" defaultValue={c?.dias_mes ?? ''} placeholder="Como el último mes" ayuda="Vacío: los del último mes facturado." />
            <Campo etiqueta="IVA %" name={`c${i}_iva`} inputMode="decimal" defaultValue={c?.iva ?? 21} ayuda="0 si es de fuera de España." />
            <Campo etiqueta="Retención %" name={`c${i}_ret`} inputMode="decimal" defaultValue={c?.retencion ?? 15} ayuda="15 %, o 7 % los primeros años." />
          </div>
        )
      })}
      <div className="sm:col-span-2">
        <Boton type="button" variante="secundario" onClick={() => setClientes(clientes + 1)}><Plus size={14} />Otro cliente</Boton>
      </div>
      <fieldset className="sm:col-span-2">
        <legend className="mb-2 text-xs font-medium text-muted">Meses que no facturas (vacaciones)</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {MESES.map((m, i) => (
            <label key={m} className="flex items-center gap-1.5 text-sm capitalize">
              <input type="checkbox" name={`sin_${i + 1}`} defaultChecked={s.meses_sin_facturar.includes(i + 1)} />{m.slice(0, 3)}
            </label>
          ))}
        </div>
      </fieldset>

      <h3 className="mt-2 text-sm font-semibold sm:col-span-2">Gastos</h3>
      <Campo etiqueta="Gastos deducibles como autónomo (€/mes)" name="gastos_autonomo_mes" inputMode="decimal"
        defaultValue={s.gastos_autonomo_mes} ayuda="Cuota de autónomos, gestoría, software… Solo para calcular el 130 y la renta. Con 0 se usa la cuota de autónomos que aparezca en el banco." />
      <Campo etiqueta="Gasto habitual (€/mes)" name="gasto_habitual_mes" inputMode="decimal" defaultValue={s.gasto_habitual_mes ?? ''}
        placeholder={habitualBanco ? `${Math.round(habitualBanco)} según el banco` : ''}
        ayuda="Lo que sale de tus cuentas cada mes. Vacío: la media de los últimos 3 meses del banco." />
    </Formulario>
  )
}

function ComoGastas({ g }: { g: GastosRecientes }) {
  const max = Math.max(1, ...g.categorias.map((c) => c.mes))
  return (
    <div className="mb-4 grid gap-4 lg:grid-cols-3">
      <Tarjeta className="lg:col-span-2" titulo={`Cómo gastas · media de los últimos ${g.meses} meses`}>
        <div className="mb-5 grid gap-6 sm:grid-cols-3">
          <Dato etiqueta="Entra al mes" valor={eur(g.ingresos_mes)} />
          <Dato etiqueta="Sale al mes" valor={eur(g.gastos_mes)} />
          <Dato etiqueta="Ahorras al mes" valor={eur(g.ahorro_mes)} tono={g.ahorro_mes >= 0 ? 'pos' : 'neg'}
            nota={g.tasa_ahorro !== null ? `${String(g.tasa_ahorro).replace('.', ',')} % de lo que entra` : undefined} />
        </div>
        {g.categorias.length ? (
          <ul className="space-y-2.5">
            {g.categorias.map((c) => (
              <li key={c.categoria}>
                <div className="mb-1 flex justify-between gap-2 text-sm"><span className="truncate">{c.categoria}</span><Importe valor={c.mes} /></div>
                <div className="h-1.5 rounded-full bg-panel-2"><div className="h-full rounded-full bg-accent" style={{ width: `${(c.mes / max) * 100}%` }} /></div>
              </li>
            ))}
          </ul>
        ) : <Vacio>Sincroniza el banco para ver en qué se va el dinero.</Vacio>}
        <p className="mt-3 text-xs text-muted">Sin traspasos entre tus cuentas ni aportaciones a Indexa; solo tu parte de las cuentas compartidas.</p>
      </Tarjeta>
      <Tarjeta titulo="Suscripciones y recibos fijos" accion={<span className="cifra text-sm font-semibold">{eur(g.suscripciones_mes)}/mes</span>}>
        {g.suscripciones.length ? (
          <ul className="divide-y divide-line">
            {g.suscripciones.map((x) => (
              <li key={x.concepto} className="flex items-center justify-between gap-3 py-2 text-sm">
                <span className="min-w-0"><span className="block truncate">{x.concepto}</span>
                  <span className="text-xs text-muted">{eur(x.anual)} al año · último {fecha(x.ultimo_cargo, { day: 'numeric', month: 'short' })}</span></span>
                <Importe valor={x.mes} />
              </li>
            ))}
          </ul>
        ) : <Vacio>Aparecerán los cargos que se repiten cada mes (Netflix, gimnasio, seguros…).</Vacio>}
      </Tarjeta>
    </div>
  )
}

function RentaPresentada({ r }: { r: NonNullable<Datos['renta_presentada']> }) {
  const c = r.casillas
  const fila = (etiqueta: string, valor: number | undefined, fuerte = false) => valor === undefined ? null : (
    <div className={`flex justify-between ${fuerte ? 'border-t border-line pt-1.5 font-medium' : ''}`}><dt className={fuerte ? '' : 'text-muted'}>{etiqueta}</dt><dd><Importe valor={valor} /></dd></div>)
  return (
    <Tarjeta titulo={`Renta ${r.anio} (presentada)`} accion={<Etiqueta tono="bien">Presentada</Etiqueta>}>
      <dl className="space-y-1.5 text-sm">
        {fila('Trabajo (nómina)', c.rendimiento_trabajo)}
        {fila('Actividad (autónomo)', c.rendimiento_actividad)}
        {fila('Alquiler', c.rendimiento_alquiler)}
        {fila(`Cuota${c.base_general ? ` (${String(Math.round((c.cuota / c.base_general) * 1000) / 10).replace('.', ',')} % de media)` : ''}`, c.cuota, true)}
        {fila('Retenido en la nómina', c.retenciones_trabajo !== undefined ? -c.retenciones_trabajo : undefined)}
        {fila('Pagos del 130', c.pagos_130 !== undefined ? -c.pagos_130 : undefined)}
        <div className="flex justify-between border-t border-line pt-1.5 font-semibold"><dt>{r.resultado >= 0 ? 'Pagaste' : 'Te devolvieron'}</dt><dd><Importe valor={Math.abs(r.resultado)} /></dd></div>
      </dl>
      {c.gastos_actividad !== undefined && <p className="mt-3 text-xs text-muted">
        Gastos de la actividad: {eur(c.gastos_actividad)} al año{c.ss_autonomo !== undefined && `, de ellos ${eur(c.ss_autonomo)} de cuota de autónomos`}.</p>}
    </Tarjeta>
  )
}

const GASTOS_FUENTE: Record<string, string> = {
  'Nómina': 'Seguridad Social', 'Autónomo': 'Cuota y gastos', 'Alquiler': 'Comunidad, seguro, IBI e intereses',
}

function LoQueGanas({ anios, cuota, origenCuota }: { anios: RentaPrevista[]; cuota: number; origenCuota: string }) {
  const [anio, setAnio] = useState(anios[0]?.anio)
  const r = anios.find((x) => x.anio === anio) ?? anios[0]
  if (!r) return null
  const mes = (v: number) => v / 12
  return (
    <Tarjeta className="mt-4" titulo={`Lo que ganas al mes en ${r.anio}`} accion={anios.length > 1 && (
      <div className="flex gap-1">{anios.map((x) => (
        <Boton key={x.anio} variante={x.anio === r.anio ? 'primario' : 'secundario'} className="px-2.5 py-1 text-xs" onClick={() => setAnio(x.anio)}>{x.anio}</Boton>
      ))}</div>)}>
      <Tabla>
        <thead><tr><th>Fuente</th><th className="num">Bruto</th><th className="num">Gastos</th><th className="num">IRPF</th><th className="num">Neto</th></tr></thead>
        <tbody>
          {r.ingresos.fuentes.map((f) => (
            <tr key={f.fuente}>
              <td>{f.fuente}<div className="text-xs text-muted">{GASTOS_FUENTE[f.fuente]}</div></td>
              <td className="num"><Importe valor={f.bruto_mes} /></td>
              <td className="num"><Importe valor={-mes(f.gastos_anual)} /></td>
              <td className="num"><Importe valor={-mes(f.irpf_anual)} /></td>
              <td className="num font-medium"><Importe valor={f.neto_mes} /></td>
            </tr>
          ))}
          <tr className="font-semibold">
            <td>Total al mes</td>
            <td className="num"><Importe valor={r.ingresos.total.bruto_mes} /></td>
            <td className="num"><Importe valor={-mes(r.ingresos.total.gastos_anual)} /></td>
            <td className="num"><Importe valor={-mes(r.ingresos.total.irpf_anual)} /></td>
            <td className="num"><Importe valor={r.ingresos.total.neto_mes} /></td>
          </tr>
          <tr className="text-muted">
            <td>Total al año</td>
            <td className="num"><Importe valor={r.ingresos.total.bruto_anual} /></td>
            <td className="num"><Importe valor={-r.ingresos.total.gastos_anual} /></td>
            <td className="num"><Importe valor={-r.ingresos.total.irpf_anual} /></td>
            <td className="num"><Importe valor={r.ingresos.total.neto_anual} /></td>
          </tr>
        </tbody>
      </Tabla>
      <p className="mt-3 text-xs text-muted">
        Media del año (las pagas extra y el variable se reparten en 12). El IRPF es el de la renta completa, no solo lo retenido:
        la nómina paga el de sus tramos, el autónomo lo que añade encima y el alquiler el resto.
        Gastos de autónomo: {eur(cuota)} al mes ({origenCuota}).
      </p>
    </Tarjeta>
  )
}

export default function Prevision() {
  const [editar, setEditar] = useState(false)
  const { data: d, isLoading, error } = useQuery({ queryKey: ['prevision'], queryFn: () => api.get<Datos>('/prevision') })
  const { data: g } = useQuery({ queryKey: ['gastos-recientes'], queryFn: () => api.get<GastosRecientes>('/gastos/recientes') })
  if (isLoading) return <Cargando />
  if (error) return <ErrorCarga error={error} />
  if (!d) return null
  const sinDatos = !d.supuestos.nomina && !d.supuestos.clientes.length
  const ultimo = d.meses[d.meses.length - 1]
  const impuestos = d.meses.reduce((s, m) => s + m.total_impuestos, 0)

  return (
    <>
      <Cabecera titulo="Previsión" subtitulo="Lo que gastas hoy y los próximos 12 meses con tu sueldo, tus clientes y los impuestos">
        <Boton onClick={() => setEditar(true)}><Settings2 size={16} />Supuestos</Boton>
      </Cabecera>
      {g && <ComoGastas g={g} />}

      {sinDatos ? (
        <Tarjeta><Vacio>Pon tu sueldo y lo que facturas a cada cliente en «Supuestos» y la app calcula los meses que vienen.</Vacio></Tarjeta>
      ) : (
        <>
          <Tarjeta>
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              <Dato etiqueta="Liquidez hoy" valor={eur(d.liquidez_hoy)} />
              <Dato etiqueta={`Liquidez en ${fecha(`${ultimo.mes}-01`, { month: 'long', year: 'numeric' })}`} valor={eur(ultimo.liquidez)}
                tono={ultimo.liquidez >= 0 ? undefined : 'neg'} />
              <Dato etiqueta="Ahorro medio al mes" valor={eur((ultimo.liquidez - d.liquidez_hoy) / d.meses.length)} />
              <Dato etiqueta="Impuestos a pagar" valor={eur(impuestos)} nota="IVA, 130 y renta en estos 12 meses" />
            </div>
            <p className="mt-4 text-sm text-muted">
              {d.clientes.map((c) => `${c.nombre}: ${String(c.dias_mes).replace('.', ',')} días al mes (${c.origen_dias}) a ${eur(c.tarifa_hora * c.horas_dia)} el día`).join(' · ')}
            </p>
            <div className="mt-6 h-64">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={d.meses} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="var(--line)" />
                  <XAxis dataKey="mes" tickFormatter={nombreMes} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis yAxisId="l" tickFormatter={eurK} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} width={68} />
                  <YAxis yAxisId="n" orientation="right" hide />
                  <Tooltip contentStyle={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, fontSize: 12 }}
                    cursor={{ fill: 'var(--panel-2)' }} labelFormatter={(v) => nombreMes(String(v))}
                    formatter={(v, n) => [eur(Number(v)), n === 'neto' ? 'Ahorro del mes' : 'Liquidez']} />
                  <Bar yAxisId="n" dataKey="neto" fill="var(--chart-2)" radius={[4, 4, 0, 0]} maxBarSize={24} />
                  <Line yAxisId="l" dataKey="liquidez" stroke="var(--chart-1)" strokeWidth={2} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </Tarjeta>

          <LoQueGanas anios={d.anios} cuota={d.gastos_autonomo_mes} origenCuota={d.origen_gastos_autonomo} />

          <Tarjeta className="mt-4" titulo="Mes a mes">
            <Tabla>
              <thead><tr><th>Mes</th><th className="num">Nómina</th><th className="num">Clientes</th><th className="num">Alquiler</th>
                <th className="num">Gastos</th><th className="num">Pagos</th><th>Impuestos</th><th className="num">Ahorro</th><th className="num">Liquidez</th></tr></thead>
              <tbody>
                {d.meses.map((m) => (
                  <tr key={m.mes}>
                    <td className="whitespace-nowrap capitalize">{nombreMes(m.mes)}</td>
                    <td className="num"><Importe valor={m.nomina} /></td>
                    <td className="num" title={`Facturado ${eur(m.facturado)} + IVA ${eur(m.iva)} − retención ${eur(m.retenciones)}`}><Importe valor={m.cobros} /></td>
                    <td className="num"><Importe valor={m.alquiler} /></td>
                    <td className="num"><Importe valor={-m.gastos} /></td>
                    <td className="num">{m.pagos_previstos ? <Importe valor={-m.pagos_previstos} /> : ''}</td>
                    <td className="text-xs">{m.impuestos.map((i) => (
                      <div key={i.concepto} className="flex justify-between gap-2 whitespace-nowrap">
                        <span className="text-muted">{i.concepto}{i.presentado && <> <Etiqueta tono="bien">Presentado</Etiqueta></>}</span>
                        <Importe valor={-i.importe} />
                      </div>))}</td>
                    <td className="num font-medium"><Importe valor={m.neto} /></td>
                    <td className="num"><Importe valor={m.liquidez} /></td>
                  </tr>
                ))}
              </tbody>
            </Tabla>
            <p className="mt-3 text-xs text-muted">Clientes es lo que cobras: base más IVA menos retención. El IVA y el 130 de cada trimestre se pagan el mes siguiente; la renta, en junio.
              «Pagos» son los de Planificación (la casa nueva, llamadas de capital…).</p>
          </Tarjeta>

          <div className={`mt-4 grid gap-4 md:grid-cols-2 ${d.renta_presentada ? 'xl:grid-cols-3' : ''}`}>
            {d.renta_presentada && <RentaPresentada r={d.renta_presentada} />}
            {d.anios.map((r) => (
              <Tarjeta key={r.anio} titulo={`Renta ${r.anio} (estimada)`} accion={<Etiqueta tono={r.resultado > 0 ? 'aviso' : 'bien'}>{r.resultado > 0 ? 'A pagar' : 'A devolver'}</Etiqueta>}>
                <dl className="space-y-1.5 text-sm">
                  <div className="flex justify-between"><dt className="text-muted">Trabajo (nómina)</dt><dd><Importe valor={r.rendimiento_trabajo} /></dd></div>
                  <div className="flex justify-between"><dt className="text-muted">Actividad (autónomo)</dt><dd><Importe valor={r.rendimiento_actividad} /></dd></div>
                  <div className="flex justify-between"><dt className="text-muted">Alquiler</dt><dd><Importe valor={r.rendimiento_alquiler} /></dd></div>
                  <div className="flex justify-between border-t border-line pt-1.5 font-medium"><dt>Cuota ({String(r.tipo_medio).replace('.', ',')} % de media)</dt><dd><Importe valor={r.cuota} /></dd></div>
                  <div className="flex justify-between"><dt className="text-muted">Retenido en la nómina</dt><dd><Importe valor={-r.retenciones_nomina} /></dd></div>
                  <div className="flex justify-between"><dt className="text-muted">Retenido en facturas</dt><dd><Importe valor={-r.retenciones_facturas} /></dd></div>
                  <div className="flex justify-between"><dt className="text-muted">Pagos del 130</dt><dd><Importe valor={-r.pagos_130} /></dd></div>
                  <div className="flex justify-between border-t border-line pt-1.5 font-semibold"><dt>Resultado en junio de {r.anio + 1}</dt><dd><Importe valor={r.resultado} /></dd></div>
                </dl>
              </Tarjeta>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted">Estimación con la escala general del IRPF y el año completo según tus supuestos; el borrador real puede variar.</p>
        </>
      )}

      <Dialogo abierto={editar} onCerrar={() => setEditar(false)} titulo="Supuestos de la previsión">
        {editar && <FormSupuestos s={d.supuestos} habitualBanco={d.gasto_habitual_banco} cerrar={() => setEditar(false)} />}
      </Dialogo>
    </>
  )
}
