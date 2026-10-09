import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { riskColor } from '../../constants/colors'
import { MODEL_METRICS, PER_CLASS_RECALL } from '../../data/mockData'

// Admin section — XGBoost test-set performance metrics and per-class recall chart
export default function ModelPerformance() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-ink">Model Performance</h2>
        <p className="text-muted mt-1">XGBoost Classifier — Test Set 2024–2026</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {MODEL_METRICS.map((m) => (
          <div key={m.label} className="bg-surface border border-border rounded-card p-5 shadow-card-rest">
            <p className="text-3xl font-bold" style={{ color: m.ok ? 'var(--risk-low)' : 'var(--risk-mod)' }}>
              {m.value.toFixed(4)}
            </p>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted mt-1">{m.label}</p>
            <span
              className={`inline-block mt-2 text-xs font-semibold px-2 py-0.5 rounded-badge ${
                m.ok ? 'bg-risk-low-bg text-risk-low' : 'bg-risk-mod-bg text-risk-mod'
              }`}
            >
              {m.ok ? '✅ Met' : '⚠ Below target'}
            </span>
          </div>
        ))}
      </div>

      <div className="bg-surface border border-border rounded-card p-6 shadow-card-rest">
        <h3 className="font-semibold text-ink mb-4">Per-Class Recall — Test Set</h3>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={PER_CLASS_RECALL}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis domain={[0, 1]} tick={{ fill: 'var(--text-muted)', fontSize: 12 }} axisLine={false} tickLine={false} />
            <Tooltip formatter={(v) => v.toFixed(4)} />
            <ReferenceLine y={0.7} stroke="var(--risk-extreme)" strokeDasharray="4 4" label={{ value: 'Target', position: 'right', fill: 'var(--risk-extreme)', fontSize: 12 }} />
            <Bar dataKey="recall" radius={[4, 4, 0, 0]}>
              {PER_CLASS_RECALL.map((entry) => (
                <Cell key={entry.name} fill={riskColor(entry.name)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="text-xs text-muted mt-4">
          ⚠ Moderate and High recall below target due to data scarcity. Will improve with TAHMO integration.
        </p>
      </div>
    </div>
  )
}
