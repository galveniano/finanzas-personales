import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Pencil } from 'lucide-react'
import { api } from '../../lib/api'
import { eur, fecha, hoyISO, pct } from '../../lib/format'
import type { CuadroHipoteca, Deuda, Inmueble, SimulacionAmortizacion } from '../../lib/tipos'
import { num, useAccion } from '../../lib/utilidades'
import type { Columna } from '../ui'
import { Barra, BorrarEnDosPasos, Boton, Campo, Dato, Etiqueta, Fila, Importe, Segmentos, TablaResponsive } from '../ui'
import { mesAnio, mesesTexto } from './comun'
import type { Accion } from './comun'

const MODOS = [{ valor: 'plazo', texto: 'Reducir plazo' }, { valor: 'cuota', texto: 'Reducir cuota' }] as const
type Modo = typeof MODOS[number]['valor']

const COLUMNAS: Columna<CuadroHipoteca['anios'][number]>[] = [
  { cabecera: 'Año', celda: (a) => a.anio, claseTd: 'cifra font-medium', papel: 'titulo' },
  { cabecera: 'Cuotas', celda: (a) => a.cuotas, num: true, claseTd: 'cifra' },
  { cabecera: 'Intereses', celda: (a) => <Importe valor={a.intereses} />, num: true },
  { cabecera: 'Amortizado', celda: (a) => <Importe valor={a.amortizado} />, num: true },
  { cabecera: 'Pendiente a final de año', celda: (a) => <Importe valor={a.pendiente_fin} />, num: true, claseTd: 'font-medium', fuerte: true },
]

