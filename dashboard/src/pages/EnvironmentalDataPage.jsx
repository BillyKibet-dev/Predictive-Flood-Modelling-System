import { useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { useAuth } from '../context/AuthContext'
import TopNav from '../components/TopNav'
import {
  SOURCE_OPTIONS,
  observedWindows,
  observationPath,
  rainfallPath,
  chartRows,
  rainfallLabel,
  validateRegistry,
  validateObservations,
  validateRainfall,
  nairobiDateInput,
} from '../services/environmental'

const inputClass = 'border border-border rounded-btn p-2 bg-surface text-ink max-w-full'
export default function EnvironmentalDataPage() {
  const { user, authorizedRequest } = useAuth()
  const [sources, setSources] = useState([]),
    [datasets, setDatasets] = useState([])
  const [datasetId, setDatasetId] = useState(''),
    [zone, setZone] = useState('')
  const [offset, setOffset] = useState(0),
    [page, setPage] = useState(null),
    [rain, setRain] = useState(null)
  const [end, setEnd] = useState(''),
    [hours, setHours] = useState(24)
  const [draftEnd, setDraftEnd] = useState(''),
    [draftHours, setDraftHours] = useState(24)
  const [error, setError] = useState(''),
    [loading, setLoading] = useState(false),
    [reload, setReload] = useState(0)
  const [truncated, setTruncated] = useState(false)
  const [importSource, setImportSource] = useState('era5-hourly-cbd'),
    [start, setStart] = useState('2024-04-24'),
    [stop, setStop] = useState('2024-05-02')
  const [importing, setImporting] = useState(false),
    [importStatus, setImportStatus] = useState('')
  const dataset = datasets.find((item) => item.id === datasetId)
  const source = sources.find((item) => item.id === dataset?.source_id)
  const windows = observedWindows(source?.temporal_resolution)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    Promise.all([
      authorizedRequest('/api/v1/environmental-data/sources', { signal: controller.signal }),
      authorizedRequest('/api/v1/environmental-data?limit=200', { signal: controller.signal }),
    ])
      .then(([registry, list]) => {
        if (controller.signal.aborted) return
        const verified = validateRegistry(registry, list)
        const visible =
          user.role === 'admin'
            ? verified
            : verified.filter(
                (item) =>
                  registry.find((source) => source.id === item.source_id)?.temporal_resolution !==
                  'static'
              )
        const preferred =
          visible.find(
            (item) =>
              registry.find((source) => source.id === item.source_id)?.temporal_resolution ===
              'hourly'
          ) ?? visible[0]
        setSources(registry)
        setDatasets(visible)
        setDatasetId((current) =>
          visible.some((item) => item.id === current) ? current : (preferred?.id ?? '')
        )
        setTruncated(list.total > list.items.length)
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(failure.message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [authorizedRequest, reload, user.role])
  useEffect(() => {
    setZone(dataset?.provenance.zone_ids?.[0] ?? '')
    setEnd(dataset?.end_at ?? '')
    setDraftEnd(nairobiDateInput(dataset?.end_at))
    setDraftHours(24)
    setHours(24)
    setOffset(0)
    setPage(null)
    setRain(null)
  }, [dataset])
  useEffect(() => {
    setOffset(0)
  }, [zone])
  useEffect(() => {
    if (!dataset || !zone || !end || !windows.length) return
    const controller = new AbortController()
    setLoading(true)
    setError('')
    setPage(null)
    setRain(null)
    Promise.all([
      authorizedRequest(observationPath(dataset.id, zone, offset, end, hours), {
        signal: controller.signal,
      }),
      authorizedRequest(rainfallPath(dataset.id, zone, end, hours), { signal: controller.signal }),
    ])
      .then(([observations, accumulation]) => {
        if (!controller.signal.aborted) {
          const verifiedPage = validateObservations(observations, dataset.id, zone)
          const verifiedRain = validateRainfall(accumulation, dataset.id, zone, end, hours)
          setPage(verifiedPage)
          setRain(verifiedRain)
        }
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(failure.message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [authorizedRequest, dataset, zone, end, hours, offset, source?.temporal_resolution])
  async function importHistory(event) {
    event.preventDefault()
    setImporting(true)
    setImportStatus('Import in progress; no result confirmed yet.')
    try {
      const result = await authorizedRequest('/api/v1/environmental-data', {
        method: 'POST',
        body: JSON.stringify({ source_id: importSource, start_date: start, end_date: stop }),
      })
      setImportStatus(`${result.attempt.status}: ${result.attempt.id}`)
      setDatasetId(result.dataset.id)
      setReload((value) => value + 1)
    } catch (failure) {
      setImportStatus(
        failure.name === 'AbortError'
          ? 'Timed out. Check ingestion history before retrying; import may have completed.'
          : failure.message
      )
    } finally {
      setImporting(false)
    }
  }
  return (
    <div className="min-h-screen bg-bg text-ink">
      <TopNav variant="app" active="Rainfall history" />
      <main className="max-w-6xl mx-auto p-6 space-y-6">
        <h1 className="text-2xl font-semibold">Rainfall history</h1>
        <p className="text-sm text-muted">
          Compare stored rainfall estimates for a study zone and time window. This helps you assess
          past weather alongside citizen reports; it does not show current flooding or a new
          forecast.
        </p>
        <div className="flex flex-wrap gap-4 items-end">
          <label>
            Rainfall dataset{' '}
            <select
              className={inputClass + ' block'}
              value={datasetId}
              onChange={(event) => setDatasetId(event.target.value)}
              aria-label="Dataset version"
            >
              <option value="">Select a dataset</option>
              {datasets.map((item) => (
                <option key={item.id} value={item.id}>
                  {sources.find((source) => source.id === item.source_id)?.name ?? item.source_id} (
                  {item.start_at?.slice(0, 10) ?? 'static'} -{' '}
                  {item.end_at?.slice(0, 10) ?? 'no observation date'})
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className={inputClass}
            onClick={() => setReload((value) => value + 1)}
          >
            Refresh data
          </button>
        </div>
        {loading && <p role="status">Loading verified source records...</p>}
        {error && <p role="alert">{error}</p>}
        {truncated && (
          <p role="status">
            Showing the latest 200 dataset versions. Use the API for older versions.
          </p>
        )}
        {!loading && !datasets.length && !error && (
          <p>
            No historical snapshots imported. An administrator can import the pinned local package
            below.
          </p>
        )}
        {dataset && (
          <section className="bg-surface border border-border rounded-card p-4 space-y-2 text-sm">
            <h2 className="font-semibold">{source?.name}</h2>
            <p>
              Historical data / {source?.temporal_resolution} records. Last stored source time:{' '}
              {dataset.end_at
                ? new Date(dataset.end_at).toLocaleString('en-GB', { timeZone: 'Africa/Nairobi' }) +
                  ' Nairobi'
                : 'Not dated (static terrain)'}
              .
            </p>
            <details>
              <summary className="text-brand cursor-pointer">Data quality and limitations</summary>
              <div className="space-y-2 mt-2 text-muted">
                <p>
                  {dataset.qc_summary.missing_or_invalid_values ?? 0} missing/invalid values;{' '}
                  {dataset.qc_summary.missing_source_bins ?? 0} missing source time bins. Missing
                  values are never treated as zero.
                </p>
                <p>
                  Rainfall is a satellite estimate or retrospective weather-model value, not a
                  ground-gauge reading. The original publication time is unknown, so this archive
                  cannot establish live readiness.
                </p>
                <p>
                  Study areas are approximate, and some share a weather grid. These values cannot
                  resolve local drainage.
                </p>
                <p>{dataset.provenance.window_semantics}</p>
                <p>Measured river levels and predicted inundation are not available.</p>
              </div>
            </details>
            {user.role === 'admin' && (
              <details>
                <summary className="text-brand cursor-pointer">Technical source details</summary>
                <pre className="text-xs overflow-x-auto whitespace-pre-wrap break-all">
                  {JSON.stringify(
                    {
                      sha256: dataset.source_sha256,
                      qc: dataset.qc_summary,
                      provenance: dataset.provenance,
                    },
                    null,
                    2
                  )}
                </pre>
              </details>
            )}
          </section>
        )}
        {!!windows.length && (
          <section className="space-y-4">
            <form
              className="flex flex-wrap gap-4 items-end"
              onSubmit={(event) => {
                event.preventDefault()
                setEnd(draftEnd + ':00+03:00')
                setHours(draftHours)
                setOffset(0)
              }}
            >
              <label>
                Study zone{' '}
                <select
                  className={inputClass + ' block'}
                  value={zone}
                  onChange={(event) => setZone(event.target.value)}
                >
                  {(dataset?.provenance.zone_ids ?? []).map((id) => (
                    <option key={id}>{id}</option>
                  ))}
                </select>
              </label>
              <label>
                Window end (Nairobi time){' '}
                <input
                  required
                  type="datetime-local"
                  className={inputClass + ' block'}
                  aria-label="Window end"
                  value={draftEnd}
                  onChange={(event) => setDraftEnd(event.target.value)}
                />
              </label>
              <label>
                Trailing source window{' '}
                <select
                  className={inputClass + ' block'}
                  value={draftHours}
                  onChange={(event) => setDraftHours(Number(event.target.value))}
                >
                  {windows.map((value) => (
                    <option key={value} value={value}>
                      {value} hours
                    </option>
                  ))}
                </select>
              </label>
              <button type="submit" className={inputClass}>
                Apply window
              </button>
            </form>
            <p className="text-xs text-muted">
              Daily datasets use their own day boundaries; keep the suggested end time for a
              complete daily window.
            </p>
            <p>
              <strong>{rainfallLabel(rain)}</strong> accumulated in the selected historical window.
            </p>
            {!!rain?.reason_codes.length && (
              <p role="status">
                {rain.reason_codes
                  .map(
                    (reason) =>
                      ({
                        MISSING_OR_INVALID_RAINFALL: 'Some rainfall values are missing or invalid.',
                        INCOMPLETE_SOURCE_BINS:
                          'Some rainfall records are missing from this window.',
                        WINDOW_INCOMPATIBLE_WITH_SOURCE_RESOLUTION:
                          'Choose a whole-day window at the suggested source boundary.',
                      })[reason] ?? reason.replaceAll('_', ' ').toLowerCase()
                  )
                  .join(' ')}
              </p>
            )}
            {!!page?.items.length && (
              <>
                <h2 className="font-semibold">
                  Rainfall in this window (mm) - page {Math.floor(offset / 200) + 1}
                </h2>
                <p>
                  The chart shows rainfall per source record within this window. The total above
                  sums complete records; gaps stay visible.
                </p>
                <div className="h-64" aria-label="Historical rainfall source bins in millimetres">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartRows(page.items)}>
                      <XAxis
                        dataKey="time"
                        tickFormatter={(time) => nairobiDateInput(time).slice(5).replace('T', ' ')}
                      />
                      <YAxis unit=" mm" />
                      <Tooltip />
                      <Line
                        type="linear"
                        dataKey="rainfall"
                        stroke="#1767a8"
                        connectNulls={false}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <details>
                  <summary className="cursor-pointer text-brand text-sm">
                    View exact records and quality flags (UTC)
                  </summary>
                  <div className="overflow-x-auto max-h-80">
                    <table className="w-full text-sm text-left">
                      <caption>Exact rainfall bins, UTC, with quality flags</caption>
                      <thead>
                        <tr>
                          <th>Bin start</th>
                          <th>Bin end</th>
                          <th>Rainfall</th>
                          <th>Publication</th>
                          <th>Flags</th>
                        </tr>
                      </thead>
                      <tbody>
                        {page.items.map((row) => (
                          <tr key={row.observed_at} className="border-t border-border">
                            <td>{row.observed_at}</td>
                            <td>{row.bin_end_at}</td>
                            <td>
                              {row.value == null ? 'Missing / invalid' : `${row.value} ${row.unit}`}
                            </td>
                            <td>{row.data_available_at ?? 'Unknown'}</td>
                            <td>{row.quality_flags.join(', ')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              </>
            )}
            {page && (
              <div className="flex gap-4 items-center">
                <button
                  type="button"
                  className={inputClass}
                  disabled={offset === 0 || loading}
                  onClick={() => setOffset((value) => Math.max(0, value - 200))}
                >
                  Previous bins
                </button>
                <span>{page.total} stored bins</span>
                <button
                  type="button"
                  className={inputClass}
                  disabled={offset + 200 >= page.total || loading}
                  onClick={() => setOffset((value) => value + 200)}
                >
                  Next bins
                </button>
              </div>
            )}
            {page && !page.total && (
              <p>No rainfall bins for this dataset and zone. No zero is inferred.</p>
            )}
          </section>
        )}
        {source?.temporal_resolution === 'static' && (
          <p>
            Static terrain summaries only; extraction has not been verified. No rainfall chart or
            invented observation date is available.
          </p>
        )}
        {user.role === 'admin' && (
          <details>
            <summary className="cursor-pointer text-sm text-brand">
              Import historical data (administrator)
            </summary>
            <form
              onSubmit={importHistory}
              className="bg-surface border border-border rounded-card p-4 space-y-3"
            >
              <h2 className="font-semibold">Import a pinned historical snapshot</h2>
              <p>
                Reads the approved local handoff files; no live fetch or model change. Maximum 366
                days; static terrain ignores date filters.
              </p>
              <div className="flex flex-wrap gap-4">
                <label>
                  Source{' '}
                  <select
                    className={inputClass + ' block'}
                    value={importSource}
                    onChange={(event) => setImportSource(event.target.value)}
                  >
                    {SOURCE_OPTIONS.map((id) => (
                      <option key={id}>{id}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Start date{' '}
                  <input
                    required
                    className={inputClass + ' block'}
                    type="date"
                    value={start}
                    onChange={(event) => setStart(event.target.value)}
                  />
                </label>
                <label>
                  End date{' '}
                  <input
                    required
                    className={inputClass + ' block'}
                    type="date"
                    value={stop}
                    onChange={(event) => setStop(event.target.value)}
                  />
                </label>
                <button className={inputClass} disabled={importing}>
                  {importing ? 'Importing...' : 'Import snapshot'}
                </button>
              </div>
              <p role="status">{importStatus}</p>
            </form>
          </details>
        )}
      </main>
    </div>
  )
}
