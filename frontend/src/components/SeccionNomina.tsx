import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, Pencil, Plus, Upload } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../lib/api'
import { MESES, capitalizar, eur, eurK, fecha, hoyISO, pct } from '../lib/format'
import { cursorBarra, eje, estiloTooltip } from '../lib/graficas'
import type { MesNomina, Nomina, Nominas as Datos, Prevision } from '../lib/tipos'
import CalculadoraSueldo from './CalculadoraSueldo'
import { num, useAccion, useAvisos } from '../lib/utilidades'
import { useSubida } from '../lib/subida'
import type { Columna } from './ui'
import { BorrarEnDosPasos, Boton, Campo, Cargando, Casilla, Dato, Dialogo, Etiqueta, ErrorCarga, Formulario, Importe, SelectorAnio, Tabla, TablaResponsive, Tarjeta, Vacio } from './ui'

const mes = (n: Nomina) => fecha(n.fecha, { month: 'long', year: 'numeric' })
const Mes = (n: Nomina) => capitalizar(mes(n))
const nombreMes = (ym: string) => MESES[Number(ym.slice(5)) - 1]

type Subida = { resultados: { fichero: string; ok: boolean; mensaje: string; avisos: string[] }[] }

const COLUMNAS: Columna<Nomina>[] = [
  { cabecera: 'Mes', celda: (n) => <>{Mes(n)}{n.paga_extra && <> <Etiqueta tono="acento">Extra</Etiqueta></>}</>, claseTd: 'whitespace-nowrap', papel: 'titulo' },
  { cabecera: 'Empresa', celda: (n) => n.empresa, claseTd: 'text-muted', papel: 'subtitulo' },
  { cabecera: 'Bruto', celda: (n) => <><Importe valor={n.bruto} />{n.especie != null && n.especie > 0 && <div className="text-xs text-muted">{eur(n.especie)} en especie</div>}</>, num: true },
  { cabecera: 'IRPF', celda: (n) => <><Importe valor={n.retencion_irpf} />{(n.tipo_irpf != null || n.base_irpf != null) && (
      <div className="text-xs text-muted">{[n.tipo_irpf != null && pct(n.tipo_irpf), n.base_irpf != null && `base ${eur(n.base_irpf)}`].filter(Boolean).join(' · ')}</div>)}</>, num: true },
  { cabecera: 'SS', celda: (n) => <Importe valor={n.seguridad_social} />, num: true },
  { cabecera: 'Neto', celda: (n) => <Importe valor={n.neto} />, num: true, claseTd: 'font-medium', fuerte: true },
]

/** Qué decir de un mes: cuadra, falta la nómina, no cuadra o aún no hay cobro visto. */
function estadoMes(m: MesNomina, hayBanco: boolean): { texto: string; tono: 'bien' | 'aviso' | 'mal' | 'neutro' } {
  if (m.cuadra) return { texto: 'Cuadra', tono: 'bien' }
  if (m.banco_importe != null && m.nomina_neto == null) return { texto: `Falta la nómina de ${nombreMes(m.mes)}`, tono: 'aviso' }
  if (m.banco_importe != null && m.nomina_neto != null) return { texto: 'No cuadra', tono: 'mal' }
  if (m.nomina_neto != null) return { texto: hayBanco ? 'Sin cobro visto' : 'Registrada', tono: 'neutro' }
  return { texto: 'Nada', tono: 'neutro' }
}

