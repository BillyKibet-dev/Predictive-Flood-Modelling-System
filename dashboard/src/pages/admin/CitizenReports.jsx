import { FileText } from 'lucide-react'
import { CITIZEN_REPORTS } from '../../data/mockData'

const SEVERITY_COLOR = {
  Mild: 'text-risk-low bg-risk-low-bg',
  Serious: 'text-risk-high bg-risk-high-bg',
  Dangerous: 'text-risk-extreme bg-risk-extreme-bg',
}

// Admin section — citizen-submitted flood condition reports
export default function CitizenReports() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-ink">Citizen Reports</h2>
        <p className="text-muted mt-1">Recent submissions from Nairobi County residents</p>
      </div>

      {CITIZEN_REPORTS.length === 0 ? (
        <div className="text-center py-20 space-y-3">
          <FileText size={40} className="mx-auto text-muted" />
          <h3 className="text-lg font-semibold text-ink">No reports yet</h3>
        </div>
      ) : (
        <div className="space-y-3">
          {CITIZEN_REPORTS.map((r) => (
            <div key={r.id} className="bg-surface border border-border rounded-card p-5 shadow-card-rest card-hover">
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <span className="text-xs font-semibold bg-brand/10 text-brand px-2 py-0.5 rounded-badge">{r.zone}</span>
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-badge ${SEVERITY_COLOR[r.severity]}`}>
                  {r.severity}
                </span>
                <span className="ml-auto text-xs text-muted">{r.timestamp}</span>
              </div>
              <p className="font-semibold text-ink">{r.condition}</p>
              <p className="text-sm text-muted italic mt-1">{r.description}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
