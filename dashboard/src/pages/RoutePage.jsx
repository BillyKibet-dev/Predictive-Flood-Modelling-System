import L from 'leaflet'
import { AlertTriangle, Car, Footprints, LocateFixed, Megaphone, Search, Waves } from 'lucide-react'
import { useEffect, useState } from 'react'
import { CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from 'react-leaflet'
import TopNav from '../components/TopNav'
import { REPORT_ICON_SVG } from '../components/CommunityReportLayer'
import { riskColor } from '../constants/colors'
import { useLanguage } from '../context/LanguageContext'
import { ADVISORY_COLOR } from '../services/advisories'
import { timeAgo } from '../services/communityReports'
import { checkRoute, findingsCount, searchPlaces } from '../services/routes'

const NAIROBI = [-1.2864, 36.8172]
const reportIcon = L.divIcon({ className: 'route-report-icon', html: REPORT_ICON_SVG, iconSize: [22, 20], iconAnchor: [11, 18] })
const input = 'w-full h-10 border border-border rounded-btn bg-surface text-ink px-3 text-sm'

function FitRoute({ geometry }) {
  const map = useMap()
  useEffect(() => { if (geometry?.length) map.fitBounds(geometry, { padding: [30, 30], animate: false, maxZoom: 16 }) }, [map, geometry])
  return null
}

// One end of the route: type and search (on submit only), or use the device location.
function PlaceField({ id, label, placeholder, value, onChange, allowLocation }) {
  const { t } = useLanguage()
  const [text, setText] = useState(''), [results, setResults] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState('')
  async function search(event) {
    event?.preventDefault()
    if (text.trim().length < 2) return
    setBusy(true); setError(''); setResults(null)
    try { setResults(await searchPlaces(text)) } catch (failure) { setError(failure.message) } finally { setBusy(false) }
  }
  function locate() {
    navigator.geolocation?.getCurrentPosition(p => { onChange({ label: t('route.myLocation'), latitude: p.coords.latitude, longitude: p.coords.longitude }); setResults(null) },
      () => setError(t('citizen.locationFailed')), { enableHighAccuracy: true, timeout: 10000 })
  }
  return <div className="space-y-1.5">
    <label htmlFor={id} className="text-sm font-medium text-ink">{label}</label>
    {value ? <div className="flex items-center gap-2 h-10 px-3 rounded-btn bg-surface-2 text-sm">
      <span className="flex-1 truncate" data-testid={`${id}-chosen`}>{value.label}</span>
      <button type="button" className="text-xs text-accent font-medium" onClick={() => { onChange(null); setText('') }}>✕</button>
    </div> : <div className="flex gap-2">
      <input id={id} className={input} value={text} placeholder={placeholder} onChange={e => setText(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') search(e) }} />
      <button type="button" onClick={search} disabled={busy} aria-label={`${t('route.search')}: ${label}`} className="press w-10 h-10 shrink-0 grid place-items-center rounded-btn border border-border bg-surface hover:bg-surface-2 disabled:opacity-50"><Search size={16} /></button>
      {allowLocation && <button type="button" onClick={locate} aria-label={t('route.myLocation')} title={t('route.myLocation')} className="press w-10 h-10 shrink-0 grid place-items-center rounded-btn border border-border bg-surface hover:bg-surface-2"><LocateFixed size={16} /></button>}
    </div>}
    {error && <p role="alert" className="text-xs text-risk-extreme">{error}</p>}
    {results && (results.length ? <ul className="panel divide-y divide-border text-sm overflow-hidden" aria-label={t('route.choose')}>
      {results.map(p => <li key={`${p.latitude},${p.longitude}`}><button type="button" className="w-full text-left px-3 py-2 hover:bg-surface-2" onClick={() => { onChange(p); setResults(null) }}>{p.label}</button></li>)}
    </ul> : <p className="text-xs text-muted">{t('route.noPlaces')}</p>)}
  </div>
}

function Finding({ icon, color, children }) {
  return <li className="flex gap-3 py-2.5 text-sm"><span className="w-6 h-6 shrink-0 grid place-items-center rounded-full" style={{ background: `color-mix(in srgb, ${color} 14%, transparent)`, color }}>{icon}</span><span className="min-w-0">{children}</span></li>
}

export default function RoutePage() {
  const { lang, t } = useLanguage()
  const [start, setStart] = useState(null), [end, setEnd] = useState(null)
  const [profile, setProfile] = useState('driving-car'), [avoid, setAvoid] = useState(true)
  const [busy, setBusy] = useState(false), [route, setRoute] = useState(null), [error, setError] = useState('')
  async function run() {
    setBusy(true); setError(''); setRoute(null)
    try { setRoute(await checkRoute({ start, end, profile, avoid })) } catch (failure) { setError(failure.message || t('route.error')) } finally { setBusy(false) }
  }
  const places = route?.places.filter(p => ['High', 'Extreme'].includes(p.category) || p.susceptibility === 'Higher') ?? []
  const crossings = route?.crossings ?? []
  const named = [...new Set(crossings.map(c => c.name).filter(Boolean))]
  return <div className="min-h-screen flex flex-col bg-bg">
    <TopNav active="route" />
    <div className="flex-1 grid lg:grid-cols-[400px_1fr] min-h-0">
      <section className="p-4 sm:p-6 space-y-5 lg:overflow-y-auto lg:max-h-[calc(100vh-56px)]" aria-label={t('route.title')}>
        <div><h1 className="text-2xl font-semibold tracking-tight text-ink">{t('route.title')}</h1><p className="text-sm text-muted mt-1">{t('route.intro')}</p></div>
        <PlaceField id="route-from" label={t('route.from')} placeholder={t('route.placeholderFrom')} value={start} onChange={setStart} allowLocation />
        <PlaceField id="route-to" label={t('route.to')} placeholder={t('route.placeholderTo')} value={end} onChange={setEnd} />
        <div className="space-y-1.5"><p className="text-sm font-medium text-ink">{t('route.mode')}</p>
          <div role="group" aria-label={t('route.mode')} className="grid grid-cols-2 gap-2">
            {[['driving-car', t('route.driving'), Car], ['foot-walking', t('route.walking'), Footprints]].map(([value, label, Icon]) =>
              <button key={value} type="button" aria-pressed={profile === value} onClick={() => setProfile(value)}
                className={`press h-10 rounded-btn border text-sm font-medium inline-flex items-center justify-center gap-2 ${profile === value ? 'bg-brand text-white border-brand' : 'border-border text-ink hover:bg-surface-2'}`}><Icon size={16} />{label}</button>)}
          </div></div>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-0.5 w-4 h-4" checked={avoid} onChange={e => setAvoid(e.target.checked)} />{t('route.avoid')}</label>
        <button type="button" onClick={run} disabled={!start || !end || busy} className="press w-full h-11 rounded-card bg-brand text-white font-semibold disabled:opacity-50">{busy ? t('route.checking') : t('route.check')}</button>
        {error && <p role="alert" className="text-sm text-risk-extreme">{error}</p>}

        {route && <div className="space-y-3" aria-live="polite" aria-label="Route findings">
          <p className="text-lg font-semibold tabular">{t('route.summary', { km: (route.distance_m / 1000).toFixed(1), min: Math.max(1, Math.round(route.duration_s / 60)) })}</p>
          {route.avoided.requested && route.avoided.applied && <p className="text-sm" style={{ color: '#7c3aed' }}>{route.avoided.count === 1 ? t('route.avoidedOne') : t('route.avoided', { count: route.avoided.count })}</p>}
          {findingsCount(route) === 0 ? <p className="panel p-4 text-sm">{t('route.nothing')}</p> : <div className="panel px-4 py-2">
            <p className="eyebrow pt-2">{t('route.found')}</p>
            <ul className="divide-y divide-border">
              {route.reports.map(r => <Finding key={`r${r.id}`} color="#7c3aed" icon={<AlertTriangle size={13} />}>{t('route.report', { condition: t(`condition.${r.observed_condition}`), severity: t(`severity.${r.perceived_severity}`), ago: timeAgo(r.reported_at, Date.now(), lang), m: r.distance_m })}</Finding>)}
              {route.advisories.map(a => <Finding key={`a${a.id}`} color={ADVISORY_COLOR[a.level]} icon={<Megaphone size={13} />}>
                {a.pinned ? t('route.advisoryPinned', { level: t(`advisory.${a.level}`), place: a.place_label || a.area_name, message: a.message })
                  : t('route.advisoryArea', { level: t(`advisory.${a.level}`), area: a.area_name, message: a.message })}</Finding>)}
              {crossings.length > 0 && <Finding color="#0369a1" icon={<Waves size={13} />}>{crossings.length === 1 ? t('route.crossing', { river: crossings[0].name || '—' })
                : t('route.crossings', { count: crossings.length, names: named.join(', ') || '—' })}</Finding>}
              {places.map(p => <Finding key={p.area_id} color={p.category ? riskColor(p.category) : '#64748b'} icon={<span className="w-2 h-2 rounded-full" style={{ background: 'currentColor' }} />}>
                {t('route.place', { name: p.name, category: p.category ? t(`category.${p.category}`) : t('category.none'), local: p.susceptibility ? t(`local.short.${p.susceptibility}`) : '—' })}</Finding>)}
            </ul></div>}
          <p className="text-sm font-semibold">{t('route.never')}</p>
        </div>}
        <p className="text-xs text-muted">{t('route.privacy')} {t('route.attribution')}</p>
      </section>

      <div className="h-[55vh] lg:h-auto min-h-[320px] lg:sticky lg:top-14">
        <MapContainer center={NAIROBI} zoom={12} className="h-full w-full" scrollWheelZoom>
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
          {route && <>
            <FitRoute geometry={route.geometry} />
            <Polyline positions={route.geometry} pathOptions={{ color: '#ffffff', weight: 9, opacity: 0.9 }} />
            <Polyline positions={route.geometry} pathOptions={{ color: '#2563eb', weight: 5 }} className="checked-route" />
            {route.reports.map(r => <Marker key={`r${r.id}`} position={[r.latitude, r.longitude]} icon={reportIcon}><Popup>{t(`condition.${r.observed_condition}`)} · {timeAgo(r.reported_at, Date.now(), lang)}</Popup></Marker>)}
            {route.advisories.filter(a => a.pinned).map(a => <CircleMarker key={`a${a.id}`} center={[a.latitude, a.longitude]} radius={8} pathOptions={{ color: '#fff', weight: 2, fillColor: ADVISORY_COLOR[a.level], fillOpacity: 1 }}><Popup>{a.message}</Popup></CircleMarker>)}
            {crossings.map(c => <CircleMarker key={`${c.latitude},${c.longitude}`} center={[c.latitude, c.longitude]} radius={5} pathOptions={{ color: '#fff', weight: 2, fillColor: '#0369a1', fillOpacity: 1 }}><Popup>{c.name || '—'}</Popup></CircleMarker>)}
            {places.map(p => <CircleMarker key={p.area_id} center={[p.latitude, p.longitude]} radius={7} pathOptions={{ color: p.susceptibility === 'Higher' ? '#111827' : '#fff', weight: p.susceptibility === 'Higher' ? 3 : 2, fillColor: p.category ? riskColor(p.category) : '#94a3b8', fillOpacity: 0.95 }}><Popup>{p.name}</Popup></CircleMarker>)}
          </>}
          {start && <CircleMarker center={[start.latitude, start.longitude]} radius={7} pathOptions={{ color: '#fff', weight: 3, fillColor: '#16a34a', fillOpacity: 1 }} />}
          {end && <CircleMarker center={[end.latitude, end.longitude]} radius={7} pathOptions={{ color: '#fff', weight: 3, fillColor: '#0b1324', fillOpacity: 1 }} />}
        </MapContainer>
      </div>
    </div>
  </div>
}
