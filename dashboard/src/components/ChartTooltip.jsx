// One tooltip style for every chart: values in ink, a small swatch carries the series colour.
export default function ChartTooltip({ active, payload, label, unit = '', format = v => v }) {
  if (!active || !payload?.length) return null
  return <div className="panel shadow-card-hover px-3 py-2 text-xs space-y-1 min-w-36">
    <p className="font-semibold text-ink">{label}</p>
    {payload.filter(p => p.value != null).map(p => <p key={p.dataKey} className="flex items-center gap-2 text-muted">
      <span className="w-2.5 h-2.5 rounded-sm" style={{ background: p.color }} aria-hidden="true" />
      <span className="flex-1">{p.name}</span><span className="tabular font-medium text-ink">{format(p.value)}{unit}</span>
    </p>)}
  </div>
}

export function ChartLegend({ items }) {
  return <ul className="flex flex-wrap gap-4 text-xs text-muted" aria-label="Chart legend">
    {items.map(i => <li key={i.label} className="flex items-center gap-1.5">
      <span className="w-2.5 h-2.5 rounded-sm" style={{ background: i.color }} aria-hidden="true" />{i.label}</li>)}
  </ul>
}

export const axisProps = { tick: { fill: 'var(--text-muted)', fontSize: 12 }, axisLine: false, tickLine: false }
