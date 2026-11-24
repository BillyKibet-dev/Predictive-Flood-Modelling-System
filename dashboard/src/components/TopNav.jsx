import { Droplets, LogOut, MessageSquarePlus, Moon, Route as RouteIcon, Sun } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'
import { useTheme } from '../context/ThemeContext'
import { LANGUAGES } from '../i18n/strings'

const STAFF_LINKS = [
  { to: '/officer', label: 'Overview' }, { to: '/officer/reports', label: 'Reports' }, { to: '/advisories', label: 'Advisories' },
  { to: '/weather-outlook', label: 'Weather' }, { to: '/history', label: 'Rainfall history' }, { to: '/downloads', label: 'Downloads' },
]

// The bar on public pages (map, report form, route checker). Signed-in staff use the
// sidebar in StaffLayout; here they get a link back to it and a compact menu.
export default function TopNav({ active }) {
  const { user, logout } = useAuth()
  const { dark, toggleTheme } = useTheme()
  const { lang, setLang, t } = useLanguage()
  const navigate = useNavigate()
  // Words on wide screens; an icon button with the same accessible name on phones.
  const link = (to, key, name, Icon) => <Link to={to} aria-current={active === name ? 'page' : undefined} aria-label={t(key)} title={t(key)}
    className={`text-sm font-medium inline-flex items-center gap-2 rounded-btn max-md:w-9 max-md:h-9 max-md:justify-center ${active === name ? 'text-ink max-md:bg-surface-2' : 'text-muted hover:text-ink max-md:hover:bg-surface-2'}`}>
    <Icon size={17} className="md:hidden" aria-hidden="true" /><span className="hidden md:inline">{t(key)}</span></Link>
  return (
    <nav className="min-h-14 bg-surface border-b border-border flex flex-wrap gap-y-2 items-center gap-x-1 md:gap-x-5 px-3 sm:px-6 sticky top-0 z-[1100]">
      <Link to="/" className="flex items-center gap-2 font-semibold text-ink tracking-tight mr-1 md:mr-0" aria-label="NairobiFloodWatch home">
        <span className="w-7 h-7 rounded-btn bg-brand text-white grid place-items-center"><Droplets size={16} /></span>
        <span className="hidden lg:inline">NairobiFloodWatch</span><span className="hidden md:inline lg:hidden">FloodWatch</span>
      </Link>
      {link('/citizen', 'nav.report', 'citizen', MessageSquarePlus)}
      {link('/route', 'nav.route', 'route', RouteIcon)}

      <div className="flex items-center gap-1.5 sm:gap-2 ml-auto">
        <div role="group" aria-label={t('nav.language')} className="flex p-0.5 rounded-btn bg-surface-2 text-xs font-semibold">
          {LANGUAGES.map(l => <button key={l.code} type="button" lang={l.code} aria-pressed={lang === l.code} title={l.label}
            onClick={() => setLang(l.code)} className={`h-7 px-2 rounded-[6px] ${lang === l.code ? 'bg-surface text-ink shadow-card-rest' : 'text-muted hover:text-ink'}`}>{l.short}</button>)}
        </div>
        <button onClick={toggleTheme} aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          className="w-9 h-9 flex items-center justify-center rounded-btn text-muted hover:text-ink hover:bg-surface-2">
          {dark ? <Sun size={18} /> : <Moon size={18} />}
        </button>
        {!user && <Link to="/login" className="press text-sm font-medium border border-border bg-surface text-ink rounded-btn px-3 sm:px-3.5 h-9 flex items-center whitespace-nowrap hover:bg-surface-2">{t('nav.signIn')}</Link>}
        {user && <>
          <select aria-label="Staff navigation" className="md:hidden max-w-28 text-xs bg-surface text-ink border border-border rounded-btn h-9 px-1" value="" onChange={event => navigate(event.target.value)}>
            <option value="" disabled>Menu</option>{STAFF_LINKS.map(l => <option key={l.to} value={l.to}>{l.label}</option>)}
            {user.role === 'admin' && <option value="/admin">Admin</option>}
          </select>
          <Link to={user.role === 'admin' ? '/admin' : '/officer'} className="hidden md:inline text-sm font-medium text-accent">Back to workspace →</Link>
          <button onClick={() => { logout(); navigate('/') }} aria-label="Sign out" title="Sign out" className="w-9 h-9 grid place-items-center rounded-btn text-muted hover:text-ink hover:bg-surface-2"><LogOut size={16} /></button>
        </>}
      </div>
    </nav>
  )
}
