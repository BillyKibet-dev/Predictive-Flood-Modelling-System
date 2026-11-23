import { useMemo } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { RefreshCw } from 'lucide-react'
import ChartTooltip, { ChartLegend, axisProps, useNarrow } from './ChartTooltip'
import { buttonClass } from './StaffLayout'
import useStaffList from '../hooks/useStaffList'
import { parseVerification, percent, share, trackRecordHeadline } from '../services/staffData'

const FORECAST = { label: 'Forecast', color: 'var(--chart-1)' }, FELL = { label: 'Fell (satellite)', color: 'var(--chart-2)' }
const shortDate = value => new Intl.DateTimeFormat('en-KE', { day: 'numeric', month: 'short' }).format(new Date(value + 'T12:00:00'))
const pct = v => v === null ? '—' : percent(v)
const STATUS = { VERIFIED: 'Checked', WAITING_FOR_SATELLITE: 'Waiting for satellite rain', FORECAST_UNREADABLE: 'Skipped (older forecast format)', NO_FORECAST: 'No forecast' }

function Tile({ label, value, detail }) {
  return <div className="panel p-5"><p className="eyebrow">{label}</p>
    <p className="text-2xl font-semibold tracking-tight mt-2 tabular">{value}</p>
    {detail && <p className="text-sm text-muted mt-1">{detail}</p>}</div>
}

// Map vs rule on the same days: which one is doing better right now.
function Comparison({ v }) {
  const rows = [
    ['Right category', s => s.exact, true, pct],
    ['Heavy rain caught', s => s.pod, true, pct, s => share(s.hits, s.hits + s.misses)],
    ['Heavy-rain false alarms', s => s.far, false, pct, s => share(s.false_alarms, s.hits + s.false_alarms)],
    ['Wet days caught (5 mm+)', s => s.wet.pod, true, pct, s => share(s.wet.hits, s.wet.hits + s.wet.misses)],
    ['Wet-day false alarms', s => s.wet.far, false, pct, s => share(s.wet.false_alarms, s.wet.hits + s.wet.false_alarms)],
  ]
  return <div className="overflow-x-auto"><table className="w-full text-sm tabular">
    <thead><tr className="text-left text-muted"><th scope="col" className="py-2 pr-4 font-medium">On the same {v.place_days} place-days</th>
      <th scope="col" className="py-2 pr-4 font-medium">Map (model where it ran)</th><th scope="col" className="py-2 font-medium">Rule alone</th></tr></thead>
    <tbody>{rows.map(([label, get, higher, format, count]) => {
      const a = get(v.shown), b = get(v.rule)
      const better = a !== null && b !== null && a !== b ? ((a > b) === higher ? 'map' : 'rule') : null
      return <tr key={label} className="border-t border-border">
        <th scope="row" className="py-2 pr-4 text-left font-normal">{label}</th>
        {[['map', v.shown, a], ['rule', v.rule, b]].map(([who, s, value]) => <td key={who} className={`py-2 pr-4 ${better === who ? 'font-semibold' : ''}`}>
          {format(value)}{count && value !== null && <span className="text-xs text-muted ml-1.5">{count(s)}</span>}{better === who && <span className="sr-only"> (better)</span>}</td>)}
      </tr>
    })}</tbody></table></div>
}

// Rows: what the map said. Columns: what fell. The diagonal is "right".
function Confusion({ v }) {
  const max = Math.max(1, ...v.shown.confusion.flat())
  return <div className="overflow-x-auto"><table className="text-xs tabular border-separate" style={{ borderSpacing: 3 }}>
    <caption className="sr-only">Map category against the category of the rain that fell, in place-days</caption>
    <thead><tr><td />{v.classes.map(c => <th key={c} scope="col" className="font-medium text-muted px-1 pb-1">{c}</th>)}</tr></thead>
    <tbody>{v.classes.map((said, i) => <tr key={said}>
      <th scope="row" className="font-medium text-muted pr-2 text-right whitespace-nowrap">{said}</th>
      {v.shown.confusion[i].map((n, j) => <td key={j} className="w-14 h-9 text-center rounded-[6px]"
        style={{ background: n ? `color-mix(in srgb, ${i === j ? 'var(--chart-1)' : 'var(--chart-2)'} ${Math.round(14 + n / max * 70)}%, var(--surface))` : 'var(--surface-2)', color: n / max > 0.6 ? '#fff' : 'var(--text)' }}>
        {n || ''}</td>)}
    </tr>)}</tbody>
  </table>
  <p className="text-xs text-muted mt-2">Rows: what the map said. Columns: what fell. Teal is right, indigo is wrong.</p></div>
}

