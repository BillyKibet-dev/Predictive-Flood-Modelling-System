import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Download } from 'lucide-react'
import ChartTooltip, { ChartLegend, axisProps } from '../components/ChartTooltip'
import StaffLayout, { PageHeader, buttonClass } from '../components/StaffLayout'
import { useAuth } from '../context/AuthContext'
import useStaffList from '../hooks/useStaffList'
import { historyHighlights, monthlyComparison, parseRainfallHistory, saveFile } from '../services/staffData'

const AVERAGE = { label: 'Average 2016–2025', color: 'var(--chart-1)' }
const longDate = value => new Intl.DateTimeFormat('en-KE', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value + 'T12:00:00'))
const mm = value => `${Math.round(value).toLocaleString('en-GB')} mm`

function Stat({ label, value, detail }) {
  return <div className="panel p-5"><p className="eyebrow">{label}</p>
    <p className="text-2xl font-semibold tracking-tight mt-2 tabular">{value}</p>
    {detail && <p className="text-sm text-muted mt-1">{detail}</p>}</div>
}

export default function RainfallHistoryPage() {
  const { authorizedDownload } = useAuth()
  const state = useStaffList('/staff/rainfall-history')
  const [history, invalid] = useMemo(() => {
    if (!state.data) return [null, '']
    try { return [parseRainfallHistory(state.data), ''] } catch (error) { return [null, error.message] }
  }, [state.data])
  const years = history?.yearly.map(y => y.year) ?? []
  const [year, setYear] = useState(2024)
  const [downloading, setDownloading] = useState(''), [downloadError, setDownloadError] = useState('')
  const highlights = history && historyHighlights(history)
  const monthly = history ? monthlyComparison(history, year) : []
  const yearly = history?.yearly.map(y => ({ ...y, label: y.complete ? String(y.year) : `${y.year}*` })) ?? []
  async function download() {
    setDownloading('all'); setDownloadError('')
    try { saveFile(await authorizedDownload('/exports/rainfall-history.csv')) } catch (error) { setDownloadError(error.message) } finally { setDownloading('') }
  }
  return <StaffLayout>
    <PageHeader title="Rainfall history" description="Daily satellite rainfall over Nairobi since 2016. Rainfall, not flooding: for flood evidence use the 2024 flood map and community reports.">
      <button className={buttonClass} onClick={download} disabled={!!downloading}><Download size={16} />{downloading ? 'Preparing…' : 'Download CSV'}</button>
    </PageHeader>
    {(state.error || invalid || downloadError) && <p role="alert" className="text-sm mb-4">{state.error || invalid || downloadError}</p>}
    {!history && state.loading && <p role="status" className="text-sm text-muted">Loading rainfall history…</p>}
    {history && <div className="space-y-8">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Average year" value={mm(highlights.averageYear)} detail="Complete years, 2016–2025" />
        <Stat label="Wettest year" value={highlights.wettestYear.year} detail={mm(highlights.wettestYear.total_mm)} />
        <Stat label="Wettest day" value={mm(highlights.wettestDay.mean_mm)} detail={longDate(highlights.wettestDay.date)} />
        <Stat label="Heavy-rain days" value={`${highlights.heavyDaysPerYear} a year`} detail={`Days averaging ${history.thresholds_mm.heavy} mm or more`} />
      </div>

      <section className="panel p-5 sm:p-6 space-y-4" aria-labelledby="month-heading">
        <div className="flex flex-wrap justify-between gap-3 items-end">
          <div><h2 id="month-heading" className="font-semibold">Month by month</h2><p className="text-sm text-muted mt-1">Long rains peak in April; short rains in November.</p></div>
          <div className="flex flex-wrap items-center gap-4">
            <ChartLegend items={[AVERAGE, { label: String(year), color: 'var(--chart-2)' }]} />
            <label className="text-sm flex items-center gap-2">Compare<select aria-label="Year to compare" className="h-8 border border-border rounded-btn bg-surface px-2 text-sm" value={year} onChange={e => setYear(Number(e.target.value))}>
              {years.map(y => <option key={y} value={y}>{y}</option>)}</select></label>
          </div>
        </div>
        <div className="h-64" role="img" aria-label={`Monthly rainfall in ${year} compared with the average`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={monthly} barGap={2} margin={{ left: -12, right: 4 }}>
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="month" {...axisProps} />
              <YAxis {...axisProps} unit="" />
              <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip unit=" mm" format={v => Math.round(v)} />} />
              <Bar isAnimationActive={false} dataKey="average" name={AVERAGE.label} fill={AVERAGE.color} radius={[4, 4, 0, 0]} maxBarSize={16} />
              <Bar isAnimationActive={false} dataKey="year" name={String(year)} fill="var(--chart-2)" radius={[4, 4, 0, 0]} maxBarSize={16} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <div className="grid lg:grid-cols-5 gap-4">
        <section className="panel p-5 sm:p-6 space-y-4 lg:col-span-3" aria-labelledby="year-heading">
          <div><h2 id="year-heading" className="font-semibold">Each year</h2><p className="text-sm text-muted mt-1">Total rainfall. * {history.last_day.slice(0, 4)} runs to {longDate(history.last_day)}.</p></div>
          <div className="h-56" role="img" aria-label="Total rainfall each year">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={yearly} margin={{ left: -4, right: 4 }}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="label" {...axisProps} tick={{ ...axisProps.tick, fontSize: 11 }} interval={0} />
                <YAxis {...axisProps} />
                <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip unit=" mm" format={v => Math.round(v).toLocaleString('en-GB')} />} />
                <Bar isAnimationActive={false} dataKey="total_mm" name="Total" fill="var(--chart-2)" radius={[4, 4, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <details className="text-sm"><summary className="cursor-pointer text-accent font-medium">Table</summary>
            <div className="overflow-x-auto mt-2"><table className="w-full tabular text-sm"><thead><tr className="text-left text-muted">{['Year', 'Total', `Days ≥ ${history.thresholds_mm.heavy} mm`, `Days ≥ ${history.thresholds_mm.very_heavy} mm`].map(h => <th key={h} scope="col" className="py-1.5 pr-4 font-medium">{h}</th>)}</tr></thead>
              <tbody>{history.yearly.map(y => <tr key={y.year} className="border-t border-border"><th scope="row" className="py-1.5 pr-4 text-left font-normal">{y.year}{y.complete ? '' : '*'}</th><td className="pr-4">{mm(y.total_mm)}</td><td className="pr-4">{y.heavy_days}</td><td>{y.very_heavy_days}</td></tr>)}</tbody></table></div>
          </details>
        </section>
        <section className="panel p-5 sm:p-6 lg:col-span-2" aria-labelledby="wettest-heading">
          <h2 id="wettest-heading" className="font-semibold">Wettest days</h2>
          <p className="text-sm text-muted mt-1">Nairobi average, with the wettest zone.</p>
          <ol className="mt-3 divide-y divide-border text-sm">{history.wettest_days.map((d, i) => <li key={d.date} className="py-2 flex gap-3 items-baseline">
            <span className="tabular text-muted w-5">{i + 1}</span><span className="flex-1">{longDate(d.date)}</span>
            <span className="tabular font-medium">{mm(d.mean_mm)}</span><span className="tabular text-xs text-muted w-28 text-right">{d.wettest_zone} {mm(d.wettest_zone_mm)}</span></li>)}</ol>
        </section>
      </div>

      <section className="text-sm text-muted space-y-2" aria-label="About this data">
        <p>{history.source}. {history.limitations.join(' ')}</p>
        <p className="flex flex-wrap gap-x-5 gap-y-1"><Link className="text-accent font-medium" to="/">Satellite flood map, 1 May 2024 (Map → Map layers)</Link>
          <Link className="text-accent font-medium" to="/environmental-data">Imported datasets</Link>
          <Link className="text-accent font-medium" to="/downloads">Download a date range</Link></p>
      </section>
    </div>}
  </StaffLayout>
}
