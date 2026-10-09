import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, Plus } from 'lucide-react'
import { api } from '../lib/api'
import { eur, fecha, hoyISO, pct } from '../lib/format'
import type { InversionPrivada, Inversiones } from '../lib/tipos'
import { useBorrarPago, useMarcarPago } from '../lib/pagos'
import { num, useAccion } from '../lib/utilidades'
import { Area, Barra, BorrarEnDosPasos, Boton, Campo, Casilla, Dato, Dialogo, Etiqueta, ErrorCarga, Formulario, Importe, Tarjeta, Vacio } from './ui'

type Fila = { fecha: string; importe: string; pagado: boolean }
const filaVacia = (): Fila => ({ fecha: '', importe: '', pagado: false })

/** Alta de un fondo: datos del resumen de la plataforma y calendario de llamadas de capital. */
function Nueva({ onCerrar }: { onCerrar: () => void }) {
  const [filas, setFilas] = useState<Fila[]>([filaVacia(), filaVacia()])
  const crear = useAccion((v: Record<string, string>) => api.post('/inversiones', {
    nombre: v.nombre, gestora: v.gestora, compromiso: num(v.compromiso) ?? 0, fecha_compromiso: v.fecha_compromiso || null,
    nav: num(v.nav) ?? 0, distribuido: num(v.distribuido) ?? 0, notas: v.notas ?? '',
    llamadas: filas.filter((f) => f.fecha && num(f.importe)).map((f) => ({ fecha: f.fecha, importe: num(f.importe), pagado: f.pagado })),
  }).then(onCerrar), 'Inversión creada')
  const cambiar = (i: number, cambio: Partial<Fila>) => setFilas(filas.map((f, j) => (j === i ? { ...f, ...cambio } : f)))

  return (
    <Formulario onEnviar={(v) => crear.mutateAsync(v)}>
      <Campo etiqueta="Fondo" name="nombre" required placeholder="Nombre del fondo" />
      <Campo etiqueta="Plataforma o gestora" name="gestora" placeholder="Concrescenta" />
      <Campo etiqueta="Capital comprometido (€)" name="compromiso" inputMode="decimal" required />
      <Campo etiqueta="Fecha del compromiso" name="fecha_compromiso" type="date" />
      <Campo etiqueta="NAV, valor actual (€)" name="nav" inputMode="decimal" ayuda="El que te enseña la plataforma" />
      <Campo etiqueta="Capital distribuido (€)" name="distribuido" inputMode="decimal" defaultValue="0" />
      <Area etiqueta="Notas" name="notas" className="sm:col-span-2" rows={2} placeholder="Estrategia, plazo, condiciones…" />
      <div className="sm:col-span-2">
        <div className="mb-2 text-xs font-medium text-muted">Llamadas de capital (las pagadas cuentan como desembolsado)</div>
        <div className="space-y-2">
          {filas.map((f, i) => (
            <div key={i} className="grid grid-cols-[1fr_1fr_auto] items-center gap-2">
              <Campo type="date" value={f.fecha} onChange={(e) => cambiar(i, { fecha: e.target.value })} aria-label="Fecha" className="min-w-0" />
              <Campo inputMode="decimal" value={f.importe} onChange={(e) => cambiar(i, { importe: e.target.value })} placeholder="Importe €" aria-label="Importe" className="min-w-0" />
              <Casilla etiqueta="Pagada" className="text-xs text-muted" checked={f.pagado} onChange={(e) => cambiar(i, { pagado: e.target.checked })} />
            </div>
          ))}
        </div>
        <Boton type="button" variante="fantasma" className="mt-2 px-2 py-1 text-xs" onClick={() => setFilas([...filas, filaVacia()])}>
          <Plus size={14} />Otra llamada
        </Boton>
      </div>
    </Formulario>
  )
}

