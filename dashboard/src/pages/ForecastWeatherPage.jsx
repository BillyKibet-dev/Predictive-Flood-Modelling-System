import { useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { RefreshCw } from 'lucide-react'
import StaffLayout, { PageHeader, buttonClass } from '../components/StaffLayout'
import { riskColor } from '../constants/colors'
import useSusceptibility from '../hooks/useSusceptibility'
import useTodayOutlook from '../hooks/useTodayOutlook'
import { todayPoint, windowLabel } from '../services/todayOutlook'
import { watchOrder } from '../services/susceptibility'
import { useAuth } from '../context/AuthContext'
import { Link } from 'react-router-dom'
import { OUTLOOK_PATH, snapshotPath, validateOutlook, validateSnapshots, nairobiTime, rainfallText, periodLabel } from '../services/forecastOutlook'
import useMonitoringAreas from '../hooks/useMonitoringAreas'
import useMonitoringOutlook from '../hooks/useMonitoringOutlook'

const inputClass = 'border border-border rounded-btn p-2 bg-surface text-ink max-w-full'
export default function ForecastWeatherPage() {
  const [archive,setArchive]=useState(false)
  return archive?<ForecastArchive onBack={()=>setArchive(false)} />:<CurrentMonitoringWeather onArchive={()=>setArchive(true)} />
}

function Pill({category}) {
  const color=riskColor(category)
  return <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2 py-1 rounded-full" style={{background:`color-mix(in srgb, ${color} 12%, transparent)`,color}}>
    <span className="w-1.5 h-1.5 rounded-full" style={{background:color}} aria-hidden="true" />{category}</span>
}
function Fact({label,value}) {
  return <div><dt className="eyebrow">{label}</dt><dd className="text-sm font-medium mt-1 tabular">{value}</dd></div>
}

function CurrentMonitoringWeather({onArchive}) {
  const areas=useMonitoringAreas(),outlook=useMonitoringOutlook(),[parent,setParent]=useState(''),susceptibility=useSusceptibility(),today=useTodayOutlook()
  const source=outlook.data?.collection, local=susceptibility.data?.byArea ?? {}
  const located=areas.data?.sites.filter(s=>s.point) || []
  const rows=new Map((outlook.data?.areas || []).map(r=>[r.area_id,r]))
  const names=new Map((areas.data?.sites || []).map(s=>[s.id,s]))
  const rank=site=>{const r=rows.get(site.id);return r?.status==='AVAILABLE'?-watchOrder(r.proxy_class,local[site.id])*1000-(r.rainfall_mm??0):1e9}
  const sites=located.filter(s=>!parent || s.parent_zone_id===parent).sort((a,b)=>rank(a)-rank(b))
  const data=outlook.data
  return <StaffLayout>
    <PageHeader title="Weather" description="Tomorrow's rainfall at every monitored place: the same outlook as the map. A rainfall category, not a flood forecast.">
      <button className={buttonClass} disabled={outlook.loading} onClick={()=>{outlook.refresh();areas.refresh()}}><RefreshCw size={15} />Refresh</button>
    </PageHeader>
    <section aria-label="Current monitored-area weather" className="panel p-5">
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Fact label="Fresh forecasts" value={outlook.loading&&!data?'…':data?`${data.available_count} of ${data.located_count}`:'None'} />
        <Fact label="For" value={source?.target_start?new Intl.DateTimeFormat('en-KE',{timeZone:'Africa/Nairobi',weekday:'short',day:'numeric',month:'short'}).format(new Date(source.target_start)):'—'} />
        <Fact label="Updated" value={source?.received_at?nairobiTime(source.received_at):'—'} />
        <Fact label="Next update" value={data?.collection_automatic&&data.next_collection_at?nairobiTime(data.next_collection_at):'Manual'} />
      </dl>
      {!outlook.loading&&!data?.available_count&&<p className="text-sm mt-4">No fresh forecast. An administrator can collect one from System.</p>}
    </section>
    {(areas.error || outlook.error) && <p role="alert" className="text-sm mt-3">Some monitoring data could not be verified. Unavailable values are withheld.</p>}

    <div className="flex flex-wrap items-end justify-between gap-3 mt-8 mb-3">
      <h2 className="text-lg font-semibold">By place</h2>
      <label className="text-sm flex items-center gap-2">Sub-county<select aria-label="Weather parent zone" className="h-9 border border-border rounded-btn bg-surface px-2 text-sm" value={parent} onChange={e=>setParent(e.target.value)}>
        <option value="">All</option>{areas.data?.groups.filter(g=>g.located_count).map(g=><option key={g.id} value={g.id}>{g.name}</option>)}
      </select></label>
    </div>
    <div className="panel overflow-x-auto"><table className="w-full text-sm text-left" aria-label="Monitored-area rainfall outlook">
      <thead><tr className="text-muted">{['Place',today.data?`Next 3 h (${windowLabel(today.data.windows[0])})`:'Next 3 h','3–6 h','Today','Tomorrow','7 days','Category (tomorrow)'].map((h,i)=><th key={h} scope="col" className={`px-4 py-3 font-medium ${[1,2,4,5].includes(i)?'text-right':''}`}>{h}</th>)}</tr></thead>
      <tbody>{sites.map(site=>{const row=rows.get(site.id),fresh=row?.status==='AVAILABLE';return <tr key={site.id} className="border-t border-border hover:bg-surface-2">
        <td className="px-4 py-3"><Link className="font-medium hover:text-accent" to={`/?area=${encodeURIComponent(site.id)}&inspect=1`}>{site.display_name}</Link>
          <span className="block text-xs text-muted">{site.parent_zone_name}{local[site.id] ? <span className={local[site.id].level==='Higher'?'text-ink font-medium':''}> · {local[site.id].level==='Higher'?'floods easily':local[site.id].level==='Lower'?'higher ground':'average ground'}</span> : ''}{fresh&&row.shared_area_ids.length>1?<span title={row.shared_area_ids.map(id=>names.get(id)?.display_name || id).join(', ')}> · same weather cell as {row.shared_area_ids.length-1} other{row.shared_area_ids.length>2?'s':''}</span>:''}</span></td>
        {[0,1].map(i=>{const w=todayPoint(today.data,site.id)?.windows[i];return <td key={i} className="px-4 py-3 text-right tabular" title={w?.intensity??''}>{w&&w.rain_mm!==null?`${w.rain_mm.toFixed(1)} mm`:'—'}{w?.intensity==='heavy'&&<span className="block text-xs font-semibold text-risk-high">heavy</span>}</td>})}
        <td className="px-4 py-3">{todayPoint(today.data,site.id)?<Pill category={todayPoint(today.data,site.id).category} />:'—'}</td>
        <td className="px-4 py-3 text-right tabular">{fresh?`${row.rainfall_mm.toFixed(1)} mm`:'—'}</td>
        <td className="px-4 py-3 text-right tabular">{fresh?<>{row.accumulation_complete?'':'≥ '}{row.accumulation_7d_mm.toFixed(1)} mm</>:'—'}</td>
        <td className="px-4 py-3">{fresh?<><Pill category={row.proxy_class} /><span className="block text-xs text-muted mt-1">{row.method==='stage2_xgboost_guarded'
            ?`model${row.rule_class!==row.proxy_class?` · rule says ${row.rule_class}`:''}${row.guard_applied?' · Extreme held back':''}`
            :`rule${row.class_driver==='accumulation'?' · raised by 7-day total':''}${!row.accumulation_complete?' · inputs missing, may understate':''}`}</span></>:<span className="text-muted">Unknown</span>}</td>
      </tr>})}</tbody>
    </table></div>
    <p className="text-xs text-muted mt-3">Low does not mean safe. Places in the same weather cell share one forecast; they are not separate measurements.</p>

    {source?.source_sha256 && <details className="panel p-4 mt-6 text-sm"><summary className="cursor-pointer font-medium">Forecast source</summary><div className="mt-3 space-y-2 break-words text-muted">
      <p>Open-Meteo / ECMWF IFS, run {nairobiTime(source.run_at)}. {source.expires_at && `Treated as fresh until ${nairobiTime(source.expires_at)}.`}</p>
      <p>The 7-day total adds 5 observed satellite days (NASA IMERG Early) to the forecast. Where any input is missing the rule is used and the total is a minimum.</p>
      <p className="text-xs">Source SHA-256: <span className="font-mono">{source.source_sha256}</span></p>
      <a className="text-accent" href="https://open-meteo.com/">Weather data by Open-Meteo.com; ECMWF IFS</a> · CC BY 4.0.
    </div></details>}
    <button className="text-sm text-accent font-medium mt-6" onClick={onArchive}>Open original eight-zone forecast archive</button>
  </StaffLayout>
}

function ForecastArchive({onBack}) {
  const { authorizedRequest } = useAuth()
  const [catalogue, setCatalogue] = useState(null)
  const [selected, setSelected] = useState('')
  const [outlook, setOutlook] = useState(null)
  const [zoneId, setZoneId] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    // Recheck stored status each minute, including midnight expiry. Never fetch provider data.
    const timer = setInterval(() => setRefresh(n => n + 1), 60000)
    return () => clearInterval(timer)
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(''); setOutlook(null)
    Promise.all([
      authorizedRequest(OUTLOOK_PATH + '/snapshots?limit=200', { signal: controller.signal }),
      authorizedRequest(snapshotPath(selected), { signal: controller.signal }),
    ]).then(([list, result]) => {
      if (controller.signal.aborted) return
      const verified = validateOutlook(result, selected)
      setCatalogue(validateSnapshots(list)); setOutlook(verified)
      setZoneId(current => verified.snapshot?.zones.some(z => z.zone_id === current) ? current : (verified.snapshot?.zones[0]?.zone_id ?? ''))
    }).catch(failure => {
      if (!controller.signal.aborted) setError(failure.message)
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [authorizedRequest, selected, refresh])
  const snapshot = outlook?.snapshot
  const zone = snapshot?.zones.find(z => z.zone_id === zoneId)
  const names = ids => ids.map(id => snapshot.zones.find(z => z.zone_id === id)?.name ?? id).join(', ')
  return <StaffLayout><div className="space-y-5">
      <h1 className="text-2xl font-semibold">Original eight-zone forecast archive</h1>
      <button className="text-sm text-brand underline" onClick={onBack}>Back to monitored-location weather</button>
      <p className="text-sm">These older eight-zone snapshots are separate from the current monitored-location outlook.</p>
      <p className="text-sm text-muted">Rainfall forecasts for monitoring points. Check the target date before using a record. These are weather forecasts, not flood predictions.</p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-0">Forecast period
          <select aria-label="Forecast snapshot" className={inputClass + ' block w-full'} value={selected} onChange={e => setSelected(e.target.value)}>
            <option value="">Current or upcoming stored forecast</option>
            {(catalogue?.items ?? []).map(s => <option key={s.snapshot_id} value={s.snapshot_id}>{periodLabel(s.period_status)}: {nairobiTime(s.target_start)} / run {nairobiTime(s.forecast_initialization)}</option>)}
          </select>
        </label>
        <button className={inputClass} onClick={() => setRefresh(n => n + 1)}>Refresh stored data</button>
      </div>
      {catalogue?.total > catalogue?.items.length && <p className="text-sm">Showing the latest 200 snapshot records; older records are available through the paginated API.</p>}
      {loading && <p role="status">Verifying stored forecast sources...</p>}
      {error && <p role="alert">Forecast unavailable: {error}</p>}
      {!loading && outlook && !snapshot && <section role="status" className="bg-surface border border-border rounded-card p-4">
        <h2 className="font-semibold">{outlook.status === 'NO_CURRENT_FORECAST' ? 'No current forecast' : 'Forecast unavailable'}</h2>
        <p>{outlook.explanation}</p>
      </section>}
      {snapshot && <>
        <section className="bg-surface border border-border rounded-card p-4 space-y-2 text-sm">
          <h2 className="font-semibold">{periodLabel(snapshot.period_status)}</h2>
          <p>{outlook.explanation}</p>
          <p><strong>Target day:</strong> {nairobiTime(snapshot.target_start)} to {nairobiTime(snapshot.target_end)} (end exclusive).</p>
          <p><strong>Source received:</strong> {nairobiTime(snapshot.source_received_at)}. Target-day coverage: complete.</p>
          <p>Collection is manual. No scheduled arrival time or freshness guarantee is established.</p>
          <details><summary className="text-brand cursor-pointer">Source provenance and limitations</summary>
            <div className="mt-2 space-y-2 break-words">
              <p>ECMWF IFS initialization: {nairobiTime(snapshot.forecast_initialization)}. Issue cutoff: {nairobiTime(snapshot.issue_cutoff)}.</p>
              <p>Original publication: {snapshot.source_publication_at ? nairobiTime(snapshot.source_publication_at) : 'Unknown; initialization and receipt do not prove publication.'}</p>
              <p>Whole-source quality: {snapshot.source_quality}. Complete target-day coverage does not imply all other hours are valid.</p>
              <p>Snapshot: {snapshot.snapshot_id}</p><p>Effective readiness: {snapshot.effective_readiness}. This is a source check for a stored shadow snapshot.</p>
              <p>Requested: {nairobiTime(snapshot.source_request_started_at)}. Stored: {nairobiTime(snapshot.source_stored_at)}. Run age at check: {snapshot.run_age_hours.toFixed(1)} hours.</p>
              <p>Run identity: explicit single-run request and source time alignment. Model cycle: unverified.</p>
              <p className="break-all">Source SHA-256: {snapshot.source_sha256} ({snapshot.source_bytes} bytes).</p>
              {outlook.limitations.map(item => <p key={item}>{item}</p>)}
            </div>
          </details>
        </section>
        <section aria-label="Monitoring zone weather" className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {snapshot.zones.map(z => <button key={z.zone_id} onClick={() => setZoneId(z.zone_id)} aria-pressed={zoneId === z.zone_id} className={'text-left bg-surface border rounded-card p-4 ' + (zoneId === z.zone_id ? 'border-brand' : 'border-border')}>
            <span className="block font-semibold">{z.name}</span><span className="block text-xl">{rainfallText(z.rainfall_mm)}</span>
            <span className="text-xs text-muted">Target-day forecast precipitation · 24/24 hours</span>
          </button>)}
        </section>
        {zone && <section className="bg-surface border border-border rounded-card p-4 space-y-4">
          <label>Hourly detail for <select aria-label="Monitoring zone" className={inputClass} value={zoneId} onChange={e => setZoneId(e.target.value)}>{snapshot.zones.map(z => <option key={z.zone_id} value={z.zone_id}>{z.name}</option>)}</select></label>
          <p className="text-sm">Each amount covers the preceding hour. Amounts are summed over the physical Nairobi target day; no missing values are filled.</p>
          <div className="h-56 w-full min-w-0" aria-label="Hourly forecast precipitation chart">
            <ResponsiveContainer width="100%" height="100%"><LineChart data={zone.hourly_rainfall} margin={{ right: 20 }}>
              <XAxis dataKey="interval_end" tickFormatter={t => new Date(t).toLocaleTimeString('en-GB', { timeZone: 'Africa/Nairobi', hour: '2-digit', minute: '2-digit' })} minTickGap={40} />
              <YAxis unit=" mm" width={62} /><Tooltip labelFormatter={nairobiTime} formatter={v => [rainfallText(v), 'Forecast precipitation']} />
              <Line dataKey="precipitation_mm" name="Forecast precipitation" stroke="#2563eb" dot={false} connectNulls={false} isAnimationActive={false} />
            </LineChart></ResponsiveContainer>
          </div>
          <p className="text-sm">Shared returned grid point: {names(zone.shared_grid_zone_ids)}. Identical target weather values: {names(zone.identical_weather_zone_ids)}. These are coarse provider values, not separate local measurements.</p>
          <details><summary className="text-brand cursor-pointer">Exact rainfall intervals and other forecast fields</summary>
            <p className="text-sm mt-2">Other fields are instantaneous at the start of each rainfall interval: temperature (°C), relative humidity (%), wind (km/h) and modelled soil moisture (m³/m³).</p>
            <div className="overflow-x-auto"><table className="w-full text-sm text-left mt-3"><thead><tr>{['Rainfall interval (EAT)', 'Precipitation (mm)', 'Temperature (°C)', 'Humidity (%)', 'Wind (km/h)', 'Soil moisture (m³/m³)'].map(t => <th className="p-2" key={t}>{t}</th>)}</tr></thead><tbody>
              {zone.hourly_rainfall.map((r, i) => { const w = zone.hourly_weather[i]; return <tr key={r.interval_end} className="border-t border-border"><td className="p-2">{nairobiTime(r.interval_start)} to {nairobiTime(r.interval_end)}</td>{[r.precipitation_mm, w.temperature_2m, w.relative_humidity_2m, w.wind_speed_10m, w.soil_moisture_0_to_7cm].map((v, j) => <td key={j} className="p-2">{v}</td>)}</tr> })}
            </tbody></table></div>
          </details>
          <details><summary className="text-brand cursor-pointer">Point coordinates and quality</summary>
            <p className="text-sm mt-2">Monitoring point: {zone.monitoring_point.latitude}, {zone.monitoring_point.longitude}. Provider grid point: {zone.returned_grid_point.latitude}, {zone.returned_grid_point.longitude}; elevation {zone.returned_elevation_m} m. Point association does not establish sub-county or street-level forecast accuracy.</p>
            <p className="text-sm">Source quality {zone.source_quality}; target quality {zone.target_quality}. {zone.warnings.join('; ') || 'No source warnings.'}</p>
          </details>
        </section>}
      </>}
      {outlook && <p className="text-xs text-muted">Checked: {nairobiTime(outlook.checked_at)}. Status rechecked every minute; this reads stored data only. <a className="text-brand underline" href="https://open-meteo.com/">Weather data by Open-Meteo.com; ECMWF IFS</a> · <a className="text-brand underline" href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>. Aggregated for the Nairobi target day.</p>}
      <nav aria-label="Other analysis" className="flex flex-wrap gap-5 text-sm border-t border-border pt-4"><Link className="text-brand underline" to="/environmental-data">Historical rainfall</Link><Link className="text-brand underline" to="/research">Experimental models</Link></nav>
    </div></StaffLayout>
}
