import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useIsFetching, useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { FileText, Pencil, Plus, Upload } from 'lucide-react'
import { api } from '../lib/api'
import { eur, fecha } from '../lib/format'
import type { Autonomo, Declaracion, Declaraciones, Fuente, Prevision, RentaPrevista, Trimestre } from '../lib/tipos'
import { RentaEstimada, RentaPresentada } from '../components/Renta'
import SeccionHacienda from '../components/Hacienda'
import { num, opc, useAccion, useAvisos } from '../lib/utilidades'
import { useSubida } from '../lib/subida'
import type { Columna } from '../components/ui'
import { BorrarEnDosPasos, Boton, Cabecera, Campo, Cargando, Casilla, Dialogo, Etiqueta, ErrorCarga, Formulario, Importe, Selector, SelectorAnio, TablaResponsive, Tarjeta, Vacio } from '../components/ui'

const RESULTADO: Record<Declaracion['resultado'], { texto: string; tono: 'neutro' | 'bien' | 'aviso' | 'mal' }> = {
  ingresar: { texto: 'A ingresar', tono: 'aviso' }, domiciliar: { texto: 'Domiciliado', tono: 'aviso' },
  devolver: { texto: 'A devolver', tono: 'bien' }, compensar: { texto: 'A compensar', tono: 'bien' },
  negativa: { texto: 'Negativa', tono: 'neutro' }, cero: { texto: 'Sin actividad', tono: 'neutro' }, otro: { texto: 'Presentada', tono: 'neutro' },
}

const periodoTexto = (p: string) => (p === '0A' ? 'Anual' : p.endsWith('T') ? `${p[0]}º trim.` : p)
const justificanteTexto = (x: Declaracion) => (x.justificante ? `Justificante ${x.justificante}${x.csv ? ` · CSV ${x.csv}` : ''}` : '')
const NOTA_EXENTO = 'En el año anterior más del 70 % de tus ingresos llevaba retención: no estás obligado a presentar el 130.'
// Secciones a las que llevan los avisos de Inicio (?ver=)
const VISTAS = new Set(['trimestres', 'hucha', 'renta', 'presentadas'])

const COLUMNAS: Columna<Declaracion>[] = [
  { cabecera: 'Modelo', papel: 'titulo', claseTd: 'whitespace-nowrap',
    celda: (x) => <span title={justificanteTexto(x) || undefined}><span className="cifra font-medium">{x.modelo}</span> <span className="text-muted">{x.nombre}</span></span> },
  { cabecera: 'Periodo', celda: (x) => `${periodoTexto(x.periodo)} ${x.ejercicio}`, claseTd: 'whitespace-nowrap', papel: 'subtitulo' },
  { cabecera: 'Presentada', celda: (x) => <span className="cifra">{x.fecha_presentacion ? fecha(x.fecha_presentacion) : '—'}</span>, claseTd: 'whitespace-nowrap text-muted' },
  { cabecera: 'Resultado', celda: (x) => <Etiqueta tono={RESULTADO[x.resultado].tono}>{RESULTADO[x.resultado].texto}</Etiqueta> },
  { cabecera: 'Importe', num: true, claseTd: 'font-medium', fuerte: true,
    celda: (x) => <span className="inline-block text-right"><Importe valor={x.importe} />
      {x.estimado != null && <span className="block text-xs font-normal text-muted">la app calculaba {eur(x.estimado)}</span>}
      {x.notas && <span className="block max-w-56 truncate text-xs font-normal text-muted" title={x.notas}>{x.notas}</span>}</span> },
]

/** Resultado de un modelo en la tarjeta del trimestre. En negativo es a compensar (se enseña en positivo con su etiqueta). */
function Modelo({ nombre, valor, fuente, exento }: { nombre: string; valor: number; fuente: Fuente; exento?: boolean }) {
  const compensar = !exento && valor < -0.005
  return (
    <div className="flex items-start justify-between gap-2">
      <dt className="whitespace-nowrap">{nombre}
        <span className={`block text-xs ${fuente === 'presentado' ? 'text-pos' : 'text-muted'}`}>{fuente === 'presentado' ? 'Presentado' : fuente === 'previsto' ? 'Previsto' : 'Estimado'}</span></dt>
      <dd className="text-right font-semibold">
        {exento ? <span className="font-normal text-muted">Exento</span> : <Importe valor={compensar ? -valor : valor} />}
        {compensar && <span className="block"><Etiqueta tono="bien">A compensar</Etiqueta></span>}
      </dd>
    </div>
  )
}

