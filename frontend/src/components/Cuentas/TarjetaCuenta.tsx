import { useState } from 'react'
import { Pencil, Upload } from 'lucide-react'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../../lib/api'
import { eur, fecha, fechaHora } from '../../lib/format'
import { estiloTooltip } from '../../lib/graficas'
import { useSubida } from '../../lib/subida'
import type { Cuenta } from '../../lib/tipos'
import { useAccion, useAvisos } from '../../lib/utilidades'
import { BorrarEnDosPasos, Boton, Dialogo, Etiqueta, Importe, Tarjeta } from '../ui'
import EditarCuenta from './EditarCuenta'
import { ORIGEN, TIPO_CUENTA, esManual } from './comun'

function Importar({ cuenta, onCerrar }: { cuenta: Cuenta; onCerrar: () => void }) {
  const avisar = useAvisos()
  const accion = useAccion(async (f: File) => {
    const fd = new FormData()
    fd.append('fichero', f)
    const r = await api.post<{ nuevos: number; duplicados: number }>(`/cuentas/${cuenta.id}/importar`, fd)
    avisar(`${r.nuevos} movimientos nuevos, ${r.duplicados} ya estaban`)
    onCerrar()
  })
  const { input, elegir, zona, arrastrando } = useSubida({ accept: '.xls,.xlsx,.csv', onFicheros: (ficheros) => accion.mutate(ficheros[0]) })
  return (
    <div className="space-y-4 text-sm">
      <p className="text-muted">Descarga los movimientos desde la web de Sabadell (Excel o CSV) y súbelos aquí. Si un movimiento ya estaba, no se duplica, y el saldo pasa a ser el del extracto.</p>
      <button type="button" onClick={elegir} disabled={accion.isPending} {...zona}
        className={`flex w-full cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-line px-4 py-8 text-center hover:border-accent ${arrastrando ? 'ring-2 ring-accent' : ''}`}>
        <Upload className="text-accent" />
        <span className="font-medium">{accion.isPending ? 'Importando…' : 'Elegir extracto'}</span>
        <span className="text-xs text-muted">.xls, .xlsx o .csv</span>
      </button>
      {input}
    </div>
  )
}

/** Saldo a fin de cada uno de los últimos meses (una línea pequeña, sin ejes) y lo que ha entrado y salido este mes. */
function MiniEvolucion({ c }: { c: Cuenta }) {
  const puntos = c.evolucion
  const hayMes = c.mes.entran > 0 || c.mes.salen > 0
  if (puntos.length < 2 && !hayMes) return null
  const primero = puntos[0]?.saldo, ultimo = puntos[puntos.length - 1]?.saldo
  return (
    <div className="mt-3">
      {puntos.length >= 2 && (
        <div className="h-10" role="img" aria-label={`Saldo de ${eur(primero)} a ${eur(ultimo)} en los últimos ${puntos.length} meses`}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={puntos} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={`saldo-${c.id}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="fecha" hide />
              <YAxis hide domain={['auto', 'auto']} />
              <Tooltip {...estiloTooltip} cursor={{ stroke: 'var(--line)' }} formatter={(v) => [eur(Number(v)), 'Saldo']}
                labelFormatter={(v) => fecha(String(v), { month: 'long', year: 'numeric' })} />
              <Area type="monotone" dataKey="saldo" stroke="var(--chart-1)" strokeWidth={1.5} fill={`url(#saldo-${c.id})`}
                dot={false} activeDot={{ r: 3 }} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="mt-1 flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5 text-xs text-muted">
        {hayMes
          ? <span>Este mes <Importe valor={c.mes.entran} signo /> / <Importe valor={-c.mes.salen} signo /></span>
          : <span>Sin movimientos este mes</span>}
        {puntos.length >= 2 && <span>Saldo a fin de mes según los movimientos</span>}
      </div>
    </div>
  )
}

export default function TarjetaCuenta({ c }: { c: Cuenta }) {
  const [editar, setEditar] = useState(false)
  const [importar, setImportar] = useState(false)
  const avisar = useAvisos()
  const borrar = useAccion((id: number) => api.del<{ oculta: boolean }>(`/cuentas/${id}`)
    .then((r) => avisar(r.oculta ? 'Cuenta oculta: deja de contar y la recuperas abajo, en «Cuentas ocultas»' : 'Cuenta borrada con sus movimientos')))
  const o = ORIGEN[c.origen] ?? ORIGEN.manual
  const manual = esManual(c)
  const sinSaldo = manual && !c.saldo_fecha
  return (
    <Tarjeta className={c.participacion === 0 ? 'opacity-60' : undefined}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-semibold">{c.nombre}</div>
          <div className="truncate text-xs text-muted">{[c.entidad, c.iban && `···${c.iban.slice(-4)}`].filter(Boolean).join(' · ') || 'Sin entidad'}</div>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-1">
          <Etiqueta>{TIPO_CUENTA[c.tipo] ?? c.tipo}</Etiqueta>
          <Etiqueta tono={o.tono}>{o.texto}</Etiqueta>
        </div>
      </div>
      <div className="cifra mt-4 text-2xl font-medium">{sinSaldo ? <span className="text-base text-muted">Sin saldo todavía</span> : eur(c.saldo)}</div>
      {c.participacion < 100 && (
        <div className="mt-1 text-xs text-muted">
          {c.participacion === 0 ? 'No es tuya: no suma en tu patrimonio ni en tus gastos' : <>Tuya al {c.participacion} % · tu parte <span className="cifra">{eur(c.saldo_tuyo)}</span></>}
        </div>
      )}
      <MiniEvolucion c={c} />
      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-2 gap-y-1 text-xs text-muted">
        <span className="min-w-0 truncate">
          {c.ultima_sincronizacion ? `Sincronizada ${fechaHora(c.ultima_sincronizacion)}` : sinSaldo ? 'Ponlo en «Editar» o importa un extracto' : `Saldo a ${fecha(c.saldo_fecha)}`}
        </span>
        <span className="flex items-center gap-0.5">
          <Boton variante="fantasma" className="px-2 py-1 text-xs" onClick={() => setEditar(true)}><Pencil size={13} />Editar</Boton>
          {manual && <Boton variante="fantasma" className="px-2 py-1 text-xs" onClick={() => setImportar(true)}><Upload size={13} />Importar extracto</Boton>}
          <BorrarEnDosPasos etiqueta={manual ? `${c.nombre} con sus movimientos` : c.nombre} disabled={borrar.isPending} onBorrar={() => borrar.mutate(c.id)} />
        </span>
      </div>
      <Dialogo abierto={editar} onCerrar={() => setEditar(false)} titulo={`Editar ${c.nombre}`}>
        <EditarCuenta c={c} onCerrar={() => setEditar(false)} />
      </Dialogo>
      <Dialogo abierto={importar} onCerrar={() => setImportar(false)} titulo={`Importar en ${c.nombre}`}>
        <Importar cuenta={c} onCerrar={() => setImportar(false)} />
      </Dialogo>
    </Tarjeta>
  )
}
