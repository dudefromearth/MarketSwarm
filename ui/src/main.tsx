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
import AdminVexyPage from './pages/AdminVexy.tsx'
import MLLabPage from './pages/MLLab.tsx'
import VPLineEditor from './pages/VPLineEditor.tsx'
import AdminEconIndicatorsPage from './pages/AdminEconIndicators.tsx'
import AdminRSSIntelPage from './pages/AdminRSSIntel.tsx'
import AdminDoctrinePage from './pages/AdminDoctrine.tsx'
import EdgeLabPage from './pages/EdgeLab.tsx'
import { AlertProvider } from './contexts/AlertContext.tsx'
import { SystemNotificationsProvider } from './contexts/SystemNotificationsContext.tsx'
import { PathProvider } from './contexts/PathContext.tsx'
import { TimezoneProvider } from './contexts/TimezoneContext.tsx'
import { RiskGraphProvider } from './contexts/RiskGraphContext.tsx'
import { TradeLogProvider } from './contexts/TradeLogContext.tsx'
import { DealerGravityProvider } from './contexts/DealerGravityContext.tsx'
import { ApiClientProvider } from './contexts/ApiClientContext.tsx'
import { PositionsProvider } from './contexts/PositionsContext.tsx'
import { AlgoAlertProvider } from './contexts/AlgoAlertContext.tsx'
import { UserPreferencesProvider } from './contexts/UserPreferencesContext.tsx'
import { TierGatesProvider } from './contexts/TierGatesContext.tsx'
import { ErrorBoundary } from './components/ErrorBoundary.tsx'

// Wrapper component for routes that need trading providers
function TradingProviders({ children }: { children: React.ReactNode }) {
  return (
    <ApiClientProvider offlineEnabled={true}>
      <DealerGravityProvider>
        <RiskGraphProvider>
          <PositionsProvider>
            <AlgoAlertProvider>
              <TradeLogProvider>
                {children}
              </TradeLogProvider>
            </AlgoAlertProvider>
          </PositionsProvider>
        </RiskGraphProvider>
      </DealerGravityProvider>
    </ApiClientProvider>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary componentName="MarketSwarm">
    <BrowserRouter>
      <UserPreferencesProvider>
      <SystemNotificationsProvider>
        <AlertProvider>
          <PathProvider>
          <AuthWrapper>
            <TierGatesProvider>
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
                <Route path="/admin/vexy" element={<AdminVexyPage />} />
                <Route path="/admin/economic-indicators" element={<AdminEconIndicatorsPage />} />
                <Route path="/admin/rss-intel" element={<AdminRSSIntelPage />} />
                <Route path="/admin/doctrine" element={<AdminDoctrinePage />} />
                <Route path="/edge-lab" element={
                  <TradingProviders>
                    <EdgeLabPage />
                  </TradingProviders>
                } />
                <Route path="/admin/vp-editor" element={
                  <TradingProviders>
                    <VPLineEditor />
                  </TradingProviders>
                } />
              </Routes>
            </TimezoneProvider>
            </TierGatesProvider>
          </AuthWrapper>
        </PathProvider>
        </AlertProvider>
      </SystemNotificationsProvider>
    </UserPreferencesProvider>
    </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>,
)
