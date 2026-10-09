import { PIPELINE_LOG } from '../../data/mockData'

const STATUS_CARDS = [
  { label: 'API Server', status: 'Online', detail: 'FastAPI — AWS EC2' },
  { label: 'Database', status: 'Online', detail: 'PostgreSQL — AWS RDS' },
  { label: 'ML Model', status: 'Loaded', detail: 'XGBoost v2 Final' },
]

// Admin section — infrastructure health and recent prediction pipeline run log
export default function SystemHealth() {
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-semibold tracking-tight text-ink">System Health</h2>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {STATUS_CARDS.map((c) => (
          <div key={c.label} className="bg-surface border border-border rounded-card p-6 shadow-card-rest">
            <p className="text-sm font-semibold text-ink">{c.label}</p>
            <p className="text-risk-low font-bold mt-1">● {c.status}</p>
            <p className="text-xs text-muted mt-1">{c.detail}</p>
          </div>
        ))}
        <div className="bg-surface border border-border rounded-card p-6 shadow-card-rest">
          <p className="text-sm font-semibold text-ink">Pipeline</p>
          <p className="text-risk-mod font-bold mt-1">Last: 14:00 EAT</p>
          <p className="text-xs text-muted mt-1">Next: 15:00 EAT</p>
        </div>
      </div>

      <div className="bg-surface border border-border rounded-card overflow-x-auto shadow-card-rest">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted border-b border-border">
              <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide">Timestamp</th>
              <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide">Stage</th>
              <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide">Status</th>
              <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide">Duration</th>
            </tr>
          </thead>
          <tbody>
            {PIPELINE_LOG.map((row) => (
              <tr key={row.id} className="border-b border-border last:border-0">
                <td className="px-4 py-3 text-muted">{row.timestamp}</td>
                <td className="px-4 py-3 font-medium text-ink">{row.stage}</td>
                <td className="px-4 py-3 text-risk-low font-medium">✅ {row.status}</td>
                <td className="px-4 py-3 text-muted">{row.duration}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
