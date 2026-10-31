import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { ServerProvider } from './lib/server'
import { CameraPage } from './pages/CameraPage'
import { Dashboard } from './pages/Dashboard'

// /camera is the iPhone page; everything else is the dashboard.
const isCamera = location.pathname.startsWith('/camera')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ServerProvider role={isCamera ? 'phone' : 'dashboard'}>
      {isCamera ? <CameraPage /> : <Dashboard />}
    </ServerProvider>
  </StrictMode>,
)
