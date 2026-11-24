import L from 'leaflet'
import { AlertTriangle, ArrowUpDown, Car, Footprints, LocateFixed, MapPin, Megaphone, Search, Waves, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import { Link, useNavigate } from 'react-router-dom'
import TopNav from '../components/TopNav'
import { REPORT_ICON_SVG } from '../components/CommunityReportLayer'
import { riskColor } from '../constants/colors'
import { useLanguage } from '../context/LanguageContext'
import { ADVISORY_COLOR } from '../services/advisories'
import { timeAgo } from '../services/communityReports'
import { checkRoute, findingsCount, namePoint, pinnedPlace, searchPlaces, tapTarget } from '../services/routes'

const NAIROBI = [-1.2864, 36.8172]
const reportIcon = L.divIcon({ className: 'route-report-icon', html: REPORT_ICON_SVG, iconSize: [22, 20], iconAnchor: [11, 18] })
// Lettered, draggable end pins: A = start (green), B = destination (dark).
const endIcon = (letter, color) => L.divIcon({ className: 'route-end-pin', iconSize: [30, 38], iconAnchor: [15, 36],
  html: `<svg viewBox="0 0 30 38" width="30" height="38" aria-hidden="true"><path d="M15 37C15 37 28 22.5 28 14A13 13 0 0 0 2 14c0 8.5 13 23 13 23z" fill="${color}" stroke="#fff" stroke-width="2.5"/><text x="15" y="19" text-anchor="middle" font-size="13" font-weight="700" fill="#fff" font-family="system-ui,sans-serif">${letter}</text></svg>` })
const START_ICON = endIcon('A', '#16a34a'), END_ICON = endIcon('B', '#0b1324')
const input = 'w-full h-10 border border-border rounded-btn bg-surface text-ink px-3 text-sm'
const iconButton = 'press w-10 h-10 shrink-0 grid place-items-center rounded-btn border border-border bg-surface hover:bg-surface-2 disabled:opacity-50'

function FitRoute({ geometry }) {
  const map = useMap()
  useEffect(() => { if (geometry?.length) map.fitBounds(geometry, { padding: [30, 30], animate: false, maxZoom: 16 }) }, [map, geometry])
  return null
}

function TapToPick({ onTap }) {
  useMapEvents({ click: event => onTap(event.latlng) })
  return null
}

// One end of the route: type and search (on submit only), use the device location, or tap the map.
function PlaceField({ id, label, placeholder, value, onChange, allowLocation, picking, onPick }) {
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
    {value ? <div className="flex items-center gap-2 h-10 pl-3 pr-1 rounded-btn bg-surface-2 text-sm">
      <span className="flex-1 truncate" data-testid={`${id}-chosen`}>{value.label}</span>
      <button type="button" aria-label={`${t('route.clear')}: ${label}`} className="w-8 h-8 grid place-items-center rounded-btn text-muted hover:text-ink" onClick={() => { onChange(null); setText('') }}><X size={15} /></button>
    </div> : <div className="flex gap-2">
      <input id={id} className={input} value={text} placeholder={placeholder} onChange={e => setText(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') search(e) }} />
      <button type="button" onClick={search} disabled={busy} aria-label={`${t('route.search')}: ${label}`} className={iconButton}><Search size={16} /></button>
      <button type="button" onClick={onPick} aria-pressed={picking} aria-label={`${t('route.pickOnMap')}: ${label}`} title={t('route.pickOnMap')}
        className={`${iconButton} ${picking ? 'border-accent text-accent' : ''}`} style={picking ? { background: 'color-mix(in srgb, var(--accent) 10%, var(--surface))' } : undefined}><MapPin size={16} /></button>
      {allowLocation && <button type="button" onClick={locate} aria-label={t('route.myLocation')} title={t('route.myLocation')} className={iconButton}><LocateFixed size={16} /></button>}
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
  const navigate = useNavigate()
  const [start, setStart] = useState(null), [end, setEnd] = useState(null), [picking, setPicking] = useState(null)
  const [profile, setProfile] = useState('driving-car'), [avoid, setAvoid] = useState(true)
  const [busy, setBusy] = useState(false), [route, setRoute] = useState(null), [error, setError] = useState('')
  const naming = useRef(0)
  // A changed start or destination makes the old route stale.
  // (Coordinates only: a street name arriving later does not clear the result.)
  useEffect(() => { setRoute(null); setError('') }, [start?.latitude, start?.longitude, end?.latitude, end?.longitude, profile])
  // Escape closes the checker (or cancels choosing on the map first).
  useEffect(() => {
    const onKey = event => { if (event.key !== 'Escape') return; if (picking) setPicking(null); else navigate('/') }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [picking, navigate])

  // A tapped point shows "Point on the map" at once, then its street name when the server finds one.
  function placeAt(which, latlng) {
    const place = pinnedPlace(latlng, t('route.pinned'))
    const set = which === 'start' ? setStart : setEnd
    set(place); setPicking(null)
    const request = ++naming.current
    namePoint(place.latitude, place.longitude).then(label => {
      if (label && request === naming.current) set(current => current?.latitude === place.latitude && current?.longitude === place.longitude ? { ...current, label } : current)
    }).catch(() => { /* the coordinates still route; the generic label stays */ })
  }
  const target = tapTarget(picking, start, end)
  function onTap(latlng) { if (target) placeAt(target, latlng) }
  function swap() { setStart(end); setEnd(start) }

  async function run() {
    setBusy(true); setError(''); setRoute(null)
    try { setRoute(await checkRoute({ start, end, profile, avoid })) } catch (failure) { setError(failure.message || t('route.error')) } finally { setBusy(false) }
  }
  const places = route?.places.filter(p => ['High', 'Extreme'].includes(p.category) || p.susceptibility === 'Higher') ?? []
  const crossings = route?.crossings ?? []
  const named = [...new Set(crossings.map(c => c.name).filter(Boolean))]
  return <div className="h-screen h-[100dvh] flex flex-col bg-bg">
    <TopNav active="route" />
    <div className="flex-1 min-h-0 flex flex-col lg:grid lg:grid-cols-[400px_1fr]">
      {/* Phones: the map comes first so a tap target is always in view. */}
      <div className="relative h-[40dvh] min-h-[240px] shrink-0 lg:h-auto lg:order-2 border-b lg:border-b-0 lg:border-l border-border">
        <MapContainer center={NAIROBI} zoom={12} className={`h-full w-full ${target ? 'cursor-crosshair' : ''}`} scrollWheelZoom>
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
          <TapToPick onTap={onTap} />
          {route && <>
            <FitRoute geometry={route.geometry} />
            <Polyline positions={route.geometry} pathOptions={{ color: '#ffffff', weight: 9, opacity: 0.9 }} />
            <Polyline positions={route.geometry} pathOptions={{ color: '#2563eb', weight: 5 }} className="checked-route" />
            {route.reports.map(r => <Marker key={`r${r.id}`} position={[r.latitude, r.longitude]} icon={reportIcon}><Popup>{t(`condition.${r.observed_condition}`)} · {timeAgo(r.reported_at, Date.now(), lang)}</Popup></Marker>)}
            {route.advisories.filter(a => a.pinned).map(a => <CircleMarker key={`a${a.id}`} center={[a.latitude, a.longitude]} radius={8} pathOptions={{ color: '#fff', weight: 2, fillColor: ADVISORY_COLOR[a.level], fillOpacity: 1 }}><Popup>{a.message}</Popup></CircleMarker>)}
            {crossings.map(c => <CircleMarker key={`${c.latitude},${c.longitude}`} center={[c.latitude, c.longitude]} radius={5} pathOptions={{ color: '#fff', weight: 2, fillColor: '#0369a1', fillOpacity: 1 }}><Popup>{c.name || '—'}</Popup></CircleMarker>)}
            {places.map(p => <CircleMarker key={p.area_id} center={[p.latitude, p.longitude]} radius={7} pathOptions={{ color: p.susceptibility === 'Higher' ? '#111827' : '#fff', weight: p.susceptibility === 'Higher' ? 3 : 2, fillColor: p.category ? riskColor(p.category) : '#94a3b8', fillOpacity: 0.95 }}><Popup>{p.name}</Popup></CircleMarker>)}
          </>}
          {start && <Marker position={[start.latitude, start.longitude]} icon={START_ICON} draggable keyboard={false} title={`${t('route.from')}: ${start.label}`}
            eventHandlers={{ dragend: e => placeAt('start', e.target.getLatLng()) }} />}
          {end && <Marker position={[end.latitude, end.longitude]} icon={END_ICON} draggable keyboard={false} title={`${t('route.to')}: ${end.label}`}
            eventHandlers={{ dragend: e => placeAt('end', e.target.getLatLng()) }} />}
        </MapContainer>
        {target && <div role="status" className="absolute z-[1000] top-3 left-1/2 -translate-x-1/2 max-w-[calc(100%-6rem)] flex items-center gap-2 pl-3 pr-1 h-9 rounded-full bg-ink text-bg text-xs sm:text-sm font-medium shadow-card-hover">
          <MapPin size={14} className="shrink-0" aria-hidden="true" /><span className="truncate">{target === 'start' ? t('route.tapStart') : t('route.tapEnd')}</span>
          {picking && <button type="button" onClick={() => setPicking(null)} className="h-7 px-2.5 rounded-full border border-current opacity-90 hover:opacity-100">{t('route.cancel')}</button>}
        </div>}
      </div>

      <section className="flex-1 min-h-0 overflow-y-auto lg:order-1 p-4 sm:p-6 space-y-5" aria-label={t('route.title')}>
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0"><h1 className="text-2xl font-semibold tracking-tight text-ink">{t('route.title')}</h1><p className="text-sm text-muted mt-1">{t('route.intro')}</p></div>
          <Link to="/" aria-label={t('route.close')} title={t('route.close')} className="press w-10 h-10 shrink-0 grid place-items-center rounded-full border border-border bg-surface text-muted hover:text-ink hover:bg-surface-2"><X size={18} /></Link>
        </div>
        <div className="relative space-y-3">
          <PlaceField id="route-from" label={t('route.from')} placeholder={t('route.placeholderFrom')} value={start} onChange={setStart} allowLocation
            picking={picking === 'start'} onPick={() => setPicking(p => p === 'start' ? null : 'start')} />
          <PlaceField id="route-to" label={t('route.to')} placeholder={t('route.placeholderTo')} value={end} onChange={setEnd}
            picking={picking === 'end'} onPick={() => setPicking(p => p === 'end' ? null : 'end')} />
          {start && end && <button type="button" onClick={swap} aria-label={t('route.swap')} title={t('route.swap')} className="absolute right-0 top-0 h-6 px-2 inline-flex items-center gap-1 text-xs text-muted hover:text-ink"><ArrowUpDown size={13} />{t('route.swapShort')}</button>}
          {(start?.pinned || end?.pinned) && <p className="text-xs text-muted">{t('route.dragHint')}</p>}
        </div>
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
    </div>
  </div>
}
