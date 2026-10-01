import { BarChart2, Bell, Droplets, FileText, LogOut, Monitor, Radio, RefreshCw, Users } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AlertThresholds from './admin/AlertThresholds'
import CitizenReports from './admin/CitizenReports'
import ModelPerformance from './admin/ModelPerformance'
import SensorStatus from './admin/SensorStatus'
import SystemHealth from './admin/SystemHealth'
import UserAccounts from './admin/UserAccounts'

const MENU = [
  { key: 'users', label: 'User Accounts', icon: Users },
  { key: 'thresholds', label: 'Alert Thresholds', icon: Bell },
  { key: 'sensors', label: 'Sensor Status', icon: Radio },
  { key: 'health', label: 'System Health', icon: Monitor },
  { key: 'performance', label: 'Model Performance', icon: BarChart2 },
  { key: 'reports', label: 'Citizen Reports', icon: FileText },
]

// System Administrator panel — sidebar navigation + switchable content sections
export default function AdminPage({ user, onLogout, users, setUsers, zones, showToast }) {
  const navigate = useNavigate()
  const [section, setSection] = useState('users')

  function handleSignOut() {
    onLogout()
    navigate('/public')
  }

  function handleRetrain() {
    showToast('Model retraining initiated. This may take several minutes.', 'info')
  }

  return (
    <div className="min-h-screen flex bg-gray-100">
      {/* Sidebar */}
      <aside className="w-64 shrink-0 bg-brand text-white flex flex-col fixed inset-y-0 left-0 overflow-y-auto">
        <div className="flex items-center gap-2 px-5 py-5 font-bold text-lg border-b border-white/10">
          <Droplets size={22} />
          NairobiFloodWatch
        </div>
        <nav className="flex-1 py-4 space-y-1 px-2">
          {MENU.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setSection(key)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                section === key ? 'bg-white/20' : 'hover:bg-white/10'
              }`}
            >
              <Icon size={18} />
              {label}
            </button>
          ))}
        </nav>
        <div className="border-t border-white/10 p-2 space-y-1">
          <button
            onClick={handleRetrain}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-semibold text-red-300 hover:bg-white/10"
          >
            <RefreshCw size={18} />
            Retrain Model
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 ml-64 flex flex-col">
        <header className="bg-white shadow px-6 py-3 flex items-center justify-end">
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold uppercase bg-brand-accent text-white px-2 py-1 rounded">
              {user.role}
            </span>
            <span className="text-sm text-gray-700">{user.name}</span>
            <button
              onClick={handleSignOut}
              className="flex items-center gap-1 bg-red-500 hover:bg-red-600 text-white text-sm px-3 py-1.5 rounded"
            >
              <LogOut size={14} /> Sign Out
            </button>
          </div>
        </header>

        <main className="flex-1 p-6 animate-fade-in-up">
          {section === 'users' && <UserAccounts users={users} setUsers={setUsers} showToast={showToast} />}
          {section === 'thresholds' && <AlertThresholds showToast={showToast} />}
          {section === 'sensors' && <SensorStatus zones={zones} />}
          {section === 'health' && <SystemHealth />}
          {section === 'performance' && <ModelPerformance />}
          {section === 'reports' && <CitizenReports />}
        </main>
      </div>
    </div>
  )
}
