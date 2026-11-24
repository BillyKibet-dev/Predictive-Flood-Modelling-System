import { ArrowRight, RefreshCw } from 'lucide-react'
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, ResponsiveContainer } from 'recharts'
import { dailyWindow, parseObservedRainfall, parseVerification, percent, recentStats, trackRecordHeadline } from '../services/staffData'
import StaffLayout, { PageHeader, buttonClass } from '../components/StaffLayout'
import { riskColor } from '../constants/colors'
import { useAuth } from '../context/AuthContext'
import useCommunityReports from '../hooks/useCommunityReports'
import useMonitoringAreas from '../hooks/useMonitoringAreas'
import useMonitoringOutlook from '../hooks/useMonitoringOutlook'
import useStaffList from '../hooks/useStaffList'
import { timeAgo } from '../services/communityReports'
import { CLASSES } from '../services/monitoringOutlook'
import { watchClosely, watchOrder } from '../services/susceptibility'
import useSusceptibility from '../hooks/useSusceptibility'

const STATUS_LABEL = { New: 'New', Reviewed: 'Reviewed', ActionNeeded: 'Action needed', Resolved: 'Resolved' }
const time = value => new Intl.DateTimeFormat('en-KE', { timeZone: 'Africa/Nairobi', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
const greeting = () => { const h = Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Africa/Nairobi', hour: 'numeric' }).format(new Date())); return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening' }

function Tile({ label, value, to, hint, tone }) {
  return <Link to={to} className="panel card-hover p-5 flex flex-col group">
    <span className="eyebrow">{label}</span>
    <span className="text-3xl font-semibold tracking-tight mt-2 tabular" style={tone ? { color: tone } : undefined}>{value}</span>
    <span className="text-xs text-muted mt-auto pt-3 flex items-center gap-1 group-hover:text-accent">{hint}<ArrowRight size={12} aria-hidden="true" /></span>
  </Link>
}

// Tomorrow at a glance: one bar split by category, each part labelled with its count.
function OutlookBar({ counts, total }) {
  return <div>
    <div className="flex h-2.5 rounded-full overflow-hidden gap-0.5 bg-surface-2" aria-hidden="true">
      {CLASSES.map(c => counts[c] ? <span key={c} style={{ flexGrow: counts[c], background: riskColor(c) }} /> : null)}
    </div>
    <ul className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-sm" aria-label="Places by category tomorrow">
      {[...CLASSES].reverse().filter(c => counts[c]).map(c => <li key={c} className="flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full" style={{ background: riskColor(c) }} aria-hidden="true" />
        <span className="tabular font-medium">{counts[c]}</span><span className="text-muted">{c}</span></li>)}
      {total > 0 && <li className="text-muted">of {total} places</li>}
    </ul>
  </div>
}

const shortDate = value => new Intl.DateTimeFormat('en-KE', { day: 'numeric', month: 'short' }).format(new Date(value + 'T12:00:00'))

// Rain that fell lately (the system's own daily satellite record), with a 14-day strip.
function RecentRain() {
  const state = useStaffList('/staff/observed-rainfall')
  const data = useMemo(() => { try { return state.data ? parseObservedRainfall(state.data) : null } catch { return null } }, [state.data])
  if (!data) return <section className="panel p-5 text-sm text-muted">{state.loading ? 'Loading recent rain…' : 'Recent rain unavailable.'}</section>
  const stats = recentStats(data), days = dailyWindow(data, 14)
  return <Link to="/history" className="panel card-hover p-5 flex flex-col gap-3 group" aria-label="Recent rain: open rainfall history">
    <div className="flex items-baseline justify-between gap-3"><h2 className="font-semibold">Rain that fell</h2><span className="text-xs text-muted">to {shortDate(data.last_day)}</span></div>
    <div className="flex items-end gap-6">
      <p><span className="text-3xl font-semibold tabular">{Math.round(stats.week.mm)}</span><span className="text-sm text-muted"> mm, last 7 days</span></p>
      <div className="flex-1 h-12" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%"><BarChart data={days} margin={{ top: 0, bottom: 0, left: 0, right: 0 }}>
          <Bar isAnimationActive={false} dataKey="mm" fill="var(--chart-2)" radius={[2, 2, 0, 0]} /></BarChart></ResponsiveContainer>
      </div>
    </div>
    <span className="text-xs text-muted flex items-center gap-1 group-hover:text-accent">{stats.daysSinceHeavy === null ? 'No heavy-rain day collected yet' : `Last heavy-rain day ${stats.daysSinceHeavy} days ago`}<ArrowRight size={12} aria-hidden="true" /></span>
  </Link>
}

// Are the map's categories right lately? One line from the live track record.
function ModelCheck() {
  const state = useStaffList('/staff/model-verification')
  const data = useMemo(() => { try { return state.data ? parseVerification(state.data) : null } catch { return null } }, [state.data])
  if (!data) return <section className="panel p-5 text-sm text-muted">{state.loading ? 'Checking past forecasts…' : 'Model checks unavailable.'}</section>
  return <Link to="/research" className="panel card-hover p-5 flex flex-col gap-3 group" aria-label="Model checks: open">
    <div className="flex items-baseline justify-between gap-3"><h2 className="font-semibold">Model checks</h2><span className="text-xs text-muted">{data.days_verified} days checked</span></div>
    <p><span className="text-3xl font-semibold tabular">{data.shown.exact === null ? '—' : percent(data.shown.exact)}</span><span className="text-sm text-muted"> right category</span></p>
    <span className="text-xs text-muted flex items-center gap-1 group-hover:text-accent">{trackRecordHeadline(data).split('. ').slice(1).join('. ') || 'See the details'}<ArrowRight size={12} aria-hidden="true" /></span>
  </Link>
}

export default function OfficerDashboardPage() {
  const { user } = useAuth()
  const incoming = useStaffList('/citizen-reports?review_status=New&limit=1')
  const action = useStaffList('/citizen-reports?review_status=ActionNeeded&limit=1')
  const recent = useStaffList('/citizen-reports?limit=6')
  const outlook = useMonitoringOutlook(), areas = useMonitoringAreas(), published = useCommunityReports(), susceptibility = useSusceptibility()
  const count = state => state.error ? '—' : state.data?.total ?? '…'
  const available = outlook.data?.areas.filter(a => a.status === 'AVAILABLE') ?? []
  const counts = Object.fromEntries(CLASSES.map(c => [c, available.filter(a => a.proxy_class === c).length]))
  const names = Object.fromEntries((areas.data?.sites ?? []).map(s => [s.id, s]))
  const local = susceptibility.data?.byArea ?? {}
  const watch = available.filter(a => ['High', 'Extreme'].includes(a.proxy_class))
  // Rank by tomorrow's category, then by how easily the place floods, then by rainfall.
  const ranked = [...available].sort((a, b) => watchOrder(b.proxy_class, local[b.area_id]) - watchOrder(a.proxy_class, local[a.area_id]) || (b.rainfall_mm ?? 0) - (a.rainfall_mm ?? 0))
  const closely = ranked.filter(a => watchClosely(a.proxy_class, local[a.area_id]))
  const updated = available[0]?.received_at
  const refresh = () => { incoming.refresh(); action.refresh(); recent.refresh(); outlook.refresh(); published.refresh() }
  return <StaffLayout>
    <PageHeader title={`${greeting()}, ${user?.name.split(' ')[0] ?? ''}`} description="Reports waiting for you and tomorrow's rainfall outlook.">
      <button className={buttonClass} onClick={refresh}><RefreshCw size={15} />Refresh</button>
    </PageHeader>

    <section className="grid grid-cols-2 lg:grid-cols-4 gap-4" aria-label="Report workload">
      <Tile label="New reports" value={count(incoming)} to="/officer/reports?review_status=New" hint="Review" tone={incoming.data?.total ? 'var(--accent)' : undefined} />
      <Tile label="Action needed" value={count(action)} to="/officer/reports?review_status=ActionNeeded" hint="Follow up" />
      <Tile label="On public map" value={published.data ? published.data.items.length : published.error ? '—' : '…'} to="/" hint="Last 24 hours" />
      <Tile label="High or Extreme" value={outlook.data ? watch.length : '…'} to="/" hint="Places tomorrow" tone={watch.length ? riskColor(watch[0].proxy_class) : undefined} />
    </section>
    {(incoming.error || action.error) && <p role="alert" className="text-sm mt-2">Could not check report counts. {incoming.error || action.error}</p>}

    <div className="grid lg:grid-cols-5 gap-4 mt-6">
      <section className="panel lg:col-span-3 overflow-hidden" aria-labelledby="recent-heading">
        <div className="px-5 pt-5 pb-3 flex items-baseline justify-between gap-3">
          <h2 id="recent-heading" className="font-semibold">Recent community reports</h2>
          <Link className="text-sm text-accent font-medium" to="/officer/reports">Open inbox</Link>
        </div>
        {recent.error && <p role="alert" className="px-5 pb-4 text-sm">Reports could not be refreshed. {recent.data ? 'Showing the last ones retrieved.' : ''}</p>}
        {recent.loading && !recent.data && <p role="status" className="px-5 pb-5 text-sm text-muted">Loading reports…</p>}
        {recent.data?.items.length === 0 && <p className="px-5 pb-5 text-sm text-muted">No reports yet.</p>}
        <ul className="divide-y divide-border">{recent.data?.items.map(r => <li key={r.id}>
          <Link to="/officer/reports" className="px-5 py-3 flex gap-3 items-start hover:bg-surface-2">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{r.observed_condition} <span className="text-muted font-normal">· {r.perceived_severity}</span></p>
              <p className="text-xs text-muted truncate mt-0.5">{r.zone_name}{r.location_description ? ` · ${r.location_description}` : ''}</p>
            </div>
            <div className="text-right shrink-0">
              <p className={`text-xs font-semibold ${r.review_status === 'New' ? 'text-accent' : r.review_status === 'ActionNeeded' ? 'text-risk-high' : 'text-muted'}`}>{STATUS_LABEL[r.review_status] ?? r.review_status}</p>
              <p className="text-xs text-muted mt-0.5">{timeAgo(r.timestamp)}</p>
            </div>
          </Link></li>)}</ul>
      </section>

      <section className="panel lg:col-span-2 p-5 space-y-4" aria-labelledby="tomorrow-heading">
        <div className="flex items-baseline justify-between gap-3"><h2 id="tomorrow-heading" className="font-semibold">Tomorrow</h2>
          {updated && <span className="text-xs text-muted">Updated {time(updated)}</span>}</div>
        {outlook.loading && !outlook.data && <p role="status" className="text-sm text-muted">Checking the outlook…</p>}
        {outlook.data && !available.length && <p className="text-sm">No fresh outlook. Check System or the Weather page.</p>}
        {available.length > 0 && <OutlookBar counts={counts} total={outlook.data.located_count} />}
        {ranked.length > 0 && <div><p className="eyebrow mb-2">{closely.length ? `Watch closely · ${closely.length}` : 'Check first'}</p>
          <ul className="space-y-1.5 text-sm" aria-label="Places to check first">{ranked.slice(0, 5).map(a => {
            const row = local[a.area_id]
            return <li key={a.area_id} className="flex gap-2 items-baseline">
              <span className="w-2.5 h-2.5 rounded-full shrink-0 translate-y-[-1px]" style={{ background: riskColor(a.proxy_class), boxShadow: row?.level === 'Higher' ? '0 0 0 2px #111827' : undefined }} aria-hidden="true" />
              <Link to={`/?area=${a.area_id}&inspect=1`} className="flex-1 min-w-0 truncate hover:text-accent">{names[a.area_id]?.display_name ?? a.area_id}</Link>
              <span className="text-xs text-muted shrink-0">{a.proxy_class}{row ? ` · ${row.level === 'Higher' ? 'floods easily' : row.level === 'Lower' ? 'higher ground' : 'average'}` : ''}</span></li>
          })}</ul>
          <p className="text-xs text-muted mt-2">Ranked by tomorrow's category, then by how easily the place floods (ringed).</p>
        </div>}
        <p className="text-xs text-muted">Rainfall categories, not flood warnings. Reviewing a report does not issue a public warning.</p>
      </section>
    </div>
    <div className="grid md:grid-cols-2 gap-4 mt-4"><RecentRain /><ModelCheck /></div>
  </StaffLayout>
}
