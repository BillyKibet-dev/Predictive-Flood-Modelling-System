import { memo } from 'react'
import { RISK_ACTION_MESSAGES, riskColor } from '../constants/colors'
import { formatPredictionTime } from '../services/predictions'
import { formatZoneScore, isZonePredictionStale, PROXY_TASK } from '../services/proxyPredictions'
import ProxyForecastDetails from './ProxyForecastDetails'
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
        <p className="text-sm font-medium" style={{ color }}>
          {zone.modelTaskType === PROXY_TASK
            ? (zone.mode === 'historical_replay' ? 'Historical proxy-label research. Not a current warning.' : 'Operational v1 indications are unavailable.')
            : RISK_ACTION_MESSAGES[zone.risk]}
        </p>

        <p className="text-xs text-muted">Updated: {formatPredictionTime(zone.timestamp)}</p>
        {isZonePredictionStale(zone) && <p className="text-xs text-risk-mod">Prediction is older than expected.</p>}
        <details className="text-xs text-muted"><summary className="cursor-pointer">About this advisory</summary><p className="mt-2">This is a weather-based indication. Local drainage and exact flood locations are not assessed. Model scores are not flood probabilities.</p><p>Model class score: {formatZoneScore(zone)}</p><ProxyForecastDetails zone={zone} /></details>
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