function Linea({ texto, valor, fuerte }: { texto: string; valor: ReactNode; fuerte?: boolean }) {
  return <div className={`flex justify-between gap-3 py-0.5 ${fuerte ? 'font-medium' : ''}`}><span className={fuerte ? undefined : 'text-muted'}>{texto}</span>{typeof valor === 'number' ? <Importe valor={valor} /> : valor}</div>
}

/** Las casillas que la app calcula para el 303 y el 130 del trimestre, y lo que calculaba si ya está presentado. */
function Casillas({ t }: { t: Trimestre }) {
  const calculaba = (fuente: Fuente, estimado: number | null) => fuente === 'presentado' && estimado != null
    ? <span className="block text-xs font-normal text-muted">la app calculaba {eur(Math.abs(estimado))}{estimado < -0.005 && ' a compensar'}</span> : null
  return (
    <details className="mt-3 text-xs">
      <summary className="cursor-pointer font-medium text-muted">Ver casillas</summary>
      <div className="mt-2">
        <div className="mb-1 font-semibold">303 · IVA</div>
        <Linea texto="Base repercutida" valor={t.base} />
        <Linea texto="IVA repercutido" valor={t.iva_repercutido} />
        <Linea texto="IVA soportado deducible" valor={-t.iva_soportado} />
        <Linea texto={t.iva_resultado < -0.005 ? 'A compensar' : 'Resultado'} fuerte
          valor={<span className="text-right"><Importe valor={Math.abs(t.iva_resultado)} />{calculaba(t.iva_fuente, t.iva_estimado)}</span>} />
        {t.base_prevista != null && <Linea texto="Base prevista del trimestre" valor={t.base_prevista} />}
        <div className="mt-3 mb-1 font-semibold">130 · IRPF</div>
        {t.exento_130 ? <p className="text-muted">Exento: no estás obligado a presentarlo.</p> : <>
          {t.ingresos_acumulados != null && <Linea texto="Ingresos acumulados del año" valor={t.ingresos_acumulados} />}
          <Linea texto="Rendimiento acumulado" valor={t.rendimiento_acumulado} />
          <Linea texto="El 20 % del rendimiento" valor={t.rendimiento_acumulado * 0.2} />
          <Linea texto="Retenciones acumuladas" valor={-t.retenciones_acumuladas} />
          <Linea texto="Resultado" fuerte valor={<span className="text-right"><Importe valor={t.irpf_resultado} />{calculaba(t.irpf_fuente, t.irpf_estimado)}</span>} />
        </>}
        <p className="mt-2 text-muted">El 130 acumula desde enero y resta lo pagado en trimestres anteriores; «la app calculaba» compara con lo que presentaste.</p>
      </div>
    </details>
  )
}

/** La regla de `autonomo.trimestre_a_pagar` del backend (la que usa Inicio): el trimestre anterior mientras dura su
 *  plazo (hasta el 20 de abril, julio y octubre, o el 30 de enero) y, pasado el plazo, el que está en curso. */
function trimestreAPagar(hoy: Date): { anio: number; t: number } {
  const anio = hoy.getFullYear(), mes = hoy.getMonth() + 1, t = Math.floor((mes - 1) / 3) + 1
  if ([1, 4, 7, 10].includes(mes) && hoy.getDate() <= (mes === 1 ? 30 : 20)) return t === 1 ? { anio: anio - 1, t: 4 } : { anio, t: t - 1 }
  return { anio, t }
}
/** Último día para presentar el 303 y el 130 del trimestre (como `autonomo.vencimiento`), en dd/mm. */
const vencimiento = (t: number) => (t === 4 ? '30/01' : `20/${String(3 * t + 1).padStart(2, '0')}`)
const presentadoEntero = (t: Trimestre) => t.iva_fuente === 'presentado' && (t.irpf_fuente === 'presentado' || t.exento_130)

