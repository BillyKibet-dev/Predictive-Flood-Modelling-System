import { MessageSquarePlus } from 'lucide-react'
import { Link } from 'react-router-dom'
import MapView from '../components/MapView'
import PredictionStatus from '../components/PredictionStatus'
import TopNav from '../components/TopNav'
import { RISK_ORDER, riskColor } from '../constants/colors'
import { formatPredictionTime } from '../services/predictions'

// Universal flood risk map — the hero landing page for every user type, public and authenticated alike
export default function MapPage({ predictions }) {
  const { data } = predictions
  const zones = data?.zones ?? []
  const highestRiskZone = zones.filter((zone) => zone.timestamp).sort(
    (a, b) => RISK_ORDER.indexOf(b.risk) - RISK_ORDER.indexOf(a.risk)
  )[0]

  return (
    <div className="h-screen flex flex-col page-transition">
      <TopNav variant="public" />

      <div className="relative flex-1">
        <MapView zones={zones} height="100%" />

        <div className="absolute top-4 left-16 right-4 z-[1000]">
          <PredictionStatus predictions={predictions} />
        </div>

        {/* Legend */}
        <div className="absolute bottom-24 sm:bottom-20 left-4 z-[1000] bg-surface shadow-card-hover rounded-card p-4 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Risk Levels</p>
          {[...RISK_ORDER, 'Unknown'].map((risk) => (
            <div key={risk} className="flex items-center gap-2 text-sm text-ink">
              <span className="w-3 h-3 rounded-full inline-block" style={{ backgroundColor: riskColor(risk) }} />
              {risk}
            </div>
          ))}
        </div>

        {/* Stats bar */}
        <div
          className="absolute bottom-0 left-0 right-0 z-[1000] h-20 sm:h-14 flex items-stretch text-white"
          style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)' }}
        >
          <div className="max-w-content w-full mx-auto grid grid-cols-2 sm:grid-cols-4 divide-x divide-white/20">
            <div className="flex flex-col items-center justify-center px-2">
              <span className="text-xs tracking-[0.08em] font-semibold">{data ? zones.length : '—'} ZONES MONITORED</span>
            </div>
            <div className="flex flex-col items-center justify-center px-2">
              <span className="text-xs text-center tracking-[0.08em] font-semibold">LAST UPDATED {formatPredictionTime(data?.lastUpdated)}</span>
            </div>
            <div className="flex flex-col items-center justify-center px-2">
              <span className="text-xs tracking-[0.08em] font-semibold">{data?.activeAlerts ?? '—'} ACTIVE ALERTS</span>
            </div>
            <div className="flex flex-col items-center justify-center px-2">
              <span
                className="text-xs tracking-[0.08em] font-semibold"
                style={
                  highestRiskZone?.risk === 'Extreme'
                    ? { textShadow: '0 0 8px rgba(220,38,38,0.9)', color: '#FCA5A5' }
                    : undefined
                }
              >
                HIGHEST RISK: {highestRiskZone ? `${highestRiskZone.risk.toUpperCase()} — ${highestRiskZone.name.toUpperCase()}` : 'UNAVAILABLE'}
              </span>
            </div>
          </div>
        </div>

        {/* Report Flood FAB */}
        <Link
          to="/citizen#report"
          className="absolute z-[1000] bottom-24 sm:bottom-20 right-4 bg-surface text-brand shadow-card-hover rounded-full px-5 h-11 flex items-center gap-2 text-sm font-semibold hover:scale-105 transition-transform"
        >
          <MessageSquarePlus size={18} />
          Report Flood
        </Link>
      </div>
    </div>
  )
}
