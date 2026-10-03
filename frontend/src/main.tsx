import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import Layout from './components/Layout'
import { ProveedorAvisos } from './components/ui'
import Panel from './pages/Panel'
import Cuentas from './pages/Cuentas'
import Autonomo from './pages/Autonomo'
import Nominas from './pages/Nominas'
import Inmuebles from './pages/Inmuebles'
import Planificacion from './pages/Planificacion'
import Conexiones from './pages/Conexiones'
import Hacienda from './pages/Hacienda'
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
              <Route index element={<Panel />} />
              <Route path="cuentas" element={<Cuentas />} />
              <Route path="autonomo" element={<Autonomo />} />
              <Route path="hacienda" element={<Hacienda />} />
              <Route path="nominas" element={<Nominas />} />
              <Route path="inmuebles" element={<Inmuebles />} />
              <Route path="planificacion" element={<Planificacion />} />
              <Route path="conexiones" element={<Conexiones />} />
              <Route path="asistente" element={<Asistente />} />
            </Route>
          </Routes>
        </HashRouter>
        </Acceso>
      </ProveedorAvisos>
    </QueryClientProvider>
  </StrictMode>,
)
