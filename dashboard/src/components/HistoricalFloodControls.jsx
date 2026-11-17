import { useState } from 'react'
import { HISTORICAL_STYLES, POINT_LABELS } from '../services/historicalFloods'

const labels = { flood: 'Satellite-detected historical water', coverage: 'Analysed area boundary', cloud: 'Mapped cloud obstruction' }
export default function HistoricalFloodControls({ historical }) {
  const [zoneId, setZoneId] = useState('mathare')
  const { allowed, enabled, setEnabled, data, error, loading, visible, setVisible, retry } = historical
  if (!allowed) return <p className="text-muted mt-3">Historical satellite evidence: sign in as an officer or administrator to inspect the research layers.</p>
  const point = data?.metadata.monitoring_points.find(p => p.zone_id === zoneId)
  const areas = data?.metadata.administrative_context.filter(a => a.monitoring_zone_ids.includes(zoneId)) ?? []
  return <section className="border-t border-border mt-3 pt-3 space-y-2" aria-label="Historical UNOSAT evidence">
    <label className="flex items-center gap-2 font-semibold"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />Historical UNOSAT · 1 May 2024</label>
    {enabled && <>
      {loading && <p role="status">Verifying historical satellite layers...</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && <button type="button" onClick={retry} className="border border-border rounded-btn px-2 py-1">{error ? 'Retry satellite evidence' : 'Recheck satellite evidence'}</button>}
      {data && <>
        <button type="button" onClick={historical.fit} className="border border-border rounded-btn px-2 py-1">Fit historical coverage</button>
        <p>Acquired 1 May 2024, 11:06 EAT (08:06 UTC). This is historical satellite interpretation, not a current flood map or predicted inundation.</p>
        {Object.keys(labels).map(kind => <label className="flex items-center gap-2" key={kind}>
          <input type="checkbox" checked={visible[kind]} onChange={e => setVisible(v => ({ ...v, [kind]: e.target.checked }))} />
          <span aria-hidden="true" className="inline-block w-5 h-3 border-2" style={{ borderColor: HISTORICAL_STYLES[kind].color, backgroundColor: kind === 'coverage' ? 'transparent' : HISTORICAL_STYLES[kind].fillColor, borderStyle: kind === 'coverage' ? 'dashed' : 'solid' }} />{labels[kind]}
        </label>)}
        <p>Outside the analysed footprint: unknown. Clouds: unassessable. No detection does not mean flood-free. Other no-data masks were not supplied.</p>
        <label className="block">Monitoring point <select className="bg-surface border border-border rounded-btn p-1 max-w-full" value={zoneId} onChange={e => setZoneId(e.target.value)} aria-label="Historical observation point">{data.metadata.monitoring_points.map(p => <option key={p.zone_id} value={p.zone_id}>{p.name}</option>)}</select></label>
        {point && <p role="status">{point.name}: {POINT_LABELS[point.observation_state]}</p>}
        {areas.map(a => <p key={a.boundary_id}>{a.name} administrative context: {a.usable_coverage_percent.toFixed(1)}% usable analysis coverage; {a.cloud_percent.toFixed(1)}% mapped cloud; {a.outside_analysis_percent.toFixed(1)}% outside analysis. Source-detected water within usable coverage: {a.detected_water_usable_km2.toFixed(3)} km². This boundary is not the original monitoring rectangle.</p>)}
        <details><summary className="cursor-pointer text-brand">Source and interpretation limits</summary>
          <p>UNITAR-UNOSAT / Pléiades. Preliminary; not field validated. Confidence: to be evaluated. Acquisition time is not flood onset.</p>
          <p>Product 3833 published 3 May 2024. Its linked event archive contains a broader Nairobi–Kiambu layer; the archive revision publication time is unknown.</p>
          <p>Flood topology repaired for valid geometry; web display simplified at 1 m in UTM 37S. Coverage summaries use full-resolution repaired data. Point results and administrative overlaps are different spatial supports.</p>
          <p>Small source-water slivers overlap cloud or extend beyond the analysed footprint. Those portions remain unassessable; blue mapping alone does not establish usable observation coverage.</p>
          <p><a href="https://unosat.org/products/3833" target="_blank" rel="noopener noreferrer" className="underline">Official source</a> · <a href="https://unitar.org/legal" target="_blank" rel="noopener noreferrer" className="underline">UNITAR research/non-commercial terms</a>. Imagery © CNES 2024 / Airbus; imagery is not redistributed here.</p>
        </details>
      </>}
    </>}
  </section>
}
