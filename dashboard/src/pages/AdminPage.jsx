import { BarChart2, Bell, FileText, Monitor, RefreshCw, Users } from 'lucide-react'
import { useState } from 'react'
import TopNav from '../components/TopNav'
import PredictionStatus from '../components/PredictionStatus'
import AlertThresholds from './admin/AlertThresholds'
import CitizenReports from './admin/CitizenReports'
import ModelPerformance from './admin/ModelPerformance'
import SystemHealth from './admin/SystemHealth'
import UserAccounts from './admin/UserAccounts'

const MENU = [
  { key: 'users', label: 'User Accounts', icon: Users },
  { key: 'thresholds', label: 'Research Alert Policy', icon: Bell },
  { key: 'health', label: 'Runtime and Data Status', icon: Monitor },
  { key: 'performance', label: 'Model Performance', icon: BarChart2 },
  { key: 'reports', label: 'Citizen Reports', icon: FileText },
]

// System Administrator panel — sidebar + content CSS grid, independently scrollable regions
export default function AdminPage({ users, setUsers, showToast, predictions }) {
  const [section, setSection] = useState('users')

  return (
    <div className="h-screen grid grid-rows-[64px_1fr] grid-cols-1">
      <div className="col-span-full">
        <TopNav variant="app" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[240px_1fr] overflow-hidden">
        {/* Sidebar */}
        <aside
          className="hidden md:flex flex-col bg-brand text-white overflow-y-auto"
          style={{ height: 'calc(100vh - 64px)' }}
        >
          <div className="px-6 py-6">
            <p className="text-sm font-semibold">NairobiFloodWatch</p>
            <p className="text-xs text-white/60 mt-0.5">Administrator</p>
          </div>
          <nav className="flex-1 px-3 space-y-1">
            {MENU.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setSection(key)}
                className={`relative w-full flex items-center gap-3 h-11 px-3 rounded-btn text-sm font-medium transition-colors ${
                  section === key ? 'bg-white/10 text-white' : 'text-white/70 hover:text-white'
                }`}
              >
                {section === key && <span className="absolute left-0 top-0 bottom-0 w-1 rounded-r bg-accent" />}
                <Icon size={18} />
                {label}
              </button>
            ))}
          </nav>
          <div className="px-3 pb-6 pt-3 border-t border-white/10">
            <button
              disabled
              title="Model training is an approved offline research task; this application does not start training."
              className="w-full flex items-center gap-3 min-h-11 px-3 rounded-btn text-sm font-medium text-accent opacity-60 cursor-not-allowed"
            >
              <RefreshCw size={18} />
              Offline training — not enabled
            </button>
          </div>
        </aside>

        {/* Main content */}
        <main className="overflow-y-auto" style={{ height: 'calc(100vh - 64px)', backgroundColor: 'var(--bg)' }}>
          <div className="max-w-[960px] mx-auto px-6 py-10 page-transition">
            {predictions && <div className="mb-6"><PredictionStatus predictions={predictions} /></div>}
            {section === 'users' && <UserAccounts users={users} setUsers={setUsers} showToast={showToast} />}
            {section === 'thresholds' && <AlertThresholds showToast={showToast} />}
            {section === 'health' && <SystemHealth />}
            {section === 'performance' && <ModelPerformance />}
            {section === 'reports' && <CitizenReports />}
          </div>
        </main>
      </div>
    </div>
  )
}
