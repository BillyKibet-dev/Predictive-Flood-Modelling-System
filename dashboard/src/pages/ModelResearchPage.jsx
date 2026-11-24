import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CloudRain, Satellite, Sparkles } from 'lucide-react'
import StaffLayout, { PageHeader } from '../components/StaffLayout'
import MapView from '../components/MapView'
import RiskBadge from '../components/RiskBadge'
import ProxyForecastDetails from '../components/ProxyForecastDetails'
import PredictionViewControls from '../components/PredictionViewControls'
import BinaryRainfallResearch from '../components/BinaryRainfallResearch'
import LiveTrackRecord from '../components/LiveTrackRecord'
import ModelPerformance from './admin/ModelPerformance'
import usePredictionView from '../hooks/usePredictionView'
import useBoundaries from '../hooks/useBoundaries'
import useStaffList from '../hooks/useStaffList'
import { useAuth } from '../context/AuthContext'
import { riskColor } from '../constants/colors'
import { formatPredictionTime } from '../services/predictions'
import { formatTargetDate, zoneStatusLabel } from '../services/proxyPredictions'
import { parseModelCard, percent } from '../services/staffData'

const THRESHOLDS = [['Low', 'under 5', 'under 25'], ['Moderate', '5 to 20', '25 to 80'], ['High', '20 to 40', '80 to 150'], ['Extreme', '40 or more', '150 or more']]

// A <details> whose contents mount only when opened, so older experiments never run unasked.
function Later({ title, description, children }) {
  const [open, setOpen] = useState(false)
  return <details className="panel" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer p-5 list-none flex items-start gap-3">
      <span className="flex-1"><span className="font-semibold block">{title}</span><span className="text-sm text-muted">{description}</span></span>
      <span className="text-sm text-accent shrink-0">{open ? 'Hide' : 'Open'}</span>
    </summary>
    {open && <div className="px-5 pb-5 space-y-4">{children}</div>}
  </details>
}

function Step({ icon: Icon, title, children }) {
  return <li className="flex gap-3"><span className="w-9 h-9 shrink-0 rounded-card bg-surface-2 grid place-items-center text-muted"><Icon size={17} /></span>
    <span><span className="font-medium block">{title}</span><span className="text-sm text-muted">{children}</span></span></li>
}

// How a category is decided, for officers new to the system.
function HowItWorks() {
  return <section className="panel p-5 sm:p-6 grid gap-6 lg:grid-cols-2" aria-labelledby="how-heading">
    <div className="space-y-4">
      <h2 id="how-heading" className="font-semibold">How a place gets its category</h2>
      <ol className="space-y-4">
        <Step icon={CloudRain} title="Rain forecast for the day">ECMWF weather model, collected every hour for each monitored place.</Step>
        <Step icon={Satellite} title="Rain that already fell">NASA satellite rain for the 5 days before, so a wet week counts.</Step>
        <Step icon={Sparkles} title="Model picks the category">Trained on past seasons. If an input is missing, the fixed rule on the right decides instead.</Step>
      </ol>
    </div>
    <div>
      <p className="text-sm font-medium mb-2">The rule (and what the model learned to predict)</p>
      <table className="w-full text-sm tabular">
        <thead><tr className="text-left text-muted"><th scope="col" className="py-1.5 pr-3 font-medium">Category</th><th scope="col" className="py-1.5 pr-3 font-medium">Rain that day (mm)</th><th scope="col" className="py-1.5 font-medium">or 7-day total (mm)</th></tr></thead>
        <tbody>{THRESHOLDS.map(([c, day, week]) => <tr key={c} className="border-t border-border">
          <th scope="row" className="py-2 pr-3 text-left font-medium"><span className="inline-flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full" style={{ background: riskColor(c) }} aria-hidden="true" />{c}</span></th>
          <td className="py-2 pr-3">{day}</td><td className="py-2">{week}</td></tr>)}</tbody>
      </table>
      <p className="text-xs text-muted mt-3">Rainfall categories, not flood warnings: they say how much rain, not whether a street floods.</p>
    </div>
  </section>
}