/** Solo se manda lo que cambia: así el NAV conserva su fecha si solo tocas lo distribuido o las notas. */
function Actualizar({ inv, onCerrar }: { inv: InversionPrivada; onCerrar: () => void }) {
  const guardar = useAccion((v: Record<string, string>) => {
    const cambios: Record<string, unknown> = {}
    const texto = (campo: 'nombre' | 'gestora' | 'notas') => { if ((v[campo] ?? '') !== inv[campo]) cambios[campo] = v[campo] ?? '' }
    const numero = (campo: 'nav' | 'distribuido' | 'compromiso') => { const n = num(v[campo]); if (n != null && n !== inv[campo]) cambios[campo] = n }
    texto('nombre'); texto('gestora'); texto('notas')
    numero('nav'); numero('distribuido'); numero('compromiso')
    if ((v.fecha_compromiso || null) !== inv.fecha_compromiso && v.fecha_compromiso) cambios.fecha_compromiso = v.fecha_compromiso
    if ((v.nav_fecha || null) !== inv.nav_fecha && v.nav_fecha) cambios.nav_fecha = v.nav_fecha
    return api.patch(`/inversiones/${inv.id}`, cambios).then(onCerrar)
  }, 'Inversión actualizada')
  const llamada = useAccion((v: Record<string, string>) => api.post(`/inversiones/${inv.id}/llamadas`, {
    fecha: v.fecha, importe: num(v.importe), pagado: v.pagado === 'on',
  }).then(onCerrar), 'Llamada añadida')
  return (
    <div className="space-y-6">
      <Formulario onEnviar={(v) => guardar.mutateAsync(v)}>
        <Campo etiqueta="NAV, valor actual (€)" name="nav" inputMode="decimal" defaultValue={String(inv.nav)} required />
        <Campo etiqueta="Fecha del NAV" name="nav_fecha" type="date" defaultValue={inv.nav_fecha ?? hoyISO()} ayuda="Si cambias el NAV sin tocar la fecha, se pone hoy" />
        <Campo etiqueta="Capital distribuido (€)" name="distribuido" inputMode="decimal" defaultValue={String(inv.distribuido)} />
        <Campo etiqueta="Capital comprometido (€)" name="compromiso" inputMode="decimal" defaultValue={String(inv.compromiso)} />
        <Campo etiqueta="Fondo" name="nombre" defaultValue={inv.nombre} required />
        <Campo etiqueta="Plataforma o gestora" name="gestora" defaultValue={inv.gestora} />
        <Campo etiqueta="Fecha del compromiso" name="fecha_compromiso" type="date" defaultValue={inv.fecha_compromiso ?? ''} />
        <Area etiqueta="Notas" name="notas" className="sm:col-span-2" rows={2} defaultValue={inv.notas} />
      </Formulario>
      <div className="border-t border-line pt-5">
        <div className="mb-3 text-sm font-medium">Añadir llamada de capital</div>
        <Formulario onEnviar={(v) => llamada.mutateAsync(v)} textoBoton="Añadir">
          <Campo etiqueta="Fecha" name="fecha" type="date" required />
          <Campo etiqueta="Importe (€)" name="importe" inputMode="decimal" required />
          <Casilla etiqueta="Ya pagada" name="pagado" />
        </Formulario>
      </div>
    </div>
  )
}

function Fondo({ inv, onEditar }: { inv: InversionPrivada; onEditar: () => void }) {
  const marcar = useMarcarPago()
  const quitar = useBorrarPago()
  const borrar = useAccion(() => api.del(`/inversiones/${inv.id}`), 'Inversión borrada')
  return (
    <Tarjeta titulo={inv.nombre} accion={
      <div className="flex items-center gap-2">
        {inv.gestora && <Etiqueta>{inv.gestora}</Etiqueta>}
        <Boton variante="secundario" className="px-2.5 py-1 text-xs" onClick={onEditar}>Actualizar</Boton>
      </div>}>
      {inv.fecha_compromiso && <p className="-mt-2 mb-4 text-xs text-muted">Compromiso del {fecha(inv.fecha_compromiso, { day: 'numeric', month: 'long', year: 'numeric' })}</p>}
      <div className="grid grid-cols-2 gap-4 [&>*]:min-w-0">
        <Dato etiqueta="Valor actual (NAV)" valor={eur(inv.nav)} nota={inv.nav_fecha ? `a ${fecha(inv.nav_fecha)}` : undefined} />
        <Dato etiqueta="TVPI" valor={inv.tvpi != null ? `${inv.tvpi.toLocaleString('es-ES', { minimumFractionDigits: 2 })}x` : '—'}
          nota={<Importe valor={inv.resultado} signo />} tono={inv.resultado >= 0 ? 'pos' : 'neg'} />
        <Dato etiqueta="Distribuido" valor={eur(inv.distribuido)} />
        <Dato etiqueta="Próxima llamada" valor={inv.proxima_llamada ? eur(inv.proxima_llamada.importe) : '—'}
          nota={inv.proxima_llamada ? fecha(inv.proxima_llamada.fecha, { month: 'long', year: 'numeric' }) : undefined} />
      </div>
      <div className="mt-5 text-sm">
        <div className="mb-1.5 flex justify-between gap-2">
          <span>Desembolsado <span className="cifra font-medium">{eur(inv.desembolsado)}</span> de {eur(inv.compromiso)}</span>
          <span className="cifra whitespace-nowrap text-muted">{pct(inv.pct_desembolsado ?? 0, 1)}</span>
        </div>
        <Barra valor={inv.desembolsado} max={inv.compromiso} />
        {inv.sin_calendario > 0 && (
          <p className="mt-2 text-xs text-warn">Faltan {eur(inv.sin_calendario)} del compromiso sin fecha prevista: añade la llamada cuando la conozcas.</p>
        )}
      </div>
      {inv.notas && <p className="mt-4 rounded-xl bg-panel-2 px-3 py-2 text-sm whitespace-pre-line">{inv.notas}</p>}
      <details className="mt-4 text-sm">
        <summary className="cursor-pointer text-muted">Llamadas de capital ({inv.llamadas.length})</summary>
        <ul className="mt-2 divide-y divide-line">
          {inv.llamadas.map((l) => (
            <li key={l.id} className="flex items-center justify-between gap-2 py-2">
              <span className={l.pagado ? 'text-muted' : ''}>{fecha(l.fecha, { day: 'numeric', month: 'short', year: 'numeric' })}</span>
              <div className="flex items-center gap-2">
                <Importe valor={l.importe} />
                <Boton variante={l.pagado ? 'secundario' : 'fantasma'} className="px-2 py-1 text-xs" disabled={marcar.isPending || quitar.isPending} onClick={() => marcar.mutate({ id: l.id, pagado: !l.pagado })}>
                  <Check size={14} />{l.pagado ? 'Pagada' : 'Marcar'}
                </Boton>
                <BorrarEnDosPasos etiqueta={`la llamada del ${fecha(l.fecha)}`} disabled={quitar.isPending} onBorrar={() => quitar.mutate(l.id)} />
              </div>
            </li>
          ))}
        </ul>
        <div className="mt-2">
          <BorrarEnDosPasos texto="Borrar inversión" etiqueta={inv.nombre} disabled={borrar.isPending} onBorrar={() => borrar.mutate(undefined)} />
        </div>
      </details>
    </Tarjeta>
  )
}

