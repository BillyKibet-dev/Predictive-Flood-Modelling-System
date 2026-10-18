import { memo } from 'react'
import { RISK_ACTION_MESSAGES, riskColor } from '../constants/colors'
import { formatConfidence, formatPredictionTime, isPredictionStale } from '../services/predictions'
import RiskBadge from './RiskBadge'

// Zone warning card for the citizen page grid — memoised to avoid re-renders on unrelated state changes
function ZoneCard({ zone, index = 0, onReport }) {
  const color = riskColor(zone.risk)
  return (
    <div
      id={`zone-${zone.id}`}
      className="stagger-item card-hover bg-surface border border-border rounded-card shadow-card-rest overflow-hidden scroll-mt-24"
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
          24h Rainfall: <span className="font-semibold">Unavailable</span>
        </p>
        <p className="text-sm font-medium" style={{ color }}>
          {RISK_ACTION_MESSAGES[zone.risk]}
        </p>
        <p className="text-xs text-muted">Confidence: {formatConfidence(zone.confidence)}</p>
        <p className="text-xs text-muted">Updated: {formatPredictionTime(zone.timestamp)}</p>
        {isPredictionStale(zone.timestamp) && <p className="text-xs text-risk-mod">Prediction is older than expected.</p>}
        {onReport && (
          <button
            type="button"
            onClick={() => onReport(zone.id)}
            aria-label={`Report conditions in ${zone.name}`}
            className="w-full border border-border rounded-btn py-2 text-sm font-medium text-ink hover:bg-bg"
          >
            Report conditions
          </button>
        )}
      </div>
    </div>
  )
}

export default memo(ZoneCard)
