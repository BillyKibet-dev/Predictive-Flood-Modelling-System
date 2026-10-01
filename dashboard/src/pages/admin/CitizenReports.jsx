import { CITIZEN_REPORTS } from '../../data/mockData'

const SEVERITY_COLOR = {
  Mild: 'text-green-600 bg-green-100',
  Serious: 'text-orange-600 bg-orange-100',
  Dangerous: 'text-red-600 bg-red-100',
}

// Admin section — citizen-submitted flood condition reports
export default function CitizenReports() {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold text-gray-800">Citizen Reports</h2>
        <p className="text-sm text-gray-500">Total reports today: {CITIZEN_REPORTS.length}</p>
      </div>

      <div className="space-y-3">
        {CITIZEN_REPORTS.map((r) => (
          <div key={r.id} className="bg-white rounded-lg shadow p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
              <span className="bg-brand-accent text-white text-xs font-semibold px-2 py-1 rounded-full">
                {r.zone}
              </span>
              <span className={`text-xs font-semibold px-2 py-1 rounded-full ${SEVERITY_COLOR[r.severity]}`}>
                {r.severity}
              </span>
            </div>
            <p className="font-semibold text-gray-800">{r.condition}</p>
            <p className="text-sm text-gray-600 mt-1">{r.description}</p>
            <p className="text-xs text-gray-400 mt-2">{r.timestamp}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
