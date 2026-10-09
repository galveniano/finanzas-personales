import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, Plus, Upload } from 'lucide-react'
import { api } from '../lib/api'
import { eur, fecha } from '../lib/format'
import type { Autonomo, Declaracion, Declaraciones, Fuente, Prevision } from '../lib/tipos'
import { RentaEstimada, RentaPresentada } from '../components/Renta'
import SeccionHacienda from '../components/Hacienda'
import { num, opc, useAccion, useAvisos } from '../lib/utilidades'
import { useSubida } from '../lib/subida'
import type { Columna } from '../components/ui'
import { BorrarEnDosPasos, Boton, Cabecera, Campo, Cargando, Dialogo, Etiqueta, ErrorCarga, Formulario, Importe, Selector, SelectorAnio, TablaResponsive, Tarjeta } from '../components/ui'

const RESULTADO: Record<Declaracion['resultado'], { texto: string; tono: 'neutro' | 'bien' | 'aviso' | 'mal' }> = {
  ingresar: { texto: 'A ingresar', tono: 'aviso' }, domiciliar: { texto: 'Domiciliado', tono: 'aviso' },
  devolver: { texto: 'A devolver', tono: 'bien' }, compensar: { texto: 'A compensar', tono: 'bien' },
  negativa: { texto: 'Negativa', tono: 'neutro' }, cero: { texto: 'Sin actividad', tono: 'neutro' }, otro: { texto: 'Presentada', tono: 'neutro' },
}

const periodoTexto = (p: string) => (p === '0A' ? 'Anual' : p.endsWith('T') ? `${p[0]}º trim.` : p)

const COLUMNAS: Columna<Declaracion>[] = [
  { cabecera: 'Modelo', celda: (x) => <><span className="cifra font-medium">{x.modelo}</span> <span className="text-muted">{x.nombre}</span></>, claseTd: 'whitespace-nowrap', papel: 'titulo' },
  { cabecera: 'Periodo', celda: (x) => `${periodoTexto(x.periodo)} ${x.ejercicio}`, claseTd: 'whitespace-nowrap', papel: 'subtitulo' },
  { cabecera: 'Presentada', celda: (x) => <span className="cifra">{x.fecha_presentacion ? fecha(x.fecha_presentacion) : '—'}</span>, claseTd: 'whitespace-nowrap text-muted' },
  { cabecera: 'Resultado', celda: (x) => <Etiqueta tono={RESULTADO[x.resultado].tono}>{RESULTADO[x.resultado].texto}</Etiqueta> },
  { cabecera: 'Importe', num: true, claseTd: 'font-medium', fuerte: true,
    celda: (x) => <><Importe valor={x.importe} />{x.estimado != null && <span className="block text-xs font-normal text-muted">la app calculaba {eur(x.estimado)}</span>}</> },
]

function Modelo({ nombre, valor, fuente, exento }: { nombre: string; valor: number; fuente: Fuente; exento?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <dt className="whitespace-nowrap">{nombre}
        <span className={`block text-xs ${fuente === 'presentado' ? 'text-pos' : 'text-muted'}`}>{fuente === 'presentado' ? 'Presentado' : fuente === 'previsto' ? 'Previsto' : 'Estimado'}</span></dt>
      <dd className="font-semibold">{exento ? <span className="font-normal text-muted">Exento</span> : <Importe valor={valor} />}</dd>
    </div>
  )
}

