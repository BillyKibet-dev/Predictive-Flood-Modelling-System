import { BarChart2, Bell, FileText, Monitor, RefreshCw, Users } from 'lucide-react'
import { useState } from 'react'
import TopNav from '../components/TopNav'
import UserAccounts from './admin/UserAccounts'
import CitizenReports from './admin/CitizenReports'
import AlertThresholds from './admin/AlertThresholds'
import ModelPerformance from './admin/ModelPerformance'
import SystemHealth from './admin/SystemHealth'

const MENU = [
  { key: 'users', label: 'User Accounts', icon: Users },
  { key: 'thresholds', label: 'Decision Support', icon: Bell },
  { key: 'health', label: 'Runtime and Data Status', icon: Monitor },
  { key: 'performance', label: 'Model Performance', icon: BarChart2 },
  { key: 'reports', label: 'Citizen Reports', icon: FileText },
]

// System Administrator panel — sidebar + content CSS grid, independently scrollable regions
export default function AdminPage({ showToast, predictions }) {
  const [section, setSection] = useState('health')

  return (
    <div className="min-h-screen bg-bg">
      <div className="col-span-full">
        <TopNav variant="app" />
      </div>

      <label className="block md:hidden p-4 text-sm text-ink">Admin section<select aria-label="Admin section" className="border border-border rounded-btn bg-surface p-2 ml-2" value={section} onChange={event => setSection(event.target.value)}>{MENU.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
      <div className="grid grid-cols-1 md:grid-cols-[240px_1fr]">
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
        </aside>

        {/* Main content */}
        <main className="overflow-y-auto" style={{ height: 'calc(100vh - 64px)', backgroundColor: 'var(--bg)' }}>
          <div className="max-w-[960px] mx-auto px-6 py-10 page-transition">

            {section === 'users' && <UserAccounts />}
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
