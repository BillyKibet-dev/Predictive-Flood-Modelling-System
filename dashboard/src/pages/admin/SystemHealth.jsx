import { RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import useStaffList from '../../hooks/useStaffList'
import { apiStatus } from '../../services/workspace'
import useMonitoringOutlook from '../../hooks/useMonitoringOutlook'
import WeatherCollectionControl from '../../components/WeatherCollectionControl'
import { PageHeader, buttonClass } from '../../components/StaffLayout'

function Status({ label, ok, value, detail, to, linkText }) {
  return <div className="panel p-5 flex flex-col">
    <p className="eyebrow">{label}</p>
    <p className="flex items-center gap-2 mt-2 font-semibold">
      <span className={`w-2 h-2 rounded-full ${ok === true ? 'bg-risk-low' : ok === false ? 'bg-risk-high' : 'bg-border'}`} aria-hidden="true" />{value}</p>
    {detail && <p className="text-xs text-muted mt-1.5">{detail}</p>}
    {to && <Link to={to} className="text-xs text-accent font-medium mt-auto pt-3">{linkText} →</Link>}
  </div>
}

export default function SystemHealth() {
  const state = useStaffList('/health')
  const outlook = useMonitoringOutlook()
  let status = null, validationError = ''
  if (state.data) {
    try { status = apiStatus(state.data) } catch (error) { validationError = error.message }
  }
  const data = outlook.data, fresh = data?.available_count ?? 0
  const applied = data?.areas.filter(a => a.status === 'AVAILABLE' && a.model_status === 'APPLIED').length ?? 0
  const every = data?.configured_interval_hours === 1 ? 'every hour' : `every ${data?.configured_interval_hours} hours`
  return <section className="text-ink">
    <PageHeader title="System" description="Whether the API, weather collection and models are running.">
      <button onClick={() => { state.refresh(); outlook.refresh() }} disabled={state.loading} className={buttonClass}><RefreshCw size={15} />{state.loading ? 'Checking…' : 'Refresh status'}</button>
    </PageHeader>
    {(state.error || validationError) && <p role="alert" className="text-sm mb-4">Status could not be confirmed. {state.error || validationError} {status && 'The last response is shown; it may be outdated.'}</p>}
    {!state.data && state.loading && <p role="status" className="text-sm text-muted">Checking API…</p>}
    {status && <div className="space-y-6">
      <div className="grid sm:grid-cols-3 gap-4">
        <Status label="API" ok={!state.error} value={state.error ? 'Last response only' : 'Responding'} detail={`Environment: ${status.environment}`} />
        <Status label="Weather" ok={outlook.loading ? undefined : fresh > 0 && fresh === data?.located_count}
          value={outlook.loading ? 'Checking…' : fresh ? `${fresh} of ${data.located_count} places fresh` : 'No fresh outlook'}
          detail={data?.collection_automatic ? `Collected automatically ${every}.` : 'Collected manually: no automatic collection on this server.'}
          to="/weather-outlook" linkText="Weather" />
        <Status label="Rainfall-risk model" ok={outlook.loading || !fresh ? undefined : applied === fresh}
          value={outlook.loading ? 'Checking…' : !fresh ? 'Waiting for weather' : applied ? `Used at ${applied} of ${fresh} places` : 'Rule fallback in use'}
          detail={fresh && applied < fresh ? 'The rainfall rule covers places where model inputs are incomplete.' : 'Validation, version and fallbacks.'}
          to="/admin/models" linkText="Models" />
      </div>

      <section className="panel p-5 sm:p-6" aria-label="Monitoring weather status">
        <WeatherCollectionControl onComplete={() => { state.refresh(); outlook.refresh() }} />
      </section>

      <details className="panel p-4 text-sm">
        <summary className="font-medium cursor-pointer">Research runtime and limits</summary>
        <div className="space-y-2 mt-3 text-muted">
          <p>Binary heavy-rain research model: {status.modelVersion ?? 'not reported'} · {status.modelStatus ?? 'not reported'}. It runs only when staff open the research page; it is not an alert service.</p>
          <p>This check shows the API is reachable. It does not measure database health, backups or uptime.</p>
          <Link to="/research" className="text-accent font-medium">Open research models</Link>
        </div>
      </details>
    </div>}
  </section>
}
