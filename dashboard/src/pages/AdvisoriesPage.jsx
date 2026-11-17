import { LocateFixed, Megaphone } from 'lucide-react'
import { useEffect, useState } from 'react'
import StaffLayout, { PageHeader, buttonClass, primaryButtonClass } from '../components/StaffLayout'
import { useAuth } from '../context/AuthContext'
import useStaffList from '../hooks/useStaffList'
import { ADVISORY_COLOR } from '../services/advisories'
import { formatPredictionTime } from '../services/predictions'
import { fetchReportingAreas } from '../services/reports'

const EMPTY = { area_id: '', place_label: '', message: '', level: 'Advice', hours: 12, latitude: '', longitude: '' }
const field = 'mt-1 w-full h-9 border border-border rounded-btn bg-surface text-ink px-2.5 text-sm'
const STATE_STYLE = { Active: 'var(--risk-low)', Expired: 'var(--text-muted)', Withdrawn: 'var(--text-muted)' }

// Officers post short, time-limited messages residents see on the public map.
export default function AdvisoriesPage() {
  const { authorizedRequest } = useAuth()
  const list = useStaffList('/advisories')
  const [areas, setAreas] = useState([]), [form, setForm] = useState(EMPTY)
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [error, setError] = useState('')
  useEffect(() => { fetchReportingAreas().then(setAreas).catch(e => setError(e.message)) }, [])
  const set = (key, value) => setForm(f => ({ ...f, [key]: value }))
  function here() {
    navigator.geolocation?.getCurrentPosition(p => setForm(f => ({ ...f, latitude: p.coords.latitude.toFixed(5), longitude: p.coords.longitude.toFixed(5) })),
      () => setError('Location could not be found; leave the pin empty or type it.'), { enableHighAccuracy: true, timeout: 10000 })
  }
  async function post(event) {
    event.preventDefault()
    setBusy(true); setError(''); setMessage('')
    const pinned = form.latitude !== '' && form.longitude !== ''
    try {
      const saved = await authorizedRequest('/advisories', { method: 'POST', body: JSON.stringify({
        area_id: form.area_id, place_label: form.place_label.trim() || null, message: form.message.trim(), level: form.level,
        hours: Number(form.hours), ...(pinned ? { latitude: Number(form.latitude), longitude: Number(form.longitude) } : {}) }) })
      if (saved.state !== 'Active') throw new Error('Not confirmed. Refresh before retrying.')
      setForm(EMPTY); setMessage('Advisory posted. It is on the public map now.'); list.refresh()
    } catch (failure) { setError(failure.message) } finally { setBusy(false) }
  }
  async function withdraw(id) {
    if (!window.confirm('Withdraw this advisory from the public map now?')) return
    setError('')
    try { await authorizedRequest(`/advisories/${id}/withdraw`, { method: 'POST' }); list.refresh() } catch (failure) { setError(failure.message) }
  }
  const items = list.data?.items ?? [], active = items.filter(a => a.state === 'Active')
  return <StaffLayout width="max-w-5xl">
    <PageHeader title="Advisories" description="Short messages for residents on the public map, e.g. “Avoid the Outering Road underpass.” They end automatically." />
    <div className="grid lg:grid-cols-[1fr_1fr] gap-6 items-start">
      <form onSubmit={post} className="panel p-5 space-y-4" aria-label="New advisory">
        <h2 className="font-semibold flex items-center gap-2"><Megaphone size={17} aria-hidden="true" />New advisory</h2>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-muted">Sub-county<select required aria-label="Advisory sub-county" className={field} value={form.area_id} onChange={e => set('area_id', e.target.value)}>
            <option value="">Choose</option>{areas.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
          <label className="text-xs text-muted">Type<select aria-label="Advisory type" className={field} value={form.level} onChange={e => set('level', e.target.value)}>
            <option value="Advice">Advice</option><option value="Warning">Warning</option></select></label>
        </div>
        <label className="block text-xs text-muted">Place (optional)<input aria-label="Advisory place" maxLength={120} className={field} placeholder="e.g. Outering Road underpass" value={form.place_label} onChange={e => set('place_label', e.target.value)} /></label>
        <label className="block text-xs text-muted">Message<textarea required aria-label="Advisory message" minLength={5} maxLength={280} rows={3} className={field + ' h-auto py-2'} placeholder="What should residents do?" value={form.message} onChange={e => set('message', e.target.value)} />
          <span className="block text-right tabular mt-0.5">{form.message.length}/280</span></label>
        <div className="grid grid-cols-[1fr_1fr_auto] gap-2 items-end">
          <label className="text-xs text-muted">Pin latitude<input aria-label="Advisory latitude" inputMode="decimal" className={field + ' tabular'} value={form.latitude} onChange={e => set('latitude', e.target.value)} /></label>
          <label className="text-xs text-muted">Pin longitude<input aria-label="Advisory longitude" inputMode="decimal" className={field + ' tabular'} value={form.longitude} onChange={e => set('longitude', e.target.value)} /></label>
          <button type="button" onClick={here} className={buttonClass} title="Use my location"><LocateFixed size={15} /><span className="sr-only">Use my location</span></button>
        </div>
        <label className="block text-xs text-muted">Show for<select aria-label="Advisory duration" className={field} value={form.hours} onChange={e => set('hours', e.target.value)}>
          {[3, 6, 12, 24, 48, 72].map(h => <option key={h} value={h}>{h} hours</option>)}</select></label>
        {error && <p role="alert" className="text-sm text-risk-extreme">{error}</p>}
        {message && <p role="status" className="text-sm">{message}</p>}
        <button disabled={busy} className={primaryButtonClass}>{busy ? 'Posting…' : 'Post advisory'}</button>
        <p className="text-xs text-muted">Shown publicly in English as written, without your name. Withdraw it once the situation clears.</p>
      </form>

      <section aria-labelledby="advisory-list" className="space-y-3">
        <h2 id="advisory-list" className="font-semibold">Live now <span className="text-muted font-normal tabular">· {active.length}</span></h2>
        {list.loading && !list.data && <p role="status" className="text-sm text-muted">Loading…</p>}
        {list.data && !items.length && <p className="text-sm text-muted">No advisories in the last 14 days.</p>}
        <ul className="space-y-3">{items.map(a => <li key={a.id} className="panel p-4 space-y-1.5" aria-label={`Advisory ${a.id}`}>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-semibold uppercase tracking-wide" style={{ color: ADVISORY_COLOR[a.level] }}>{a.level}</span>
            <span className="text-muted">{a.area_name}{a.latitude != null ? ' · pinned' : ''}</span>
            <span className="ml-auto font-semibold" style={{ color: STATE_STYLE[a.state] }}>{a.state}</span>
          </div>
          {a.place_label && <p className="font-medium">{a.place_label}</p>}
          <p className="text-sm">{a.message}</p>
          <p className="text-xs text-muted">{a.issued_by} · {formatPredictionTime(a.issued_at)} → {formatPredictionTime(a.expires_at)}</p>
          {a.state === 'Active' && <button type="button" onClick={() => withdraw(a.id)} className={buttonClass + ' text-risk-extreme mt-1'}>Withdraw</button>}
        </li>)}</ul>
      </section>
    </div>
  </StaffLayout>
}
