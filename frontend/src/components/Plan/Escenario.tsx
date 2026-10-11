import { useState } from 'react'
import { Eraser, FlaskConical } from 'lucide-react'
import { eur } from '../../lib/format'
import type { Escenario as Valores, Prevision } from '../../lib/tipos'
import { num } from '../../lib/utilidades'
import { Boton, Campo, Formulario, Importe, Tarjeta } from '../ui'
import { mesLargo } from './comun'

const signo = (v: number) => (v > 0 ? `+${v} %` : v < 0 ? `−${-v} %` : 'sin cambios')

/** «¿Y si…?»: cambia tarifas, días, gasto o ahorro extra y compara con la previsión de hoy. No se guarda nada. */
export default function Escenario({ valor, onCambiar, prev, esc, cargando }: {
  valor: Valores | null; onCambiar: (e: Valores | null) => void; prev: Prevision; esc?: Prevision; cargando: boolean
}) {
  const [tarifa, setTarifa] = useState(valor?.tarifa_pct ?? 0)
  const [version, setVersion] = useState(0)  // para vaciar el formulario al quitar el escenario
  const ultimo = prev.meses[prev.meses.length - 1]
  const ultimoEsc = esc?.meses[esc.meses.length - 1]
  const dias = prev.clientes[0]?.dias_mes
  const gasto = prev.supuestos.gasto_habitual_mes ?? prev.gasto_habitual_banco
  const quitar = () => { setTarifa(0); setVersion((v) => v + 1); onCambiar(null) }

  return (
    <Tarjeta className="mt-4" titulo={<span className="inline-flex items-center gap-2"><FlaskConical size={16} className="text-accent" />¿Y si…?</span>}
      accion={valor && <Boton variante="fantasma" className="px-2.5 py-1 text-xs" onClick={quitar}><Eraser size={14} />Quitar escenario</Boton>}>
      <Formulario key={version} textoBoton="Simular" onEnviar={async (v) => {
        const e: Valores = {}
        const t = num(v.tarifa_pct)
        if (t) e.tarifa_pct = t
        for (const clave of ['dias_mes', 'gasto_habitual', 'ahorro_extra_mes'] as const) {
          const n = num(v[clave])
          if (n != null) e[clave] = n
        }
        onCambiar(Object.keys(e).length ? e : null)
      }}>
        <label className="flex flex-col gap-1.5 text-xs font-medium text-muted sm:col-span-2">
          <span className="flex justify-between">Tarifa de tus clientes <output className="cifra">{signo(tarifa)}</output></span>
          <input type="range" name="tarifa_pct" min={-50} max={100} step={5} value={tarifa} onChange={(e) => setTarifa(Number(e.target.value))}
            className="w-full accent-[var(--accent)]" aria-label="Cambio de la tarifa en %" aria-valuetext={signo(tarifa)} />
          <span className="font-normal">De −50 % a +100 % sobre la tarifa de hoy de todos los clientes.</span>
        </label>
        <Campo etiqueta="Días al mes" name="dias_mes" inputMode="decimal" defaultValue={valor?.dias_mes ?? ''}
          placeholder={dias != null ? `Hoy ${dias}` : ''} ayuda="Para todos los clientes. Los meses con días planificados a mano no cambian." />
        <Campo etiqueta="Gasto habitual (€/mes)" name="gasto_habitual" inputMode="decimal" defaultValue={valor?.gasto_habitual ?? ''}
          placeholder={gasto != null ? `Hoy ${Math.round(gasto)}` : ''} ayuda="Lo que sale de tus cuentas en un mes normal." />
        <Campo etiqueta="Ahorro extra (€/mes)" name="ahorro_extra_mes" inputMode="decimal" defaultValue={valor?.ahorro_extra_mes ?? ''}
          placeholder="0" ayuda="Lo que apartarías cada mes además de lo de ahora." />
      </Formulario>
      {valor && ultimo && (
        <div className={`mt-4 rounded-xl bg-panel-2 px-4 py-3 text-sm transition-opacity ${cargando ? 'opacity-60' : ''}`} aria-live="polite">
          {ultimoEsc ? (
            <>
              Tendrás en {mesLargo(ultimoEsc.mes)}: <strong className="cifra">{eur(ultimoEsc.liquidez)}</strong>
              {' '}<Importe valor={ultimoEsc.liquidez - ultimo.liquidez} signo className="text-xs" />
              <span className="text-muted"> (hoy la previsión dice {eur(ultimo.liquidez)})</span>
            </>
          ) : 'Calculando el escenario…'}
        </div>
      )}
      <p className="mt-3 text-xs text-muted">Solo es una simulación sobre tus supuestos de hoy: no cambia nada de lo guardado. Impuestos y renta se recalculan con ella.</p>
    </Tarjeta>
  )
}
