import { useState } from 'react'
import { Link } from 'react-router-dom'
import StaffLayout from '../components/StaffLayout'
import MapView from '../components/MapView'
import RiskBadge from '../components/RiskBadge'
import ProxyForecastDetails from '../components/ProxyForecastDetails'
import PredictionViewControls from '../components/PredictionViewControls'
import BinaryRainfallResearch from '../components/BinaryRainfallResearch'
import ModelPerformance from './admin/ModelPerformance'
import usePredictionView from '../hooks/usePredictionView'
import useBoundaries from '../hooks/useBoundaries'
import { formatPredictionTime } from '../services/predictions'
import { formatTargetDate, zoneStatusLabel } from '../services/proxyPredictions'

export default function ModelResearchPage() {
  const results = usePredictionView(), boundaries = useBoundaries()
  const [evaluationOpen, setEvaluationOpen] = useState(false)
  const zones = results.data?.zones ?? []
  return <StaffLayout><div className="space-y-5">
      <div className="flex flex-wrap justify-between gap-3 items-start"><div><h1 className="text-2xl font-semibold">Model research</h1><p className="text-sm text-muted mt-1">Research outputs are separate from public monitoring, satellite evidence and community reports.</p></div><Link className="text-sm text-brand underline" to="/">Back to monitoring map</Link></div>
      <section className="border border-border rounded-card bg-surface p-4 text-sm space-y-2"><p className="font-semibold">Not public flood warnings</p><p>Neither output establishes street flooding, flood probability, water depth, inundation extent or safety. Officers must interpret it with local observations and official guidance.</p></section>
      <BinaryRainfallResearch />
      <section className="space-y-3"><div className="flex flex-wrap justify-between gap-3 items-end"><div><h2 className="text-lg font-semibold">Historical v1 replay</h2><p className="text-sm text-muted">The retained 20-feature model can only replay verified historical inputs; it has no live-data path.</p></div><PredictionViewControls selection={results.selection} /></div>
        <p className="font-medium text-sm">Input {formatTargetDate(results.selection.inputDate)} · target {formatTargetDate(results.data?.forecastTargetDate)}. Not a current warning.</p>
        {results.error && <p role="alert" className="text-sm">Could not refresh historical replay. {results.data ? 'The last matching records remain visible.' : 'No result is confirmed.'}</p>}
        {!results.data && results.isRefreshing && <p role="status">Loading historical records…</p>}
        {!!zones.length && <><section className="rounded-card border border-border overflow-hidden"><div className="p-3 bg-surface text-xs">Historical v1 classes at the original monitoring points. Administrative outlines are geographic context.</div><MapView zones={zones} boundaries={boundaries.data} boundaryRevision={boundaries.revision} height="360px" showModelOutputs pointHref={() => '/officer/reports'} /></section>
          <section className="bg-surface border border-border rounded-card overflow-hidden"><h3 className="font-semibold p-4">Historical classifications</h3><div className="overflow-x-auto"><table className="w-full text-sm text-left"><thead><tr>{['Monitoring location', 'Saved class', 'Saved time', 'Record status', 'Details'].map(label => <th key={label} className="p-3 text-muted font-medium">{label}</th>)}</tr></thead><tbody>{zones.map(zone => <tr key={zone.id} className="border-t border-border"><td className="p-3">{zone.name}</td><td className="p-3"><RiskBadge risk={zone.risk} size="sm" /></td><td className="p-3">{formatPredictionTime(zone.timestamp)}</td><td className="p-3">{zoneStatusLabel(zone)}</td><td className="p-3"><details><summary className="text-brand cursor-pointer">Inspect</summary><div className="min-w-52 mt-2"><ProxyForecastDetails zone={zone} /></div></details></td></tr>)}</tbody></table></div></section></>}
      </section>
      <details className="border border-border bg-surface rounded-card p-4" onToggle={event => setEvaluationOpen(event.currentTarget.open)}><summary className="text-sm font-medium cursor-pointer">Historical v1 evaluation and live-input limitations</summary>{evaluationOpen && <div className="mt-5"><ModelPerformance /></div>}</details>
    </div></StaffLayout>
}
