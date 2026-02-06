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
import { DealerGravityProvider } from './contexts/DealerGravityContext.tsx'

// Wrapper component for routes that need trading providers
function TradingProviders({ children }: { children: React.ReactNode }) {
  return (
    <DealerGravityProvider>
      <RiskGraphProvider>
        <TradeLogProvider>
          {children}
        </TradeLogProvider>
      </RiskGraphProvider>
    </DealerGravityProvider>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AlertProvider>
        <PathProvider>
          <AuthWrapper>
            <TimezoneProvider>
              <Routes>
                <Route path="/" element={
                  <TradingProviders>
                    <AppLayout><App /></AppLayout>
                  </TradingProviders>
                } />
                <Route path="/profile" element={<ProfilePage />} />
                <Route path="/workbench" element={
                  <TradingProviders>
                    <WorkbenchPage />
                  </TradingProviders>
                } />
                <Route path="/admin" element={<AdminPage />} />
                <Route path="/admin/ml-lab" element={<MLLabPage />} />
              </Routes>
            </TimezoneProvider>
          </AuthWrapper>
        </PathProvider>
      </AlertProvider>
    </BrowserRouter>
  </StrictMode>,
)
