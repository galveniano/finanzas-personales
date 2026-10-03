export interface Linea { nombre: string; grupo: string; importe: number; detalle: string }
export interface UltimaSync { fecha: string; ok: boolean; mensaje: string }
export interface EstadoSync {
  sabadell: {
    configurado: boolean; conectado: boolean; valida_hasta: string | null; ultima: UltimaSync | null
    url_vuelta?: string; vuelta_automatica?: boolean
  }
  indexa: { configurado: boolean; ultima: UltimaSync | null }
  cada_horas: number
  en_vercel?: boolean
}
export interface Resumen {
  fecha: string; neto: number; activos: number; pasivos: number
  grupos: { grupo: string; importe: number }[]
  lineas_activo: Linea[]; lineas_pasivo: Linea[]
  historico: { fecha: string; neto: number; liquidez: number; inversiones: number; inmuebles: number; deudas: number }[]
  flujo_mensual: { mes: string; ingresos: number; gastos: number }[]
  gasto_categorias: { categoria: string; importe: number }[]
  proximos_pagos: { id: number; concepto: string; fecha: string; importe: number }[]
  fiscal: {
    trimestre: number; anio: number
    iva: { resultado: number; presentado: boolean; previsto: boolean; repercutido: number; soportado: number; plazo: string }
    irpf: { resultado: number; presentado: boolean; previsto: boolean; exento: boolean; notas: string[]; plazo: string }
    renta: { anio: number; resultado: number; cuota: number; neto_mes: number; bruto_mes: number } | null
  }
  sync: EstadoSync
}
export interface Cuenta {
  id: number; nombre: string; entidad: string; tipo: string; iban: string; origen: string
  saldo: number; saldo_fecha: string | null; ultima_sincronizacion: string | null
  participacion: number; saldo_tuyo: number
}
export interface Categoria { id: number; nombre: string; tipo: string; ambito: string }
export interface Movimiento {
  id: number; cuenta_id: number; cuenta: string; fecha: string; concepto: string
  importe: number; saldo: number | null; categoria_id: number | null
}
export interface Trimestre {
  trimestre: number; plazo: string; base: number; iva_repercutido: number; iva_soportado: number
  iva_resultado: number; rendimiento_acumulado: number; retenciones_acumuladas: number
  irpf_resultado: number; exento_130: boolean; notas: string[]
  iva_fuente: Fuente; irpf_fuente: Fuente; iva_estimado: number | null; irpf_estimado: number | null
  ingresos_acumulados: number | null; base_prevista: number | null
}
export type Fuente = 'presentado' | 'previsto' | 'estimado'
export interface Factura {
  id: number; numero: string; cliente: string; fecha: string; concepto: string; base: number
  tipo_iva: number; tipo_retencion: number; cuota_iva: number; retencion: number; total: number
  fecha_cobro: string | null
}
export interface GastoAutonomo {
  id: number; fecha: string; proveedor: string; concepto: string; categoria: string
  base: number; tipo_iva: number; cuota_iva: number; deducible_pct: number
}
export interface Autonomo {
  anio: number; trimestres: Trimestre[]; total_facturado: number
  por_anio: { anio: number; facturado: number; gastos: number; irpf: number; neto: number; previsto: boolean }[]
  ingresos_declarados: number | null; ultimo_130: number | null; pagado_iva: number; pagado_irpf: number
  por_cliente: { cliente: string; base: number }[]
  facturas: Factura[]; gastos: GastoAutonomo[]; clientes: string[]
}
export interface Nomina {
  id: number; empresa: string; fecha: string; bruto: number; retencion_irpf: number
  seguridad_social: number; neto: number
}
export interface Nominas {
  anio: number; nominas: Nomina[]; bruto_12_meses: number | null
  totales: { bruto: number; retencion_irpf: number; seguridad_social: number; neto: number }
  fuente: 'nominas' | 'banco' | 'ninguna'
  estimado_banco: { neto_medio_mes: number; meses: number; bruto_anual: number; irpf_anual: number; ss_anual: number; tipo_irpf: number } | null
  banco: { id: number; fecha: string; concepto: string; importe: number; cuenta: string }[]
}
export interface Rendimiento {
  anio: number; ingresos: number; gastos_limitados: number; gastos_otros: number; amortizacion: number
  rendimiento_neto: number; reduccion_pct: number; reduccion: number; rendimiento_reducido: number; notas: string[]
}
export interface Inmueble {
  id: number; nombre: string; tipo: string; uso: string; fecha_compra: string | null
  precio_compra: number; gastos_compra: number; valor_catastral: number; valor_catastral_construccion: number
  porcentaje_propiedad: number; valor: number; valor_detalle: string; deuda: number; equity: number
  valoraciones: { fecha: string; valor: number }[]
  hipotecas: { id: number; nombre: string; entidad: string; capital_inicial: number; tipo_interes_anual: number
    plazo_meses: number; fecha_inicio: string | null; cuota: number; pendiente: number; intereses_anio: number; futura: boolean }[]
  contratos: { id: number; inquilino: string; fecha_inicio: string; fecha_fin: string | null; renta_inicial: number
    renta_actual: number; reduccion_pct: number; cambios: { desde: string; renta: number }[] }[]
  gastos: { id: number; fecha: string; tipo: string; importe: number; concepto: string }[]
  pagos: { id: number; concepto: string; fecha: string; importe: number; pagado: boolean }[]
  rendimiento: Rendimiento | null
  rentabilidad: Rentabilidad | null; notas: string
}
export interface Rentabilidad {
  renta_anual: number; gastos_anuales: number; intereses_anuales: number; cuotas_anuales: number
  coste: number; aportado: number; bruta: number | null; neta: number | null; neta_sobre_valor: number | null
  sobre_aportado: number | null; flujo_caja_anual: number
}
export interface Objetivo {
  id: number; nombre: string; tipo: string; fecha_objetivo: string | null; importe_objetivo: number
  ahorrado: number; ahorro_mensual: number | null
}
export interface Pago {
  id: number; concepto: string; fecha: string; importe: number; pagado: boolean
  objetivo: string | null; inmueble: string | null; inversion: string | null
}
export interface Planificacion {
  liquidez: number; pendiente_12_meses: number; objetivos: Objetivo[]; pagos: Pago[]
  inmuebles: { id: number; nombre: string }[]
}
export interface EstadoAuth { requerida: boolean; client_id: string | null; email: string | null }
export interface Declaracion {
  id: number; modelo: string; nombre: string; ejercicio: number; periodo: string
  resultado: 'ingresar' | 'devolver' | 'compensar' | 'negativa' | 'cero' | 'domiciliar' | 'otro'
  importe: number; fecha_presentacion: string | null; justificante: string; csv: string
  tiene_pdf: boolean; estimado: number | null; notas: string
}
export interface Declaraciones {
  declaraciones: Declaracion[]
  por_anio: { ejercicio: number; pagado: number; devuelto: number }[]
}
export interface CalculoNomina {
  bruto_anual: number; pagas: number; tipo_irpf: number; ss_anual: number; irpf_anual: number
  neto_anual: number; neto_mes: number; neto_paga_extra: number | null
  meses: { mes: number; bruto: number; seguridad_social: number; irpf: number; neto: number; paga_extra: boolean }[]
}
export interface DocumentoDrive {
  id: number; nombre: string; enlace: string; tipo: 'emitida' | 'recibida' | 'aeat' | 'otro'
  estado: 'importado' | 'pendiente' | 'ignorado' | 'error'; mensaje: string; revisado: string
  datos: { fecha?: string; contraparte?: string; concepto?: string; base?: number; tipo_iva?: number; total?: number; avisos?: string[] }
}
export interface DocumentosDrive { ia: boolean; google_client_id: string | null; documentos: DocumentoDrive[] }
export interface MensajeChat { role: 'user' | 'assistant'; content: string }

