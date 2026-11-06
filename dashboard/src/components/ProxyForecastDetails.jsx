import { formatPredictionTime } from '../services/predictions'
import { formatTargetDate, PROXY_TASK, readableReason, zoneStatusLabel } from '../services/proxyPredictions'

export default function ProxyForecastDetails({ zone }) {
  if (zone.modelTaskType !== PROXY_TASK) return null
  return (
    <div className="space-y-1 text-xs text-muted">
      <p className="font-medium">{zoneStatusLabel(zone)}</p>
      <p>Target day: {formatTargetDate(zone.forecastTargetDate)} · Next calendar day</p>
      <p>Input day: {formatTargetDate(zone.inputDate)} · {zone.mode === 'historical_replay' ? 'Simulated issue' : 'Issue'}: {formatPredictionTime(zone.issuedAt)}</p>
      <p>Model output: {formatPredictionTime(zone.executedAt)}</p>
      <p>Data as of: {formatPredictionTime(zone.dataAsOf)} · Freshness: {readableReason(zone.freshness)}</p>
      {zone.reasonCodes.length > 0 && <ul className="list-disc pl-4" aria-label="Unavailable prediction reasons">
        {zone.reasonCodes.map((reason) => <li key={reason}>{readableReason(reason)}</li>)}
      </ul>}
      {zone.limitationFlags.length > 0 && <details>
        <summary className="cursor-pointer">Source and model limitations</summary>
        <ul className="list-disc pl-4 mt-1">{zone.limitationFlags.map((flag) => <li key={flag}>{readableReason(flag)}</li>)}</ul>
      </details>}
      <p>Proxy class scores are not flood probabilities. No predicted inundation depth or extent.</p>
    </div>
  )
}
