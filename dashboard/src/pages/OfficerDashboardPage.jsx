import { Link } from 'react-router-dom'
import TopNav from '../components/TopNav'
import RiskBadge from '../components/RiskBadge'
import useStaffList from '../hooks/useStaffList'
import { formatPredictionTime } from '../services/predictions'

export default function OfficerDashboardPage({ predictions }) {
  const { data, error, refresh, isRefreshing } = predictions
  const reports = useStaffList('/citizen-reports?review_status=New&limit=1')
  const zones = data?.zones ?? []
  return (
    <div className="min-h-screen bg-bg">
      <TopNav variant="app" active="Dashboard" />
      <main className="max-w-6xl mx-auto px-6 py-8 space-y-6 text-ink">
        <div className="flex flex-wrap justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Officer overview</h1>
            <p className="text-sm text-muted mt-1">
              Latest saved weather advisories and community reports support your assessment.
              Decisions remain with officers.
            </p>
          </div>
          <Link className="text-brand underline" to="/">
            Open risk map
          </Link>
        </div>
        {error && (
          <p role="alert">
            Could not refresh advisories.{' '}
            {data ? 'The last fetched records remain visible.' : 'No data is confirmed.'}
          </p>
        )}
        <div className="grid sm:grid-cols-3 gap-4">
          {[
            ['Study zones', data ? zones.length : 'Unavailable'],
            [
              'New citizen reports',
              reports.data?.total ?? (reports.error ? 'Unavailable' : 'Loading...'),
            ],
            ['Latest saved advisory', formatPredictionTime(data?.lastUpdated)],
          ].map(([label, value]) => (
            <div key={label} className="bg-surface border border-border rounded-card p-4">
              <p className="text-sm text-muted">{label}</p>
              <p className="font-semibold mt-2">{value}</p>
            </div>
          ))}
        </div>
        {reports.error && (
          <p role="alert">
            Report inbox could not be loaded.{' '}
            <Link className="underline" to="/officer/reports">
              Open inbox to retry
            </Link>
            .
          </p>
        )}
        <div className="flex gap-4 text-sm">
          <Link className="text-brand underline" to="/officer/reports">
            Review citizen reports
          </Link>
          <Link className="text-brand underline" to="/officer/alerts">
            Review saved advisories
          </Link>
          <Link className="text-brand underline" to="/environmental-data">
            Inspect rainfall history
          </Link>
        </div>
        <section className="space-y-3">
          <div className="flex justify-between">
            <h2 className="text-lg font-semibold">Saved zone indications</h2>
            <button
              onClick={refresh}
              disabled={isRefreshing}
              className="border border-border rounded-btn p-2 text-sm"
            >
              Refresh advisories
            </button>
          </div>
          <p className="text-sm text-muted">
            The older model shares Nairobi weather across study zones. Check the timestamps; these
            records do not resolve street drainage or predict inundation.
          </p>
          <div className="overflow-x-auto bg-surface rounded-card border border-border">
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  {['Study zone', 'Advisory class', 'Saved at'].map((label) => (
                    <th key={label} className="p-3">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {zones.map((zone) => (
                  <tr className="border-t border-border" key={zone.id}>
                    <td className="p-3">{zone.name}</td>
                    <td className="p-3">
                      <RiskBadge risk={zone.risk} size="sm" />
                    </td>
                    <td className="p-3">{formatPredictionTime(zone.timestamp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!zones.length && <p className="p-4">No zone advisories loaded.</p>}
          </div>
        </section>
      </main>
    </div>
  )
}
