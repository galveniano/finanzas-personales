import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { api } from '../lib/api'
import type { Inmuebles as Datos } from '../lib/tipos'
import { Boton, Cabecera, Cargando, Dialogo, ErrorCarga, SelectorAnio, Vacio } from '../components/ui'
import { Ficha } from '../components/Bienes/Ficha'
import { Formularios } from '../components/Bienes/Formularios'
import { Prestamos } from '../components/Bienes/Prestamos'
import { TITULOS } from '../components/Bienes/comun'
import type { Accion } from '../components/Bienes/comun'

export default function Inmuebles() {
  const [accion, setAccion] = useState<Accion | null>(null)
  const [actual] = useState(() => new Date().getFullYear())
  const [anio, setAnio] = useState(actual)
  const { data, isLoading, error } = useQuery({
    queryKey: ['inmuebles', anio], queryFn: () => api.get<Datos>(`/inmuebles?anio=${anio}`), placeholderData: (prev) => prev,
  })
  const titulo = accion ? `${TITULOS[accion.tipo]} · ${accion.deuda?.nombre ?? accion.inmueble?.nombre ?? ''}`.replace(/ · $/, '') : ''
  return (
    <>
      <Cabecera titulo="Bienes" subtitulo="Pisos, la casa nueva, hipotecas, préstamos y coche">
        <SelectorAnio valor={anio} onCambiar={setAnio} hasta={actual} />
        <Boton variante="secundario" onClick={() => setAccion({ tipo: 'prestamo' })}><Plus size={16} />Añadir préstamo</Boton>
        <Boton onClick={() => setAccion({ tipo: 'nuevo' })}><Plus size={16} />Añadir</Boton>
      </Cabecera>
      {anio !== actual && (
        <p className="mb-4 rounded-xl bg-panel-2 px-4 py-2.5 text-sm">
          Viendo la renta y los intereses de {anio}; el valor, lo pendiente y los cobros son los de hoy.
        </p>
      )}
      {isLoading ? <Cargando /> : error && !data ? <ErrorCarga error={error} /> :
        data?.inmuebles.length ? data.inmuebles.map((i) => <Ficha key={i.id} i={i} anio={data.anio} constantes={data.constantes} abrir={setAccion} />)
          : <Vacio>Añade el piso alquilado, la casa de obra nueva o el coche con «Añadir».</Vacio>}
      <Prestamos abrir={setAccion} />
      <Dialogo abierto={!!accion} onCerrar={() => setAccion(null)} titulo={titulo}>
        {accion && <Formularios a={accion} cerrar={() => setAccion(null)} bienes={data?.inmuebles ?? []} constantes={data?.constantes} />}
      </Dialogo>
    </>
  )
}
