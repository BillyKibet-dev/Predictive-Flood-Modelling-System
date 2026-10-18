import { formatPredictionTime, isPredictionStale } from '../services/predictions'

export default function PredictionStatus({ predictions }) {
  const { data, error, isRefreshing, refresh } = predictions
  const missing = data?.zones.filter((zone) => !zone.timestamp).length ?? 0
  const stale = data?.zones.some((zone) => isPredictionStale(zone.timestamp)) ?? false
  let message = `Predictions updated: ${formatPredictionTime(data?.lastUpdated)}`

  if (!data) message = error ? 'Predictions are unavailable. Please retry.' : 'Loading flood predictions...'
  else if (error) message = 'Could not refresh predictions. Showing the last available data.'
  else if (data.zones.length === 0) message = 'No zones are available yet.'
  else if (!data.lastUpdated) message = 'No predictions are available yet.'
  else if (stale) message = `Some predictions are older than expected. Latest: ${formatPredictionTime(data.lastUpdated)}`
  else if (missing) message += ` · ${missing} ${missing === 1 ? 'zone is' : 'zones are'} awaiting predictions.`

  const warning = Boolean(error || stale || missing || (data && !data.zones.length))
  return (
    <div className="bg-surface border border-border rounded-card px-4 py-3 flex flex-wrap items-center justify-between gap-3 text-sm shadow-card-rest">
      <p role="status" className={warning ? 'text-risk-mod' : 'text-muted'}>{message}</p>
      <button
        type="button"
        onClick={refresh}
        disabled={isRefreshing}
        className="shrink-0 border border-border rounded-btn px-3 py-1.5 font-medium text-ink hover:bg-bg disabled:opacity-50 disabled:cursor-wait"
      >
        {isRefreshing ? 'Refreshing...' : 'Refresh predictions'}
      </button>
    </div>
  )
}
