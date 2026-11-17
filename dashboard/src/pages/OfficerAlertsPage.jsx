import { useState } from 'react'
import StaffLayout from '../components/StaffLayout'
import useStaffList from '../hooks/useStaffList'
import { useAuth } from '../context/AuthContext'
import { formatPredictionTime } from '../services/predictions'
import RiskBadge from '../components/RiskBadge'
import { Link } from 'react-router-dom'

export default function OfficerAlertsPage() {
  const { authorizedRequest } = useAuth()
  const [filter, setFilter] = useState(''),
    [date, setDate] = useState(''),
    [offset, setOffset] = useState(0),
    [busy, setBusy] = useState(null),
    [message, setMessage] = useState('')
  const query = new URLSearchParams({
    limit: '50',
    offset: String(offset),
    ...(filter ? { acknowledged: filter } : {}),
    ...(date ? { on_date: date } : {}),
  })
  const list = useStaffList('/alerts?' + query)
  async function acknowledge(alert) {
    setBusy(alert.id)
    setMessage('')
    try {
      const saved = await authorizedRequest(`/alerts/${alert.id}/acknowledge`, { method: 'POST' })
      if (saved.id !== alert.id || !saved.acknowledged_status)
        throw new Error('Acknowledgement not confirmed. Refresh before retrying.')
      list.refresh()
    } catch (failure) {
      setMessage(failure.message)
    } finally {
      setBusy(null)
    }
  }
  function exportPage() {
    if (!list.data?.items.length) return
    const cell = (value) => {
      const text = String(value ?? '')
      return '"' + (/^[\t\r\n ]*[=+@-]/.test(text) ? "'" + text : text).replaceAll('"', '""') + '"'
    }
    const csv = [
      ['ID', 'Zone', 'Class', 'Saved at', 'Acknowledged', 'Acknowledged by'],
      ...list.data.items.map((item) => [
        item.id,
        item.zone_name,
        item.risk_level,
        item.timestamp,
        item.acknowledged_status,
        item.acknowledged_by_name,
      ]),
    ]
      .map((row) => row.map(cell).join(','))
      .join('\r\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'saved-advisories-page.csv'
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return (
    <StaffLayout><div className="space-y-5">
        <h1 className="text-2xl font-semibold">Saved model notice history</h1>
        <Link className="text-sm text-brand underline" to="/research">Back to experimental models</Link>
        <p className="text-sm text-muted">
          Persisted advisory records for officer review. Acknowledgement records who reviewed an
          item; it does not send a public warning. Records may come from current or older experimental pipelines and do not confirm flooding.
        </p>
        <div className="flex flex-wrap gap-3">
          <select
            aria-label="Acknowledgement filter"
            className="border border-border rounded-btn bg-surface p-2"
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value)
              setOffset(0)
            }}
          >
            <option value="">All records</option>
            <option value="false">Awaiting review</option>
            <option value="true">Acknowledged</option>
          </select>
          <label className="text-sm">
            Saved date (Nairobi)
            <input
              type="date"
              className="block border border-border rounded-btn bg-surface p-2"
              value={date}
              onChange={(event) => {
                setDate(event.target.value)
                setOffset(0)
              }}
            />
          </label>
          <button className="border border-border rounded-btn p-2" onClick={list.refresh}>
            Refresh records
          </button>
          <button
            className="border border-border rounded-btn p-2"
            onClick={exportPage}
            disabled={!list.data?.items.length}
          >
            Export this page
          </button>
        </div>
        {list.loading && <p role="status">Loading saved advisories...</p>}
        {(list.error || message) && <p role="alert">{message || list.error}</p>}
        {list.data && (
          <>
            <p className="text-sm text-muted">{list.data.total} matching records</p>
            {!list.data.items.length && <p>No saved advisories match this filter.</p>}
            {list.data.items.map((alert) => (
              <article
                key={alert.id}
                className="bg-surface border border-border rounded-card p-4 flex flex-wrap gap-3 items-center"
              >
                <span className="font-semibold">{alert.zone_name}</span>
                <RiskBadge risk={alert.risk_level} />
                <span className="text-sm text-muted">{formatPredictionTime(alert.timestamp)}</span>
                {alert.acknowledged_status ? (
                  <span className="text-sm">
                    Reviewed by {alert.acknowledged_by_name ?? 'staff'} at{' '}
                    {formatPredictionTime(alert.acknowledged_at)}
                  </span>
                ) : (
                  <button
                    className="bg-brand text-white rounded-btn p-2 text-sm"
                    disabled={busy !== null}
                    onClick={() => acknowledge(alert)}
                  >
                    {busy === alert.id ? 'Saving...' : 'Acknowledge'}
                  </button>
                )}
              </article>
            ))}
            <div className="flex gap-3">
              <button
                className="border border-border p-2 rounded-btn"
                disabled={!offset}
                onClick={() => setOffset((value) => Math.max(0, value - 50))}
              >
                Previous
              </button>
              <button
                className="border border-border p-2 rounded-btn"
                disabled={offset + 50 >= list.data.total}
                onClick={() => setOffset((value) => value + 50)}
              >
                Next
              </button>
            </div>
          </>
        )}
      </div></StaffLayout>
  )
}
