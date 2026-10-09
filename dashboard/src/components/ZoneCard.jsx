import { memo } from 'react'
import { RISK_ACTION_MESSAGES, riskColor } from '../constants/colors'
import RiskBadge from './RiskBadge'

// Zone warning card for the citizen page grid — memoised to avoid re-renders on unrelated state changes
function ZoneCard({ zone, index = 0 }) {
  const color = riskColor(zone.risk)
  return (
    <div
      id={`zone-${zone.id}`}
      className="stagger-item card-hover bg-surface border border-border rounded-card shadow-card-rest overflow-hidden"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      <div style={{ backgroundColor: color, height: 4 }} />
      <div className="p-6 space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="text-lg font-semibold text-ink">{zone.name}</h3>
            <p className="text-xs text-muted">{zone.subCounty}</p>
          </div>
          <RiskBadge risk={zone.risk} size="sm" />
        </div>
        <p className="text-sm text-ink">
          24h Rainfall: <span className="font-semibold">{zone.rainfall24h}mm</span>
        </p>
        <p className="text-sm font-medium" style={{ color }}>
          {RISK_ACTION_MESSAGES[zone.risk]}
        </p>
        <p className="text-xs text-muted">Confidence: {Math.round(zone.confidence * 100)}%</p>
      </div>
    </div>
  )
}

export default memo(ZoneCard)
