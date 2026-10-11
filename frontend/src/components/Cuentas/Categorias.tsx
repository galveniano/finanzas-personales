import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import type { Categoria, ReglaCategoria } from '../../lib/tipos'
import { useAccion } from '../../lib/utilidades'
import { BorrarEnDosPasos, Campo, ErrorCarga, Etiqueta, Formulario, Pestanas, Selector, Vacio } from '../ui'
import { useCategorias } from './comun'

const PESTANAS = [{ id: 'categorias', texto: 'Categorías' }, { id: 'reglas', texto: 'Reglas' }] as const
const TIPOS = [['gasto', 'Gasto'], ['ingreso', 'Ingreso'], ['transferencia', 'Transferencia']] as const
const AMBITOS = [['personal', 'Personal'], ['autonomo', 'Autónomo'], ['piso', 'Piso'], ['nomina', 'Nómina']] as const

type Cambio = { nombre?: string; tipo?: string; ambito?: string }

function FilaCategoria({ c, onCambiar, onBorrar }: { c: Categoria; onCambiar: (d: Cambio) => void; onBorrar: () => void }) {
  const renombrar = (v: string) => { const nombre = v.trim(); if (nombre && nombre !== c.nombre) onCambiar({ nombre }) }
  return (
    <li className="flex flex-wrap items-center gap-2 py-2">
      <Campo defaultValue={c.nombre} aria-label="Nombre de la categoría" readOnly={c.de_serie} className={`min-w-0 flex-1 basis-36 py-1.5! ${c.de_serie ? 'text-muted' : ''}`}
        onBlur={(e) => renombrar(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur() } }} />
      {c.de_serie && <Etiqueta tono="acento">De serie</Etiqueta>}
      <Selector value={c.tipo} aria-label={`Tipo de ${c.nombre}`} className="w-auto! py-1.5! text-xs" onChange={(e) => onCambiar({ tipo: e.target.value })}>
        {TIPOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
      </Selector>
      <Selector value={c.ambito} aria-label={`Ámbito de ${c.nombre}`} className="w-auto! py-1.5! text-xs" onChange={(e) => onCambiar({ ambito: e.target.value })}>
        {AMBITOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
      </Selector>
      <BorrarEnDosPasos etiqueta={`la categoría ${c.nombre}`} onBorrar={onBorrar} disabled={c.de_serie} />
    </li>
  )
}

function ListaCategorias() {
  const { data, error } = useCategorias()
  const [version, setVersion] = useState(0)  // para vaciar el formulario de nueva categoría al crearla
  const cambiar = useAccion(({ id, ...d }: Cambio & { id: number }) => api.patch(`/categorias/${id}`, d), 'Categoría guardada')
  const borrar = useAccion((id: number) => api.del(`/categorias/${id}`), 'Categoría borrada; sus movimientos quedan sin categoría')
  const crear = useAccion((d: Record<string, string>) => api.post('/categorias', d).then(() => setVersion((v) => v + 1)), 'Categoría creada')
  if (error && !data) return <ErrorCarga error={error} />
  return (
    <div className="space-y-5 text-sm">
      <ul className="divide-y divide-line">
        {data?.map((c) => <FilaCategoria key={c.id} c={c} onCambiar={(d) => cambiar.mutate({ id: c.id, ...d })} onBorrar={() => borrar.mutate(c.id)} />)}
      </ul>
      <p className="text-xs text-muted">Cambia el nombre y pulsa Intro o sal del campo para guardarlo. Las «de serie» las usa la app por su nombre (nóminas, cuota de autónomos, traspasos…): puedes cambiarles el tipo y el ámbito, pero no renombrarlas ni borrarlas. Al borrar una categoría, sus movimientos se quedan sin categoría y sus reglas desaparecen.</p>
      <div className="rounded-xl bg-panel-2 p-4">
        <h3 className="mb-3 text-xs font-medium tracking-wider text-muted uppercase">Nueva categoría</h3>
        <Formulario key={version} onEnviar={(d) => crear.mutateAsync(d)} textoBoton="Crear categoría">
          <Campo etiqueta="Nombre" name="nombre" required placeholder="Mascotas, Regalos, Gimnasio…" className="sm:col-span-2" />
          <Selector etiqueta="Tipo" name="tipo" defaultValue="gasto">{TIPOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</Selector>
          <Selector etiqueta="Ámbito" name="ambito" defaultValue="personal">{AMBITOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</Selector>
        </Formulario>
      </div>
    </div>
  )
}

function Reglas() {
  const { data, error } = useQuery({ queryKey: ['reglas'], queryFn: () => api.get<ReglaCategoria[]>('/categorias/reglas') })
  const borrar = useAccion((id: number) => api.del(`/categorias/reglas/${id}`), 'Regla borrada')
  if (error && !data) return <ErrorCarga error={error} />
  const aprendidas = data?.filter((r) => r.aprendida) ?? [], deSerie = data?.filter((r) => !r.aprendida) ?? []
  return (
    <div className="space-y-4 text-sm">
      <p className="text-xs text-muted">Cada vez que cambias la categoría de un movimiento, la app aprende: lo que contenga ese patrón (el concepto sin números ni fechas) irá a esa categoría. Las aprendidas mandan sobre las de serie.</p>
      {aprendidas.length
        ? (
          <ul className="divide-y divide-line">
            {aprendidas.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-3 py-2">
                <span className="min-w-0 truncate">lo que contenga <span className="font-medium">«{r.patron}»</span> → {r.categoria}</span>
                <BorrarEnDosPasos etiqueta={`la regla «${r.patron}»`} onBorrar={() => borrar.mutate(r.id)} disabled={borrar.isPending} />
              </li>
            ))}
          </ul>
        )
        : <Vacio>{data ? 'Aún no has enseñado ninguna regla: cambia la categoría de un movimiento y aparecerá aquí.' : 'Cargando…'}</Vacio>}
      {deSerie.length > 0 && (
        <details className="rounded-xl border border-line px-4 py-3">
          <summary className="cursor-pointer text-xs font-medium text-muted">Reglas de serie ({deSerie.length}), solo lectura</summary>
          <ul className="mt-2 max-h-64 space-y-1 overflow-y-auto text-xs text-muted">
            {deSerie.map((r) => <li key={r.id}>«{r.patron}» → {r.categoria}</li>)}
          </ul>
        </details>
      )}
    </div>
  )
}

/** Diálogo «Categorías»: las categorías (nombre, tipo, ámbito, crear, borrar) y las reglas que las asignan. */
export default function Categorias() {
  const [ver, setVer] = useState<'categorias' | 'reglas'>('categorias')
  return (
    <>
      <Pestanas className="mb-4" pestanas={PESTANAS} activa={ver} onCambiar={setVer} />
      {ver === 'categorias' ? <ListaCategorias /> : <Reglas />}
    </>
  )
}
