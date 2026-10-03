import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Search, Upload } from 'lucide-react'
import { api } from '../lib/api'
import { eur, fecha } from '../lib/format'
import type { Categoria, Cuenta, Movimiento } from '../lib/tipos'
import CarteraIndexa from '../components/CarteraIndexa'
import InversionesPrivadas from '../components/InversionesPrivadas'
import { Boton, Cabecera, Campo, Cargando, Dialogo, Etiqueta, Formulario, Importe, Selector, Tabla, Tarjeta, Vacio, num, useAccion, useAvisos } from '../components/ui'

const ORIGEN: Record<string, { texto: string; tono: 'acento' | 'neutro' | 'bien' }> = {
  enable_banking: { texto: 'Sincronizada', tono: 'bien' },
  indexa: { texto: 'Indexa API', tono: 'bien' },
  csv: { texto: 'Extracto', tono: 'neutro' },
  manual: { texto: 'Manual', tono: 'neutro' },
}

function Importar({ cuenta, onCerrar }: { cuenta: Cuenta; onCerrar: () => void }) {
  const avisar = useAvisos()
  const accion = useAccion(async (f: File) => {
    const fd = new FormData()
    fd.append('fichero', f)
    const r = await api.post<{ nuevos: number; duplicados: number }>(`/cuentas/${cuenta.id}/importar`, fd)
    avisar(`${r.nuevos} movimientos nuevos, ${r.duplicados} ya estaban`)
    onCerrar()
  })
  return (
    <div className="space-y-4 text-sm">
      <p className="text-muted">Descarga los movimientos desde la web de Sabadell (Excel o CSV) y súbelos aquí. Si un movimiento ya estaba, no se duplica.</p>
      <label className="flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-line px-4 py-8 text-center hover:border-accent">
        <Upload className="text-accent" />
        <span className="font-medium">{accion.isPending ? 'Importando…' : 'Elegir extracto'}</span>
        <span className="text-xs text-muted">.xls, .xlsx o .csv</span>
        <input type="file" accept=".xls,.xlsx,.csv" className="sr-only" disabled={accion.isPending}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) accion.mutate(f) }} />
      </label>
    </div>
  )
}

/** De quién es la cuenta: tuya, compartida (cuenta tu parte) o de otra persona (se ve pero no cuenta). */
function Titularidad({ c }: { c: Cuenta }) {
  const cambiar = useAccion((participacion: number) => api.patch(`/cuentas/${c.id}`, { participacion }), 'Cuenta actualizada')
  const fijas = [100, 50, 0]
  return (
    <select value={c.participacion} disabled={cambiar.isPending} aria-label="De quién es la cuenta"
      onChange={(e) => {
        if (e.target.value === 'otro') {
          const v = num(prompt('¿Qué parte de la cuenta es tuya? (en %)', String(c.participacion)) ?? undefined)
          if (v != null && v >= 0 && v <= 100) cambiar.mutate(v)
        } else cambiar.mutate(Number(e.target.value))
      }}
      className="max-w-full rounded-lg border border-line bg-panel px-2 py-1 text-xs">
      <option value={100}>Mía</option>
      <option value={50}>Compartida a medias</option>
      <option value={0}>No es mía (no cuenta)</option>
      {!fijas.includes(c.participacion) && <option value={c.participacion}>Mía al {c.participacion} %</option>}
      <option value="otro">Otro porcentaje…</option>
    </select>
  )
}

