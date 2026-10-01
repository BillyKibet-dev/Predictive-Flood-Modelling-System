import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AuthNavbar from '../components/Navbar'
import RiskBadge from '../components/RiskBadge'
import { RISK_ORDER, riskColor } from '../constants/colors'

// Alert management page — filter, sort, acknowledge and (mock) export flood alerts
export default function AlertsPage({ user, alerts, setAlerts, onLogout, showToast }) {
  const navigate = useNavigate()
  const [zoneFilter, setZoneFilter] = useState('All')
  const [riskFilter, setRiskFilter] = useState('All')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [sortKey, setSortKey] = useState(null)
  const [sortDir, setSortDir] = useState('asc')

  function handleSignOut() {
    onLogout()
    navigate('/public')
  }

  const zoneOptions = ['All', ...new Set(alerts.map((a) => a.zone))]

  const filtered = useMemo(() => {
    let list = alerts.filter((a) => {
      if (zoneFilter !== 'All' && a.zone !== zoneFilter) return false
      if (riskFilter !== 'All' && a.risk !== riskFilter) return false
      return true
    })
    if (sortKey) {
      list = [...list].sort((a, b) => {
        let av = a[sortKey]
        let bv = b[sortKey]
        if (sortKey === 'risk') {
          av = RISK_ORDER.indexOf(av)
          bv = RISK_ORDER.indexOf(bv)
        }
        if (av < bv) return sortDir === 'asc' ? -1 : 1
        if (av > bv) return sortDir === 'asc' ? 1 : -1
        return 0
      })
    }
    return list
  }, [alerts, zoneFilter, riskFilter, sortKey, sortDir])

  function toggleSort(key) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  function acknowledgeAlert(id) {
    setAlerts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, acknowledged: true, acknowledgedBy: user.name } : a))
    )
    showToast('Alert acknowledged', 'success')
  }

  function exportCsv() {
    showToast('Alerts exported to CSV', 'info')
  }

  const total = alerts.length
  const unacknowledgedCount = alerts.filter((a) => !a.acknowledged).length
  const acknowledgedCount = total - unacknowledgedCount

  return (
    <div className="min-h-screen flex flex-col bg-gray-100">
      <AuthNavbar user={user} active="alerts" onSignOut={handleSignOut} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6 space-y-6">
        <h1 className="text-2xl font-bold text-gray-800">Alert Management</h1>

        {/* Summary cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-white rounded-lg shadow p-4 text-center">
            <p className="text-xs text-gray-500 font-semibold">TOTAL</p>
            <p className="text-2xl font-bold text-gray-800">{total}</p>
          </div>
          <div className="bg-white rounded-lg shadow p-4 text-center">
            <p className="text-xs text-gray-500 font-semibold">UNACKNOWLEDGED</p>
            <p className="text-2xl font-bold text-red-500">{unacknowledgedCount}</p>
          </div>
          <div className="bg-white rounded-lg shadow p-4 text-center">
            <p className="text-xs text-gray-500 font-semibold">ACKNOWLEDGED</p>
            <p className="text-2xl font-bold text-green-600">{acknowledgedCount}</p>
          </div>
        </div>

        {/* Filter bar */}
        <div className="bg-white rounded-lg shadow p-4 flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Zone</label>
            <select
              value={zoneFilter}
              onChange={(e) => setZoneFilter(e.target.value)}
              className="border rounded-lg px-3 py-1.5 text-sm"
            >
              {zoneOptions.map((z) => (
                <option key={z} value={z}>
                  {z}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Risk</label>
            <select
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value)}
              className="border rounded-lg px-3 py-1.5 text-sm"
            >
              <option value="All">All</option>
              {RISK_ORDER.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">From</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="border rounded-lg px-3 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">To</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="border rounded-lg px-3 py-1.5 text-sm"
            />
          </div>
          <button
            onClick={exportCsv}
            className="ml-auto bg-brand-accent hover:bg-brand text-white text-sm font-medium px-4 py-2 rounded-lg"
          >
            Export CSV
          </button>
        </div>

        {/* Table */}
        <div className="bg-white rounded-lg shadow overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="px-4 py-3 cursor-pointer select-none" onClick={() => toggleSort('zone')}>
                  Zone
                </th>
                <th className="px-4 py-3 cursor-pointer select-none" onClick={() => toggleSort('risk')}>
                  Risk Level
                </th>
                <th className="px-4 py-3 cursor-pointer select-none" onClick={() => toggleSort('timestamp')}>
                  Timestamp
                </th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((alert) => {
                const isSevere = alert.risk === 'Extreme' || alert.risk === 'High'
                const rowBg = alert.acknowledged
                  ? 'bg-gray-50'
                  : alert.risk === 'Extreme'
                  ? 'bg-red-50'
                  : alert.risk === 'High'
                  ? 'bg-orange-50'
                  : ''
                const borderColor = alert.acknowledged ? '#9ca3af' : riskColor(alert.risk)
                return (
                  <tr
                    key={alert.id}
                    className={`border-b border-l-4 ${rowBg} ${alert.acknowledged ? 'text-gray-400' : 'text-gray-800'}`}
                    style={{ borderLeftColor: borderColor }}
                  >
                    <td className="px-4 py-3 font-medium">{alert.zone}</td>
                    <td className="px-4 py-3">
                      <RiskBadge risk={alert.risk} size="sm" />
                    </td>
                    <td className="px-4 py-3">{alert.timestamp}</td>
                    <td className="px-4 py-3">
                      {alert.acknowledged ? `Acknowledged by ${alert.acknowledgedBy}` : 'Unacknowledged'}
                    </td>
                    <td className="px-4 py-3">
                      {alert.acknowledged ? (
                        <button
                          onClick={() => showToast(`Viewing details for ${alert.zone}`, 'info')}
                          className="bg-gray-200 hover:bg-gray-300 text-gray-700 text-xs font-medium px-3 py-1.5 rounded"
                        >
                          View Details
                        </button>
                      ) : (
                        <button
                          onClick={() => acknowledgeAlert(alert.id)}
                          className="text-white text-xs font-medium px-3 py-1.5 rounded"
                          style={{ backgroundColor: riskColor(alert.risk) }}
                        >
                          Acknowledge ✓
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <p className="text-sm text-gray-500">
          Showing 1–{filtered.length} of {total} alerts
        </p>
      </main>
    </div>
  )
}
