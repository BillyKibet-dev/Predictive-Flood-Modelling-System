import useProxyModel from '../../hooks/useProxyModel'
import { readableReason } from '../../services/proxyPredictions'

export default function SystemHealth() {
  const { data, error, loading, refresh } = useProxyModel()
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-semibold tracking-tight text-ink">v1 Runtime and Data Status</h2>
        <button type="button" onClick={refresh} disabled={loading} className="border border-border rounded-btn px-3 py-2 text-sm text-ink disabled:opacity-50">
          {loading ? 'Checking metadata...' : 'Refresh metadata'}
        </button>
      </div>
      <p className="text-sm text-muted">This panel reports the model metadata response. It does not measure server uptime, cloud deployment, database health or scheduled execution.</p>
      {!data && <p role="status" className="text-sm text-muted">{error ?? 'Requesting current model status...'}</p>}
      {error && data && <p role="alert" className="text-sm text-risk-mod">{error} Showing the last retrieved metadata; status may have changed.</p>}
      {data && <>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Status label="Native model" value={data.loaded ? 'Loaded' : 'Unavailable'} detail={`${data.modelVersion} · ${readableReason(data.status)}`} />
          <Status label="Operational data" value="Unavailable" detail={readableReason(data.operationalStatus)} />
          <Status label="Emergency delivery" value="Disabled" detail="Research/advisory use only; stakeholder policy required." />
        </div>
        <div className="bg-surface border border-border rounded-card p-5 space-y-2 text-sm text-muted">
          <h3 className="font-semibold text-ink">Runtime reported by the backend</h3>
          {['python', 'xgboost', 'numpy'].map((name) => <p key={name}>{name}: {typeof data.runtime[name] === 'string' ? data.runtime[name] : 'Not reported'}</p>)}
          <p>No observed scheduler run or hosting location is inferred from the native model being loaded.</p>
        </div>
        <div className="text-sm text-muted space-y-2">
          <h3 className="font-semibold text-ink">Live-data blockers</h3>
          <ul className="list-disc pl-5 space-y-1">{data.blockers.map((item) => <li key={item}>{readableReason(item)}</li>)}</ul>
        </div>
      </>}
    </div>
  )
}

function Status({ label, value, detail }) {
  return <div className="bg-surface border border-border rounded-card p-5">
    <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
    <p className="font-semibold text-ink mt-2">{value}</p>
    <p className="text-xs text-muted mt-1">{detail}</p>
  </div>
}
