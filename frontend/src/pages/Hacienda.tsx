import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, Plus, Trash2, Upload } from 'lucide-react'
import { api } from '../lib/api'
import { eur, fecha } from '../lib/format'
import type { Declaracion, Declaraciones } from '../lib/tipos'
import { Boton, Cabecera, Campo, Cargando, Dialogo, Etiqueta, ErrorCarga, Formulario, Importe, Selector, Tabla, Tarjeta, Vacio, num, opc, useAccion, useAvisos } from '../components/ui'

const RESULTADO: Record<Declaracion['resultado'], { texto: string; tono: 'neutro' | 'bien' | 'aviso' | 'mal' }> = {
  ingresar: { texto: 'A ingresar', tono: 'aviso' }, domiciliar: { texto: 'Domiciliado', tono: 'aviso' },
  devolver: { texto: 'A devolver', tono: 'bien' }, compensar: { texto: 'A compensar', tono: 'bien' },
  negativa: { texto: 'Negativa', tono: 'neutro' }, cero: { texto: 'Sin actividad', tono: 'neutro' }, otro: { texto: 'Presentada', tono: 'neutro' },
}

const periodoTexto = (p: string) => (p === '0A' ? 'Anual' : p.endsWith('T') ? `${p[0]}º trim.` : p)

function Diferencia({ d }: { d: Declaracion }) {
  if (d.estimado == null) return <span className="text-muted">—</span>
  const dif = d.importe - d.estimado
  if (Math.abs(dif) < 1) return <Etiqueta tono="bien">Cuadra</Etiqueta>
  return <span className="cifra text-xs text-muted" title={`La app calcula ${eur(d.estimado)}`}>{dif > 0 ? '+' : ''}{eur(dif)}</span>
}

