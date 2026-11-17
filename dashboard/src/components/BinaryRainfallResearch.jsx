import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { fetchBinaryRainfall } from '../services/binaryRainfall'
import { formatPredictionTime } from '../services/predictions'

export default function BinaryRainfallResearch() {
  const { authorizedRequest } = useAuth()
  const [state, setState] = useState({ data: null, error: '', loading: true })
  const load = useCallback(async () => {
    setState(previous => ({ ...previous, loading: true, error: '' }))
    try { setState({ data: await fetchBinaryRainfall({ authorizedRequest }), error: '', loading: false }) }
    catch (error) { setState(previous => ({ ...previous, error: error.message, loading: false })) }
  }, [authorizedRequest])
  useEffect(() => { void load() }, [load])
  const data = state.data
  return <section className="border border-border rounded-card bg-surface p-4 space-y-3" aria-label="Binary rainfall research">
    <div className="flex flex-wrap justify-between gap-3"><div><h2 className="font-semibold">Next-day rainfall research</h2><p className="text-sm text-muted mt-1">Staff-only, on-demand model execution from the latest verified forecast receipt.</p></div><button onClick={load} disabled={state.loading} className="border border-border rounded-btn px-3 py-2 text-sm disabled:opacity-50">{state.loading ? 'Checking…' : 'Refresh source and score'}</button></div>
    <p className="text-sm"><strong>What it estimates:</strong> {data?.target ?? 'Checking the model and source.'}</p><p className="text-sm text-muted">{data?.interpretation ?? 'No public flood prediction or alert is produced.'}</p>
    {state.error && <p role="alert" className="text-sm">Could not verify the research output. {state.error}</p>}
    {data?.status === 'UNAVAILABLE' && <p role="status" className="text-sm">Unavailable: {data.reason ?? data.model?.reason ?? 'no eligible verified weather receipt'}.</p>}
    {data?.source?.target_start && <p className="text-xs text-muted">Forecast target starts {formatPredictionTime(data.source.target_start)}. Receipt eligibility: {data.source.temporal_eligibility ?? 'not reported'}.</p>}
    {data?.areas?.length > 0 && <div className="overflow-x-auto"><table className="w-full text-sm text-left"><thead><tr>{['Monitoring area', 'Result', 'Raw score', 'Shared forecast grid', 'Status'].map(label => <th key={label} className="p-2 text-muted font-medium">{label}</th>)}</tr></thead><tbody>{data.areas.map(area => <tr key={area.id} className="border-t border-border"><td className="p-2">{area.name}</td><td className="p-2">{area.classification === 'AT_OR_ABOVE_5_MM' ? 'Rainfall proxy ≥ 5 mm' : area.classification === 'BELOW_5_MM' ? 'Rainfall proxy < 5 mm' : 'Unavailable'}</td><td className="p-2">{area.score === null ? '—' : area.score.toFixed(4)}</td><td className="p-2">{area.sharedAreaIds.length || '—'} area(s)</td><td className="p-2">{area.status === 'AVAILABLE_RESEARCH_ONLY' ? 'Research only' : area.reason ?? 'Unavailable'}</td></tr>)}</tbody></table></div>}
    {data?.limitations?.length > 0 && <details className="text-xs text-muted"><summary className="cursor-pointer">Method and use limitations</summary><ul className="list-disc pl-5 mt-2 space-y-1">{data.limitations.map(item => <li key={item}>{item}</li>)}</ul></details>}
  </section>
}
