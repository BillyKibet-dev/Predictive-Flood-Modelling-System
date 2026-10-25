import { useState } from 'react'
import { MessageSquarePlus } from 'lucide-react'
import { Link } from 'react-router-dom'
import BoundaryControls from '../components/BoundaryControls'
import MapView from '../components/MapView'
import PredictionStatus from '../components/PredictionStatus'
import TopNav from '../components/TopNav'
import { RISK_ORDER, riskColor } from '../constants/colors'
import { formatPredictionTime } from '../services/predictions'
import useBoundaries from '../hooks/useBoundaries'

// Universal flood risk map — the hero landing page for every user type, public and authenticated alike
export default function MapPage({ predictions }) {
  const boundaries = useBoundaries()
  const [showPolygons, setShowPolygons] = useState(true)
  const [showMarkers, setShowMarkers] = useState(true)
  const [fitRequest, setFitRequest] = useState(0)
  const { data } = predictions
  const zones = data?.zones ?? []
  const highestRiskZone = zones.filter((zone) => zone.timestamp).sort(
    (a, b) => RISK_ORDER.indexOf(b.risk) - RISK_ORDER.indexOf(a.risk)
  )[0]

  return (
    <div className="h-screen h-[100dvh] min-h-[600px] flex flex-col page-transition">
      <TopNav variant="public" />
      <div className="shrink-0 bg-surface border-b border-border px-4 py-2 space-y-2">
        <PredictionStatus predictions={predictions} />
        <BoundaryControls boundaries={boundaries} showPolygons={showPolygons} setShowPolygons={setShowPolygons}
          showMarkers={showMarkers} setShowMarkers={setShowMarkers} fitCounty={() => setFitRequest((value) => value + 1)} />
      </div>
      <div className="relative flex-1 min-h-0">
        <MapView zones={zones} boundaries={boundaries.data} boundaryRevision={boundaries.revision}
          showPolygons={showPolygons} showMarkers={showMarkers} fitRequest={fitRequest} />

        {/* Legend */}
        <details className="absolute top-4 right-4 z-[1000] bg-surface shadow-card-hover rounded-card p-3 text-xs">
          <summary className="font-semibold text-ink cursor-pointer">Risk legend</summary>
          <p className="text-muted mt-2 mb-2 max-w-44">Sub-county colour: highest monitored risk.</p>
          {[...RISK_ORDER, 'Unknown'].map((risk) => (
            <div key={risk} className="flex items-center gap-2 text-sm text-ink">
              <span className="w-3 h-3 rounded-full inline-block" style={{ backgroundColor: riskColor(risk) }} />
              {risk}
            </div>
          ))}
        </details>

        <Link to="/citizen#report"
          className="absolute z-[1000] bottom-14 right-4 bg-surface text-ink shadow-card-hover rounded-full px-4 h-11 flex items-center gap-2 text-sm font-semibold hover:scale-105 transition-transform">
          <MessageSquarePlus size={18} />Report Flood
        </Link>
      </div>

      {/* Stats bar sits below the map so attribution remains visible. */}
      <div className="shrink-0 min-h-20 sm:min-h-14 flex items-stretch text-white"
        style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)' }}>
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
            <span className="text-xs tracking-[0.08em] font-semibold"
              style={highestRiskZone?.risk === 'Extreme' ? { textShadow: '0 0 8px rgba(220,38,38,0.9)', color: '#FCA5A5' } : undefined}>
              HIGHEST RISK: {highestRiskZone ? `${highestRiskZone.risk.toUpperCase()} — ${highestRiskZone.name.toUpperCase()}` : 'UNAVAILABLE'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
