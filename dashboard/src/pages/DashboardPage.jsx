import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import MapView from '../components/MapView'
import AuthNavbar from '../components/Navbar'
import ZoneCard from '../components/ZoneCard'
import { RISK_ORDER, riskColor } from '../constants/colors'

// Authorities dashboard — live flood risk map + zone status panel + footer stats
export default function DashboardPage({ user, zones, setZones, alerts, onLogout }) {
  const navigate = useNavigate()
  const [now, setNow] = useState(new Date())

  function handleSignOut() {
    onLogout()
    navigate('/public')
  }

  // Simulate a real-time feed: every 60s randomly rotate one zone's risk level
  useEffect(() => {
    const interval = setInterval(() => {
      setZones((prev) => {
        const idx = Math.floor(Math.random() * prev.length)
        const currentIdx = RISK_ORDER.indexOf(prev[idx].risk)
        let nextIdx = Math.floor(Math.random() * RISK_ORDER.length)
        while (nextIdx === currentIdx) {
          nextIdx = Math.floor(Math.random() * RISK_ORDER.length)
        }
        const timestamp =
          new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) + ' EAT'
        return prev.map((z, i) =>
          i === idx ? { ...z, risk: RISK_ORDER[nextIdx], riskClass: nextIdx, lastUpdated: timestamp } : z
        )
      })
      setNow(new Date())
    }, 60000)
    return () => clearInterval(interval)
  }, [setZones])

  const unacknowledged = alerts
    .filter((a) => !a.acknowledged)
    .sort((a, b) => RISK_ORDER.indexOf(b.risk) - RISK_ORDER.indexOf(a.risk))
  const topAlert = unacknowledged[0]

  const highestRiskZone = [...zones].sort(
    (a, b) => RISK_ORDER.indexOf(b.risk) - RISK_ORDER.indexOf(a.risk)
  )[0]

  return (
    <div className="min-h-screen flex flex-col bg-gray-100">
      <AuthNavbar user={user} active="dashboard" onSignOut={handleSignOut} />

      {topAlert && (
        <div className="bg-red-500 text-white text-center py-2.5 px-4 font-semibold text-sm">
          🔴 ACTIVE ALERT — {topAlert.zone} — {topAlert.risk.toUpperCase()} RISK — Click Alerts to acknowledge
        </div>
      )}

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-10 gap-6">
        {/* LEFT — Flood Risk Map (70%) */}
        <section className="lg:col-span-7">
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="text-lg font-bold text-gray-800 mb-3">Nairobi County — Flood Risk Map</h2>
            <MapView zones={zones} height={420} />
          </div>
        </section>

        {/* RIGHT — Zone Status Panel (30%) */}
        <section className="lg:col-span-3 space-y-3">
          <div className="flex items-baseline justify-between">
            <h2 className="text-lg font-bold text-gray-800">Zone Status</h2>
            <span className="text-xs text-gray-400">Auto-refresh 60s</span>
          </div>
          {zones.map((zone) => (
            <ZoneCard key={zone.id} zone={zone} variant="dashboard" />
          ))}
        </section>
      </main>

      {/* Footer stats bar */}
      <footer className="bg-gray-200 border-t">
        <div className="max-w-7xl mx-auto grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-gray-300">
          <div className="px-6 py-4 text-center">
            <p className="text-xs text-gray-500 font-semibold">LAST UPDATED</p>
            <p className="text-gray-800 font-medium">
              {now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })} EAT
            </p>
          </div>
          <div className="px-6 py-4 text-center">
            <p className="text-xs text-gray-500 font-semibold">ACTIVE SENSORS</p>
            <p className="text-gray-800 font-medium">3 / 3 Online</p>
          </div>
          <div className="px-6 py-4 text-center">
            <p className="text-xs text-gray-500 font-semibold">HIGHEST CURRENT RISK</p>
            <p className="font-medium" style={{ color: riskColor(highestRiskZone.risk) }}>
              {highestRiskZone.name} — {highestRiskZone.risk}
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}
