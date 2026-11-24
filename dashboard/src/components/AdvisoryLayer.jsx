import L from 'leaflet'
import { Megaphone } from 'lucide-react'
import { useState } from 'react'
import { Marker, Pane, Popup } from 'react-leaflet'
import { formatNairobi, useLanguage } from '../context/LanguageContext'
import { ADVISORY_COLOR } from '../services/advisories'

// A diamond, unlike round risk pins and triangle reports.
const icon = level => L.divIcon({ className: 'officer-advisory-icon',
  html: `<svg viewBox="0 0 22 22" width="22" height="22" aria-hidden="true"><path d="M11 1 21 11 11 21 1 11z" fill="${ADVISORY_COLOR[level]}" stroke="#fff" stroke-width="2" stroke-linejoin="round"/><path d="M11 6.5v6M11 15v1" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/></svg>`,
  iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -10] })

function Advisory({ a, compact = false }) {
  const { lang, t } = useLanguage()
  const until = formatNairobi(lang, a.expires_at, { weekday: 'short', hour: '2-digit', minute: '2-digit' })
  return <div className={compact ? 'space-y-0.5' : 'space-y-1'}>
    <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: ADVISORY_COLOR[a.level] }}>{t(`advisory.${a.level}`)} · {a.area_name}</p>
    {a.place_label && <p className="text-sm font-semibold">{a.place_label}</p>}
    <p className="text-sm">{a.message}</p>
    <p className="text-xs text-muted">{t('advisory.until', { time: until })}</p>
  </div>
}

export function AdvisoryList({ items }) {
  return <div className="rounded-card border p-3 space-y-3" style={{ borderColor: ADVISORY_COLOR.Warning, background: 'color-mix(in srgb, #b45309 6%, var(--surface))' }}>
    {items.map(a => <Advisory key={a.id} a={a} compact />)}
  </div>
}

// Pinned advisories on the map.
export default function AdvisoryLayer({ advisories }) {
  const pinned = advisories.filter(a => a.latitude != null)
  if (!pinned.length) return null
  return <Pane name="officer-advisories" style={{ zIndex: 470 }}>
    {pinned.map(a => <Marker key={a.id} position={[a.latitude, a.longitude]} icon={icon(a.level)} keyboard title={a.place_label || a.area_name}
      eventHandlers={{ add: e => e.target.getElement()?.classList.add('officer-advisory') }}>
      <Popup maxHeight={240}><div className="p-3 text-ink"><Advisory a={a} /></div></Popup>
    </Marker>)}
  </Pane>
}

// A slim strip across the top of the map while any advisory is in force.
export function AdvisoryBanner({ advisories }) {
  const { t } = useLanguage()
  const [open, setOpen] = useState(false)
  if (!advisories.length) return null
  const first = advisories[0], warning = advisories.some(a => a.level === 'Warning')
  return <div role="status" aria-label={t('advisory.banner')} className="absolute z-[1040] top-3 left-14 right-3 md:right-auto md:max-w-md">
    <div className="bg-surface border rounded-card shadow-card-hover text-ink" style={{ borderColor: ADVISORY_COLOR[warning ? 'Warning' : 'Advice'] }}>
      <button type="button" onClick={() => setOpen(o => !o)} aria-expanded={open} className="w-full flex items-start gap-2 p-3 text-left">
        <Megaphone size={16} className="shrink-0 mt-0.5" style={{ color: ADVISORY_COLOR[warning ? 'Warning' : 'Advice'] }} aria-hidden="true" />
        <span className={`text-sm min-w-0 ${open ? '' : 'max-md:line-clamp-2'}`}><span className="font-semibold">{first.place_label || first.area_name}: </span>{first.message}
          {advisories.length > 1 && <span className="text-muted"> · +{advisories.length - 1}</span>}</span>
      </button>
      {open && advisories.length > 1 && <div className="px-3 pb-3 space-y-3 border-t border-border pt-3 max-h-64 overflow-y-auto">
        {advisories.slice(1).map(a => <Advisory key={a.id} a={a} compact />)}
      </div>}
    </div>
  </div>
}
