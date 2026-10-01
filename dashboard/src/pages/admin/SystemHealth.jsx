import { PIPELINE_LOG } from '../../data/mockData'

const STATUS_CARDS = [
  { label: 'API Server', status: 'Online', detail: 'AWS EC2' },
  { label: 'Database', status: 'Online', detail: 'AWS RDS' },
  { label: 'ML Model', status: 'Loaded', detail: 'v2 — XGBoost' },
]

// Admin section — system infrastructure health & recent pipeline run log
export default function SystemHealth() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-gray-800">System Health</h2>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {STATUS_CARDS.map((c) => (
          <div key={c.label} className="bg-white rounded-lg shadow p-4">
            <p className="text-sm font-semibold text-gray-700">{c.label}</p>
            <p className="text-green-600 font-bold mt-1">● {c.status}</p>
            <p className="text-xs text-gray-400 mt-1">{c.detail}</p>
          </div>
        ))}
        <div className="bg-white rounded-lg shadow p-4">
          <p className="text-sm font-semibold text-gray-700">Last Pipeline</p>
          <p className="text-yellow-600 font-bold mt-1">14:00 EAT</p>
          <p className="text-xs text-gray-400 mt-1">Next: 15:00 EAT</p>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b">
              <th className="px-4 py-3">Timestamp</th>
              <th className="px-4 py-3">Stage</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Duration</th>
            </tr>
          </thead>
          <tbody>
            {PIPELINE_LOG.map((row) => (
              <tr key={row.id} className="border-b">
                <td className="px-4 py-3 text-gray-600">{row.timestamp}</td>
                <td className="px-4 py-3 font-medium text-gray-800">{row.stage}</td>
                <td className="px-4 py-3 text-green-600 font-medium">✅ {row.status}</td>
                <td className="px-4 py-3 text-gray-600">{row.duration}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
