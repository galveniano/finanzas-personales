import { lazy } from 'react'

// Cada página se descarga al visitarla: así recharts no va en el paquete inicial.
// El <Suspense> que las espera está en Layout, alrededor del <Outlet />.
export const Inicio = lazy(() => import('./pages/Inicio'))
export const Cuentas = lazy(() => import('./pages/Cuentas'))
export const Gastos = lazy(() => import('./pages/Gastos'))
export const Ingresos = lazy(() => import('./pages/Ingresos'))
export const Impuestos = lazy(() => import('./pages/Impuestos'))
export const Inmuebles = lazy(() => import('./pages/Inmuebles'))
export const Plan = lazy(() => import('./pages/Plan'))
export const Ajustes = lazy(() => import('./pages/Ajustes'))
export const Asistente = lazy(() => import('./pages/Asistente'))
