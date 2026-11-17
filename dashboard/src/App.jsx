import { useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useSearchParams } from 'react-router-dom'
import ProtectedRoute from './components/ProtectedRoute'
import Toast from './components/Toast'
import { AuthProvider } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import { LanguageProvider } from './context/LanguageContext'
import AdminPage from './pages/AdminPage'
import CitizenPage from './pages/CitizenPage'
import LoginPage from './pages/LoginPage'
import MapPage from './pages/MapPage'
import OfficerAlertsPage from './pages/OfficerAlertsPage'
import OfficerDashboardPage from './pages/OfficerDashboardPage'
import EnvironmentalDataPage from './pages/EnvironmentalDataPage'
import ForecastWeatherPage from './pages/ForecastWeatherPage'
import ModelResearchPage from './pages/ModelResearchPage'
import StaffReportsPage from './pages/StaffReportsPage'
import ModelsPage from './pages/ModelsPage'
import RainfallHistoryPage from './pages/RainfallHistoryPage'
import DownloadsPage from './pages/DownloadsPage'
import AdvisoriesPage from './pages/AdvisoriesPage'
import RoutePage from './pages/RoutePage'

function LegacyAreaRedirect() {
  const [params] = useSearchParams(), next = new URLSearchParams()
  const area = params.get('site') || params.get('hotspot')
  if (area) next.set('area',area)
  return <Navigate to={`/${next.size ? '?' + next.toString() : ''}`} replace />
}

// Model polling belongs to the guarded research screen; reporting and geography are independent.
// Auth and theme are provided via Context so every nested page/component can read them.
export default function App() {
  const [toasts, setToasts] = useState([])

  function showToast(message, type = 'success') {
    const id = Date.now() + Math.random()
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 3000)
  }

  return (
    <ThemeProvider>
      <LanguageProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<MapPage />} />
            <Route path="/hotspots" element={<LegacyAreaRedirect />} />
            <Route path="/citizen" element={<CitizenPage showToast={showToast} />} />
            <Route path="/officer/reports" element={<ProtectedRoute role="officer"><StaffReportsPage /></ProtectedRoute>} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/environmental-data" element={<ProtectedRoute role="officer"><EnvironmentalDataPage /></ProtectedRoute>} />
            <Route path="/weather-outlook" element={<ProtectedRoute role="officer"><ForecastWeatherPage /></ProtectedRoute>} />
            <Route path="/research" element={<ProtectedRoute role="officer"><ModelResearchPage /></ProtectedRoute>} />
            <Route path="/v2-shadow" element={<ProtectedRoute role="officer"><Navigate to="/research?retired=v2" replace /></ProtectedRoute>} />
            <Route
              path="/officer"
              element={
                <ProtectedRoute role="officer">
                  <OfficerDashboardPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/officer/alerts"
              element={
                <ProtectedRoute role="officer">
                  <OfficerAlertsPage />
                </ProtectedRoute>
              }
            />
            <Route path="/history" element={<ProtectedRoute role="officer"><RainfallHistoryPage /></ProtectedRoute>} />
            <Route path="/advisories" element={<ProtectedRoute role="officer"><AdvisoriesPage /></ProtectedRoute>} />
            <Route path="/route" element={<RoutePage />} />
            <Route path="/downloads" element={<ProtectedRoute role="officer"><DownloadsPage /></ProtectedRoute>} />
            <Route path="/admin" element={<ProtectedRoute role="admin"><AdminPage section="health" /></ProtectedRoute>} />
            <Route path="/admin/users" element={<ProtectedRoute role="admin"><AdminPage section="users" /></ProtectedRoute>} />
            <Route path="/admin/models" element={<ProtectedRoute role="admin"><ModelsPage /></ProtectedRoute>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          <Toast toasts={toasts} />
        </BrowserRouter>
      </AuthProvider>
      </LanguageProvider>
    </ThemeProvider>
  )
}
