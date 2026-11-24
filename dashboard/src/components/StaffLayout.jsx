import { Activity, CloudRain, Megaphone, Cpu, Download, Droplets, FlaskConical, History, Inbox, LayoutGrid, LogOut, Map, Menu, Moon, Sun, Users, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import useStaffList from '../hooks/useStaffList'
import usePageTitle from '../hooks/usePageTitle'

// Three short groups instead of one long row of links. Admin tools appear only for admins.
export const STAFF_NAV = [
  { group: 'Today', items: [
    { to: '/officer', label: 'Overview', icon: LayoutGrid },
    { to: '/officer/reports', label: 'Reports', icon: Inbox, badge: 'new-reports' },
    { to: '/advisories', label: 'Advisories', icon: Megaphone },
    { to: '/', label: 'Map', icon: Map },
  ] },
  { group: 'Data', items: [
    { to: '/weather-outlook', label: 'Weather', icon: CloudRain },
    { to: '/history', label: 'Rainfall history', icon: History },
    { to: '/downloads', label: 'Downloads', icon: Download },
  ] },
  { group: 'Admin', admin: true, items: [
    { to: '/admin/models', label: 'Models', icon: Cpu },
    { to: '/admin/users', label: 'Users', icon: Users },
    { to: '/admin', label: 'System', icon: Activity },
  ] },
]
const RESEARCH = { to: '/research', label: 'Model checks', icon: FlaskConical }

function isActive(pathname, to) {
  if (to === '/officer') return pathname === '/officer'
  if (to === '/admin') return pathname === '/admin'
  return pathname === to || pathname.startsWith(to + '/')
}

function NavLinks({ pathname, role, newReports, onNavigate }) {
  const link = ({ to, label, icon: Icon, badge }) => {
    const active = isActive(pathname, to)
    return <li key={to}><Link to={to} onClick={onNavigate} aria-current={active ? 'page' : undefined}
      className={`staff-nav-link flex items-center gap-3 h-9 px-3 rounded-btn text-sm ${active ? 'bg-surface-2 text-ink font-semibold' : 'text-muted hover:text-ink hover:bg-surface-2'}`}>
      <Icon size={17} strokeWidth={active ? 2.2 : 1.8} aria-hidden="true" />
      <span className="flex-1">{label}</span>
      {badge === 'new-reports' && newReports > 0 && <span className="tabular text-[11px] font-semibold min-w-5 h-5 px-1.5 rounded-full bg-accent text-white grid place-items-center" aria-label={`${newReports} new`}>{newReports}</span>}
    </Link></li>
  }
  return <nav aria-label="Staff" className="space-y-5">
    {STAFF_NAV.filter(g => !g.admin || role === 'admin').map(g => <div key={g.group}>
      <p className="eyebrow px-3 mb-1.5">{g.group}</p>
      <ul className="space-y-0.5">{g.items.map(link)}</ul>
    </div>)}
    <ul className="pt-1 border-t border-border">{link(RESEARCH)}</ul>
  </nav>
}

function Account({ user, onSignOut }) {
  const { dark, toggleTheme } = useTheme()
  const initials = user.name.split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase()
  return <div className="flex items-center gap-2 pt-3 border-t border-border">
    <span aria-hidden="true" className="w-8 h-8 rounded-full bg-brand text-white grid place-items-center text-xs font-semibold">{initials}</span>
    <div className="min-w-0 flex-1"><p className="text-sm font-medium truncate">{user.name}</p><p className="text-xs text-muted">{user.role === 'admin' ? 'Administrator' : 'Officer'}</p></div>
    <button onClick={toggleTheme} aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'} className="w-8 h-8 grid place-items-center rounded-btn text-muted hover:text-ink hover:bg-surface-2">{dark ? <Sun size={16} /> : <Moon size={16} />}</button>
    <button onClick={onSignOut} aria-label="Sign out" title="Sign out" className="w-8 h-8 grid place-items-center rounded-btn text-muted hover:text-ink hover:bg-surface-2"><LogOut size={16} /></button>
  </div>
}

// The signed-in workspace: sidebar on wide screens, a drawer on phones.
export default function StaffLayout({ children, width = 'max-w-6xl' }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate(), { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const pending = useStaffList('/citizen-reports?review_status=New&limit=1')
  const newReports = pending.data?.total ?? 0
  useEffect(() => { setOpen(false) }, [pathname])
  useEffect(() => {
    if (!open) return
    const close = event => { if (event.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [open])
  if (!user) return null
  const signOut = () => { logout(); navigate('/') }
  const brand = <Link to="/officer" className="flex items-center gap-2 font-semibold text-ink" aria-label="NairobiFloodWatch overview">
    <span className="w-7 h-7 rounded-btn bg-brand text-white grid place-items-center"><Droplets size={16} /></span>
    <span className="tracking-tight">FloodWatch</span>
  </Link>
  return <div className="min-h-screen bg-bg text-ink lg:grid lg:grid-cols-[240px_1fr]">
    <aside className="hidden lg:flex flex-col gap-6 sticky top-0 h-screen border-r border-border bg-surface px-3 py-4">
      <div className="px-3">{brand}</div>
      <div className="flex-1 overflow-y-auto"><NavLinks pathname={pathname} role={user.role} newReports={newReports} /></div>
      <Account user={user} onSignOut={signOut} />
    </aside>

    <header className="lg:hidden sticky top-0 z-[1100] h-14 flex items-center gap-3 px-4 bg-surface border-b border-border">
      <button onClick={() => setOpen(true)} aria-label="Open menu" aria-expanded={open} className="w-9 h-9 -ml-1.5 grid place-items-center rounded-btn hover:bg-surface-2"><Menu size={20} /></button>
      {brand}
      {newReports > 0 && <Link to="/officer/reports?review_status=New" className="ml-auto text-xs font-semibold text-accent tabular">{newReports} new</Link>}
    </header>
    <div className="staff-scrim lg:hidden fixed inset-0 z-[1190] bg-black/30" data-open={open} onClick={() => setOpen(false)} aria-hidden="true" />
    <div className="staff-drawer lg:hidden fixed inset-y-0 left-0 z-[1200] w-72 max-w-[85vw] bg-surface border-r border-border flex flex-col gap-6 px-3 py-4"
      data-open={open} role="dialog" aria-modal="true" aria-label="Menu" inert={open ? undefined : ''}>
      <div className="flex items-center justify-between px-3">{brand}<button onClick={() => setOpen(false)} aria-label="Close menu" className="w-8 h-8 grid place-items-center rounded-btn hover:bg-surface-2"><X size={18} /></button></div>
      <div className="flex-1 overflow-y-auto"><NavLinks pathname={pathname} role={user.role} newReports={newReports} onNavigate={() => setOpen(false)} /></div>
      <Account user={user} onSignOut={signOut} />
    </div>

    <main className={`${width} w-full mx-auto px-4 sm:px-8 py-6 sm:py-10 page-transition min-w-0`}>{children}</main>
  </div>
}

// One consistent page heading: a title, one short line, and actions on the right.
export function PageHeader({ title, description, children }) {
  // The greeting on Overview is personal; the tab just says Overview.
  usePageTitle(/^Good (morning|afternoon|evening)/.test(title) ? 'Overview' : title)
  return <div className="flex flex-wrap items-end justify-between gap-3 mb-6 sm:mb-8">
    <div className="min-w-0"><h1 className="text-2xl sm:text-[28px] font-semibold tracking-tight">{title}</h1>
      {description && <p className="text-sm text-muted mt-1.5 max-w-2xl">{description}</p>}</div>
    {children && <div className="flex flex-wrap gap-2">{children}</div>}
  </div>
}

export const buttonClass = 'press inline-flex items-center gap-2 h-9 px-3.5 rounded-btn border border-border bg-surface text-sm font-medium hover:bg-surface-2 disabled:opacity-50'
export const primaryButtonClass = 'press inline-flex items-center gap-2 h-9 px-3.5 rounded-btn bg-brand text-white text-sm font-medium hover:bg-brand-light disabled:opacity-50'
