import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ExternalLink, FolderSync, X } from 'lucide-react'
import { api } from '../lib/api'
import { eur, fecha, pct } from '../lib/format'
import { permisoDrive } from '../lib/google'
import type { DocumentoDrive, DocumentosDrive } from '../lib/tipos'
import { num, useAccion, useAvisos } from '../lib/utilidades'
import { CATEGORIAS_GASTO } from './categoriasGasto'
import { Boton, Campo, Dialogo, ErrorCarga, Etiqueta, Formulario, Selector, Tarjeta, Vacio } from './ui'

/** Antes de apuntar una factura recibida como gasto: categoría y parte deducible, con lo que se ha leído del documento. */
function FormGastoDrive({ doc, onHecho }: { doc: DocumentoDrive; onHecho: () => void }) {
  const d = doc.datos
  const apuntar = useAccion((v: Record<string, string>) => api.post(`/drive/documentos/${doc.id}/gasto`, {
    categoria: v.categoria, deducible_pct: num(v.deducible_pct) ?? 100,
  }).then(onHecho), 'Apuntado como gasto')
  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 rounded-xl bg-panel-2 p-4 text-sm sm:grid-cols-4">
        <div className="col-span-2"><dt className="text-xs text-muted">Leído del documento</dt><dd className="truncate font-medium">{d.contraparte ?? doc.nombre}{d.fecha && <span className="font-normal text-muted"> · {fecha(d.fecha)}</span>}</dd></div>
        <div><dt className="text-xs text-muted">Base · IVA</dt><dd className="cifra">{eur(d.base)} · {d.tipo_iva ?? 0} %</dd></div>
        <div><dt className="text-xs text-muted">Total · retención</dt><dd className="cifra">{eur(d.total)} · {d.tipo_retencion ? pct(d.tipo_retencion) : 'sin'}</dd></div>
      </dl>
      <Formulario onEnviar={(v) => apuntar.mutateAsync(v)} textoBoton="Apuntar como gasto">
        <Selector etiqueta="Categoría" name="categoria" defaultValue={d.categoria_gasto && d.categoria_gasto in CATEGORIAS_GASTO ? d.categoria_gasto : 'otros'}>
          {Object.entries(CATEGORIAS_GASTO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Selector>
        <Campo etiqueta="% deducible" name="deducible_pct" defaultValue="100" inputMode="decimal" ayuda="Por ejemplo, 30 % para suministros de casa." />
      </Formulario>
    </div>
  )
}

/** Importa de tu Drive las facturas emitidas, las recibidas y los justificantes de Hacienda. */
export default function DriveImport() {
  const qc = useQueryClient()
  const avisar = useAvisos()
  const [progreso, setProgreso] = useState<string | null>(null)
  const [gastoDe, setGastoDe] = useState<DocumentoDrive | null>(null)
  const { data: d, error } = useQuery({ queryKey: ['drive'], queryFn: () => api.get<DocumentosDrive>('/drive/documentos') })
  const ignorar = useAccion((id: number) => api.post(`/drive/documentos/${id}/ignorar`))

  const importar = async () => {
    if (!d?.google_client_id) return
    try {
      setProgreso('Pidiendo permiso a Google…')
      const token = await permisoDrive(d.google_client_id)
      let total = 0
      for (;;) {
        setProgreso(total ? `Leídos ${total} documentos…` : 'Buscando facturas en tu Drive…')
        const r = await api.post<{ procesados: unknown[]; quedan: number }>('/drive/importar', { access_token: token })
        total += r.procesados.length
        await qc.invalidateQueries()
        if (!r.quedan || !r.procesados.length) break
      }
      avisar(total ? `Drive revisado: ${total} documentos nuevos` : 'No hay documentos nuevos en Drive')
    } catch (e) {
      avisar((e as Error).message, 'error')
    } finally {
      setProgreso(null)
    }
  }

  const docs = d?.documentos ?? []
  const pendientes = docs.filter((x) => x.estado === 'pendiente')
  const importados = docs.filter((x) => x.estado === 'importado')
  const errores = docs.filter((x) => x.estado === 'error')

  return (
    <Tarjeta titulo="Google Drive" accion={pendientes.length > 0 && <Etiqueta tono="aviso">{pendientes.length} por revisar</Etiqueta>}>
      <p className="mb-4 text-sm text-muted">
        Busca en tu Drive facturas y justificantes de Hacienda. Tus facturas emitidas pasan a Autónomo y los justificantes a Hacienda;
        las facturas que recibes te las enseño aquí para que decidas si son gasto de la actividad. Solo lectura: no se toca nada de tu Drive.
      </p>
      {!d ? (error ? <ErrorCarga error={error} /> : null) : !d.google_client_id ? (
        <Vacio>Funciona con la app publicada y el inicio de sesión de Google configurado.</Vacio>
      ) : !d.ia ? (
        <Vacio>Para leer las facturas hace falta configurar el asistente: pon tu clave de OpenAI o de Claude en Ajustes, en la tarjeta Asistente (IA) de arriba.</Vacio>
      ) : (
        <Boton onClick={importar} disabled={!!progreso}><FolderSync size={15} className={progreso ? 'animate-pulse' : ''} />{progreso ?? 'Importar de Drive'}</Boton>
      )}

      {pendientes.length > 0 && (
        <ul className="mt-5 divide-y divide-line">
          {pendientes.map((x) => (
            <li key={x.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
              <div className="min-w-0">
                <div className="font-medium">{x.datos.contraparte ?? x.nombre}{x.datos.concepto && <span className="font-normal text-muted"> · {x.datos.concepto}</span>}</div>
                <div className="text-xs text-muted">
                  {x.datos.fecha && fecha(x.datos.fecha)} · base {eur(x.datos.base)} · IVA {x.datos.tipo_iva ?? 0} %
                  {x.datos.total != null && <> · total {eur(x.datos.total)}</>}{!!x.datos.tipo_retencion && <> · retención {pct(x.datos.tipo_retencion)}</>}
                  {x.enlace && <a href={x.enlace} target="_blank" rel="noreferrer" className="ml-2 inline-flex items-center gap-1 text-accent">ver <ExternalLink size={11} /></a>}
                </div>
                {x.datos.avisos?.map((a) => <div key={a} className="text-xs text-neg">{a}</div>)}
              </div>
              <div className="flex gap-2">
                <Boton variante="secundario" className="px-2.5 py-1 text-xs" disabled={ignorar.isPending} onClick={() => setGastoDe(x)}><Check size={14} />Es gasto</Boton>
                <Boton variante="fantasma" className="px-2.5 py-1 text-xs" disabled={ignorar.isPending} onClick={() => ignorar.mutate(x.id)}><X size={14} />No</Boton>
              </div>
            </li>
          ))}
        </ul>
      )}
      {(importados.length > 0 || errores.length > 0) && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-muted">{importados.length} importados{errores.length > 0 && `, ${errores.length} con error`}</summary>
          <ul className="mt-2 space-y-1 text-xs">
            {[...errores, ...importados].map((x) => (
              <li key={x.id} className={x.estado === 'error' ? 'text-neg' : 'text-muted'}>
                {x.nombre}: {x.mensaje}{x.datos.avisos?.length ? ` (${x.datos.avisos.join('; ')})` : ''}
              </li>
            ))}
          </ul>
        </details>
      )}
      <Dialogo abierto={!!gastoDe} onCerrar={() => setGastoDe(null)} titulo="Apuntar como gasto de la actividad">
        {gastoDe && <FormGastoDrive key={gastoDe.id} doc={gastoDe} onHecho={() => setGastoDe(null)} />}
      </Dialogo>
    </Tarjeta>
  )
}