/** Cuadro por años y mini simulador de amortización anticipada de una deuda; se carga al abrir el desplegable. */
export function CuadroYSimulador({ d }: { d: Deuda }) {
  const [abierto, setAbierto] = useState(false)
  const [modo, setModo] = useState<Modo>('plazo')
  const [texto, setTexto] = useState('')
  const [importe, setImporte] = useState<number | undefined>()
  useEffect(() => {
    const t = setTimeout(() => setImporte(num(texto)), 400)
    return () => clearTimeout(t)
  }, [texto])
  const cuadro = useQuery({ queryKey: ['cuadro', d.id], queryFn: () => api.get<CuadroHipoteca>(`/deudas/${d.id}/cuadro`), enabled: abierto })
  const sim = useQuery({
    queryKey: ['simular', d.id, importe ?? null, modo], enabled: abierto && !!importe && importe > 0, retry: false,
    queryFn: () => api.get<SimulacionAmortizacion>(`/deudas/${d.id}/simular?importe=${importe}&modo=${modo}`),
    placeholderData: (prev) => prev,
  })
  const r = cuadro.data?.resumen
  const s = sim.data
  return (
    <details className="mt-3" onToggle={(e) => setAbierto((e.target as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-sm font-medium text-accent">Cuadro y amortización anticipada</summary>
      {cuadro.error && <p className="mt-2 text-xs text-neg">{cuadro.error.message}</p>}
      {r && cuadro.data && (
        <div className="mt-3">
          <p className="mb-3 text-xs text-muted">
            Quedan {r.cuotas_restantes} cuotas de {eur(r.cuota)} hasta {mesAnio(r.fin)}: {eur(r.intereses_restantes)} de intereses por pagar
            {r.desde_saldo_real ? ', contando desde el pendiente real que diste' : ''}. Con el interés de hoy; si es variable, irá cambiando.
          </p>
          <TablaResponsive filas={cuadro.data.anios} columnas={COLUMNAS} clave={(a) => a.anio} />
        </div>
      )}
      <div className="mt-4 rounded-xl border border-line p-4">
        <h4 className="text-sm font-semibold">Si amortizas hoy…</h4>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <Campo etiqueta="Importe (€)" inputMode="decimal" value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="10.000" className="w-40" />
          <Segmentos etiqueta="Qué reducir" opciones={MODOS} valor={modo} onCambiar={setModo} pequeno />
        </div>
        {sim.error && <p className="mt-3 text-xs text-neg" role="alert">{sim.error.message}</p>}
        {s && !sim.error && (
          <div className={sim.isFetching ? 'opacity-60' : undefined}>
            <div className="mt-4 grid gap-4 sm:grid-cols-3">
              <Dato etiqueta="Intereses que ahorras" valor={eur(s.ahorro_intereses)} tono="pos" nota={`De ${eur(s.intereses_restantes)} que quedan por pagar`} />
              {s.modo === 'plazo'
                ? <Dato etiqueta="Te quitas" valor={mesesTexto(s.meses_menos)} nota={`Con la misma cuota de ${eur(s.cuota_actual)}`} />
                : <Dato etiqueta="Nueva cuota" valor={eur(s.nueva_cuota)} nota={`Antes ${eur(s.cuota_actual)} al mes`} />}
              <Dato etiqueta="Acabarías en" valor={mesAnio(s.nuevo_fin)}
                nota={s.modo === 'plazo' ? `En vez de ${mesAnio(s.fin_actual)}` : 'La misma fecha, pagando menos cada mes'} />
            </div>
            <p className="mt-3 text-xs text-muted">{s.fiscal.nota}</p>
            {s.comparativa && (
              <p className="mt-1 text-xs text-muted">
                Ese dinero en {s.comparativa.cuenta}, al {pct(s.comparativa.rentabilidad_esperada)} anual que espera Indexa, rendiría
                unos {eur(s.comparativa.rendiria)} ({eur(s.comparativa.rendiria_neto)} tras el IRPF del ahorro) en los {mesesTexto(s.comparativa.meses)} que
                quedan: {s.comparativa.mejor === 'invertir' ? 'sobre el papel sale mejor invertirlo' : 'sale mejor amortizar'}
                {s.fiscal.deducible ? ` (comparado con los ${eur(s.fiscal.ahorro_neto)} de ahorro real).` : '.'}
              </p>
            )}
            {s.notas.map((n) => <p key={n} className="mt-1 text-xs text-muted">{n}</p>)}
          </div>
        )}
      </div>
    </details>
  )
}

/** Bloque de una hipoteca en la ficha del inmueble: lo amortizado, la cuota, el pendiente y su cuadro. */
export function Hipoteca({ h, anio, inmueble, abrir }: { h: Deuda; anio: number; inmueble: Inmueble; abrir: (a: Accion) => void }) {
  const borrar = useAccion((id: number) => api.del(`/deudas/${id}`), 'Hipoteca borrada')
  const esteAnio = anio === Number(hoyISO().slice(0, 4))
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="min-w-0 truncate text-sm font-semibold">
          {h.nombre}{h.entidad && ` · ${h.entidad}`}{h.futura && <> <Etiqueta tono="acento">Prevista</Etiqueta></>}
        </h3>
        <span className="flex shrink-0 items-center gap-1">
          <Boton variante="fantasma" className="px-2 py-1" onClick={() => abrir({ tipo: 'editarDeuda', inmueble, deuda: h })} aria-label={`Editar ${h.nombre}`}><Pencil size={14} /></Boton>
          <BorrarEnDosPasos etiqueta={`la hipoteca ${h.nombre}`} disabled={borrar.isPending} onBorrar={() => borrar.mutate(h.id)} />
        </span>
      </div>
      {h.futura ? (
        <>
          <Fila etiqueta="Capital que pedirás" valor={h.capital_inicial} />
          <Fila etiqueta={`Cuota prevista (${pct(h.tipo_interes_anual, 3)}, ${h.plazo_meses} meses)`} valor={h.cuota} />
          <Fila etiqueta="Empieza" valor={<span className="cifra">{fecha(h.fecha_inicio)}</span>} />
          <p className="mt-2 text-xs text-muted">Hasta entonces no cuenta como deuda; el capital y sus cuotas ya cuentan en el Plan. Al escriturar la obra nueva, empezará ese día.</p>
        </>
      ) : (
        <>
          <div className="mb-1 flex justify-between text-xs text-muted"><span>{eur(h.capital_inicial - h.pendiente)} amortizado</span><span>{eur(h.capital_inicial)}</span></div>
          <Barra valor={h.capital_inicial - h.pendiente} max={h.capital_inicial} />
          <Fila etiqueta="Cuota mensual" valor={h.cuota} />
          <Fila etiqueta={`Interés ${pct(h.tipo_interes_anual, 3)}, intereses ${esteAnio ? 'este año' : `de ${anio}`}`} valor={h.intereses_anio} />
          <Fila etiqueta="Pendiente hoy" valor={h.pendiente} fuerte />
          <p className="mt-1 text-xs text-muted">
            {h.saldo_fecha
              ? `Pendiente real a ${fecha(h.saldo_fecha)}: ${eur(h.saldo_pendiente_manual)}; desde ahí baja con cada cuota al interés actual.`
              : 'Según el cuadro de la firma; si el interés es variable, edita la hipoteca y pon el pendiente real del recibo.'}
            {h.fin && ` Quedan ${h.cuotas_restantes} cuotas, hasta ${mesAnio(h.fin)}.`}
          </p>
          <CuadroYSimulador d={h} />
        </>
      )}
    </div>
  )
}
