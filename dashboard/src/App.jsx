import { useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import ProtectedRoute from './components/ProtectedRoute'
import Toast from './components/Toast'
import { AuthProvider } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import usePredictionView from './hooks/usePredictionView'
import AdminPage from './pages/AdminPage'
import CitizenPage from './pages/CitizenPage'
import LoginPage from './pages/LoginPage'
import MapPage from './pages/MapPage'
import OfficerAlertsPage from './pages/OfficerAlertsPage'
import OfficerDashboardPage from './pages/OfficerDashboardPage'
import EnvironmentalDataPage from './pages/EnvironmentalDataPage'

// One prediction subscription is shared across routes. Unconnected management is disabled.
// Auth and theme are provided via Context so every nested page/component can read them.
export default function App() {
  const predictions = usePredictionView()
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
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<MapPage predictions={predictions} />} />
            <Route path="/citizen" element={<CitizenPage predictions={predictions} showToast={showToast} />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/environmental-data" element={<ProtectedRoute role="officer"><EnvironmentalDataPage /></ProtectedRoute>} />
            <Route
              path="/officer"
              element={
                <ProtectedRoute role="officer">
                  <OfficerDashboardPage predictions={predictions} alerts={[]} showToast={showToast} />
                </ProtectedRoute>
              }
            />
            <Route
              path="/officer/alerts"
              element={
                <ProtectedRoute role="officer">
                  <OfficerAlertsPage alerts={[]} showToast={showToast} predictions={predictions} />
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin"
              element={
                <ProtectedRoute role="admin">
                  <AdminPage showToast={showToast} predictions={predictions} />
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          <Toast toasts={toasts} />
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  )
}
