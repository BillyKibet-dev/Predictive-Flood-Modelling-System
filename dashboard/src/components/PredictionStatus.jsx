import { formatPredictionTime } from '../services/predictions'
import { formatTargetDate, PREDICTION_VIEWS } from '../services/proxyPredictions'
import PredictionViewControls from './PredictionViewControls'

// Map-only overlay: concise by default, explanations available on request.
export default function PredictionStatus({ predictions }) {
  const { data, error, refresh, isRefreshing, selection } = predictions
  const view =
    PREDICTION_VIEWS.find((item) => item.value === selection?.view) ?? PREDICTION_VIEWS[0]
  const replay = selection?.view === 'v1_replay'
  const live = selection?.view === 'v1_live'
  const status = !data
    ? error
      ? 'Data unavailable. Please retry.'
      : 'Loading advisory...'
    : error
      ? 'Refresh failed. Showing the last retrieved data.'
      : live
        ? 'Not ready. No estimated availability.'
      : replay
        ? ['SUCCESS', 'PARTIAL'].includes(data.status)
          ? `Past-date analysis: ${formatTargetDate(data.forecastTargetDate)}`
          : 'No saved result for this date. Choose another input date.'
          : `Updated ${formatPredictionTime(data.lastUpdated)}`
  return (
    <section
      aria-label="Map prediction controls"
      className="bg-surface border border-border rounded-card shadow-card-hover p-3 text-xs text-ink max-h-[65vh] overflow-y-auto"
    >
      <div className="flex items-start gap-2 justify-between">
        <div className="min-w-0">
          <p className="font-semibold text-sm">{view.label}</p>
          <p role="status" className="text-muted mt-1">
            {status}
          </p>
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={isRefreshing}
          aria-label="Refresh predictions"
          className="border border-border rounded-btn p-2 shrink-0 disabled:opacity-50"
        >
          {isRefreshing ? 'Checking...' : 'Refresh'}
        </button>
      </div>
      {replay && <p className="mt-1 text-risk-mod">Historical result. Not a current warning.</p>}
      <details className="mt-2">
        <summary className="cursor-pointer text-brand font-medium">
          Change view or learn more
        </summary>
        <div className="space-y-3 pt-3">
          <PredictionViewControls selection={selection} />
          <p>{view.description}</p>
          <details>
            <summary className="cursor-pointer">Which view should I use?</summary>
            <dl className="space-y-2 mt-2">
              {PREDICTION_VIEWS.map((item) => (
                <div key={item.value}>
                  <dt className="font-semibold">{item.label}</dt>
                  <dd className="text-muted">{item.description}</dd>
                </div>
              ))}
            </dl>
          </details>
          <p className="text-muted">
            Weather-based indications support officer decisions. Local drainage and street-level
            flood depth are not predicted.
          </p>
          {live && (
            <p>
              Verified live rainfall and complete weather inputs are still required. Waiting a few
              minutes or hours will not resolve this setup gap.
            </p>
          )}
          {replay && (
            <p>
              Input: {formatTargetDate(data?.inputDate)}. Target:{' '}
              {formatTargetDate(data?.forecastTargetDate)} (the next calendar day).
            </p>
          )}
        </div>
      </details>
    </section>
  )
}
