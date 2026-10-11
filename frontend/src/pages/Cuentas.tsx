import { useState } from 'react'
import { Eye, Plus, Tags } from 'lucide-react'
import { api } from '../lib/api'
import { eur } from '../lib/format'
import { num, useAccion } from '../lib/utilidades'
import Categorias from '../components/Cuentas/Categorias'
import Movimientos from '../components/Cuentas/Movimientos'
import TarjetaCuenta from '../components/Cuentas/TarjetaCuenta'
import { TIPO_CUENTA, useCategorias, useCuentas } from '../components/Cuentas/comun'
import { Boton, Cabecera, Campo, Cargando, Dialogo, ErrorCarga, Formulario, Selector, Vacio } from '../components/ui'

/** Cuentas bancarias (corrientes, de ahorro y tarjetas) y sus movimientos. Las de inversión van en Inversiones. */
export default function Cuentas() {
  const cuentas = useCuentas()
  const categorias = useCategorias()
  const [nueva, setNueva] = useState(false)
  const [verCategorias, setVerCategorias] = useState(false)
  const visibles = (cuentas.data ?? []).filter((c) => c.activa && c.tipo !== 'inversion')
  const ocultas = (cuentas.data ?? []).filter((c) => !c.activa)
  // Mismo criterio que «En tus cuentas» en Inicio: corrientes y de ahorro, solo tu parte
  const liquidez = visibles.filter((c) => c.tipo === 'corriente' || c.tipo === 'ahorro').reduce((s, c) => s + c.saldo_tuyo, 0)
  const crear = useAccion((d: Record<string, string>) => api.post('/cuentas', { ...d, saldo: num(d.saldo) ?? 0 }).then(() => setNueva(false)), 'Cuenta creada')
  const mostrar = useAccion((id: number) => api.patch(`/cuentas/${id}`, { activa: true }), 'Cuenta recuperada: vuelve a contar y a sincronizarse')

  return (
    <>
      <Cabecera titulo="Cuentas"
        subtitulo={cuentas.data ? `${visibles.length} ${visibles.length === 1 ? 'cuenta' : 'cuentas'} · ${eur(liquidez)} en cuentas corrientes y de ahorro` : undefined}>
        <Boton variante="secundario" onClick={() => setVerCategorias(true)}><Tags size={16} />Categorías</Boton>
        <Boton onClick={() => setNueva(true)}><Plus size={16} />Nueva cuenta</Boton>
      </Cabecera>

      {cuentas.isLoading ? <Cargando /> : cuentas.error ? <ErrorCarga error={cuentas.error} /> : (
        <>
          {visibles.length
            ? <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{visibles.map((c) => <TarjetaCuenta key={c.id} c={c} />)}</div>
            : <Vacio>Crea una cuenta con «Nueva cuenta» (y apunta sus movimientos o importa el extracto) o conecta Sabadell en Ajustes.</Vacio>}
          <p className="mt-2 text-xs text-muted">
            Lo de «en cuentas corrientes y de ahorro» es tu parte de cada una (lo mismo que «En tus cuentas» en Inicio); las tarjetas no suman y las cuentas de inversión se ven en Inversiones.
          </p>
          {ocultas.length > 0 && (
            <details className="mt-4 rounded-2xl border border-dashed border-line px-5 py-3 text-sm">
              <summary className="cursor-pointer font-medium text-muted">Cuentas ocultas ({ocultas.length})</summary>
              <ul className="mt-2 divide-y divide-line">
                {ocultas.map((c) => (
                  <li key={c.id} className="flex items-center justify-between gap-3 py-2">
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{c.nombre}</span>
                      <span className="block truncate text-xs text-muted">{[TIPO_CUENTA[c.tipo] ?? c.tipo, c.entidad].filter(Boolean).join(' · ')} · no cuenta ni se sincroniza</span>
                    </span>
                    <Boton variante="secundario" className="shrink-0 px-3 py-1.5 text-xs" disabled={mostrar.isPending} onClick={() => mostrar.mutate(c.id)}>
                      <Eye size={14} />Mostrar
                    </Boton>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}

      <Movimientos cuentas={visibles} categorias={categorias.data ?? []} />

      <Dialogo abierto={nueva} onCerrar={() => setNueva(false)} titulo="Nueva cuenta">
        <Formulario onEnviar={(d) => crear.mutateAsync(d)} textoBoton="Crear cuenta">
          <Campo etiqueta="Nombre" name="nombre" required placeholder="Cuenta Sabadell" />
          <Campo etiqueta="Entidad" name="entidad" defaultValue="Banco Sabadell" />
          <Selector etiqueta="Tipo" name="tipo" defaultValue="corriente">
            <option value="corriente">Corriente</option><option value="ahorro">Ahorro</option><option value="tarjeta">Tarjeta de crédito</option>
          </Selector>
          <Campo etiqueta="Saldo actual (€)" name="saldo" inputMode="decimal" placeholder="0,00" ayuda="Déjalo vacío si vas a importar un extracto." />
          <Campo etiqueta="IBAN" name="iban" className="sm:col-span-2" placeholder="ES00 0081 0000 0000 0000 0000" ayuda="Con espacios o sin ellos. Si luego conectas Sabadell, el banco reconoce esta cuenta por el IBAN y no la duplica." />
        </Formulario>
      </Dialogo>
      <Dialogo abierto={verCategorias} onCerrar={() => setVerCategorias(false)} titulo="Categorías y reglas">
        <Categorias />
      </Dialogo>
    </>
  )
}