function Trimestres() {
  const [hoy] = useState(() => new Date())
  const actual = hoy.getFullYear()
  const [anio, setAnio] = useState(actual)
  const { data: d, error } = useQuery({ queryKey: ['autonomo', anio], queryFn: () => api.get<Autonomo>(`/autonomo?anio=${anio}`) })
  const trimActual = anio === actual ? Math.floor(hoy.getMonth() / 3) + 1 : 0
  const aPagar = trimestreAPagar(hoy)
  const trimPagar = anio === aPagar.anio ? aPagar.t : 0
  const notas = d ? [...new Set(d.trimestres.flatMap((t) => t.notas.length ? t.notas : t.exento_130 ? [NOTA_EXENTO] : []))] : []
  return (
    <section id="trimestres" className="scroll-mt-16">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">IVA e IRPF por trimestre</h2>
        <SelectorAnio valor={anio} onCambiar={setAnio} />
      </div>
      {d ? <>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {d.trimestres.map((t) => (
            <Tarjeta key={t.trimestre} className={t.trimestre === trimPagar ? 'ring-2 ring-accent' : ''}
              titulo={`${t.trimestre}º trimestre`}
              accion={<span className="flex flex-wrap items-center justify-end gap-1.5 text-xs text-muted">
                {t.trimestre === trimPagar && (presentadoEntero(t) ? <Etiqueta tono="bien">Presentado</Etiqueta> : <Etiqueta tono="aviso">Toca pagar · hasta el {vencimiento(t.trimestre)}</Etiqueta>)}
                {t.trimestre === trimActual && <Etiqueta tono="acento">En curso</Etiqueta>}
                <span className="whitespace-nowrap">{t.plazo}</span>
              </span>}>
              <dl className="space-y-2 text-sm">
                <Modelo nombre="IVA · 303" valor={t.iva_resultado} fuente={t.iva_fuente} />
                <Modelo nombre="IRPF · 130" valor={t.irpf_resultado} fuente={t.irpf_fuente} exento={t.exento_130} />
              </dl>
              <Casillas t={t} />
            </Tarjeta>
          ))}
        </div>
        <p className="mt-3 text-sm">
          {d.pagado_iva < -0.005
            ? <>En {d.anio} llevas pagados <strong className="cifra">{eur(d.pagado_irpf)}</strong> de IRPF y tienes <strong className="cifra">{eur(-d.pagado_iva)}</strong> de IVA a compensar (según las declaraciones que has subido).</>
            : d.pagado_iva > 0 || d.pagado_irpf > 0
              ? <>En {d.anio} llevas pagados <strong className="cifra">{eur(d.pagado_iva)}</strong> de IVA y <strong className="cifra">{eur(d.pagado_irpf)}</strong> de IRPF (según las declaraciones que has subido).</>
              : <span className="text-muted">En {d.anio} no consta ningún pago de IVA ni de IRPF: sube los justificantes de tus 303 y 130 para verlos aquí.</span>}
        </p>
        <p className="mt-2 text-sm text-muted">El 130 es el 20 % de lo que ganas en el año menos retenciones y lo ya pagado; el resto se ajusta en la renta.
          Lo no presentado se prevé con tus tarifas y los días que trabajas.</p>
        {notas.map((n) => <p key={n} className="mt-2 text-sm text-muted">{n}</p>)}
      </> : error ? <ErrorCarga error={error} /> : <Cargando />}
    </section>
  )
}

function Rentas() {
  // anios_todos trae también el año pasado mientras su renta siga en la previsión: así se compara con la presentada
  const { data: d, error } = useQuery({ queryKey: ['prevision'], queryFn: () => api.get<Prevision & { anios_todos?: RentaPrevista[] }>('/prevision') })
  const presentada = d?.renta_presentada
  const estimadaDeLaPresentada = presentada ? d?.anios_todos?.find((a) => a.anio === presentada.anio) : undefined
  // Del más antiguo al más reciente: la del año pasado (a presentar en junio) antes que la de este año
  const anios = d ? [...d.anios].sort((a, b) => a.anio - b.anio) : []
  const tarjetas = (presentada ? 1 : 0) + anios.length
  return (
    <section id="renta" className="mt-8 scroll-mt-16">
      <h2 className="mb-3 text-lg font-semibold">Renta</h2>
      {error ? <ErrorCarga error={error} /> : !d ? <Cargando /> : (!presentada && !d.anios.length) ? (
        <Vacio>Pon tu sueldo y tus tarifas en Ingresos para estimar la renta, o sube el PDF de tu última renta para verla aquí.</Vacio>
      ) : <>
        <div className={`grid gap-4 md:grid-cols-2 ${tarjetas >= 3 ? 'xl:grid-cols-3' : ''}`}>
          {presentada && <RentaPresentada r={presentada} estimada={estimadaDeLaPresentada} />}
          {anios.map((r) => <RentaEstimada key={r.anio} r={r} />)}
        </div>
        <p className="mt-3 text-xs text-muted">Estimada con la escala general del IRPF, tu nómina, lo que facturas y el alquiler, ajustada con tu última renta presentada. El borrador real puede variar.</p>
      </>}
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
      <Casilla etiqueta="Es una complementaria de un modelo que ya tengo apuntado (se suma a lo pagado)" name="complementaria" className="sm:col-span-2" />
    </Formulario>
  )
}

