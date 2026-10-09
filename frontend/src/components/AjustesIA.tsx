import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PlugZap, Save } from 'lucide-react'
import { api } from '../lib/api'
import type { AjustesIA as Ajustes } from '../lib/tipos'
import { useAccion, useAvisos } from '../lib/utilidades'
import { Boton, Campo, EnDosPasos, ErrorCarga, Etiqueta, Selector, Tarjeta } from './ui'

type Proveedor = Ajustes['proveedor']

const AYUDA: Record<Proveedor, { url: string; texto: string }> = {
  openai: { url: 'https://platform.openai.com/api-keys', texto: 'platform.openai.com → API keys' },
  anthropic: { url: 'https://console.anthropic.com/settings/keys', texto: 'console.anthropic.com → API keys' },
}

/** Elige el modelo de IA del asistente y de la lectura de facturas, y guarda su clave (cifrada) en la app. */
export default function AjustesIA() {
  const { data: d, error } = useQuery({ queryKey: ['ajustes-ia'], queryFn: () => api.get<Ajustes>('/ajustes/ia') })
  if (error && !d) return <Tarjeta titulo="Asistente (IA)"><ErrorCarga error={error} /></Tarjeta>
  if (!d) return null
  // La clave hace que el formulario vuelva a empezar con lo guardado cada vez que cambia
  return <Formulario key={`${d.proveedor}:${d.proveedores[d.proveedor].modelo}`} d={d} />
}

function Formulario({ d }: { d: Ajustes }) {
  const avisar = useAvisos()
  const [proveedor, setProveedor] = useState<Proveedor>(d.proveedor)
  const [clave, setClave] = useState('')
  const [modelo, setModelo] = useState(d.proveedores[d.proveedor].modelo)

  const guardar = useAccion(() => api.put('/ajustes/ia', { proveedor, modelo, clave: clave || undefined })
    .then(() => setClave('')), 'Asistente guardado')
  const probar = useAccion(async () => {
    const r = await api.post<{ proveedor: string; modelo: string; respuesta: string }>('/ajustes/ia/probar')
    avisar(`${r.proveedor} (${r.modelo}) responde: ${r.respuesta || 'OK'}`)
  })
  const borrar = useAccion(() => api.put('/ajustes/ia', { proveedor, clave: '' }), 'Clave borrada de la app')

  const p = d.proveedores[proveedor]
  const cambiado = proveedor !== d.proveedor || modelo !== p.modelo || !!clave

  return (
    <Tarjeta titulo="Asistente (IA)" accion={
      <Etiqueta tono={d.disponible ? 'bien' : 'aviso'}>{d.disponible ? `${d.proveedores[d.proveedor].nombre} · ${d.modelo}` : 'Sin clave'}</Etiqueta>}>
      <p className="mb-4 text-sm text-muted">
        El modelo que usan el asistente y la lectura de facturas de Drive. La clave se guarda cifrada en tu base de datos
        y nunca se vuelve a enseñar entera.
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <Selector etiqueta="Proveedor" value={proveedor} onChange={(e) => {
          const nuevo = e.target.value as Proveedor
          setProveedor(nuevo)
          setModelo(d.proveedores[nuevo].modelo)
          setClave('')
        }}>
          <option value="openai">OpenAI</option>
          <option value="anthropic">Claude (Anthropic)</option>
        </Selector>
        <Campo etiqueta="Clave de API" type="password" autoComplete="off" value={clave} onChange={(e) => setClave(e.target.value)}
          placeholder={p.clave ? `Guardada ${p.clave}` : proveedor === 'openai' ? 'sk-…' : 'sk-ant-…'}
          ayuda={p.origen_clave === 'entorno' ? 'Ahora usa la de las variables de entorno' : undefined} />
        <Campo etiqueta="Modelo" value={modelo} onChange={(e) => setModelo(e.target.value)} placeholder={p.modelo_defecto}
          ayuda="Vacío = el recomendado" />
      </div>
      <p className="mt-3 text-xs text-muted">
        La clave se saca en <a className="text-accent" href={AYUDA[proveedor].url} target="_blank" rel="noreferrer">{AYUDA[proveedor].texto}</a>.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Boton onClick={() => guardar.mutate(undefined)} disabled={!cambiado || guardar.isPending}><Save size={15} />Guardar</Boton>
        <Boton variante="secundario" onClick={() => probar.mutate(undefined)} disabled={!d.disponible || cambiado || probar.isPending}>
          <PlugZap size={15} className={probar.isPending ? 'animate-pulse' : ''} />{probar.isPending ? 'Probando…' : 'Probar'}
        </Boton>
        {p.origen_clave === 'app' && proveedor === d.proveedor && (
          <EnDosPasos variante="fantasma" texto="Borrar clave" textoConfirmar="¿Seguro? Borrar la clave" disabled={borrar.isPending}
            onConfirmar={() => borrar.mutate(undefined)} />
        )}
      </div>
    </Tarjeta>
  )
}
