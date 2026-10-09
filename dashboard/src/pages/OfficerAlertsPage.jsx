import { BellOff } from 'lucide-react'
import { useMemo, useState } from 'react'
import RiskBadge from '../components/RiskBadge'
import TopNav from '../components/TopNav'
import { RISK_ORDER, riskColor } from '../constants/colors'

// Officer alert management — filter, acknowledge, and (mock) export flood alerts
export default function OfficerAlertsPage({ alerts, setAlerts, showToast }) {
  const [zoneFilter, setZoneFilter] = useState('All')
  const [riskFilter, setRiskFilter] = useState('All')
  const [dateFilter, setDateFilter] = useState('')

  const unacknowledged = alerts.filter((a) => !a.acknowledged)
  const zoneOptions = ['All', ...new Set(alerts.map((a) => a.zone))]

  const filtered = useMemo(
    () =>
      alerts.filter((a) => {
        if (zoneFilter !== 'All' && a.zone !== zoneFilter) return false
        if (riskFilter !== 'All' && a.risk !== riskFilter) return false
        return true
      }),
    [alerts, zoneFilter, riskFilter]
  )

  function clearFilters() {
    setZoneFilter('All')
    setRiskFilter('All')
    setDateFilter('')
  }

  function acknowledge(alert) {
    setAlerts((prev) =>
      prev.map((a) => (a.id === alert.id ? { ...a, acknowledged: true, acknowledgedBy: 'Jane Mwangi' } : a))
    )
    showToast(`✓ Alert acknowledged — ${alert.zone} Zone`, 'success')
  }

  function exportCsv() {
    showToast('Alerts exported to CSV', 'info')
  }

  return (
    <div className="min-h-screen flex flex-col page-transition">
      <TopNav variant="app" active="Alerts" unacknowledgedCount={unacknowledged.length} />

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-content mx-auto px-6 py-10 space-y-6">
          <div className="flex items-center justify-between">
            <h1 className="text-4xl font-bold tracking-tight text-ink">Alert Management</h1>
            <button
              onClick={exportCsv}
              className="text-sm font-medium border border-border rounded-btn px-4 h-11 hover:bg-bg transition-colors"
            >
              ⬇ Export CSV
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <SummaryCard label="Total" value={alerts.length} />
            <SummaryCard label="Unacknowledged" value={unacknowledged.length} highlight />
            <SummaryCard label="Acknowledged" value={alerts.length - unacknowledged.length} />
          </div>

          <div className="bg-surface border border-border rounded-card p-4 flex flex-wrap items-center gap-4">
            <select
              value={zoneFilter}
              onChange={(e) => setZoneFilter(e.target.value)}
              className="h-10 border border-border rounded-btn px-3 text-sm bg-surface text-ink"
              aria-label="Filter by zone"
            >
              {zoneOptions.map((z) => (
                <option key={z} value={z}>
                  {z}
                </option>
              ))}
            </select>
            <select
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value)}
              className="h-10 border border-border rounded-btn px-3 text-sm bg-surface text-ink"
              aria-label="Filter by risk"
            >
              <option value="All">All risk levels</option>
              {RISK_ORDER.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <input
              type="date"
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value)}
              className="h-10 border border-border rounded-btn px-3 text-sm bg-surface text-ink"
              aria-label="Filter by date"
            />
            <button onClick={clearFilters} className="text-sm font-medium text-muted hover:text-ink ml-auto">
              Clear filters
            </button>
          </div>

          {filtered.length === 0 ? (
            <div className="text-center py-20 space-y-3">
              <BellOff size={40} className="mx-auto text-muted" />
              <h3 className="text-lg font-semibold text-ink">No alerts found</h3>
              <p className="text-muted text-sm">All alerts match your current filters.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {filtered.map((alert) => (
                <div
                  key={alert.id}
                  className="bg-surface border border-border rounded-card p-5 flex items-center gap-4 border-l-[6px] card-hover shadow-card-rest"
                  style={{ borderLeftColor: riskColor(alert.risk) }}
                >
                  <div className="flex-1 space-y-1">
                    <div className="flex items-center gap-3">
                      <h3 className="text-lg font-semibold text-ink">{alert.zone}</h3>
                      <RiskBadge risk={alert.risk} size="sm" />
                      <span className="text-xs text-muted">{alert.timestamp}</span>
                    </div>
                    <p className="text-sm text-muted">
                      {alert.subCounty} ·{' '}
                      {alert.acknowledged ? `Acknowledged by ${alert.acknowledgedBy}` : 'Unacknowledged'}
                    </p>
                  </div>
                  {alert.acknowledged ? (
                    <span className="min-h-[44px] flex items-center text-sm font-medium border border-border rounded-btn px-4 text-muted">
                      Acknowledged by {alert.acknowledgedBy}
                    </span>
                  ) : (
                    <button
                      onClick={() => acknowledge(alert)}
                      className="min-h-[44px] flex items-center text-sm font-semibold text-white rounded-btn px-4"
                      style={{ backgroundColor: riskColor(alert.risk) }}
                    >
                      Acknowledge ✓
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

function SummaryCard({ label, value, highlight }) {
  return (
    <div
      className={`bg-surface rounded-card p-6 border shadow-card-rest ${highlight ? 'border-risk-extreme' : 'border-border'}`}
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
      <p className={`text-4xl font-bold mt-1 ${highlight ? 'text-risk-extreme' : 'text-ink'}`}>{value}</p>
    </div>
  )
}
