import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import AuthWrapper from './AuthWrapper.tsx'
import AppLayout from './components/AppLayout.tsx'
import ProfilePage from './pages/Profile.tsx'
import WorkbenchPage from './pages/Workbench.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthWrapper>
        <Routes>
          <Route path="/" element={<AppLayout><App /></AppLayout>} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/workbench" element={<WorkbenchPage />} />
        </Routes>
      </AuthWrapper>
    </BrowserRouter>
  </StrictMode>,
)