export default function Cuentas() {
  const [filtro, setFiltro] = useState({ cuenta: '', categoria: '', q: '' })
  const [nueva, setNueva] = useState(false)
  const [importando, setImportando] = useState<Cuenta | null>(null)
  const cuentas = useQuery({ queryKey: ['cuentas'], queryFn: () => api.get<Cuenta[]>('/cuentas') })
  const categorias = useQuery({ queryKey: ['categorias'], queryFn: () => api.get<Categoria[]>('/categorias') })
  const params = new URLSearchParams()
  if (filtro.cuenta) params.set('cuenta_id', filtro.cuenta)
  if (filtro.categoria) params.set('categoria_id', filtro.categoria)
  if (filtro.q) params.set('q', filtro.q)
  if (!filtro.cuenta) params.set('solo_tuyas', 'true')  // las cuentas que no son tuyas, solo si las eliges
  const qs = params.toString()
  const movs = useQuery({ queryKey: ['movimientos', qs], queryFn: () => api.get<Movimiento[]>(`/movimientos${qs ? `?${qs}` : ''}`) })
  const crear = useAccion((d: Record<string, string>) => api.post('/cuentas', { ...d, saldo: num(d.saldo) ?? 0 }).then(() => setNueva(false)), 'Cuenta creada')
  const categorizar = useAccion(({ id, cat }: { id: number; cat: string }) => api.patch(`/movimientos/${id}`, { categoria_id: cat ? Number(cat) : null }))

  const total = (cuentas.data ?? []).filter((c) => c.tipo !== 'tarjeta').reduce((s, c) => s + c.saldo_tuyo, 0)

  return (
    <>
      <Cabecera titulo="Cuentas" subtitulo={cuentas.data ? `${cuentas.data.length} cuentas · ${eur(total)} tuyos` : undefined}>
        <Boton onClick={() => setNueva(true)}><Plus size={16} />Nueva cuenta</Boton>
      </Cabecera>

      {cuentas.isLoading ? <Cargando /> : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {cuentas.data?.map((c) => {
            const o = ORIGEN[c.origen] ?? ORIGEN.manual
            return (
              <Tarjeta key={c.id} className={c.participacion === 0 ? 'opacity-60' : undefined}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate font-semibold">{c.nombre}</div>
                    <div className="truncate text-xs text-muted">{c.entidad}{c.iban && ` · ···${c.iban.slice(-4)}`}</div>
                  </div>
                  <Etiqueta tono={o.tono}>{o.texto}</Etiqueta>
                </div>
                <div className="cifra mt-4 text-2xl font-medium">{eur(c.saldo)}</div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
                  <Titularidad c={c} />
                  {c.participacion > 0 && c.participacion < 100 && <span>Tuyo: <span className="cifra">{eur(c.saldo_tuyo)}</span></span>}
                  {c.participacion === 0 && <span>No suma en tu patrimonio ni en tus gastos</span>}
                </div>
                <div className="mt-1 flex items-center justify-between gap-2 text-xs text-muted">
                  <span>{c.ultima_sincronizacion ? `Sincronizada ${fecha(c.ultima_sincronizacion, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}` : `Saldo a ${fecha(c.saldo_fecha)}`}</span>
                  {c.origen !== 'indexa' && (
                    <button className="font-medium text-accent" onClick={() => setImportando(c)}>Importar extracto</button>
                  )}
                </div>
              </Tarjeta>
            )
          })}
          {!cuentas.data?.length && <Vacio>Crea tu cuenta de Sabadell o conéctala en Conexiones.</Vacio>}
        </div>
      )}

      <CarteraIndexa />
      <InversionesPrivadas />

      <Tarjeta className="mt-6" titulo="Movimientos">
        <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_1fr_1.4fr]">
          <Selector value={filtro.cuenta} onChange={(e) => setFiltro({ ...filtro, cuenta: e.target.value })} aria-label="Cuenta">
            <option value="">Todas las cuentas</option>
            {cuentas.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
          </Selector>
          <Selector value={filtro.categoria} onChange={(e) => setFiltro({ ...filtro, categoria: e.target.value })} aria-label="Categoría">
            <option value="">Todas las categorías</option>
            <option value="0">Sin categoría</option>
            {categorias.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
          </Selector>
          <label className="relative">
            <Search size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-muted" />
            <input value={filtro.q} onChange={(e) => setFiltro({ ...filtro, q: e.target.value })} placeholder="Buscar concepto"
              className="w-full rounded-xl border border-line bg-panel py-2 pr-3 pl-9 text-sm" />
          </label>
        </div>
        {movs.data?.length ? (
          <Tabla>
            <thead><tr><th>Fecha</th><th>Concepto</th><th className="hidden md:table-cell">Cuenta</th><th>Categoría</th><th className="num">Importe</th></tr></thead>
            <tbody>
              {movs.data.map((m) => (
                <tr key={m.id}>
                  <td className="cifra whitespace-nowrap text-muted">{fecha(m.fecha, { day: '2-digit', month: 'short' })}</td>
                  <td className="max-w-[320px]"><div className="truncate">{m.concepto}</div></td>
                  <td className="hidden text-muted md:table-cell">{m.cuenta}</td>
                  <td>
                    <select value={m.categoria_id ?? ''} onChange={(e) => categorizar.mutate({ id: m.id, cat: e.target.value })}
                      className={`max-w-[170px] rounded-lg border border-transparent bg-transparent px-1.5 py-1 text-sm hover:border-line ${m.categoria_id ? '' : 'text-warn'}`}
                      aria-label="Categoría">
                      <option value="">Sin categoría</option>
                      {categorias.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
                    </select>
                  </td>
                  <td className="num"><Importe valor={m.importe} signo /></td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        ) : <Vacio>{movs.isLoading ? 'Cargando…' : 'No hay movimientos con estos filtros.'}</Vacio>}
      </Tarjeta>

      <Dialogo abierto={nueva} onCerrar={() => setNueva(false)} titulo="Nueva cuenta">
        <Formulario onEnviar={(d) => crear.mutateAsync(d)} textoBoton="Crear cuenta">
          <Campo etiqueta="Nombre" name="nombre" required placeholder="Cuenta Sabadell" />
          <Campo etiqueta="Entidad" name="entidad" defaultValue="Banco Sabadell" />
          <Selector etiqueta="Tipo" name="tipo" defaultValue="corriente">
            <option value="corriente">Corriente</option><option value="ahorro">Ahorro</option>
            <option value="tarjeta">Tarjeta de crédito</option><option value="inversion">Inversión</option>
          </Selector>
          <Campo etiqueta="Saldo actual (€)" name="saldo" inputMode="decimal" placeholder="0" ayuda="Déjalo vacío si vas a importar un extracto." />
          <Campo etiqueta="IBAN" name="iban" className="sm:col-span-2" placeholder="ES00 0081 ..." />
        </Formulario>
      </Dialogo>
      <Dialogo abierto={!!importando} onCerrar={() => setImportando(null)} titulo={`Importar en ${importando?.nombre ?? ''}`}>
        {importando && <Importar cuenta={importando} onCerrar={() => setImportando(null)} />}
      </Dialogo>
    </>
  )
}
