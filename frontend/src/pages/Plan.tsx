import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { CheckCheck, Plus } from 'lucide-react'
import { api } from '../lib/api'
import type { Cuenta, Escenario as ValoresEscenario, Objetivo, Pago, Planificacion, Prevision } from '../lib/tipos'
import { useBorrarPago, useMarcarPago } from '../lib/pagos'
import { num, useAccion, useAvisos } from '../lib/utilidades'
import ListaPagos from '../components/ListaPagos'
import Escenario from '../components/Plan/Escenario'
import FormObjetivo from '../components/Plan/FormObjetivo'
import FormPago from '../components/Plan/FormPago'
import ImpuestosQueVienen from '../components/Plan/ImpuestosQueVienen'
import MesAMes from '../components/Plan/MesAMes'
import Objetivos from '../components/Plan/Objetivos'
import Previsto from '../components/Plan/Previsto'
import { rutaPrevision, tieneSupuestos } from '../components/Plan/comun'
import { Boton, Cabecera, Cargando, Dialogo, EnDosPasos, ErrorCarga, Segmentos, Tarjeta } from '../components/ui'

const HORIZONTES = [{ valor: 12, texto: '12 meses' }, { valor: 24, texto: '24 meses' }]

export default function Plan() {
  const [meses, setMeses] = useState<number>(12)
  const [escenario, setEscenario] = useState<ValoresEscenario | null>(null)
  const [dialogo, setDialogo] = useState<'objetivo' | 'pago' | null>(null)
  const [objetivo, setObjetivo] = useState<Objetivo | null>(null)
  const [pago, setPago] = useState<Pago | null>(null)
  const avisar = useAvisos()

  const { data: d, isLoading, error } = useQuery({ queryKey: ['planificacion'], queryFn: () => api.get<Planificacion>('/planificacion') })
  const { data: prev } = useQuery({
    queryKey: ['prevision', meses], queryFn: () => api.get<Prevision>(rutaPrevision(meses, null)), placeholderData: keepPreviousData,
  })
  const { data: simulada, isFetching: simulando } = useQuery({
    queryKey: ['prevision', meses, escenario], queryFn: () => api.get<Prevision>(rutaPrevision(meses, escenario)), enabled: !!escenario,
  })
  const esc = escenario ? simulada : undefined
  const { data: cuentas } = useQuery({ queryKey: ['cuentas'], queryFn: () => api.get<Cuenta[]>('/cuentas') })

  const cerrar = () => { setDialogo(null); setObjetivo(null); setPago(null) }
  const guardarObjetivo = useAccion((v: Record<string, string>) => {
    const datos = {
      nombre: v.nombre, tipo: v.tipo, fecha_objetivo: v.fecha_objetivo || null, importe_objetivo: num(v.importe_objetivo) ?? 0,
      // Con cuenta ligada el campo va apagado y no viene: no se toca
      ahorrado: v.ahorrado === undefined ? undefined : num(v.ahorrado) ?? 0,
      notas: v.notas ?? '', cuenta_id: v.cuenta_id ? Number(v.cuenta_id) : null,
    }
    return (objetivo ? api.patch(`/objetivos/${objetivo.id}`, datos) : api.post('/objetivos', datos)).then(cerrar)
  }, 'Objetivo guardado')
  const borrarObjetivo = useAccion((o: Objetivo) => api.del(`/objetivos/${o.id}`), 'Objetivo borrado')
  const guardarPago = useAccion((v: Record<string, string>) => {
    const datos = {
      concepto: v.concepto, fecha: v.fecha, importe: num(v.importe),
      objetivo_id: v.objetivo_id ? Number(v.objetivo_id) : null, activo_id: v.activo_id ? Number(v.activo_id) : null,
      pagado: v.pagado === 'on',
    }
    return (pago ? api.patch(`/pagos/${pago.id}`, datos) : api.post('/pagos', datos)).then(cerrar)
  }, 'Pago previsto guardado')
  const borrarPago = useBorrarPago()
  const marcar = useMarcarPago()
  const conciliar = useAccion(async () => {
    const r = await api.post<{ marcados: number }>('/pagos/conciliar')
    avisar(r.marcados ? `${r.marcados === 1 ? 'Un pago marcado' : `${r.marcados} pagos marcados`} como pagados` : 'No había nada que marcar')
  })

  if (isLoading) return <Cargando />
  if (error) return <ErrorCarga error={error} />
  if (!d) return null
  const conSupuestos = !!prev && tieneSupuestos(prev)
  const vistos = d.pagos.filter((p) => !p.pagado && p.visto_en_banco).length
  const ocupado = marcar.isPending || borrarPago.isPending || conciliar.isPending

  return (
    <>
      <Cabecera titulo="Plan" subtitulo="El dinero que tendrás, tus objetivos y los pagos que vienen">
        <Segmentos etiqueta="Horizonte de la previsión" opciones={HORIZONTES} valor={meses} onCambiar={setMeses} />
        <Boton variante="secundario" onClick={() => { setPago(null); setDialogo('pago') }}><Plus size={16} />Pago previsto</Boton>
        <Boton onClick={() => { setObjetivo(null); setDialogo('objetivo') }}><Plus size={16} />Objetivo</Boton>
      </Cabecera>

      <Previsto d={d} prev={prev} esc={esc} meses={meses} />
      {prev && conSupuestos && <Escenario valor={escenario} onCambiar={setEscenario} prev={prev} esc={esc} cargando={simulando} />}

      <Objetivos d={d} borrando={borrarObjetivo.isPending} onNuevo={() => { setObjetivo(null); setDialogo('objetivo') }}
        onEditar={(o) => { setObjetivo(o); setDialogo('objetivo') }} onBorrar={(o) => borrarObjetivo.mutate(o)} />

      {prev && conSupuestos && <ImpuestosQueVienen prev={prev} meses={meses} />}

      <h2 className="mt-8 mb-3 text-lg font-semibold">Pagos previstos</h2>
      <Tarjeta>
        <ListaPagos pagos={d.pagos} ocupado={ocupado}
          onMarcar={(p, pagado) => marcar.mutate({ id: p.id, pagado })}
          onBorrar={(p) => borrarPago.mutate(p.id)}
          onEditar={(p) => { setPago(p); setDialogo('pago') }}
          acciones={vistos > 0 && (
            <EnDosPasos variante="secundario" className="px-2.5 py-1 text-xs" icono={<CheckCheck size={14} />} disabled={ocupado}
              texto={vistos === 1 ? 'Marcar el pago visto en el banco' : `Marcar los ${vistos} vistos en el banco`}
              textoConfirmar={`¿Seguro? Marcar ${vistos === 1 ? 'el pago' : `los ${vistos}`} como pagados`} onConfirmar={() => conciliar.mutate(undefined)} />
          )}
          vacio="Apunta aquí los plazos de la obra nueva, la señal de la boda o el viaje. Si el cargo aparece en el banco, te lo digo." />
        <p className="mt-3 text-xs text-muted">Un pago se da por «visto en el banco» cuando hay un cargo del mismo importe a menos de 20 días de su fecha.
          Los vencidos sin marcar se descuentan del mes en curso en la previsión.</p>
      </Tarjeta>

      {prev && conSupuestos && <MesAMes prev={prev} />}

      <Dialogo abierto={dialogo === 'objetivo'} onCerrar={cerrar} titulo={objetivo ? 'Editar objetivo' : 'Nuevo objetivo'}>
        <FormObjetivo key={objetivo?.id ?? 'nuevo'} editando={objetivo} cuentas={cuentas ?? []} onEnviar={(v) => guardarObjetivo.mutateAsync(v)} />
      </Dialogo>
      <Dialogo abierto={dialogo === 'pago'} onCerrar={cerrar} titulo={pago ? 'Editar pago previsto' : 'Nuevo pago previsto'}>
        <FormPago key={pago?.id ?? 'nuevo'} editando={pago} inmuebles={d.inmuebles} objetivos={d.objetivos} onEnviar={(v) => guardarPago.mutateAsync(v)} />
      </Dialogo>
    </>
  )
}