function Totales({ t }: { t: Inversiones['totales'] }) {
  return (
    <Tarjeta className="mb-4">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4 [&>*]:min-w-0">
        <Dato etiqueta="Comprometido" valor={eur(t.compromiso)} nota={`quedan ${eur(t.pendiente)} por desembolsar`} />
        <Dato etiqueta="Desembolsado" valor={eur(t.desembolsado)} nota={t.compromiso ? `${pct((t.desembolsado / t.compromiso) * 100, 0)} del compromiso` : undefined} />
        <Dato etiqueta="Distribuido" valor={eur(t.distribuido)} nota="Lo que los fondos ya te han devuelto" />
        <Dato etiqueta="Valor actual (NAV)" valor={eur(t.nav)} nota={<Importe valor={t.nav + t.distribuido - t.desembolsado} signo />}
          tono={t.nav + t.distribuido - t.desembolsado >= 0 ? 'pos' : 'neg'} />
      </div>
      <p className="mt-3 text-xs text-muted">El NAV es el que da cada plataforma en la fecha que pusiste; el resultado es NAV más distribuido menos desembolsado, sin descontar impuestos.</p>
    </Tarjeta>
  )
}

/** Private equity (Concrescenta y similares): no tienen API, se actualizan a mano con lo que enseña la plataforma. */
export default function InversionesPrivadas() {
  const [nueva, setNueva] = useState(false)
  const [editando, setEditando] = useState<InversionPrivada | null>(null)
  const { data, error } = useQuery({ queryKey: ['inversiones'], queryFn: () => api.get<Inversiones>('/inversiones') })
  if (error && !data) return <section className="mt-8"><h2 className="mb-3 text-lg font-semibold">Inversión privada</h2><ErrorCarga error={error} /></section>
  if (!data) return null
  return (
    <section className="mt-8">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Inversión privada</h2>
          {data.inversiones.length > 0 && (
            <p className="text-sm text-muted">{data.inversiones.length} {data.inversiones.length === 1 ? 'fondo' : 'fondos'} · {eur(data.totales.nav)} de valor</p>
          )}
        </div>
        <Boton variante="secundario" onClick={() => setNueva(true)}><Plus size={16} />Fondo</Boton>
      </div>
      {data.inversiones.length ? (
        <>
          <Totales t={data.totales} />
          <div className="grid gap-4 lg:grid-cols-2">
            {data.inversiones.map((i) => <Fondo key={i.id} inv={i} onEditar={() => setEditando(i)} />)}
          </div>
        </>
      ) : (
        <Vacio>Añade aquí tus fondos de private equity (por ejemplo, de Concrescenta) con el compromiso y las llamadas de capital. Las pendientes salen en el Plan.</Vacio>
      )}
      <Dialogo abierto={nueva} onCerrar={() => setNueva(false)} titulo="Nuevo fondo">
        <Nueva onCerrar={() => setNueva(false)} />
      </Dialogo>
      <Dialogo abierto={!!editando} onCerrar={() => setEditando(null)} titulo={`Actualizar ${editando?.nombre ?? ''}`}>
        {editando && <Actualizar inv={editando} onCerrar={() => setEditando(null)} />}
      </Dialogo>
    </section>
  )
}
