import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Download, RefreshCw } from 'lucide-react'
import ChartTooltip, { ChartLegend, axisProps, useNarrow } from '../components/ChartTooltip'
import StaffLayout, { PageHeader, buttonClass } from '../components/StaffLayout'
import { useAuth } from '../context/AuthContext'
import useStaffList from '../hooks/useStaffList'
import { areaGrid, collectedMonthly, dailyWindow, historyHighlights, monthlyComparison, parseObservedRainfall, parseRainfallHistory, recentStats, saveFile } from '../services/staffData'

const AVERAGE = { label: 'Average 2016–2025', color: 'var(--chart-1)' }
const COLLECTED = { label: 'Collected', color: 'var(--chart-2)' }
const longDate = value => new Intl.DateTimeFormat('en-KE', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value + 'T12:00:00'))
const shortDate = value => new Intl.DateTimeFormat('en-KE', { day: 'numeric', month: 'short' }).format(new Date(value + 'T12:00:00'))
const dayLetter = value => new Intl.DateTimeFormat('en-KE', { weekday: 'narrow' }).format(new Date(value + 'T12:00:00'))
const when = value => new Intl.DateTimeFormat('en-KE', { timeZone: 'Africa/Nairobi', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
const mm = value => `${Math.round(value).toLocaleString('en-GB')} mm`
const mm1 = value => `${value < 10 ? value.toFixed(1) : Math.round(value)} mm`
const RANGES = [[30, '30 days'], [90, '90 days'], [365, '1 year'], [null, 'All']]

function Stat({ label, value, detail }) {
  return <div className="panel p-5"><p className="eyebrow">{label}</p>
    <p className="text-2xl font-semibold tracking-tight mt-2 tabular">{value}</p>
    {detail && <p className="text-sm text-muted mt-1">{detail}</p>}</div>
}

function Segmented({ label, options, value, onChange }) {
  return <div role="group" aria-label={label} className="inline-flex p-0.5 rounded-btn bg-surface-2 text-sm">
    {options.map(([v, text]) => <button key={String(v)} type="button" aria-pressed={value === v} onClick={() => onChange(v)}
      className={`h-8 px-3 rounded-[6px] whitespace-nowrap ${value === v ? 'bg-surface text-ink font-semibold shadow-card-rest' : 'text-muted hover:text-ink'}`}>{text}</button>)}
  </div>
}

// One hue, light to dark: more rain, deeper blue. 40 mm (Extreme on the rule) is the darkest.
const heat = value => value === null ? 'var(--surface-2)' : value < 0.5 ? 'var(--surface)' : `color-mix(in srgb, #0369a1 ${Math.round(12 + Math.min(value, 40) / 40 * 88)}%, var(--surface))`

function Collected() {
  const { authorizedDownload } = useAuth()
  const narrow = useNarrow()
  const state = useStaffList('/staff/observed-rainfall')
  const [range, setRange] = useState(90)
  const [downloading, setDownloading] = useState(false), [downloadError, setDownloadError] = useState('')
  const [data, invalid] = useMemo(() => {
    if (!state.data) return [null, '']
    try { return [parseObservedRainfall(state.data), ''] } catch (error) { return [null, error.message] }
  }, [state.data])
  if (!data) return <>
    {(state.error || invalid) && <p role="alert" className="text-sm">{state.error || invalid}</p>}
    {state.loading && <p role="status" className="text-sm text-muted">Loading collected rainfall…</p>}
  </>
  // Phones: the latest 12 months, so each month stays readable.
  const stats = recentStats(data), daily = dailyWindow(data, range), months = collectedMonthly(data).slice(narrow ? -12 : 0), grid = areaGrid(data, narrow ? 10 : 14)
  const heavy = data.thresholds_mm.heavy
  const tickEvery = Math.max(1, Math.round(daily.length / (narrow ? 4 : 8)))
  async function download() {
    setDownloading(true); setDownloadError('')
    try { saveFile(await authorizedDownload('/exports/observed-rainfall.csv')) } catch (error) { setDownloadError(error.message) } finally { setDownloading(false) }
  }
  return <div className="space-y-6">
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <Stat label="Latest day" value={stats.latest ? mm1(stats.latest.nairobi_mm) : '—'} detail={stats.latest ? longDate(stats.latest.date) : 'Not collected yet'} />
      <Stat label="Last 7 days" value={mm(stats.week.mm)} detail={stats.week.days < 7 ? `${stats.week.days} of 7 days collected` : 'Nairobi average'} />
      <Stat label="Last 30 days" value={mm(stats.month.mm)} detail={`${stats.rainyDays30} rainy days (1 mm or more)`} />
      <Stat label="Since heavy rain" value={stats.daysSinceHeavy === null ? 'None yet' : stats.daysSinceHeavy === 0 ? 'Today' : `${stats.daysSinceHeavy} days`}
        detail={stats.lastHeavy ? `${mm1(stats.lastHeavy.nairobi_mm)} on ${shortDate(stats.lastHeavy.date)}` : `No day of ${heavy} mm or more`} />
    </div>

    <section className="panel p-5 sm:p-6 space-y-4" aria-labelledby="daily-heading">
      <div className="flex flex-wrap justify-between gap-3 items-end">
        <div><h2 id="daily-heading" className="font-semibold">Each day</h2><p className="text-sm text-muted mt-1">Nairobi average. Dashed line: {heavy} mm, a heavy-rain day.</p></div>
        <Segmented label="Period" options={RANGES} value={range} onChange={setRange} />
      </div>
      <div className="h-64" role="img" aria-label={`Daily rainfall over Nairobi for the last ${daily.length} days`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={daily} barCategoryGap={daily.length > 120 ? 0 : 2} margin={{ left: -12, right: 4, top: 8 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="date" {...axisProps} tickFormatter={shortDate} interval={tickEvery - 1} minTickGap={8} />
            <YAxis {...axisProps} allowDecimals={false} />
            <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip unit=" mm" format={v => v.toFixed(1)} labelFormat={longDate} />} />
            <ReferenceLine y={heavy} stroke="var(--text-muted)" strokeDasharray="4 4" />
            <Bar isAnimationActive={false} dataKey="mm" name="Rainfall" fill={COLLECTED.color} radius={daily.length > 120 ? 0 : [3, 3, 0, 0]} maxBarSize={18} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {daily.some(d => !d.collected) && <p className="text-xs text-muted">Gaps are days that were not collected; they are not dry days.</p>}
    </section>

    <section className="panel p-5 sm:p-6 space-y-4" aria-labelledby="grid-heading">
      <div><h2 id="grid-heading" className="font-semibold">By sub-county</h2><p className="text-sm text-muted mt-1">Last {grid.dates.length} days, wettest first. Darker blue, more rain.</p></div>
      <div className="overflow-x-auto -mx-1 px-1">
        <table className="text-xs tabular border-separate" style={{ borderSpacing: 2 }}>
          <caption className="sr-only">Daily rainfall in millimetres by sub-county</caption>
          <thead><tr><th scope="col" className="sr-only">Sub-county</th>{grid.dates.map(d => <th key={d} scope="col" className="font-normal text-muted w-9 text-center pb-1">
            <span className="block">{dayLetter(d)}</span><span className="block">{d.slice(8)}</span></th>)}
            <th scope="col" className="font-medium text-muted text-right pl-2">Total</th></tr></thead>
          <tbody>{grid.rows.map(row => <tr key={row.id}>
            <th scope="row" className="text-left font-normal pr-3 whitespace-nowrap max-w-36 truncate">{row.name}</th>
            {row.values.map((v, i) => <td key={grid.dates[i]} title={`${row.name}, ${longDate(grid.dates[i])}: ${v === null ? 'not collected' : `${v.toFixed(1)} mm`}`}
              className="w-9 h-8 text-center rounded-[4px]" style={{ background: heat(v), color: v !== null && v >= 18 ? '#fff' : 'var(--text)' }}>
              {v === null ? '·' : v >= 1 ? Math.round(v) : ''}</td>)}
            <td className="text-right pl-2 font-medium">{Math.round(row.total)}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <p className="flex items-center gap-2 text-xs text-muted" aria-hidden="true">0
        <span className="h-2.5 w-32 rounded-full" style={{ background: 'linear-gradient(to right, var(--surface-2), #0369a1)' }} />40+ mm
        <span className="ml-3">· not collected</span></p>
    </section>

    <section className="panel p-5 sm:p-6 space-y-4" aria-labelledby="months-heading">
      <div className="flex flex-wrap justify-between gap-3 items-end">
        <div><h2 id="months-heading" className="font-semibold">Month by month</h2><p className="text-sm text-muted mt-1">Collected totals next to the usual amount for that month. * Not every day collected.</p></div>
        <ChartLegend items={[COLLECTED, AVERAGE]} />
      </div>
      <div className="h-64" role="img" aria-label="Collected monthly rainfall compared with the 2016–2025 average">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={months.map(m => ({ ...m, label: m.complete ? m.label : `${m.label}*` }))} barGap={2} margin={{ left: -12, right: 4 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" minTickGap={10} />
            <YAxis {...axisProps} />
            <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip unit=" mm" format={v => Math.round(v)} />} />
            <Bar isAnimationActive={false} dataKey="collected" name={COLLECTED.label} fill={COLLECTED.color} radius={[3, 3, 0, 0]} maxBarSize={14} />
            <Bar isAnimationActive={false} dataKey="average" name={AVERAGE.label} fill={AVERAGE.color} radius={[3, 3, 0, 0]} maxBarSize={14} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>

    <section className="text-sm text-muted space-y-2" aria-label="About this data">
      <p>{data.source}. {data.days_stored.toLocaleString('en-GB')} days since {longDate(data.first_day)}{data.days_missing ? `, ${data.days_missing} missing` : ''}.
        {data.last_received_at && ` Last collected ${when(data.last_received_at)}. A new day appears each morning.`}</p>
      <details><summary className="cursor-pointer text-accent font-medium">Limits</summary>
        <ul className="list-disc pl-5 mt-2 space-y-1">{data.limitations.map(l => <li key={l}>{l}</li>)}</ul></details>
      <div className="flex flex-wrap gap-3 items-center">
        <button className={buttonClass} onClick={download} disabled={downloading}><Download size={16} />{downloading ? 'Preparing…' : 'Download collected days (CSV)'}</button>
        <button className={buttonClass} onClick={state.refresh} disabled={state.loading}><RefreshCw size={15} />Refresh</button>
        {downloadError && <span role="alert">{downloadError}</span>}
      </div>
    </section>
  </div>
}

function Archive() {
  const { authorizedDownload } = useAuth()
  const narrow = useNarrow()
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
  return <>
    {(state.error || invalid || downloadError) && <p role="alert" className="text-sm mb-4">{state.error || invalid || downloadError}</p>}
    {!history && state.loading && <p role="status" className="text-sm text-muted">Loading rainfall history…</p>}
    {history && <div className="space-y-6">
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
                <XAxis dataKey="label" {...axisProps} tick={{ ...axisProps.tick, fontSize: 11 }} interval={narrow ? 'preserveStartEnd' : 0}
                  tickFormatter={label => narrow ? `’${label.slice(2)}` : label} minTickGap={4} />
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
            <span className="tabular text-muted w-5 shrink-0">{i + 1}</span>
            <span className="flex-1 min-w-0">{longDate(d.date)}<span className="block sm:hidden text-xs text-muted tabular">{d.wettest_zone} {mm(d.wettest_zone_mm)}</span></span>
            <span className="tabular font-medium">{mm(d.mean_mm)}</span><span className="hidden sm:block tabular text-xs text-muted w-28 text-right">{d.wettest_zone} {mm(d.wettest_zone_mm)}</span></li>)}</ol>
        </section>
      </div>

      <section className="text-sm text-muted space-y-2" aria-label="About this data">
        <p>{history.source}. {history.limitations.join(' ')}</p>
        <p className="flex flex-wrap gap-x-5 gap-y-1 items-center">
          <button className={buttonClass} onClick={download} disabled={!!downloading}><Download size={16} />{downloading ? 'Preparing…' : 'Download archive (CSV)'}</button>
          <Link className="text-accent font-medium" to="/">Satellite flood map, 1 May 2024 (Map → Map layers)</Link>
          <Link className="text-accent font-medium" to="/environmental-data">Imported datasets</Link></p>
      </section>
    </div>}
  </>
}

// Two views of the same question, "how much rain fell?": the days the system has collected
// itself (growing daily) and the 2016–2026 archive the models were built on.
export default function RainfallHistoryPage() {
  const [params, setParams] = useSearchParams()
  const view = params.get('view') === 'archive' ? 'archive' : 'collected'
  return <StaffLayout>
    <PageHeader title="Rainfall history" description="Rain that fell over Nairobi. Rainfall, not flooding.">
      <Segmented label="View" value={view} onChange={v => setParams(v === 'archive' ? { view: 'archive' } : {})}
        options={[['collected', 'Collected daily'], ['archive', 'Since 2016']]} />
    </PageHeader>
    {view === 'collected' ? <Collected /> : <Archive />}
  </StaffLayout>
}