// Before launch: the one-off test that decided the model could replace the rule.
function BeforeLaunch() {
  const { user } = useAuth()
  const state = useStaffList('/staff/model-card')
  const card = useMemo(() => { try { return state.data ? parseModelCard(state.data) : null } catch { return null } }, [state.data])
  if (!card) return state.loading ? <p role="status" className="text-sm text-muted">Loading the launch test…</p> : null
  const m = card.validation.model.high_or_above, r = card.validation.rule.high_or_above
  const seasons = card.validation.seasons, wins = seasons.filter(s => s.model_csi > s.rule_csi).length
  return <section className="panel p-5 sm:p-6 space-y-4" aria-labelledby="launch-heading">
    <div><h2 id="launch-heading" className="font-semibold">Before launch</h2>
      <p className="text-sm text-muted mt-1">Tested on {seasons.length} past rainy and dry seasons it had never seen.</p></div>
    <dl className="grid sm:grid-cols-3 gap-4">
      {[['Heavy-rain days caught', percent(m.pod), percent(r.pod)], ['False alarms', percent(m.far), percent(r.far)], ['Seasons where it beat the rule', `${wins} of ${seasons.length}`, null]].map(([label, model, rule]) =>
        <div key={label} className="rounded-card bg-surface-2 p-4"><dt className="eyebrow">{label}</dt><dd className="text-2xl font-semibold tabular mt-1">{model}</dd>
          {rule && <dd className="text-xs text-muted mt-0.5">Rule alone: {rule}</dd>}</div>)}
    </dl>
    {user?.role === 'admin' && <Link to="/admin/models" className="text-sm text-accent font-medium">Full model record →</Link>}
  </section>
}

function HistoricalReplay() {
  const results = usePredictionView(), boundaries = useBoundaries()
  const [evaluationOpen, setEvaluationOpen] = useState(false)
  const zones = results.data?.zones ?? []
  return <>
    <div className="flex flex-wrap justify-between gap-3 items-end"><p className="text-sm font-medium">Input {formatTargetDate(results.selection.inputDate)} · target {formatTargetDate(results.data?.forecastTargetDate)}. Not a current warning.</p><PredictionViewControls selection={results.selection} /></div>
    {results.error && <p role="alert" className="text-sm">Could not refresh historical replay. {results.data ? 'The last matching records remain visible.' : 'No result is confirmed.'}</p>}
    {!results.data && results.isRefreshing && <p role="status">Loading historical records…</p>}
    {!!zones.length && <>
      <div className="rounded-card border border-border overflow-hidden"><MapView zones={zones} boundaries={boundaries.data} boundaryRevision={boundaries.revision} height="320px" showModelOutputs pointHref={() => '/officer/reports'} /></div>
      <div className="overflow-x-auto"><table className="w-full text-sm text-left"><thead><tr>{['Zone', 'Class', 'Saved', 'Status', ''].map(label => <th key={label} className="p-2 text-muted font-medium">{label}</th>)}</tr></thead>
        <tbody>{zones.map(zone => <tr key={zone.id} className="border-t border-border"><td className="p-2">{zone.name}</td><td className="p-2"><RiskBadge risk={zone.risk} size="sm" /></td>
          <td className="p-2 whitespace-nowrap">{formatPredictionTime(zone.timestamp)}</td><td className="p-2">{zoneStatusLabel(zone)}</td>
          <td className="p-2"><details><summary className="text-brand cursor-pointer">Inspect</summary><div className="min-w-52 mt-2"><ProxyForecastDetails zone={zone} /></div></details></td></tr>)}</tbody></table></div>
    </>}
    <details className="border-t border-border pt-3" onToggle={event => setEvaluationOpen(event.currentTarget.open)}><summary className="text-sm font-medium cursor-pointer">Its stored test results</summary>{evaluationOpen && <div className="mt-5"><ModelPerformance /></div>}</details>
  </>
}

// Officers' view of the models: are the map's categories right? Older experiments sit
// below, closed, and only run when opened.
export default function ModelResearchPage() {
  return <StaffLayout>
    <PageHeader title="How the models are doing" description="Each day's rainfall categories, checked against the rain that fell. Updates by itself as days pass." />
    <div className="space-y-8">
      <section aria-labelledby="live-heading" className="space-y-4">
        <h2 id="live-heading" className="text-lg font-semibold">Since launch</h2>
        <LiveTrackRecord />
      </section>
      <BeforeLaunch />
      <HowItWorks />
      <section aria-labelledby="older-heading" className="space-y-3">
        <div><h2 id="older-heading" className="text-lg font-semibold">Older experiments</h2>
          <p className="text-sm text-muted mt-1">Kept for comparison. Not used on the map.</p></div>
        <Later title="Will it rain tomorrow? (yes/no model)" description="Runs only when opened. Says whether 5 mm or more is likely; no categories.">
          <BinaryRainfallResearch />
        </Later>
        <Later title="First model (2016–2025 replay)" description="The original 20-input model. It needs inputs published weeks late, so it can only replay past dates.">
          <HistoricalReplay />
        </Later>
      </section>
    </div>
  </StaffLayout>
}
