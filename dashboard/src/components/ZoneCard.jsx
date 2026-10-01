import { ArrowUp } from 'lucide-react'
import { RISK_ACTION_MESSAGES, riskColor } from '../constants/colors'
import RiskBadge from './RiskBadge'

// Reusable zone card — supports the public "warning" layout and the
// dashboard "status panel" layout via the `variant` prop.
export default function ZoneCard({ zone, variant = 'public' }) {
  const color = riskColor(zone.risk)

  if (variant === 'dashboard') {
    return (
      <div
        className="bg-white rounded-lg shadow p-4 border-t-4"
        style={{ borderTopColor: color }}
      >
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-bold text-gray-800">{zone.name}</h4>
          <RiskBadge risk={zone.risk} size="sm" />
        </div>
        <div className="text-sm text-gray-600 space-y-1">
          <p className="flex items-center gap-1">
            Water level: <span className="font-semibold text-gray-800">{zone.waterLevel.toFixed(1)}m</span>
            {zone.waterLevel > 1.5 && <ArrowUp size={14} className="text-red-500" />}
          </p>
          <p>
            6h Rainfall: <span className="font-semibold text-gray-800">{zone.rainfall6h}mm</span>
          </p>
          <p>
            Confidence: <span className="font-semibold text-gray-800">{Math.round(zone.confidence * 100)}%</span>
          </p>
          <p className="text-xs text-gray-400">Last updated: {zone.lastUpdated}</p>
        </div>
      </div>
    )
  }

  // Public "current warnings" variant
  return (
    <div className="bg-white rounded-lg shadow p-4 border-l-4" style={{ borderLeftColor: color }}>
      <div className="flex items-center justify-between mb-2">
        <h4 className="font-bold text-gray-800 text-lg">{zone.name}</h4>
        <RiskBadge risk={zone.risk} />
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm text-gray-600 mb-2">
        <p>
          Water level: <span className="font-semibold text-gray-800">{zone.waterLevel.toFixed(1)}m</span>
        </p>
        <p>
          6h Rainfall: <span className="font-semibold text-gray-800">{zone.rainfall6h}mm</span>
        </p>
        <p>
          Confidence: <span className="font-semibold text-gray-800">{Math.round(zone.confidence * 100)}%</span>
        </p>
        <p className="text-gray-400">Updated: {zone.lastUpdated}</p>
      </div>
      <p className="text-sm font-medium" style={{ color }}>
        {RISK_ACTION_MESSAGES[zone.risk]}
      </p>
    </div>
  )
}
