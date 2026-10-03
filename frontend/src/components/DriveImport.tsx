import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ExternalLink, FolderSync, X } from 'lucide-react'
import { api } from '../lib/api'
import { eur, fecha } from '../lib/format'
import { permisoDrive } from '../lib/google'
import type { DocumentosDrive } from '../lib/tipos'
import { Boton, Etiqueta, Tarjeta, Vacio, useAccion, useAvisos } from './ui'

/** Importa de tu Drive las facturas emitidas, las recibidas y los justificantes de Hacienda. */
export default function DriveImport() {
  const qc = useQueryClient()
  const avisar = useAvisos()
  const [progreso, setProgreso] = useState<string | null>(null)
  const { data: d } = useQuery({ queryKey: ['drive'], queryFn: () => api.get<DocumentosDrive>('/drive/documentos') })
  const gasto = useAccion((id: number) => api.post(`/drive/documentos/${id}/gasto`, { deducible_pct: 100 }), 'Apuntado como gasto')
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
      {!d ? null : !d.google_client_id ? (
        <Vacio>Funciona con la app publicada y el inicio de sesión de Google configurado.</Vacio>
      ) : !d.ia ? (
        <Vacio>Para leer las facturas hace falta la clave de Claude (<code>ANTHROPIC_API_KEY</code>), la misma que usa el asistente.</Vacio>
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
                  {x.enlace && <a href={x.enlace} target="_blank" rel="noreferrer" className="ml-2 inline-flex items-center gap-1 text-accent">ver <ExternalLink size={11} /></a>}
                </div>
                {x.datos.avisos?.map((a) => <div key={a} className="text-xs text-neg">{a}</div>)}
              </div>
              <div className="flex gap-2">
                <Boton variante="secundario" className="px-2.5 py-1 text-xs" onClick={() => gasto.mutate(x.id)}><Check size={14} />Es gasto</Boton>
                <Boton variante="fantasma" className="px-2.5 py-1 text-xs" onClick={() => ignorar.mutate(x.id)}><X size={14} />No</Boton>
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
    </Tarjeta>
  )
}
