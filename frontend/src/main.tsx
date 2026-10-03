import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import Layout from './components/Layout'
import { ProveedorAvisos } from './components/ui'
import Inicio from './pages/Inicio'
import Cuentas from './pages/Cuentas'
import Ingresos from './pages/Ingresos'
import Impuestos from './pages/Impuestos'
import Inmuebles from './pages/Inmuebles'
import Plan from './pages/Plan'
import Ajustes from './pages/Ajustes'
import Asistente from './pages/Asistente'
import Acceso from './components/Acceso'

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } } })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <ProveedorAvisos>
        <Acceso>
        <HashRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<Inicio />} />
              <Route path="cuentas" element={<Cuentas />} />
              <Route path="ingresos" element={<Ingresos />} />
              <Route path="impuestos" element={<Impuestos />} />
              <Route path="inmuebles" element={<Inmuebles />} />
              <Route path="plan" element={<Plan />} />
              <Route path="ajustes" element={<Ajustes />} />
              <Route path="asistente" element={<Asistente />} />
              {/* Direcciones antiguas */}
              <Route path="autonomo" element={<Navigate to="/ingresos" replace />} />
              <Route path="nominas" element={<Navigate to="/ingresos?ver=nomina" replace />} />
              <Route path="hacienda" element={<Navigate to="/impuestos" replace />} />
              <Route path="prevision" element={<Navigate to="/plan" replace />} />
              <Route path="planificacion" element={<Navigate to="/plan" replace />} />
              <Route path="conexiones" element={<Navigate to="/ajustes" replace />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </HashRouter>
        </Acceso>
      </ProveedorAvisos>
    </QueryClientProvider>
  </StrictMode>,
)