export interface AjustesIA {
  proveedor: 'openai' | 'anthropic'
  modelo: string
  disponible: boolean
  proveedores: Record<'openai' | 'anthropic', {
    nombre: string
    modelo_defecto: string
    modelo: string
    clave: string | null
    origen_clave: 'app' | 'entorno' | null
  }>
}

export interface Llamada { id: number; fecha: string; importe: number; pagado: boolean }
export interface InversionPrivada {
  id: number; nombre: string; gestora: string; compromiso: number; fecha_compromiso: string | null
  nav: number; nav_fecha: string | null; distribuido: number; desembolsado: number; pendiente: number
  sin_calendario: number; pct_desembolsado: number | null; tvpi: number | null; resultado: number
  proxima_llamada: { fecha: string; importe: number } | null; llamadas: Llamada[]; notas: string
}
export interface Inversiones {
  inversiones: InversionPrivada[]
  totales: { compromiso: number; desembolsado: number; pendiente: number; nav: number; distribuido: number }
}

export interface PosicionIndexa {
  nombre: string; codigo: string; clase: string; gestora: string; titulos: number | null; precio: number | null
  valor: number; coste: number | null; fecha: string | null; peso: number
}
export interface CarteraIndexa {
  cuenta_id: number; nombre: string; numero: string; fecha: string | null
  tipo?: string | null; producto?: string | null; perfil_riesgo?: number | null
  total?: number; efectivo?: number | null; invertido?: number; coste?: number | null; plusvalia?: number | null
  rentabilidad_anual?: number | null; rentabilidad_total?: number | null; rentabilidad_dinero?: number | null
  rentabilidad_esperada?: number | null; volatilidad?: number | null; posiciones?: PosicionIndexa[]
}
export interface SupuestosPrevision {
  nomina: { empresa: string; bruto_anual: number; variable_pct: number; mes_variable: number; pagas: number } | null
  clientes: { nombre: string; tarifa_hora: number; horas_dia: number; dias_mes: number | null; iva: number; retencion: number }[]
  gastos_autonomo_mes: number; gasto_habitual_mes: number | null; meses_sin_facturar: number[]
}
export interface MesPrevision {
  mes: string; nomina: number; facturado: number; cobros: number; iva: number; retenciones: number; alquiler: number
  gastos: number; pagos_previstos: number; impuestos: { concepto: string; importe: number; presentado: boolean }[]
  total_impuestos: number; neto: number; liquidez: number
}
export interface RentaPrevista {
  anio: number; rendimiento_trabajo: number; rendimiento_actividad: number; rendimiento_alquiler: number; base: number
  cuota: number; retenciones_nomina: number; retenciones_facturas: number; pagos_130: number; resultado: number; tipo_medio: number
  ingresos: { fuentes: IngresoFuente[]; total: Omit<IngresoFuente, 'fuente'> }
}
export interface IngresoFuente {
  fuente: string; bruto_anual: number; neto_anual: number; gastos_anual: number; irpf_anual: number; bruto_mes: number; neto_mes: number
}
export interface Prevision {
  supuestos: SupuestosPrevision; gasto_habitual_banco: number | null; liquidez_hoy: number
  gastos_autonomo_mes: number; origen_gastos_autonomo: string
  renta_presentada: { anio: number; resultado: number; casillas: Record<string, number> } | null
  clientes: { nombre: string; tarifa_hora: number; horas_dia: number; dias_mes: number; origen_dias: string }[]
  meses: MesPrevision[]; anios: RentaPrevista[]
}
export interface GastosRecientes {
  desde: string; meses: number; ingresos_mes: number; gastos_mes: number; ahorro_mes: number; tasa_ahorro: number | null
  categorias: { categoria: string; mes: number }[]
  suscripciones: { concepto: string; mes: number; anual: number; ultimo_cargo: string; veces: number }[]
  suscripciones_mes: number
}