export default function SeccionNomina() {
  const avisar = useAvisos()
  const [anio, setAnio] = useState(() => new Date().getFullYear())
  // null: cerrado; 'nueva': registrar a mano; una nómina: corregirla
  const [editando, setEditando] = useState<Nomina | 'nueva' | null>(null)
  const { data: d, isLoading, error } = useQuery({ queryKey: ['nominas', anio], queryFn: () => api.get<Datos>(`/nominas?anio=${anio}`) })
  const { data: prev } = useQuery({ queryKey: ['prevision'], queryFn: () => api.get<Prevision>('/prevision') })
  const brutoSupuesto = prev?.supuestos.nomina ? prev.supuestos.nomina.bruto_anual * (1 + (prev.supuestos.nomina.variable_pct ?? 0) / 100) : null
  const guardar = useAccion((v: Record<string, string>) => {
    const actual = editando && editando !== 'nueva' ? editando : null
    const cuerpo = {
      empresa: v.empresa || 'Empresa', fecha: v.fecha, bruto: num(v.bruto), retencion_irpf: num(v.retencion_irpf),
      seguridad_social: num(v.seguridad_social), neto: num(v.neto), tipo_irpf: num(v.tipo_irpf) ?? null, base_irpf: num(v.base_irpf) ?? null,
      especie: num(v.especie) ?? null, otras_deducciones: num(v.otras_deducciones) ?? null, paga_extra: v.paga_extra === 'on',
    }
    return (actual ? api.put(`/nominas/${actual.id}`, cuerpo) : api.post('/nominas', cuerpo)).then(() => setEditando(null))
  }, 'Nómina guardada')
  const borrar = useAccion((id: number) => api.del(`/nominas/${id}`), 'Nómina borrada')
  const subir = useAccion(async (ficheros: File[]) => {
    const fd = new FormData()
    ficheros.forEach((f) => fd.append('ficheros', f))
    const r = await api.post<Subida>('/nominas/pdf', fd)
    const bien = r.resultados.filter((x) => x.ok)
    if (bien.length) avisar(bien.length === 1 ? bien[0].mensaje : `${bien.length} nóminas leídas`)
    bien.forEach((x) => x.avisos.forEach((a) => avisar(`${x.mensaje}: ${a}`, 'error')))
    r.resultados.filter((x) => !x.ok).forEach((x) => avisar(`${x.fichero}: ${x.mensaje}`, 'error'))
  })
  const { input, elegir, zona, arrastrando } = useSubida({
    accept: 'application/pdf,.pdf', multiple: true, filtro: (f) => /\.pdf$/i.test(f.name) || f.type === 'application/pdf',
    onFicheros: (ficheros) => { if (!subir.isPending) subir.mutate(ficheros) },
  })

  if (isLoading) return <Cargando />
  if (error) return <ErrorCarga error={error} />
  if (!d) return null
  const t = d.totales
  const tipoMedio = t.bruto ? (t.retencion_irpf / t.bruto) * 100 : 0
  const renta = prev?.anios.find((a) => a.anio === d.anio)
  const delAnio = d.nominas.slice().reverse()
  const r = d.retencion_recomendada
  const mesesConAlgo = d.meses.filter((m) => m.nomina_neto != null || m.banco_importe != null)
  const hayBanco = d.meses.some((m) => m.banco_importe != null)

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">Trabajo por cuenta ajena en {d.anio}</p>
        <div className="flex flex-wrap items-center gap-2">
          <SelectorAnio valor={anio} onCambiar={setAnio} />
          <Boton variante="secundario" onClick={() => setEditando('nueva')}><Plus size={16} />A mano</Boton>
          <Boton onClick={elegir} disabled={subir.isPending}><Upload size={16} />{subir.isPending ? 'Leyendo…' : 'Subir nóminas'}</Boton>
        </div>
      </div>
      {input}
      <Tarjeta>
        {d.fuente === 'banco' && d.estimado_banco && (
          <p className="mb-4 text-sm text-muted">Sacado de los ingresos de nómina de tus cuentas: el banco solo da el neto, así que
            bruto, IRPF y Seguridad Social están estimados (unos {eur(d.estimado_banco.bruto_anual)} brutos al año,
            {' '}{pct(d.estimado_banco.tipo_irpf)} de retención). Si registras una nómina, manda la nómina.</p>
        )}
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <Dato etiqueta="Bruto acumulado" valor={eur(t.bruto)} />
          <Dato etiqueta="Retenido IRPF" valor={eur(t.retencion_irpf)} nota={d.tipo_irpf_actual != null ? `${pct(d.tipo_irpf_actual)} en la última nómina` : `${pct(tipoMedio)} de media`} />
          <Dato etiqueta="Seguridad Social" valor={eur(t.seguridad_social)} />
          <Dato etiqueta="Neto cobrado" valor={eur(t.neto)} nota={d.fuente === 'banco' ? 'según el banco' : undefined} />
        </div>
        {r && (
          <p className="mt-4 rounded-xl bg-accent-soft px-4 py-3 text-sm">
            Pide a tu empresa un <strong>{pct(r.tipo_recomendado, 1)}</strong> desde el mes que viene y la renta de junio quedará en ±0.
            <span className="block text-xs text-muted">Ahora te retienen un {pct(r.tipo_actual)} y la previsión dice que la renta de {d.anio} saldría a pagar {eur(r.resultado_previsto)};
              repartido entre el bruto que te queda por cobrar en {r.meses_restantes} {r.meses_restantes === 1 ? 'mes' : 'meses'} sale esa subida. Es una estimación: la renta real depende de todo lo demás.</span>
          </p>
        )}
        {d.tipo_irpf_actual != null && renta && renta.tipo_medio > d.tipo_irpf_actual + 1 && (
          <p className="mt-4 text-sm text-muted">La empresa te retiene un {pct(d.tipo_irpf_actual)}, pero en la renta de {renta.anio} tu tipo
            medio sale un {pct(renta.tipo_medio)} porque la nómina se suma a lo que facturas como autónomo. La diferencia
            es parte de lo que te toca pagar en junio, y la previsión ya la cuenta.</p>
        )}
      </Tarjeta>

      {mesesConAlgo.length > 0 && (
        <Tarjeta className="mt-4" titulo="Mes a mes" accion={<span className="text-xs text-muted">Nómina frente al banco</span>}>
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {d.meses.map((m) => {
              const e = estadoMes(m, hayBanco)
              return (
                <li key={m.mes} className="flex items-center justify-between gap-3 rounded-xl bg-panel-2 px-3 py-2 text-sm">
                  <div className="min-w-0">
                    <div className="font-medium capitalize">{nombreMes(m.mes)}</div>
                    <div className="cifra truncate text-xs text-muted">
                      {m.nomina_neto != null ? `nómina ${eur(m.nomina_neto)}` : 'sin nómina'} · {m.banco_importe != null ? `banco ${eur(m.banco_importe)}${m.banco_fecha ? ` el ${fecha(m.banco_fecha, { day: '2-digit', month: '2-digit' })}` : ''}` : 'sin cobro'}
                    </div>
                  </div>
                  <Etiqueta tono={e.tono}>{e.texto}</Etiqueta>
                </li>
              )
            })}
          </ul>
          <p className="mt-3 text-xs text-muted">Cruza el neto de cada nómina registrada con los ingresos de categoría «Nómina» de tus cuentas (±1 €). Un cobro de los
            primeros días del mes cuenta como el del mes anterior. Si no tienes el banco conectado, solo se ve lo registrado.</p>
        </Tarjeta>
      )}

      {delAnio.length > 1 && (
        <Tarjeta className="mt-4" titulo="Bruto y retención por mes">
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={delAnio} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--line)" />
                <XAxis dataKey="fecha" tickFormatter={(v) => fecha(v, { month: 'short' })} {...eje} />
                <YAxis tickFormatter={eurK} {...eje} width={68} />
                <Tooltip {...estiloTooltip} cursor={cursorBarra} formatter={(v, n) => [eur(Number(v)), n === 'neto' ? 'Neto' : 'IRPF']} labelFormatter={(v) => fecha(String(v), { month: 'long' })} />
                <Bar dataKey="neto" stackId="a" fill="var(--chart-1)" maxBarSize={28} />
                <Bar dataKey="retencion_irpf" stackId="a" fill="var(--chart-3)" radius={[4, 4, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Tarjeta>
      )}

      {d.banco.length > 0 && (
        <Tarjeta className="mt-4" titulo="Cobros de nómina en el banco">
          <Tabla>
            <thead><tr><th>Fecha</th><th>Concepto</th><th>Cuenta</th><th className="num">Importe</th></tr></thead>
            <tbody>
              {d.banco.map((m) => (
                <tr key={m.id}>
                  <td className="cifra whitespace-nowrap text-muted">{fecha(m.fecha)}</td>
                  <td className="max-w-xs truncate">{m.concepto}</td>
                  <td className="text-muted">{m.cuenta}</td>
                  <td className="num font-medium"><Importe valor={m.importe} /></td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        </Tarjeta>
      )}

      <div {...zona}>
      <Tarjeta className={`mt-4 ${arrastrando ? 'ring-2 ring-[var(--accent)]' : ''}`} titulo={`Nóminas registradas en ${d.anio}`}>
        {d.nominas.length ? (
          <TablaResponsive filas={d.nominas} columnas={COLUMNAS} clave={(n) => n.id}
            acciones={(n) => <>
              {n.tiene_pdf && (
                <a href={`/api/nominas/${n.id}/pdf`} target="_blank" rel="noreferrer" aria-label={`Ver la nómina de ${mes(n)}`} title="Ver el PDF"
                  className="inline-flex rounded-lg p-1.5 text-muted hover:bg-panel-2 hover:text-ink"><FileText size={14} /></a>
              )}
              <Boton variante="fantasma" className="px-2 py-1" onClick={() => setEditando(n)} aria-label={`Corregir la nómina de ${mes(n)}`}><Pencil size={14} /></Boton>
              <BorrarEnDosPasos etiqueta={`la nómina de ${mes(n)}`} disabled={borrar.isPending} onBorrar={() => borrar.mutate(n.id)} />
            </>} />
        ) : <Vacio>Sube tus nóminas en PDF (puedes arrastrarlas aquí, varias a la vez) y la app saca el bruto, lo que te retienen de IRPF y la Seguridad Social.{d.banco.length ? ' Mientras tanto se estiman con los cobros del banco.' : ''}</Vacio>}
        {d.nominas.length > 0 && <p className="mt-3 text-xs text-muted">Puedes arrastrar aquí los PDF. Si subes otra vez la nómina de un mes (o ya la habías apuntado a mano), se actualiza en vez de repetirse.</p>}
      </Tarjeta>
      </div>

      <CalculadoraSueldo key={brutoSupuesto ?? d.bruto_12_meses ?? 0} brutoInicial={d.bruto_12_meses || brutoSupuesto} />

      <Dialogo abierto={editando != null} onCerrar={() => setEditando(null)} titulo={editando && editando !== 'nueva' ? `Nómina de ${mes(editando)}` : 'Registrar nómina'}>
        {editando && (() => {
          const x = editando === 'nueva' ? null : editando
          const valor = (v: number | null | undefined) => (v == null ? undefined : String(v).replace('.', ','))
          return (
            <Formulario key={x?.id ?? 'nueva'} onEnviar={(v) => guardar.mutateAsync(v)}>
              <Campo etiqueta="Empresa" name="empresa" placeholder="Empresa" maxLength={80} defaultValue={x?.empresa} />
              <Campo etiqueta="Fecha" name="fecha" type="date" defaultValue={x?.fecha ?? hoyISO()} required />
              <Campo etiqueta="Bruto (€)" name="bruto" inputMode="decimal" defaultValue={valor(x?.bruto)} required />
              <Campo etiqueta="Retribución en especie (€)" name="especie" inputMode="decimal" defaultValue={valor(x?.especie)} placeholder="Opcional" ayuda="Seguro médico, coche… incluido en el bruto." />
              <Campo etiqueta="Retención IRPF (€)" name="retencion_irpf" inputMode="decimal" defaultValue={valor(x?.retencion_irpf)} required />
              <Campo etiqueta="Tipo de IRPF (%)" name="tipo_irpf" inputMode="decimal" defaultValue={valor(x?.tipo_irpf)} placeholder="Opcional" />
              <Campo etiqueta="Base sujeta a IRPF (€)" name="base_irpf" inputMode="decimal" defaultValue={valor(x?.base_irpf)} placeholder="Opcional" />
              <Campo etiqueta="Seguridad Social (€)" name="seguridad_social" inputMode="decimal" defaultValue={valor(x?.seguridad_social)} required />
              <Campo etiqueta="Otras deducciones (€)" name="otras_deducciones" inputMode="decimal" defaultValue={valor(x?.otras_deducciones)} placeholder="Anticipos, cuota sindical…" />
              <Campo etiqueta="Neto (€)" name="neto" inputMode="decimal" defaultValue={valor(x?.neto)} required />
              <Casilla etiqueta="Es una paga extra suelta" name="paga_extra" defaultChecked={x?.paga_extra} className="sm:col-span-2" />
            </Formulario>
          )
        })()}
      </Dialogo>
    </>
  )
}