// The live categories scored against the rain that fell, day by day. Grows by itself.
export default function LiveTrackRecord({ detailed = false }) {
  const narrow = useNarrow()
  const state = useStaffList('/staff/model-verification')
  const [v, invalid] = useMemo(() => {
    if (!state.data) return [null, '']
    try { return [parseVerification(state.data), ''] } catch (error) { return [null, error.message] }
  }, [state.data])
  if (!v) return <div className="panel p-5 text-sm">
    {state.loading ? <p role="status" className="text-muted">Checking past forecasts against the rain that fell…</p>
      : <p role="alert">{state.error || invalid || 'Live track record unavailable.'}</p>}</div>
  const checked = v.daily.filter(d => d.status === 'VERIFIED')
  const s = v.shown
  return <div className="space-y-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <p className="text-base max-w-2xl">{trackRecordHeadline(v)}</p>
      <button className={buttonClass} onClick={state.refresh} disabled={state.loading}><RefreshCw size={15} />Refresh</button>
    </div>
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <Tile label="Days checked" value={v.days_verified} detail={`${v.place_days} place-days · ${v.cell_days} satellite cell-days${v.days_waiting ? ` · ${v.days_waiting} waiting` : ''}`} />
      <Tile label="Right category" value={pct(s.exact)} detail={s.within_one === null ? 'No days yet' : `${pct(s.within_one)} within one step`} />
      <Tile label="Heavy rain caught" value={s.hits + s.misses ? share(s.hits, s.hits + s.misses) : 'None yet'}
        detail={s.hits + s.misses ? `False alarms: ${s.false_alarms}` : 'No heavy rain has fallen yet'} />
      <Tile label="Rain amount off by" value={v.amounts.mae_mm === null ? '—' : `${v.amounts.mae_mm} mm`}
        detail={v.amounts.bias_mm === null ? 'Average per place-day' : `Forecasts ran ${Math.abs(v.amounts.bias_mm)} mm ${v.amounts.bias_mm >= 0 ? 'high' : 'low'} on average`} />
    </div>

    {checked.length > 0 && <section className="panel p-5 sm:p-6 space-y-4" aria-labelledby="days-heading">
      <div className="flex flex-wrap justify-between gap-3 items-end">
        <div><h3 id="days-heading" className="font-semibold">Forecast against what fell</h3><p className="text-sm text-muted mt-1">Average over the monitored places, each checked day.</p></div>
        <ChartLegend items={[FORECAST, FELL]} />
      </div>
      <div className="h-56" role="img" aria-label="Forecast rainfall against the satellite rainfall that fell, by day">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={checked} barGap={2} margin={{ left: -12, right: 4 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="date" {...axisProps} tickFormatter={shortDate} interval="preserveStartEnd" minTickGap={narrow ? 14 : 8} />
            <YAxis {...axisProps} />
            <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip unit=" mm" format={x => x.toFixed(1)} labelFormat={shortDate} />} />
            <Bar isAnimationActive={false} dataKey="forecast_mm" name={FORECAST.label} fill={FORECAST.color} radius={[3, 3, 0, 0]} maxBarSize={14} />
            <Bar isAnimationActive={false} dataKey="observed_mm" name={FELL.label} fill={FELL.color} radius={[3, 3, 0, 0]} maxBarSize={14} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>}

    {v.place_days > 0 && <div className={`grid gap-4 ${detailed ? 'lg:grid-cols-5' : ''}`}>
      <section className={`panel p-5 sm:p-6 space-y-3 ${detailed ? 'lg:col-span-3' : ''}`} aria-labelledby="compare-heading">
        <h3 id="compare-heading" className="font-semibold">Is the model still earning its place?</h3>
        <p className="text-sm text-muted">The map uses the model where its inputs are complete. If the rule alone keeps doing better, the model should be retrained or switched off.</p>
        <Comparison v={v} />
      </section>
      {detailed && <section className="panel p-5 sm:p-6 space-y-3 lg:col-span-2" aria-labelledby="confusion-heading">
        <h3 id="confusion-heading" className="font-semibold">Where it goes wrong</h3>
        <Confusion v={v} />
      </section>}
    </div>}

    <details className="text-sm text-muted"><summary className="cursor-pointer text-accent font-medium">How this is checked</summary>
      <div className="mt-2 space-y-2">
        <p>{v.method}</p>
        <ul className="list-disc pl-5 space-y-1">{v.limitations.map(l => <li key={l}>{l}</li>)}</ul>
        <ul className="text-xs space-y-0.5 pt-1">{[...v.daily].reverse().map(d => <li key={d.date} className="tabular">{shortDate(d.date)}: {STATUS[d.status] ?? d.status}{d.places ? ` · ${d.places} places · ${d.exact} right` : ''}</li>)}</ul>
        {v.model_versions.length > 0 && <p className="text-xs">Model version{v.model_versions.length > 1 ? 's' : ''}: <span className="font-mono">{v.model_versions.join(', ')}</span></p>}
      </div>
    </details>
  </div>
}
