import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import RiskBadge from '../components/RiskBadge'
import PredictionStatus from '../components/PredictionStatus'
import TopNav from '../components/TopNav'
import { RISK_ORDER, riskColor } from '../constants/colors'
import { formatConfidence, formatPredictionTime, isPredictionStale } from '../services/predictions'

// Officer dashboard — county-wide summary, zone risk table, and recent alerts
export default function OfficerDashboardPage({ predictions, alerts, setAlerts, showToast }) {
  const { data } = predictions
  const zones = data?.zones ?? []
  const activeAlerts = data?.activeAlerts ?? 0

  const sortedZones = useMemo(
    () => [...zones].sort((a, b) => RISK_ORDER.indexOf(b.risk) - RISK_ORDER.indexOf(a.risk)),
    [zones]
  )
  const highestRiskZone = sortedZones.find((zone) => zone.timestamp)
  const recentAlerts = [...alerts].slice(-3).reverse()

  function acknowledge(id) {
    setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, acknowledged: true, acknowledgedBy: 'Jane Mwangi' } : a)))
    showToast('Alert acknowledged', 'success')
  }

  return (
    <div className="min-h-screen flex flex-col page-transition">
      <TopNav variant="app" active="Dashboard" unacknowledgedCount={activeAlerts} />

      {activeAlerts > 0 && (
        <div className="bg-red-600 text-white text-sm font-medium text-center py-2.5 px-4 sticky top-16 z-[1050]">
          {activeAlerts} unacknowledged alert{activeAlerts > 1 ? 's' : ''}.
        </div>
      )}

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-content mx-auto px-6 py-10 space-y-10">
          <PredictionStatus predictions={predictions} />
          {/* Summary cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <SummaryCard label="Zones Monitored" value={data ? zones.length : '—'} color="var(--brand)" />
            <SummaryCard label="Active Alerts" value={data?.activeAlerts ?? '—'} color="var(--risk-extreme)" />
            <SummaryCard label="Highest Risk" value={highestRiskZone?.risk.toUpperCase() ?? 'UNAVAILABLE'} color={riskColor(highestRiskZone?.risk)} />
            <SummaryCard label="Last Updated" value={formatPredictionTime(data?.lastUpdated)} color="var(--text-muted)" />
          </div>

          {/* Zone risk overview */}
          <section className="space-y-4">
            <div className="flex items-baseline justify-between">
              <h2 className="text-2xl font-semibold tracking-tight text-ink">Zone Risk Overview</h2>
              <span className="text-sm text-muted">Nairobi County</span>
            </div>
            <div className="bg-surface border border-border rounded-card overflow-x-auto shadow-card-rest">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted border-b border-border">
                    {['Zone', 'Sub-County', 'Risk', '24h Rainfall', 'Model score', 'Status'].map((h) => (
                      <th key={h} className="px-4 py-3 text-xs font-semibold uppercase tracking-wide">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedZones.map((zone) => {
                    const severe = zone.risk === 'Extreme' || zone.risk === 'High'
                    return (
                      <tr
                        key={zone.id}
                        className={`border-b border-border last:border-0 hover:bg-bg transition-colors ${
                          severe ? 'border-l-4' : ''
                        }`}
                        style={severe ? { borderLeftColor: riskColor(zone.risk) } : undefined}
                      >
                        <td className="px-4 py-3 font-semibold text-ink">{zone.name}</td>
                        <td className="px-4 py-3 text-muted">{zone.subCounty}</td>
                        <td className="px-4 py-3">
                          <RiskBadge risk={zone.risk} size="sm" />
                        </td>
                        <td className="px-4 py-3 text-muted">
                          Unavailable
                        </td>
                        <td className="px-4 py-3 w-36">
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-ink">{formatConfidence(zone.confidence)}</span>
                            {zone.confidence !== null && (
                              <div className="flex-1 h-1.5 rounded-full bg-border overflow-hidden">
                                <div
                                  className="h-full rounded-full"
                                  style={{ width: `${zone.confidence * 100}%`, backgroundColor: 'var(--brand)' }}
                                />
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-muted text-xs">
                          {zone.timestamp ? (isPredictionStale(zone.timestamp) ? 'Older than expected' : 'Available') : 'Awaiting prediction'}
                          <p>{formatPredictionTime(zone.timestamp)}</p>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>

          {/* Recent alerts */}
          <section className="space-y-4">
            <div className="flex items-baseline justify-between">
              <h2 className="text-2xl font-semibold tracking-tight text-ink">Recent Alerts (Demo)</h2>
              <Link to="/officer/alerts" className="text-sm font-medium text-brand hover:underline">
                View all
              </Link>
            </div>
            <p className="text-sm text-muted">These sample alerts and acknowledgement actions use demo data.</p>
            <div className="space-y-3">
              {recentAlerts.map((alert) => (
                <div
                  key={alert.id}
                  className="bg-surface border border-border rounded-card p-4 flex items-center gap-4 card-hover shadow-card-rest"
                >
                  <span className="font-semibold text-ink">{alert.zone}</span>
                  <RiskBadge risk={alert.risk} size="sm" />
                  <span className="text-xs text-muted">{alert.timestamp}</span>
                  <span className="ml-auto">
                    {alert.acknowledged ? (
                      <span className="text-xs font-medium text-muted">Acknowledged by {alert.acknowledgedBy}</span>
                    ) : (
                      <button
                        onClick={() => acknowledge(alert.id)}
                        className="text-xs font-semibold text-white rounded-btn px-3 py-1.5"
                        style={{ backgroundColor: riskColor(alert.risk) }}
                      >
                        Acknowledge
                      </button>
                    )}
                  </span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  )
}

function SummaryCard({ label, value, color }) {
  return (
    <div className="bg-surface border border-border rounded-card p-6 card-hover shadow-card-rest">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
      <p className="text-xl sm:text-2xl font-bold mt-1 break-words" style={{ color }}>
        {value}
      </p>
    </div>
  )
}
