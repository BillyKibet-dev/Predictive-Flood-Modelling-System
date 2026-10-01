import { Droplets, LogOut } from 'lucide-react'
import { Link } from 'react-router-dom'

// Top navigation bar shown on the authenticated Dashboard and Alerts pages
export default function AuthNavbar({ user, active, onSignOut }) {
  const linkClass = (name) =>
    `text-sm font-medium pb-1 ${
      active === name ? 'text-brand border-b-2 border-brand' : 'text-gray-500 hover:text-brand'
    }`

  return (
    <nav className="bg-white shadow px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2 font-bold text-brand text-lg">
        <Droplets size={22} />
        NairobiFloodWatch
      </div>

      <div className="flex items-center gap-6">
        <Link to="/dashboard" className={linkClass('dashboard')}>
          Dashboard
        </Link>
        <Link to="/alerts" className={linkClass('alerts')}>
          Alerts
        </Link>
        {user?.role === 'admin' && (
          <Link to="/admin" className={linkClass('admin')}>
            Admin
          </Link>
        )}
      </div>

      <div className="flex items-center gap-3">
        <span className="text-xs font-semibold uppercase bg-brand-accent text-white px-2 py-1 rounded">
          {user?.role}
        </span>
        <span className="text-sm text-gray-700">{user?.name}</span>
        <button
          onClick={onSignOut}
          className="flex items-center gap-1 bg-red-500 hover:bg-red-600 text-white text-sm px-3 py-1.5 rounded"
        >
          <LogOut size={14} /> Sign Out
        </button>
      </div>
    </nav>
  )
}
