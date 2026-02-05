import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import AuthWrapper from './AuthWrapper.tsx'
import AppLayout from './components/AppLayout.tsx'
import ProfilePage from './pages/Profile.tsx'
import WorkbenchPage from './pages/Workbench.tsx'
import AdminPage from './pages/Admin.tsx'
import MLLabPage from './pages/MLLab.tsx'
import { AlertProvider } from './contexts/AlertContext.tsx'
import { PathProvider } from './contexts/PathContext.tsx'
import { TimezoneProvider } from './contexts/TimezoneContext.tsx'
import { RiskGraphProvider } from './contexts/RiskGraphContext.tsx'
import { TradeLogProvider } from './contexts/TradeLogContext.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AlertProvider>
        <PathProvider>
          <AuthWrapper>
            <TimezoneProvider>
            <RiskGraphProvider>
            <TradeLogProvider>
            <Routes>
              <Route path="/" element={<AppLayout><App /></AppLayout>} />
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/workbench" element={<WorkbenchPage />} />
              <Route path="/admin" element={<AdminPage />} />
              <Route path="/admin/ml-lab" element={<MLLabPage />} />
            </Routes>
            </TradeLogProvider>
            </RiskGraphProvider>
            </TimezoneProvider>
          </AuthWrapper>
        </PathProvider>
      </AlertProvider>
    </BrowserRouter>
  </StrictMode>,
)
