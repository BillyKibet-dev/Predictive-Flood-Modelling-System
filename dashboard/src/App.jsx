import { useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import RequireAuth from './components/RequireAuth'
import Toast from './components/Toast'
import { ALERTS, MOCK_CREDENTIALS, USERS, ZONES } from './data/mockData'
import AdminPage from './pages/AdminPage'
import AlertsPage from './pages/AlertsPage'
import DashboardPage from './pages/DashboardPage'
import LoginPage from './pages/LoginPage'
import PublicPage from './pages/PublicPage'

// Root component — owns all lifted application state (auth, zones, alerts, users, toasts)
// and wires up the four top-level routes.
export default function App() {
  const [user, setUser] = useState(null)
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

  function handleLogin(email, password) {
    const account = MOCK_CREDENTIALS[email]
    if (account && account.password === password) {
      setUser({ name: account.name, email, role: account.role })
      return account.role
    }
    return null
  }

  function handleLogout() {
    setUser(null)
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/public" replace />} />
        <Route path="/public" element={<PublicPage zones={zones} showToast={showToast} />} />
        <Route path="/login" element={<LoginPage onLogin={handleLogin} />} />
        <Route
          path="/dashboard"
          element={
            <RequireAuth user={user}>
              <DashboardPage user={user} zones={zones} setZones={setZones} alerts={alerts} onLogout={handleLogout} />
            </RequireAuth>
          }
        />
        <Route
          path="/alerts"
          element={
            <RequireAuth user={user}>
              <AlertsPage
                user={user}
                alerts={alerts}
                setAlerts={setAlerts}
                onLogout={handleLogout}
                showToast={showToast}
              />
            </RequireAuth>
          }
        />
        <Route
          path="/admin"
          element={
            <RequireAuth user={user} role="admin">
              <AdminPage
                user={user}
                onLogout={handleLogout}
                users={users}
                setUsers={setUsers}
                zones={zones}
                showToast={showToast}
              />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/public" replace />} />
      </Routes>
      <Toast toasts={toasts} />
    </BrowserRouter>
  )
}