/** Editar una declaración ya apuntada: resultado, importe, fecha y notas. El justificante no se toca. */
function FormEditar({ x, onEnviar }: { x: Declaracion; onEnviar: (v: Record<string, string>) => Promise<unknown> }) {
  return (
    <>
      <p className="mb-4 text-sm text-muted">Modelo {x.modelo} · {periodoTexto(x.periodo)} {x.ejercicio}{justificanteTexto(x) && <span className="block text-xs">{justificanteTexto(x)}</span>}</p>
      <Formulario onEnviar={onEnviar}>
        <Selector etiqueta="Resultado" name="resultado" defaultValue={x.resultado}>
          <option value="ingresar">A ingresar</option><option value="domiciliar">Domiciliado</option><option value="devolver">A devolver</option>
          <option value="compensar">A compensar</option><option value="negativa">Negativa</option><option value="cero">Sin actividad</option><option value="otro">Otro</option>
        </Selector>
        <Campo etiqueta="Importe (€)" name="importe" inputMode="decimal" defaultValue={String(Math.abs(x.importe)).replace('.', ',')} required ayuda="Sin signo: lo pone el resultado" />
        <Campo etiqueta="Fecha de presentación" name="fecha_presentacion" type="date" defaultValue={x.fecha_presentacion ?? ''} />
        <Campo etiqueta="Notas" name="notas" className="sm:col-span-2" defaultValue={x.notas} placeholder="Opcional" />
      </Formulario>
    </>
  )
}

const COLUMNAS_ANIO: Columna<Declaraciones['por_anio'][number]>[] = [
  { cabecera: 'Ejercicio', papel: 'titulo', celda: (a) => <span className="cifra font-medium">{a.ejercicio}</span> },
  { cabecera: 'Por modelo', papel: 'subtitulo', claseTd: 'text-xs text-muted',
    celda: (a) => Object.entries(a.por_modelo).map(([m, v]) => <span key={m} className="mr-2 inline-block whitespace-nowrap"><span className="cifra">{m}</span> <Importe valor={v} /></span>) },
  { cabecera: 'Pagado', num: true, celda: (a) => <Importe valor={a.pagado} /> },
  { cabecera: 'Devuelto', num: true, celda: (a) => <Importe valor={a.devuelto} /> },
  { cabecera: 'Neto', num: true, fuerte: true, claseTd: 'font-medium', celda: (a) => <Importe valor={a.neto} /> },
]