export default function Hacienda() {
  const avisar = useAvisos()
  const input = useRef<HTMLInputElement>(null)
  const [manual, setManual] = useState(false)
  const [arrastrando, setArrastrando] = useState(false)
  const { data: d, isLoading, error } = useQuery({ queryKey: ['declaraciones'], queryFn: () => api.get<Declaraciones>('/declaraciones') })

  const subir = useAccion(async (ficheros: File[]) => {
    const fd = new FormData()
    ficheros.forEach((f) => fd.append('ficheros', f))
    const r = await api.post<{ resultados: { fichero: string; ok: boolean; mensaje: string }[] }>('/declaraciones/pdf', fd)
    const bien = r.resultados.filter((x) => x.ok)
    const mal = r.resultados.filter((x) => !x.ok)
    if (bien.length) avisar(`${bien.length === 1 ? bien[0].mensaje : `${bien.length} justificantes`} guardado${bien.length === 1 ? '' : 's'}`)
    mal.forEach((x) => avisar(`${x.fichero}: ${x.mensaje}`, 'error'))
  })
  const crear = useAccion((v: Record<string, string>) => api.post('/declaraciones', {
    modelo: v.modelo, ejercicio: Number(v.ejercicio), periodo: v.periodo, resultado: v.resultado,
    importe: num(v.importe) ?? 0, fecha_presentacion: opc(v.fecha_presentacion) ?? null, notas: v.notas ?? '',
  }).then(() => setManual(false)), 'Declaración guardada')
  const borrar = useAccion((id: number) => api.del(`/declaraciones/${id}`), 'Borrada')

  const elegir = (lista: FileList | null) => {
    const pdfs = [...(lista ?? [])].filter((f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'))
    if (pdfs.length) subir.mutate(pdfs)
  }

  return (
    <>
      <Cabecera titulo="Hacienda" subtitulo="Los modelos que ya has presentado: IVA, IRPF y renta">
        <Boton variante="secundario" onClick={() => setManual(true)}><Plus size={16} />A mano</Boton>
        <Boton onClick={() => input.current?.click()} disabled={subir.isPending}><Upload size={16} />{subir.isPending ? 'Leyendo…' : 'Subir justificantes'}</Boton>
      </Cabecera>
      <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(e) => { elegir(e.target.files); e.target.value = '' }} />

      <div
        onDragOver={(e) => { e.preventDefault(); setArrastrando(true) }}
        onDragLeave={() => setArrastrando(false)}
        onDrop={(e) => { e.preventDefault(); setArrastrando(false); elegir(e.dataTransfer.files) }}
        className={`mb-6 rounded-2xl border-2 border-dashed px-5 py-6 text-sm transition ${arrastrando ? 'border-accent bg-accent-soft' : 'border-line'}`}>
        <p className="font-medium">Arrastra aquí los PDF que te da la sede de la Agencia Tributaria al presentar</p>
        <p className="mt-1 text-muted">
          Se leen solos el modelo, el periodo, la fecha y el importe. Hacienda no tiene una API para particulares, así que
          para los antiguos entra en la sede con Cl@ve, ve a <em>Mis expedientes</em> o <em>Consulta de declaraciones</em> y descarga los justificantes.
        </p>
      </div>

      {isLoading ? <Cargando /> : error ? <ErrorCarga error={error} /> : d && (
        <>
          {d.por_anio.length > 0 && (
            <div className="mb-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {d.por_anio.slice(0, 4).map((a) => (
                <Tarjeta key={a.ejercicio} titulo={`Ejercicio ${a.ejercicio}`}>
                  <div className="cifra text-xl font-medium">{eur(a.pagado)}</div>
                  <div className="text-xs text-muted">pagado{a.devuelto > 0 && ` · ${eur(a.devuelto)} devuelto`}</div>
                </Tarjeta>
              ))}
            </div>
          )}
          <Tarjeta titulo="Presentadas">
            {d.declaraciones.length ? (
              <Tabla>
                <thead><tr><th>Modelo</th><th>Periodo</th><th>Presentada</th><th>Resultado</th><th className="num">Importe</th><th className="num">Frente a la app</th><th /></tr></thead>
                <tbody>
                  {d.declaraciones.map((x) => (
                    <tr key={x.id}>
                      <td className="whitespace-nowrap"><span className="cifra font-medium">{x.modelo}</span> <span className="text-muted">{x.nombre}</span></td>
                      <td className="whitespace-nowrap">{periodoTexto(x.periodo)} {x.ejercicio}</td>
                      <td className="cifra whitespace-nowrap text-muted">{x.fecha_presentacion ? fecha(x.fecha_presentacion) : '—'}</td>
                      <td><Etiqueta tono={RESULTADO[x.resultado].tono}>{RESULTADO[x.resultado].texto}</Etiqueta></td>
                      <td className="num font-medium"><Importe valor={x.importe} /></td>
                      <td className="num"><Diferencia d={x} /></td>
                      <td className="whitespace-nowrap text-right">
                        {x.tiene_pdf && (
                          <a href={`/api/declaraciones/${x.id}/pdf`} target="_blank" rel="noreferrer" aria-label="Ver justificante"
                            className="inline-flex rounded-lg p-1.5 text-muted hover:bg-panel-2 hover:text-ink"><FileText size={15} /></a>
                        )}
                        <Boton variante="fantasma" className="px-1.5 py-1.5" aria-label="Borrar" onClick={() => borrar.mutate(x.id)}><Trash2 size={14} /></Boton>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Tabla>
            ) : <Vacio>Sube los justificantes de tus 303, 130 y la renta para tenerlos aquí y compararlos con lo que calcula la app.</Vacio>}
          </Tarjeta>
        </>
      )}

      <Dialogo abierto={manual} onCerrar={() => setManual(false)} titulo="Añadir declaración a mano">
        <Formulario onEnviar={(v) => crear.mutateAsync(v)}>
          <Selector etiqueta="Modelo" name="modelo" defaultValue="303">
            <option value="303">303 · IVA</option><option value="130">130 · IRPF</option><option value="100">100 · Renta</option><option value="390">390 · Resumen IVA</option>
          </Selector>
          <Campo etiqueta="Ejercicio" name="ejercicio" inputMode="numeric" defaultValue={String(new Date().getFullYear() - 1)} required />
          <Selector etiqueta="Periodo" name="periodo" defaultValue="1T">
            <option value="1T">1º trimestre</option><option value="2T">2º trimestre</option><option value="3T">3º trimestre</option><option value="4T">4º trimestre</option><option value="0A">Anual</option>
          </Selector>
          <Selector etiqueta="Resultado" name="resultado" defaultValue="ingresar">
            <option value="ingresar">A ingresar</option><option value="devolver">A devolver</option><option value="compensar">A compensar</option><option value="cero">Sin actividad</option>
          </Selector>
          <Campo etiqueta="Importe (€)" name="importe" inputMode="decimal" required />
          <Campo etiqueta="Fecha de presentación" name="fecha_presentacion" type="date" />
        </Formulario>
      </Dialogo>
    </>
  )
}
