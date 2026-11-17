import { useEffect, useState } from 'react'
import { classExplanation } from '../services/monitoringOutlook'

const mm=value=>`${value.toFixed(1)} mm`

export default function PointForecastContext({ state }) {
  const context=state?.data
  const [expired,setExpired]=useState(false)
  useEffect(() => {
    setExpired(false)
    if (context?.status !== 'AVAILABLE_FORECAST_RULE_CONTEXT') return
    const deadline=Math.min(Date.parse(context.receivedAt)+6*3600000,Date.parse(context.runAt)+24*3600000,Date.parse(context.target_start))
    const timer=setTimeout(()=>setExpired(true),Math.max(0,deadline-Date.now()))
    return ()=>clearTimeout(timer)
  },[context])
  if (!state) return null
  const date=value=>new Intl.DateTimeFormat('en-KE',{timeZone:'Africa/Nairobi',dateStyle:'medium',timeStyle:'short'}).format(new Date(value))
  const complete=context?.accumulationComplete
  return <section className="border-t border-border pt-3 text-sm" aria-label="Point forecast rainfall proxy">
    <h3 className="font-semibold">Rainfall risk outlook for tomorrow</h3>
    {state.loading ? <p className="text-xs text-muted mt-2">Checking stored weather…</p> : context?.status === 'AVAILABLE_FORECAST_RULE_CONTEXT' && !expired ? <div className="space-y-2 mt-2">
      <p>Rainfall risk category <strong>{context.proxy_class}</strong>{context.method==='stage2_xgboost_guarded' && <span className="text-xs text-muted"> · model (XGBoost); rule gives {context.ruleClass}</span>}</p>
      <ul className="text-xs space-y-1" aria-label="Rainfall components">
        <li>Tomorrow (forecast): <strong>{mm(context.daily_forecast_rainfall_mm)}</strong></li>
        <li>7-day total: <strong>{complete ? '' : 'at least '}{mm(context.accumulation7dMm)}</strong> = {context.observedMm===null ? 'observed rain unavailable' : `${mm(context.observedMm)} observed (last 5 days, satellite)`} + {mm(context.issueDayForecastMm)} forecast today + tomorrow's forecast</li>
      </ul>
      <p className="text-xs">{classExplanation(context)}</p>
      <p className="text-xs text-muted">Target starts {date(context.target_start)} EAT, for one complete day.</p>
      <p className="text-xs text-muted">Forecast received {date(context.receivedAt)} EAT. {context.shared.length} monitored records share this forecast grid in the collected sample.</p>
      <p className="text-xs text-muted">A rainfall category does not establish whether this location will flood. Low does not mean safe.</p>
      <details className="text-xs text-muted"><summary className="cursor-pointer">How this outlook is calculated</summary><p className="mt-2">When all inputs are available, the category comes from an XGBoost model. It was trained on real ECMWF forecasts and NASA IMERG Early satellite rainfall (March 2024 to September 2026), checked against CHIRPS-based outcomes, and adopted only after it beat the fixed rule in every-season-held-out testing. It may show Extreme only when the fixed rule also reaches High.</p><p className="mt-2">The fixed rule, shown alongside and used when inputs are incomplete, takes the higher of two rainfall rules. Tomorrow's forecast: Moderate from 5 mm, High from 20 mm, Extreme from 40 mm. 7-day total ending tomorrow: Moderate from 25 mm, High from 80 mm, Extreme from 150 mm. These are the same thresholds used to label the project's v1 model. The rule is not an XGBoost output. Neither is a probability of flooding; local terrain and drainage do not adjust them.</p></details>
    </div> : <p className="text-xs text-muted mt-2">No fresh, complete forecast has been confirmed at this point. Manual collection has no guaranteed next arrival time.</p>}
  </section>
}
