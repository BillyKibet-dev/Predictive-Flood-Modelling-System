import { useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { useAuth } from '../context/AuthContext'
import TopNav from '../components/TopNav'
import { SOURCE_OPTIONS, observedWindows, observationPath, rainfallPath, chartRows, rainfallLabel, validateRegistry, validateObservations, validateRainfall } from '../services/environmental'

const inputClass = 'border border-border rounded-btn p-2 bg-surface text-ink max-w-full'
export default function EnvironmentalDataPage() {
  const { user, authorizedRequest } = useAuth()
  const [sources, setSources] = useState([]), [datasets, setDatasets] = useState([])
  const [datasetId, setDatasetId] = useState(''), [zone, setZone] = useState('')
  const [offset, setOffset] = useState(0), [page, setPage] = useState(null), [rain, setRain] = useState(null)
  const [end, setEnd] = useState(''), [hours, setHours] = useState(24)
  const [error, setError] = useState(''), [loading, setLoading] = useState(false), [reload, setReload] = useState(0)
  const [truncated, setTruncated] = useState(false)
  const [importSource, setImportSource] = useState('era5-hourly-cbd'), [start, setStart] = useState('2024-04-24'), [stop, setStop] = useState('2024-05-02')
  const [importing, setImporting] = useState(false), [importStatus, setImportStatus] = useState('')
  const dataset = datasets.find(item => item.id === datasetId)
  const source = sources.find(item => item.id === dataset?.source_id)
  const windows = observedWindows(source?.temporal_resolution)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    Promise.all([authorizedRequest('/api/v1/environmental-data/sources', { signal: controller.signal }),
      authorizedRequest('/api/v1/environmental-data?limit=200', { signal: controller.signal })])
      .then(([registry, list]) => { if (controller.signal.aborted) return
        const verified = validateRegistry(registry, list)
        setSources(registry); setDatasets(verified)
        setDatasetId(current => list.items.some(item => item.id === current) ? current : list.items[0]?.id ?? '')
        setTruncated(list.total > list.items.length)
      }).catch(failure => { if (!controller.signal.aborted) setError(failure.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [authorizedRequest, reload])
  useEffect(() => {
    setZone(dataset?.provenance.zone_ids?.[0] ?? ''); setEnd(dataset?.end_at ?? '')
    setHours(24); setOffset(0); setPage(null); setRain(null)
  }, [dataset])
  useEffect(() => {
    setOffset(0)
  }, [zone])
  useEffect(() => {
    if (!dataset || !zone || !end || !windows.length) return
    const controller = new AbortController()
    setLoading(true); setError(''); setPage(null); setRain(null)
    Promise.all([authorizedRequest(observationPath(dataset.id, zone, offset), { signal: controller.signal }),
      authorizedRequest(rainfallPath(dataset.id, zone, end, hours), { signal: controller.signal })])
      .then(([observations, accumulation]) => { if (!controller.signal.aborted) {
        const verifiedPage = validateObservations(observations, dataset.id, zone)
        const verifiedRain = validateRainfall(accumulation, dataset.id, zone, end, hours)
        setPage(verifiedPage); setRain(verifiedRain)
      } })
      .catch(failure => { if (!controller.signal.aborted) setError(failure.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [authorizedRequest, dataset, zone, end, hours, offset, source?.temporal_resolution])
  async function importHistory(event) {
    event.preventDefault(); setImporting(true); setImportStatus('Import in progress; no result confirmed yet.')
    try {
      const result = await authorizedRequest('/api/v1/environmental-data', { method: 'POST', body: JSON.stringify({ source_id: importSource, start_date: start, end_date: stop }) })
      setImportStatus(`${result.attempt.status}: ${result.attempt.id}`)
      setDatasetId(result.dataset.id); setReload(value => value + 1)
    } catch (failure) { setImportStatus(failure.name === 'AbortError' ? 'Timed out. Check ingestion history before retrying; import may have completed.' : failure.message) }
    finally { setImporting(false) }
  }
  return <div className="min-h-screen bg-bg text-ink">
    <TopNav variant="app" active="Environmental data" />
    <main className="max-w-6xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-semibold">Historical environmental data</h1>
      <p>Research snapshots only. Rainfall estimates and retrospective reanalysis are not ground-sensor readings or forecasts. Import time is not publication time.</p>
      <p className="text-sm">Water levels: <strong>UNAVAILABLE</strong>. Sensor adapter disabled pending the company contract, datum and validation. Predicted inundation extent/depth: <strong>NOT AVAILABLE</strong>.</p>
      <div className="flex flex-wrap gap-4 items-end">
        <label>Dataset version <select className={inputClass+' block'} value={datasetId} onChange={event => setDatasetId(event.target.value)} aria-label="Dataset version"><option value="">Select a dataset</option>{datasets.map(item => <option key={item.id} value={item.id}>{item.source_id} / {item.id.slice(0, 12)}</option>)}</select></label>
        <button type="button" className={inputClass} onClick={() => setReload(value => value + 1)}>Refresh registry</button>
      </div>
      {loading && <p role="status">Loading verified source records...</p>}
      {error && <p role="alert">{error}</p>}
      {truncated && <p role="status">Showing the latest 200 dataset versions. Use the API for older versions.</p>}
      {!loading && !datasets.length && !error && <p>No historical snapshots imported. An administrator can import the pinned local package below.</p>}
      {dataset && <section className="bg-surface border border-border rounded-card p-4 space-y-3">
        <h2 className="font-semibold">Source and quality</h2>
        <p>{source?.name} / {source?.source_kind} / {source?.temporal_resolution} bins / timezone {dataset.provenance.bin_timezone ?? 'not applicable'}</p>
        <p>Latest bin end: {dataset.freshness.latest_bin_end_at ?? 'No observation date for static terrain'}. Status: {dataset.freshness.status}. Publication: UNKNOWN. Operational freshness: NOT ESTABLISHED.</p>
        <p>Snapshot age: {dataset.freshness.age_hours == null ? 'not applicable' : `${Math.floor(dataset.freshness.age_hours)} hours since last bin end`}.</p>
        <p>{dataset.provenance.window_semantics}</p>
        <p>Zone keys refer to approximate study areas. Some weather grids are shared; this does not establish street-level flood skill.</p>
        <details><summary>Hashes, grids and quality checks</summary><pre className="text-xs overflow-x-auto whitespace-pre-wrap break-all">{JSON.stringify({ sha256: dataset.source_sha256, qc: dataset.qc_summary, provenance: dataset.provenance }, null, 2)}</pre></details>
      </section>}
      {!!windows.length && <section className="space-y-4">
        <div className="flex flex-wrap gap-4 items-end">
          <label>Study zone <select className={inputClass+' block'} value={zone} onChange={event => setZone(event.target.value)}>{(dataset?.provenance.zone_ids ?? []).map(id => <option key={id}>{id}</option>)}</select></label>
          <label>Window end (explicit UTC offset) <input className={inputClass+' block'} aria-label="Window end" value={end} onChange={event => setEnd(event.target.value)} /></label>
          <label>Trailing source window <select className={inputClass+' block'} value={hours} onChange={event => setHours(Number(event.target.value))}>{windows.map(value => <option key={value} value={value}>{value} hours</option>)}</select></label>
        </div>
        <p><strong>{rainfallLabel(rain)}</strong> across the selected trailing source bins. This is not a forecast horizon.</p>
        {!!rain?.reason_codes.length && <p role="status">{rain.reason_codes.join(', ')}</p>}
        {!!page?.items.length && <>
          <h2 className="font-semibold">Rainfall source bins (mm) - page {Math.floor(offset / 200) + 1}</h2>
          <p>UTC timestamps; values represent each source bin, not a rolling sum. Gaps/nulls are not zero. The table provides exact values and flags.</p>
          <div className="h-64" aria-label="Historical rainfall source bins in millimetres"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartRows(page.items)}><XAxis dataKey="time" tickFormatter={time => time.slice(5, 16)} /><YAxis unit=" mm" /><Tooltip /><Line type="linear" dataKey="rainfall" stroke="#1767a8" connectNulls={false} isAnimationActive={false} /></LineChart></ResponsiveContainer></div>
          <div className="overflow-x-auto max-h-80"><table className="w-full text-sm text-left"><caption>Exact rainfall bins, UTC, with quality flags</caption><thead><tr><th>Bin start</th><th>Bin end</th><th>Rainfall</th><th>Publication</th><th>Flags</th></tr></thead><tbody>{page.items.map(row => <tr key={row.observed_at} className="border-t border-border"><td>{row.observed_at}</td><td>{row.bin_end_at}</td><td>{row.value == null ? 'Missing / invalid' : `${row.value} ${row.unit}`}</td><td>{row.data_available_at ?? 'Unknown'}</td><td>{row.quality_flags.join(', ')}</td></tr>)}</tbody></table></div>
        </>}
        {page && <div className="flex gap-4 items-center"><button type="button" className={inputClass} disabled={offset === 0 || loading} onClick={() => setOffset(value => Math.max(0, value - 200))}>Previous bins</button><span>{page.total} stored bins</span><button type="button" className={inputClass} disabled={offset + 200 >= page.total || loading} onClick={() => setOffset(value => value + 200)}>Next bins</button></div>}
        {page && !page.total && <p>No rainfall bins for this dataset and zone. No zero is inferred.</p>}
      </section>}
      {source?.temporal_resolution === 'static' && <p>Static terrain summaries only; extraction has not been verified. No rainfall chart or invented observation date is available.</p>}
      {user.role === 'admin' && <form onSubmit={importHistory} className="bg-surface border border-border rounded-card p-4 space-y-3">
        <h2 className="font-semibold">Import a pinned historical snapshot</h2><p>Reads the approved local handoff files; no live fetch or model change. Maximum 366 days; static terrain ignores date filters.</p>
        <div className="flex flex-wrap gap-4"><label>Source <select className={inputClass+' block'} value={importSource} onChange={event => setImportSource(event.target.value)}>{SOURCE_OPTIONS.map(id => <option key={id}>{id}</option>)}</select></label><label>Start date <input required className={inputClass+' block'} type="date" value={start} onChange={event => setStart(event.target.value)} /></label><label>End date <input required className={inputClass+' block'} type="date" value={stop} onChange={event => setStop(event.target.value)} /></label><button className={inputClass} disabled={importing}>{importing ? 'Importing...' : 'Import snapshot'}</button></div>
        <p role="status">{importStatus}</p>
      </form>}
    </main>
  </div>
}
