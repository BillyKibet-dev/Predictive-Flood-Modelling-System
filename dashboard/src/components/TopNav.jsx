import { Droplets, LogOut, Moon, Sun } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'

const APP_LINKS = [
  { to: '/', label: 'Map' },
  { to: '/officer', label: 'Dashboard' },
  { to: '/officer/alerts', label: 'Alerts' },
]

// Universal top navigation — adapts between the public (map/citizen) shell
// and the authenticated app shell (officer/admin) used across protected pages.
export default function TopNav({ variant = 'public', active, unacknowledgedCount = 0 }) {
  const { user, logout } = useAuth()
  const { dark, toggleTheme } = useTheme()
  const navigate = useNavigate()

  function handleSignOut() {
    logout()
    navigate('/')
  }

  const ThemeToggle = (
    <button
      onClick={toggleTheme}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      className="w-9 h-9 flex items-center justify-center rounded-btn text-muted hover:text-ink hover:bg-bg transition-colors"
    >
      {dark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  )

  return (
    <nav className="h-16 bg-surface border-b border-border flex items-center px-6 sticky top-0 z-[1100]">
      <Link to="/" className="flex items-center gap-2 font-semibold text-brand" aria-label="NairobiFloodWatch home">
        <Droplets size={22} />
        NairobiFloodWatch
        {variant === 'app' && user?.role === 'admin' && (
          <span className="text-xs font-semibold bg-brand/10 text-brand px-2 py-0.5 rounded-badge">Admin</span>
        )}
      </Link>

      {variant === 'app' && (
        <div className="hidden md:flex items-center gap-6 mx-auto" aria-label="Primary">
          {APP_LINKS.filter((l) => l.to !== '/admin' || user?.role === 'admin').map((l) => (
            <Link
              key={l.to}
              to={l.to}
              className={`text-sm font-medium pb-1 border-b-2 transition-colors ${
                active === l.label ? 'text-brand border-brand' : 'text-muted border-transparent hover:text-ink'
              }`}
            >
              {l.label}
            </Link>
          ))}
          {user?.role === 'admin' && (
            <Link
              to="/admin"
              className={`text-sm font-medium pb-1 border-b-2 transition-colors ${
                active === 'Admin' ? 'text-brand border-brand' : 'text-muted border-transparent hover:text-ink'
              }`}
            >
              Admin
            </Link>
          )}
        </div>
      )}

      <div className="flex items-center gap-3 ml-auto">
        {variant === 'public' && (
          <Link
            to="/citizen"
            className={`hidden sm:inline text-sm font-medium ${active === 'citizen' ? 'text-brand underline underline-offset-4' : 'text-muted hover:text-ink'}`}
          >
            View Warnings
          </Link>
        )}

        {variant === 'app' && unacknowledgedCount > 0 && (
          <span
            className="text-xs font-semibold bg-risk-extreme text-white rounded-full w-6 h-6 flex items-center justify-center"
            style={{ animation: 'marker-pulse 2s ease-in-out infinite' }}
            aria-label={`${unacknowledgedCount} unacknowledged alerts`}
          >
            {unacknowledgedCount}
          </span>
        )}

        {ThemeToggle}

        {!user && variant === 'public' && (
          <Link
            to="/login"
            className="text-sm font-medium border border-brand text-brand rounded-btn px-4 h-10 flex items-center hover:bg-brand hover:text-white transition-colors"
          >
            Sign In
          </Link>
        )}

        {user && (
          <>
            {variant === 'public' && (
              <Link
                to={user.role === 'admin' ? '/admin' : '/officer'}
                className="text-sm font-medium text-brand hover:underline"
              >
                Go to {user.role === 'admin' ? 'Admin' : 'Dashboard'} →
              </Link>
            )}
            <span className="hidden sm:inline text-sm text-ink">{user.name}</span>
            <button
              onClick={handleSignOut}
              aria-label="Sign out"
              className="flex items-center gap-1 text-sm font-medium text-muted hover:text-ink"
            >
              <LogOut size={16} /> Sign Out
            </button>
          </>
        )}
      </div>
    </nav>
  )
}
