import { useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import ProtectedRoute from './components/ProtectedRoute'
import Toast from './components/Toast'
import { AuthProvider } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import { ALERTS, USERS, ZONES } from './data/mockData'
import AdminPage from './pages/AdminPage'
import CitizenPage from './pages/CitizenPage'
import LoginPage from './pages/LoginPage'
import MapPage from './pages/MapPage'
import OfficerAlertsPage from './pages/OfficerAlertsPage'
import OfficerDashboardPage from './pages/OfficerDashboardPage'

// Root component — owns lifted domain state (zones, alerts, users, toasts) and wires up routing.
// Auth and theme are provided via Context so every nested page/component can read them.
export default function App() {
  const [zones, setZones] = useState(ZONES)
  const [alerts, setAlerts] = useState(ALERTS)
  const [users, setUsers] = useState(USERS)
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
            <Route path="/" element={<MapPage zones={zones} alerts={alerts} />} />
            <Route path="/citizen" element={<CitizenPage zones={zones} showToast={showToast} />} />
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/officer"
              element={
                <ProtectedRoute role="officer">
                  <OfficerDashboardPage zones={zones} alerts={alerts} setAlerts={setAlerts} showToast={showToast} />
                </ProtectedRoute>
              }
            />
            <Route
              path="/officer/alerts"
              element={
                <ProtectedRoute role="officer">
                  <OfficerAlertsPage alerts={alerts} setAlerts={setAlerts} showToast={showToast} />
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin"
              element={
                <ProtectedRoute role="admin">
                  <AdminPage users={users} setUsers={setUsers} showToast={showToast} />
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