function Trimestres() {
  const [hoy] = useState(() => new Date())
  const actual = hoy.getFullYear()
  const [anio, setAnio] = useState(actual)
  const { data: d, error } = useQuery({ queryKey: ['autonomo', anio], queryFn: () => api.get<Autonomo>(`/autonomo?anio=${anio}`) })
  const trimActual = anio === actual ? Math.floor(hoy.getMonth() / 3) + 1 : 0
  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">IVA e IRPF por trimestre</h2>
        <SelectorAnio valor={anio} onCambiar={setAnio} />
      </div>
      {d ? <>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {d.trimestres.map((t) => (
            <Tarjeta key={t.trimestre} className={t.trimestre === trimActual ? 'ring-2 ring-accent' : ''}
              titulo={`${t.trimestre}º trimestre`} accion={<span className="text-xs text-muted">{t.plazo}</span>}>
              <dl className="space-y-2 text-sm">
                <Modelo nombre="IVA · 303" valor={t.iva_resultado} fuente={t.iva_fuente} />
                <Modelo nombre="IRPF · 130" valor={t.irpf_resultado} fuente={t.irpf_fuente} exento={t.exento_130} />
              </dl>
            </Tarjeta>
          ))}
        </div>
        <p className="mt-3 text-sm text-muted">El 130 es el 20 % de lo que ganas en el año menos retenciones y lo ya pagado; el resto se ajusta en la renta.
          Lo no presentado se prevé con tus tarifas y los días que trabajas.</p>
        {d.trimestres[3].notas.map((n) => <p key={n} className="mt-2 text-sm text-muted">{n}</p>)}
      </> : error ? <ErrorCarga error={error} /> : <Cargando />}
    </section>
  )
}

function Rentas() {
  const { data: d, error } = useQuery({ queryKey: ['prevision'], queryFn: () => api.get<Prevision>('/prevision') })
  if (error) return <section className="mt-8"><h2 className="mb-3 text-lg font-semibold">Renta</h2><ErrorCarga error={error} /></section>
  if (!d || (!d.renta_presentada && !d.anios.length)) return null
  return (
    <section className="mt-8">
      <h2 className="mb-3 text-lg font-semibold">Renta</h2>
      <div className={`grid gap-4 md:grid-cols-2 ${d.renta_presentada && d.anios.length > 1 ? 'xl:grid-cols-3' : ''}`}>
        {d.renta_presentada && <RentaPresentada r={d.renta_presentada} />}
        {d.anios.map((r) => <RentaEstimada key={r.anio} r={r} />)}
      </div>
      <p className="mt-3 text-xs text-muted">Estimada con la escala general del IRPF, tu nómina, lo que facturas y el alquiler, ajustada con tu última renta presentada. El borrador real puede variar.</p>
    </section>
  )
}

// Modelos anuales: el periodo es «0A», como en los justificantes de Hacienda
const ANUALES = new Set(['100', '390'])

function FormDeclaracion({ onEnviar }: { onEnviar: (v: Record<string, string>) => Promise<unknown> }) {
  const [ejercicio] = useState(() => String(new Date().getFullYear() - 1))
  const [periodo, setPeriodo] = useState('1T')
  return (
    <Formulario onEnviar={onEnviar}>
      <Selector etiqueta="Modelo" name="modelo" defaultValue="303"
        onChange={(e) => setPeriodo(ANUALES.has(e.target.value) ? '0A' : periodo === '0A' ? '1T' : periodo)}>
        <option value="303">303 · IVA</option><option value="130">130 · IRPF</option><option value="100">100 · Renta</option><option value="390">390 · Resumen IVA</option>
      </Selector>
      <Campo etiqueta="Ejercicio" name="ejercicio" inputMode="numeric" defaultValue={ejercicio} required />
      <Selector etiqueta="Periodo" name="periodo" value={periodo} onChange={(e) => setPeriodo(e.target.value)}>
        <option value="1T">1º trimestre</option><option value="2T">2º trimestre</option><option value="3T">3º trimestre</option><option value="4T">4º trimestre</option><option value="0A">Anual</option>
      </Selector>
      <Selector etiqueta="Resultado" name="resultado" defaultValue="ingresar">
        <option value="ingresar">A ingresar</option><option value="devolver">A devolver</option><option value="compensar">A compensar</option><option value="cero">Sin actividad</option>
      </Selector>
      <Campo etiqueta="Importe (€)" name="importe" inputMode="decimal" required />
      <Campo etiqueta="Fecha de presentación" name="fecha_presentacion" type="date" />
      <Campo etiqueta="Notas" name="notas" className="sm:col-span-2" placeholder="Opcional" />
    </Formulario>
  )
}