export default function Impuestos() {
  const avisar = useAvisos()
  const [params] = useSearchParams()
  const ver = params.get('ver')
  const cargando = useIsFetching() > 0
  const yaVisto = useRef<string | null>(null)
  const [manual, setManual] = useState(false)
  const [editar, setEditar] = useState<Declaracion | null>(null)
  const [ejercicio, setEjercicio] = useState<number | null>(null)
  const { data: d, isLoading, error } = useQuery({ queryKey: ['declaraciones'], queryFn: () => api.get<Declaraciones>('/declaraciones') })

  // Los avisos de Inicio llegan con ?ver=: al cargar todo, bajar a esa sección (una vez por aviso)
  useEffect(() => {
    if (!ver || !VISTAS.has(ver) || cargando || yaVisto.current === ver) return
    yaVisto.current = ver
    const t = setTimeout(() => document.getElementById(ver)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100)
    return () => clearTimeout(t)
  }, [ver, cargando])

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
    complementaria: v.complementaria === 'on',
  }).then(() => setManual(false)), 'Declaración guardada')
  const guardar = useAccion((v: Record<string, string>) => api.patch(`/declaraciones/${editar!.id}`, {
    resultado: v.resultado, importe: num(v.importe) ?? 0, fecha_presentacion: opc(v.fecha_presentacion) ?? null, notas: v.notas ?? '',
  }).then(() => setEditar(null)), 'Declaración actualizada')
  const borrar = useAccion((id: number) => api.del(`/declaraciones/${id}`), 'Borrada')

  const { input, elegir, zona, arrastrando } = useSubida({
    accept: 'application/pdf,.pdf,.txt,text/plain', multiple: true, filtro: (f) => /\.(pdf|txt)$/i.test(f.name) || f.type === 'application/pdf',
    onFicheros: (ficheros) => { if (!subir.isPending) subir.mutate(ficheros) },
  })
  const ejercicios = d ? [...new Set(d.declaraciones.map((x) => x.ejercicio))].sort((a, b) => b - a) : []
  const filtradas = d ? d.declaraciones.filter((x) => ejercicio == null || x.ejercicio === ejercicio) : []

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

      <section id="presentadas" className="mt-8 scroll-mt-16" {...zona}>
        <h2 className="mb-3 text-lg font-semibold">Lo que has presentado</h2>
        {isLoading ? <Cargando /> : error ? <ErrorCarga error={error} /> : d && (
          <div className="grid gap-4">
            {d.por_anio.length > 0 && (
              <Tarjeta titulo="Pagado a Hacienda por año" accion={<span className="text-xs text-muted">Según las declaraciones subidas</span>}>
                <TablaResponsive filas={d.por_anio} columnas={COLUMNAS_ANIO} clave={(a) => a.ejercicio}
                  acciones={(a) => <Boton variante="fantasma" className="px-2 py-1 text-xs" aria-pressed={ejercicio === a.ejercicio}
                    onClick={() => setEjercicio(ejercicio === a.ejercicio ? null : a.ejercicio)}>{ejercicio === a.ejercicio ? 'Ver todas' : 'Ver'}</Boton>} />
                <p className="mt-3 text-xs text-muted">«Devuelto» es lo que Hacienda te devolvió; en «por modelo» cada modelo va en neto (negativo si te devolvieron). Lo compensado no cuenta como devuelto.</p>
              </Tarjeta>
            )}
            <Tarjeta titulo="Presentadas" className={arrastrando ? 'ring-2 ring-accent' : ''}
              accion={<div className="flex items-center gap-3">
                <span className="hidden text-xs text-muted sm:inline">Arrastra aquí los PDF o .txt de Hacienda</span>
                {ejercicios.length > 1 && (
                  <Selector aria-label="Ejercicio" className="!w-28" value={ejercicio ?? ''} onChange={(e) => setEjercicio(e.target.value ? Number(e.target.value) : null)}>
                    <option value="">Todos</option>
                    {ejercicios.map((a) => <option key={a} value={a}>{a}</option>)}
                  </Selector>
                )}
              </div>}>
              <TablaResponsive filas={filtradas} columnas={COLUMNAS} clave={(x) => x.id}
                acciones={(x) => <>
                  {x.tiene_pdf && (
                    <a href={`/api/declaraciones/${x.id}/pdf`} target="_blank" rel="noreferrer" aria-label="Ver justificante" title={justificanteTexto(x) || 'Ver justificante'}
                      className="inline-flex rounded-lg p-1.5 text-muted hover:bg-panel-2 hover:text-ink"><FileText size={15} /></a>
                  )}
                  <Boton variante="fantasma" className="px-2 py-1" aria-label={`Editar el modelo ${x.modelo} de ${periodoTexto(x.periodo)} ${x.ejercicio}`} title="Editar" onClick={() => setEditar(x)}><Pencil size={14} /></Boton>
                  <BorrarEnDosPasos etiqueta={`el modelo ${x.modelo} de ${periodoTexto(x.periodo)} ${x.ejercicio}`} disabled={borrar.isPending} onBorrar={() => borrar.mutate(x.id)} />
                </>}
                vacio={ejercicio != null ? `No hay declaraciones de ${ejercicio}.` : 'Sube los justificantes de tus 303, 130 y la renta (PDF o .txt). Los antiguos se descargan en la sede de Hacienda con Cl@ve, en «Mis expedientes».'} />
            </Tarjeta>
          </div>
        )}
      </section>

      <Dialogo abierto={manual} onCerrar={() => setManual(false)} titulo="Añadir declaración a mano">
        <FormDeclaracion onEnviar={(v) => crear.mutateAsync(v)} />
      </Dialogo>
      <Dialogo abierto={editar != null} onCerrar={() => setEditar(null)} titulo="Editar declaración">
        {editar && <FormEditar x={editar} onEnviar={(v) => guardar.mutateAsync(v)} />}
      </Dialogo>
    </>
  )
}
