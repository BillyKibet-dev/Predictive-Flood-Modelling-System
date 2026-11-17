import { CloudRain, Download, History, Inbox } from 'lucide-react'
import { useState } from 'react'
import StaffLayout, { PageHeader, primaryButtonClass } from '../components/StaffLayout'
import { useAuth } from '../context/AuthContext'
import { exportPath, saveFile } from '../services/staffData'

const input = 'h-9 border border-border rounded-btn bg-surface px-2 text-sm'
const STATUSES = [['', 'Any status'], ['New', 'New'], ['Reviewed', 'Reviewed'], ['ActionNeeded', 'Action needed'], ['Resolved', 'Resolved']]

function DateRange({ id, value, onChange, min, max }) {
  return <>{['start', 'end'].map(key => <label key={key} className="text-sm flex flex-col gap-1">
    <span className="text-xs text-muted">{key === 'start' ? 'From' : 'To'}</span>
    <input type="date" aria-label={`${id} ${key === 'start' ? 'from' : 'to'} date`} className={input} min={min} max={max}
      value={value[key]} onChange={e => onChange({ ...value, [key]: e.target.value })} />
  </label>)}</>
}

function Row({ icon: Icon, title, description, children, onDownload, busy, error }) {
  return <li className="p-5 sm:p-6 grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
    <div className="flex gap-4 min-w-0">
      <span className="w-10 h-10 shrink-0 rounded-card bg-surface-2 grid place-items-center text-muted"><Icon size={18} /></span>
      <div className="min-w-0 space-y-3"><div><h2 className="font-semibold">{title}</h2><p className="text-sm text-muted mt-0.5">{description}</p></div>
        {children && <div className="flex flex-wrap gap-3 items-end">{children}</div>}
        {error && <p role="alert" className="text-sm text-risk-extreme">{error}</p>}</div>
    </div>
    <button className={primaryButtonClass + ' md:justify-self-end'} onClick={onDownload} disabled={busy}><Download size={16} />{busy ? 'Preparing…' : 'Download CSV'}</button>
  </li>
}

// Every file is built on the server from the same records the dashboard shows.
export default function DownloadsPage() {
  const { authorizedDownload } = useAuth()
  const [reports, setReports] = useState({ start: '', end: '', review_status: '' })
  const [history, setHistory] = useState({ start: '2024-01-01', end: '' })
  const [busy, setBusy] = useState(''), [errors, setErrors] = useState({})
  async function run(key, path) {
    setBusy(key); setErrors(e => ({ ...e, [key]: '' }))
    try { saveFile(await authorizedDownload(path)) } catch (error) { setErrors(e => ({ ...e, [key]: error.message })) } finally { setBusy('') }
  }
  const backwards = range => range.start && range.end && range.end < range.start
  return <StaffLayout width="max-w-4xl">
    <PageHeader title="Downloads" description="Spreadsheet files (CSV) for reports, analysis and record-keeping. They open in Excel or Google Sheets." />
    <ul className="panel divide-y divide-border">
      <Row icon={Inbox} title="Community reports" description="Every report with its sub-county, location, review decision and who reviewed it."
        busy={busy === 'reports'} error={errors.reports || (backwards(reports) ? 'The end date is before the start date.' : '')}
        onDownload={() => !backwards(reports) && run('reports', exportPath('/exports/citizen-reports.csv', reports))}>
        <DateRange id="Reports" value={reports} onChange={setReports} />
        <label className="text-sm flex flex-col gap-1"><span className="text-xs text-muted">Status</span>
          <select aria-label="Reports status" className={input} value={reports.review_status} onChange={e => setReports({ ...reports, review_status: e.target.value })}>
            {STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      </Row>
      <Row icon={CloudRain} title="Tomorrow's rainfall outlook" description="The category at all 36 monitored places as shown on the map now, with rainfall amounts and forecast times."
        busy={busy === 'outlook'} error={errors.outlook} onDownload={() => run('outlook', '/exports/rainfall-outlook.csv')} />
      <Row icon={History} title="Rainfall history" description="Daily satellite rainfall (CHIRPS) for the eight original zones, 2016 to September 2026."
        busy={busy === 'history'} error={errors.history || (backwards(history) ? 'The end date is before the start date.' : '')}
        onDownload={() => !backwards(history) && run('history', exportPath('/exports/rainfall-history.csv', history))}>
        <DateRange id="History" value={history} onChange={setHistory} min="2016-01-01" max="2026-09-30" />
      </Row>
    </ul>
    <p className="text-sm text-muted mt-4">Report files include what citizens wrote. Treat them as personal data: share them only with people who need them.</p>
  </StaffLayout>
}
