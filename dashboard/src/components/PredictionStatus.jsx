import { formatPredictionTime, isPredictionStale } from '../services/predictions'
import { formatTargetDate, readableReason } from '../services/proxyPredictions'
import PredictionViewControls from './PredictionViewControls'

export default function PredictionStatus({ predictions }) {
  const { data, error, isRefreshing, refresh } = predictions
  const proxyView = predictions.selection?.view !== undefined && predictions.selection.view !== 'legacy'
  const missing = data?.zones.filter((zone) => !zone.timestamp).length ?? 0
  const stale = data?.zones.some((zone) => isPredictionStale(zone.timestamp)) ?? false
  let message = `Predictions updated: ${formatPredictionTime(data?.lastUpdated)}`

  if (!data) message = error ? 'Predictions are unavailable. Please retry.' : 'Loading flood predictions...'
  else if (error) message = 'Could not refresh predictions. Showing the last available data.'
  else if (data.zones.length === 0) message = 'No zones are available yet.'
  else if (!data.lastUpdated) message = 'No predictions are available yet.'
  else if (stale) message = `Some predictions are older than expected. Latest: ${formatPredictionTime(data.lastUpdated)}`
  else if (missing) message += ` · ${missing} ${missing === 1 ? 'zone is' : 'zones are'} awaiting predictions.`

  if (proxyView) {
    if (!data) message = error ? 'v1 research data are unavailable. Please retry.' : 'Loading v1 research status...'
    else if (error) message = 'Could not refresh v1 data. Showing the last fetched research snapshot.'
    else if (data.mode === 'historical_replay') message = `Historical research replay · target ${formatTargetDate(data.forecastTargetDate)}. This is not a current warning.`
    else message = 'v1 next-day research · operational predictions are unavailable.'
  }
  const warning = Boolean(error || (!proxyView && stale) || missing || (data && !data.zones.length) || (proxyView && data?.status !== 'SUCCESS'))
  return (
    <div className="bg-surface border border-border rounded-card px-4 py-3 flex flex-col gap-3 text-sm shadow-card-rest">
      {predictions.selection && <PredictionViewControls selection={predictions.selection} />}
      <div className="flex flex-col sm:flex-row items-start justify-between gap-3">
      <div className="min-w-0 w-full sm:w-auto flex-1 space-y-1">
        <p role="status" className={warning ? 'text-risk-mod' : 'text-muted'}>{message}</p>
        {proxyView && data && <div className="text-xs text-muted space-y-1">
          <p className="font-medium">{data.mode === 'historical_replay' ? 'Historical replay — not a current warning.' : 'Operational v1 unavailable.'} Target: {formatTargetDate(data.forecastTargetDate)} · Next calendar day</p>
          <p>Class scores are not calibrated flood probabilities. No predicted inundation. Emergency delivery disabled.</p>
          <details>
            <summary className="cursor-pointer">Output times, data freshness and limitations</summary>
            <div className="space-y-1 mt-1">
              <p>{data.modelVersion} · Input: {formatTargetDate(data.inputDate)}</p>
              <p>{data.mode === 'historical_replay' ? 'Simulated issue' : 'Issue'}: {formatPredictionTime(data.issuedAt)} · Model output: {formatPredictionTime(data.executedAt)} · Data as of: {formatPredictionTime(data.dataAsOf)}</p>
              <p>Zone-associated environmental proxy risk. Nearby zones may share coarse weather grids. No validated street-level flood skill.</p>
              <p>Execution status: {readableReason(data.status)}</p>
              {data.blockers.length > 0 && <>
                <p>Operational v1 blockers:</p>
                <ul className="list-disc pl-4 mt-1">{data.blockers.map((reason) => <li key={reason}>{readableReason(reason)}</li>)}</ul>
              </>}
            </div>
          </details>
        </div>}
        {!proxyView && data && <p className="text-xs text-muted">
          {data.predictionContext?.spatialScope === 'shared_nairobi_weather'
            ? 'Shared Nairobi weather indication. Street-level flooding and local drainage are not assessed. Model scores are not calibrated flood probabilities.'
            : 'Prediction coverage has not been specified by the API.'}
        </p>}
      </div>
      <button
        type="button"
        onClick={refresh}
        disabled={isRefreshing}
        className="shrink-0 self-start sm:self-auto border border-border rounded-btn px-3 py-1.5 font-medium text-ink hover:bg-bg disabled:opacity-50 disabled:cursor-wait"
      >
        {isRefreshing ? 'Refreshing...' : 'Refresh predictions'}
      </button>
      </div>
    </div>
  )
}
