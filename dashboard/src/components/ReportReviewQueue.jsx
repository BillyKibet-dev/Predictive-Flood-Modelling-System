import { Camera, ChevronLeft, ChevronRight, ExternalLink, MapPin, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import useStaffList from '../hooks/useStaffList'
import { useAuth } from '../context/AuthContext'
import { timeAgo } from '../services/communityReports'
import { formatPredictionTime } from '../services/predictions'
import { cleanReference } from '../services/reports'
import { PageHeader, buttonClass, primaryButtonClass } from './StaffLayout'

const statuses = ['New', 'ActionNeeded', 'Reviewed', 'Resolved']
const PAGE = 20
const label = (status) => (status === 'ActionNeeded' ? 'Action needed' : status)
const tint = color => ({ background: `color-mix(in srgb, ${color} 12%, transparent)`, color })
const STATUS_STYLE = {
  New: tint('var(--accent)'), ActionNeeded: tint('var(--risk-high)'),
  Reviewed: { background: 'var(--surface-2)', color: 'var(--text-muted)' }, Resolved: tint('var(--risk-low)'),
}
const SEVERITY = { Mild: 'var(--risk-low)', Serious: 'var(--risk-high)', Dangerous: 'var(--risk-extreme)' }
const field = 'border border-border rounded-btn bg-surface text-sm px-2.5'

export default function ReportReviewQueue() {
  const { authorizedRequest } = useAuth()
  const [filters, setFilters] = useSearchParams()
  const status = statuses.includes(filters.get('review_status')) ? filters.get('review_status') : ''
  const reference = filters.get('reference') || ''
  const [offset, setOffset] = useState(0), [typed, setTyped] = useState(reference)
  useEffect(() => setOffset(0), [status, reference])
  const query = new URLSearchParams({ limit: String(PAGE), offset: String(offset), ...(status ? { review_status: status } : {}), ...(reference ? { reference } : {}) })
  function findReference(event) {
    event.preventDefault()
    const clean = cleanReference(typed)
    setFilters(clean ? { reference: clean } : {})
  }
  const list = useStaffList('/citizen-reports?' + query)
  const total = list.data?.total ?? 0
  return (
    <section>
      <PageHeader title="Reports" description="Flooding seen by residents. Check each one and record a decision. Reviewing never sends a public warning.">
        <button type="button" className={buttonClass} onClick={list.refresh} disabled={list.loading}><RefreshCw size={15} />Refresh inbox</button>
      </PageHeader>

      <div role="group" aria-label="Report review status filter" className="no-scrollbar flex gap-1 p-1 rounded-card bg-surface-2 w-full sm:w-fit overflow-x-auto [&>button]:shrink-0 [&>button]:whitespace-nowrap">
        {['', ...statuses].map(value => <button key={value || 'all'} type="button" aria-pressed={status === value}
          onClick={() => { setFilters(value ? { review_status: value } : {}); setOffset(0) }}
          className={`h-8 px-3 rounded-btn text-sm whitespace-nowrap ${status === value ? 'bg-surface text-ink font-semibold shadow-card-rest' : 'text-muted hover:text-ink'}`}>
          {value ? label(value) : 'All'}
        </button>)}
      </div>
      {/* A resident quoting their reference (e.g. on the phone) can be found directly. */}
      <form onSubmit={findReference} className="mt-3 flex flex-wrap items-center gap-2" role="search" aria-label="Find a report by the resident's reference">
        <input value={typed} onChange={e => setTyped(e.target.value)} placeholder="Resident's reference, e.g. FW-K7Q2M9" autoComplete="off" spellCheck={false}
          className={`${field} h-9 w-64 max-w-full font-mono uppercase placeholder:normal-case placeholder:font-sans`} />
        <button type="submit" className={buttonClass}>Find</button>
        {reference && <button type="button" className="text-sm text-accent" onClick={() => { setTyped(''); setFilters({}) }}>Clear · showing {reference}</button>}
        {typed.trim() && !cleanReference(typed) && <span className="text-xs text-muted">References look like FW-K7Q2M9.</span>}
      </form>

      <div className="mt-5 space-y-3">
        {list.loading && !list.data && <p role="status" className="text-sm text-muted">Loading reports…</p>}
        {list.error && <p role="alert" className="text-sm text-risk-extreme">{list.error}</p>}
        {list.data && !list.data.items.length && <div className="panel p-10 text-center">
          <p className="font-medium">Nothing here</p>
          <p className="text-sm text-muted mt-1">{status ? `No reports are marked ${label(status).toLowerCase()}.` : 'No reports have been received yet.'}</p>
        </div>}
        {list.data?.items.map(report => <ReportItem key={report.id} report={report} request={authorizedRequest} refresh={list.refresh} />)}
      </div>

      {total > PAGE && <div className="flex items-center justify-between mt-4 text-sm text-muted">
        <span className="tabular">{offset + 1}–{Math.min(offset + PAGE, total)} of {total}</span>
        <div className="flex gap-2">
          <button className={buttonClass} aria-label="Previous page" disabled={!offset || list.loading} onClick={() => setOffset(v => Math.max(0, v - PAGE))}><ChevronLeft size={16} /></button>
          <button className={buttonClass} aria-label="Next page" disabled={offset + PAGE >= total || list.loading} onClick={() => setOffset(v => v + PAGE)}><ChevronRight size={16} /></button>
        </div>
      </div>}
      {list.data && total > 0 && total <= PAGE && <p className="text-xs text-muted mt-3">{total} report{total === 1 ? '' : 's'} · checked every 30 seconds</p>}
    </section>
  )
}

// Staff-only photo: fetched with the session token, shown from memory, never cached.
function ReportPhoto({ id }) {
  const { authorizedDownload } = useAuth()
  const [url, setUrl] = useState(''), [state, setState] = useState('idle')
  useEffect(() => () => { if (url) URL.revokeObjectURL(url) }, [url])
  async function load() {
    setState('loading')
    try { const { blob } = await authorizedDownload(`/citizen-reports/${id}/photo`); setUrl(URL.createObjectURL(blob)); setState('shown') }
    catch { setState('error') }
  }
  if (state === 'shown') return <a href={url} target="_blank" rel="noopener noreferrer" className="block w-fit">
    <img src={url} alt={`Photo sent with report ${id}`} className="max-h-64 rounded-btn border border-border" /></a>
  return <button type="button" onClick={load} disabled={state === 'loading'} className="inline-flex items-center gap-1.5 text-sm font-medium text-accent disabled:opacity-50">
    <Camera size={15} aria-hidden="true" />{state === 'loading' ? 'Loading photo…' : state === 'error' ? 'Photo unavailable · retry' : 'Show photo'}</button>
}

function ReportItem({ report, request, refresh }) {
  const [status, setStatus] = useState(report.review_status),
    [note, setNote] = useState(report.review_note ?? ''),
    [publicMap, setPublicMap] = useState(Boolean(report.public_visible)),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState('')
  const [version, setVersion] = useState(report.review_version)
  const changed = version !== report.review_version
  async function save(event) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    try {
      const saved = await request(`/citizen-reports/${report.id}/review`, {
        method: 'PATCH',
        body: JSON.stringify({ status, note: note.trim() || null, expected_version: version, public: status !== 'Resolved' && publicMap }),
      })
      if (saved.id !== report.id || saved.review_status !== status || saved.public_visible !== (status !== 'Resolved' && publicMap))
        throw new Error('No matching save confirmation. Refresh before retrying.')
      setVersion(saved.review_version)
      setMessage('Decision saved.')
      refresh()
    } catch (failure) {
      setMessage(failure.name === 'AbortError' ? 'Save not confirmed. Refresh before retrying.' : failure.message)
    } finally {
      setBusy(false)
    }
  }
  const hasCoordinates = Number.isFinite(report.latitude) && Number.isFinite(report.longitude)
  const publicUntil = Date.parse(report.timestamp) + 24 * 3600000
  const expired = Date.now() >= publicUntil
  const onMap = report.public_visible && !expired
  return (
    <article className="panel overflow-hidden" aria-label={`Citizen report ${report.id}`}>
      <div className="p-4 sm:p-5 space-y-3">
        <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
          <div className="min-w-0 flex-1">
            <h2 className="font-semibold leading-snug">
              {report.observed_condition}
              <span className="ml-2 inline-flex items-center gap-1 text-xs font-medium text-muted align-middle">
                <span className="w-2 h-2 rounded-full" style={{ background: SEVERITY[report.perceived_severity] ?? 'var(--text-muted)' }} aria-hidden="true" />
                {report.perceived_severity}
              </span>
            </h2>
            <p className="text-sm text-muted mt-0.5">{report.zone_name} · <span title={formatPredictionTime(report.timestamp)}>{timeAgo(report.timestamp)}</span> · #{report.id}</p>
          </div>
          <div className="flex gap-1.5">
            {onMap && <span className="text-xs font-semibold px-2 py-1 rounded-full" style={tint('#7c3aed')}>On public map</span>}
            <span className="text-xs font-semibold px-2 py-1 rounded-full" style={STATUS_STYLE[report.review_status]}>{label(report.review_status)}</span>
          </div>
        </div>
        <p className="text-sm font-medium">{report.location_description || <span className="text-muted font-normal">No landmark given (older report)</span>}</p>
        {report.photo_attached && <ReportPhoto id={report.id} />}
        {report.description && <blockquote className="text-sm border-l-2 border-border pl-3 text-ink/90">{report.description}</blockquote>}
        {hasCoordinates && <p className="text-xs text-muted flex flex-wrap items-center gap-x-2 gap-y-1">
          <MapPin size={13} aria-hidden="true" />
          <span className="tabular">{report.latitude.toFixed(5)}, {report.longitude.toFixed(5)}</span>
          {report.location_accuracy_m != null && <span>· ±{Math.round(report.location_accuracy_m)} m</span>}
          <a className="text-accent font-medium inline-flex items-center gap-1" target="_blank" rel="noopener noreferrer"
            href={`https://www.openstreetmap.org/?mlat=${report.latitude}&mlon=${report.longitude}#map=17/${report.latitude}/${report.longitude}`}>
            Open map<ExternalLink size={11} aria-hidden="true" /></a>
        </p>}
      </div>

      <form onSubmit={save} className="border-t border-border p-4 sm:p-5 space-y-3" style={{ background: 'color-mix(in srgb, var(--surface-2) 60%, transparent)' }}>
        <div className="grid sm:grid-cols-[180px_1fr] gap-3">
          <label className="text-xs text-muted flex flex-col gap-1">Decision
            <select aria-label={`Decision for report ${report.id}`} className={field + ' h-9 text-ink'} value={status} onChange={e => setStatus(e.target.value)} disabled={busy}>
              {statuses.map(value => <option key={value} value={value}>{label(value)}</option>)}
            </select>
          </label>
          <label className="text-xs text-muted flex flex-col gap-1">Note for staff (never public)
            <textarea aria-label={`Review note for report ${report.id}`} maxLength={1000} rows={1}
              className={field + ' py-2 text-ink min-h-9 resize-y'} value={note} onChange={e => setNote(e.target.value)} disabled={busy} />
          </label>
        </div>
        <label className="text-sm flex items-start gap-2.5">
          <input type="checkbox" className="mt-0.5 w-4 h-4 accent-[#7c3aed]" aria-label={`Show report ${report.id} on the public map`}
            checked={status !== 'Resolved' && publicMap} disabled={busy || !hasCoordinates || status === 'Resolved'}
            onChange={e => setPublicMap(e.target.checked)} />
          <span>Show on the public map
            <span className="block text-xs text-muted mt-0.5">
              {!hasCoordinates ? 'Needs a map pin.'
                : status === 'Resolved' ? 'Resolved reports are not shown.'
                  : expired ? 'More than 24 hours old, so it would not appear.'
                    : `Until ${formatPredictionTime(new Date(publicUntil).toISOString())}. Shows condition, severity and landmark at about 100 m; never the description, note or contact details.`}
            </span></span>
        </label>
        {changed && <p role="status" className="text-sm">Someone else saved a newer review. Your draft is kept.{' '}
          <button type="button" className="text-accent font-medium" onClick={() => {
            setVersion(report.review_version); setStatus(report.review_status); setNote(report.review_note ?? '')
            setPublicMap(Boolean(report.public_visible)); setMessage('')
          }}>Load latest review</button></p>}
        <div className="flex flex-wrap items-center gap-3">
          <button disabled={busy || changed} className={primaryButtonClass}>{busy ? 'Saving…' : 'Save decision'}</button>
          {message && <p role="status" className="text-sm">{message}</p>}
          {report.reviewed_at && !message && <p className="text-xs text-muted">Last reviewed by {report.reviewed_by_name || 'staff'}, {formatPredictionTime(report.reviewed_at)}</p>}
        </div>
      </form>
    </article>
  )
}