export default function Impuestos() {
  const avisar = useAvisos()
  const [manual, setManual] = useState(false)
  const { data: d, isLoading, error } = useQuery({ queryKey: ['declaraciones'], queryFn: () => api.get<Declaraciones>('/declaraciones') })

  const subir = useAccion(async (ficheros: File[]) => {
    const fd = new FormData()
    ficheros.forEach((f) => fd.append('ficheros', f))
    const r = await api.post<{ resultados: { fichero: string; ok: boolean; mensaje: string }[] }>('/declaraciones/pdf', fd)
    const bien = r.resultados.filter((x) => x.ok)
    const mal = r.resultados.filter((x) => !x.ok)
    if (bien.length) avisar(bien.length === 1 ? bien[0].mensaje : `${bien.length} declaraciones guardadas`)
    mal.forEach((x) => avisar(`${x.fichero}: ${x.mensaje}`, 'error'))
  })
  const crear = useAccion((v: Record<string, string>) => api.post('/declaraciones', {
    modelo: v.modelo, ejercicio: Number(v.ejercicio), periodo: v.periodo, resultado: v.resultado,
    importe: num(v.importe) ?? 0, fecha_presentacion: opc(v.fecha_presentacion) ?? null, notas: v.notas ?? '',
  }).then(() => setManual(false)), 'Declaración guardada')
  const borrar = useAccion((id: number) => api.del(`/declaraciones/${id}`), 'Borrada')

  const { input, elegir, zona, arrastrando } = useSubida({
    accept: 'application/pdf,.pdf,.txt,text/plain', multiple: true, filtro: (f) => /\.(pdf|txt)$/i.test(f.name) || f.type === 'application/pdf',
    onFicheros: (ficheros) => { if (!subir.isPending) subir.mutate(ficheros) },
  })

  return (
    <>
      <Cabecera titulo="Impuestos" subtitulo="IVA e IRPF de cada trimestre, la renta y lo que ya has presentado">
        <Boton variante="secundario" onClick={() => setManual(true)}><Plus size={16} />A mano</Boton>
        <Boton onClick={elegir} disabled={subir.isPending}><Upload size={16} />{subir.isPending ? 'Leyendo…' : 'Subir declaraciones'}</Boton>
      </Cabecera>
      {input}

      <Trimestres />
      <SeccionHacienda />
      <Rentas />

      <div className="mt-8" {...zona}>
      {isLoading ? <Cargando /> : error ? <ErrorCarga error={error} /> : d && (
        <>
          <Tarjeta titulo="Presentadas" className={arrastrando ? 'ring-2 ring-accent' : ''}
            accion={<span className="text-xs text-muted">Arrastra aquí los PDF o .txt de Hacienda</span>}>
            <TablaResponsive filas={d.declaraciones} columnas={COLUMNAS} clave={(x) => x.id}
              acciones={(x) => <>
                {x.tiene_pdf && (
                  <a href={`/api/declaraciones/${x.id}/pdf`} target="_blank" rel="noreferrer" aria-label="Ver justificante"
                    className="inline-flex rounded-lg p-1.5 text-muted hover:bg-panel-2 hover:text-ink"><FileText size={15} /></a>
                )}
                <BorrarEnDosPasos etiqueta={`el modelo ${x.modelo} de ${periodoTexto(x.periodo)} ${x.ejercicio}`} disabled={borrar.isPending} onBorrar={() => borrar.mutate(x.id)} />
              </>}
              vacio="Sube los justificantes de tus 303, 130 y la renta (PDF o .txt). Los antiguos se descargan en la sede de Hacienda con Cl@ve, en «Mis expedientes»." />
          </Tarjeta>
        </>
      )}
      </div>

      <Dialogo abierto={manual} onCerrar={() => setManual(false)} titulo="Añadir declaración a mano">
        <FormDeclaracion onEnviar={(v) => crear.mutateAsync(v)} />
      </Dialogo>
    </>
  )
}
