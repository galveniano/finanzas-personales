// Categorías de los gastos de la actividad (las mismas claves que guarda el backend en GastoAutonomo.categoria).
export const CATEGORIAS_GASTO: Record<string, string> = {
  cuota_reta: 'Cuota de autónomos', gestoria: 'Gestoría', software: 'Software y suscripciones', equipos: 'Equipos',
  formacion: 'Formación', suministros: 'Suministros', otros: 'Otros',
}

export const nombreCategoria = (clave: string) => CATEGORIAS_GASTO[clave] ?? clave.replace('_', ' ')
