import { useState } from 'react'
import useStaffList from '../hooks/useStaffList'
import { useAuth } from '../context/AuthContext'
import { formatPredictionTime } from '../services/predictions'

const statuses = ['New', 'Reviewed', 'ActionNeeded', 'Resolved']
const label = (status) => (status === 'ActionNeeded' ? 'Action needed' : status)
export default function ReportReviewQueue() {
  const { authorizedRequest } = useAuth()
  const [status, setStatus] = useState(''),
    [offset, setOffset] = useState(0)
  const query = new URLSearchParams({
    limit: '20',
    offset: String(offset),
    ...(status ? { review_status: status } : {}),
  })
  const list = useStaffList('/citizen-reports?' + query)
  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-ink">Citizen report inbox</h1>
          <p className="text-sm text-muted mt-1">
            Review community observations and record your decision. Reporting is available on the
            citizen page only.
          </p>
        </div>
        <button
          type="button"
          className="border border-border rounded-btn p-2 text-ink"
          onClick={list.refresh}
          disabled={list.loading}
        >
          Refresh inbox
        </button>
      </div>
      <p className="text-sm text-muted">
        Updates are checked every 30 seconds. Reports are unverified observations, separate from
        model predictions. No public warning is sent by reviewing a report.
      </p>
      <label className="text-sm text-ink">
        Review status{' '}
        <select
          aria-label="Report review status filter"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value)
            setOffset(0)
          }}
          className="border border-border p-2 rounded-btn bg-surface"
        >
          <option value="">All reports</option>
          {statuses.map((value) => (
            <option key={value} value={value}>
              {label(value)}
            </option>
          ))}
        </select>
      </label>
      {list.loading && <p role="status">Loading reports...</p>}
      {list.error && (
        <p role="alert" className="text-risk-extreme">
          {list.error}
        </p>
      )}
      {list.data && (
        <>
          <p className="text-sm text-muted">{list.data.total} matching reports</p>
          {list.data.items.length ? (
            list.data.items.map((report) => (
              <ReportItem
                key={report.id}
                report={report}
                request={authorizedRequest}
                refresh={list.refresh}
              />
            ))
          ) : (
            <p>No reports match this filter.</p>
          )}
          <div className="flex gap-3">
            <button
              disabled={!offset || list.loading}
              onClick={() => setOffset((value) => Math.max(0, value - 20))}
              className="border border-border rounded-btn p-2"
            >
              Previous
            </button>
            <button
              disabled={offset + 20 >= list.data.total || list.loading}
              onClick={() => setOffset((value) => value + 20)}
              className="border border-border rounded-btn p-2"
            >
              Next
            </button>
          </div>
        </>
      )}
    </section>
  )
}
function ReportItem({ report, request, refresh }) {
  const [status, setStatus] = useState(report.review_status),
    [note, setNote] = useState(report.review_note ?? ''),
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
        body: JSON.stringify({ status, note: note.trim() || null, expected_version: version }),
      })
      if (saved.id !== report.id || saved.review_status !== status)
        throw new Error('No matching save confirmation. Refresh before retrying.')
      setVersion(saved.review_version)
      setMessage('Decision saved.')
      refresh()
    } catch (failure) {
      setMessage(
        failure.name === 'AbortError'
          ? 'Save not confirmed. Refresh before retrying.'
          : failure.message
      )
    } finally {
      setBusy(false)
    }
  }
  const hasCoordinates = Number.isFinite(report.latitude) && Number.isFinite(report.longitude)
  return (
    <article
      className="bg-surface border border-border rounded-card p-4 space-y-3 text-ink"
      aria-label={`Citizen report ${report.id}`}
    >
      <div className="flex flex-wrap justify-between gap-2">
        <h2 className="font-semibold">
          #{report.id} - {report.zone_name} - {report.observed_condition}
        </h2>
        <span className="text-sm">
          {label(report.review_status)} / {report.perceived_severity}
        </span>
      </div>
      <p className="text-xs text-muted">Reported {formatPredictionTime(report.timestamp)}</p>
      <p className="text-sm">
        <strong>Specific location:</strong>{' '}
        {report.location_description || 'Not supplied (older report)'}
      </p>
      {hasCoordinates && (
        <p className="text-sm">
          Reported pin: {report.latitude}, {report.longitude}
          {report.location_accuracy_m != null
            ? ` (device accuracy approximately ${Math.round(report.location_accuracy_m)} m)`
            : ''}
          .{' '}
          <a
            className="text-brand underline"
            href={`https://www.openstreetmap.org/?mlat=${report.latitude}&mlon=${report.longitude}#map=17/${report.latitude}/${report.longitude}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open reported location
          </a>
        </p>
      )}
      {report.description && <p className="text-sm">{report.description}</p>}
      {report.reviewed_at && (
        <p className="text-xs text-muted">
          Last reviewed by {report.reviewed_by_name || 'staff'} at{' '}
          {formatPredictionTime(report.reviewed_at)}
        </p>
      )}
      <form onSubmit={save} className="space-y-2">
        <label className="text-sm block">
          Decision{' '}
          <select
            aria-label={`Decision for report ${report.id}`}
            className="border border-border rounded-btn bg-surface p-2 ml-2"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            disabled={busy}
          >
            {statuses.map((value) => (
              <option key={value} value={value}>
                {label(value)}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm block">
          Review note
          <textarea
            aria-label={`Review note for report ${report.id}`}
            maxLength={1000}
            className="block w-full border border-border rounded-btn bg-surface p-2 mt-1"
            rows={2}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            disabled={busy}
          />
        </label>
        {changed && (
          <p role="status" className="text-sm">
            A newer review is available. Your draft is retained.{' '}
            <button
              type="button"
              className="underline"
              onClick={() => {
                setVersion(report.review_version)
                setStatus(report.review_status)
                setNote(report.review_note ?? '')
                setMessage('')
              }}
            >
              Load latest review
            </button>{' '}
            before editing further.
          </p>
        )}
        <button
          disabled={busy || changed}
          className="rounded-btn bg-brand text-white px-4 py-2 text-sm"
        >
          {busy ? 'Saving...' : 'Save decision'}
        </button>
        {message && (
          <p role="status" className="text-sm">
            {message}
          </p>
        )}
      </form>
    </article>
  )
}
