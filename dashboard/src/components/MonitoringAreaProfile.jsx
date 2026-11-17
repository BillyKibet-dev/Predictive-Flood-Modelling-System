import { EVIDENCE_LABELS, REFERENCE_LABELS, nearbyWaterSummary } from '../services/monitoringAreas'
import { safeSourceUrl } from '../services/boundaries'

function SourceLink({ url, children }) {
  const safe = safeSourceUrl(url)
  return safe ? <a className="text-brand underline" href={safe} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>
}

function ContextDetails({ profile, technical }) {
  return <details className="text-xs text-muted mt-2"><summary className="cursor-pointer">Method and source</summary>
    <div className="space-y-2 mt-2 break-words"><p>{profile.method}</p><p>{profile.resolution}</p>
      {profile.source_url && <SourceLink url={profile.source_url}>Dataset documentation</SourceLink>}
      {profile.source && <><p>Retrieved {profile.source.received_at_utc}</p>
        {technical && <p>Evidence SHA-256: <span className="break-all">{profile.source.raw.sha256}</span></p>}</>}
      <p>{profile.limitations}</p></div>
  </details>
}

// technical: show evidence hashes (signed-in staff only).
export default function MonitoringAreaProfile({ site, sources = [], technical = false }) {
  if (!site) return <p className="text-muted">Select a monitored area to view its location and geographic context.</p>
  const { terrain, vegetation, drainage } = site
  const nearest = drainage.nearest_mapped_waterway
  return <article aria-label={`${site.display_name} monitored area profile`} className="space-y-5">
    <div><p className="text-xs text-muted">{site.id} · Zone: {site.parent_zone_name}</p>
      <h2 className="text-xl font-semibold mt-1">{site.display_name}</h2>
      <p className="text-sm mt-2">{REFERENCE_LABELS[site.reference_kind]}{site.point ? ' · needs field verification' : ' · no map pin'}</p>
      {site.point && <><p className="text-sm text-muted mt-1">{site.point.lat.toFixed(6)}, {site.point.lon.toFixed(6)}</p>
        </>}
      <p className="text-xs text-muted mt-2">{site.location.description || site.location.reason}</p>
      {site.reference_kind === 'USER_REPORTED_LOCATION' && <p className="text-xs text-muted mt-2">Supplied location: {site.location.original_coordinate_text}. Event dates, measured flood depth and surveyed accuracy have not been established.</p>}
      <p className="text-xs text-muted mt-2">{site.point ? `Parent zone assigned using the reference point and the ${site.administrative_context[0]?.source_year || ''} administrative polygons.` : 'Parent zone is tentative until the location is established.'}</p>
    </div>
    <details className="text-sm"><summary className="cursor-pointer font-semibold">Historical context and sources</summary>
      <p className="text-xs mt-2">Source record: {site.name}</p>
      {site.historical_evidence_spatial_note && <p className="text-xs text-muted mt-2">{site.historical_evidence_spatial_note}</p>}
      <p className="text-xs text-muted mt-1">{EVIDENCE_LABELS[site.evidence_category]} · {site.evidence_date}</p>
      <p className="text-sm mt-2">{site.evidence_summary}</p>
      <p className="text-xs text-muted mt-2">Reported mechanism (unverified): {site.reported_mechanism_hypothesis}.</p>
      <ul className="text-xs space-y-2 mt-2">{sources.filter(s => site.source_ids.includes(s.source_id)).map(s =>
        <li key={s.source_id}><SourceLink url={s.url}>{s.title}</SourceLink> · {s.source_date}</li>)}</ul>
      <p className="text-xs text-muted mt-2">Historical press reports and warnings are evidence leads, not field-validated flood measurements.</p>
    </details>
    <details className="nearby-water-reference text-sm"><summary className="cursor-pointer font-semibold">Historical nearby-water reference · 1 May 2024</summary>
      <div className="space-y-2 mt-3">
        <p>{nearbyWaterSummary(site.nearby_water_reference)}</p>
        <p className="text-xs text-muted">UNITAR-UNOSAT / Pléiades, acquired 1 May 2024 at 11:06 EAT. Preliminary satellite interpretation, not field validated.</p>
        <p className="text-xs text-muted">The 500 m window is a reference search area. Nearby satellite-mapped water does not confirm flooding at this point. Missing coverage, cloud and no mapped water do not establish safety.</p>
        <p className="text-xs text-muted">This is dated historical context, independent of current flood conditions and model predictions.</p>
        <SourceLink url={site.nearby_water_reference.source_product_url}>UNOSAT source · event FL20240426KEN</SourceLink>
      </div>
    </details>
    <section><h3 className="font-semibold text-sm">Terrain context</h3>
      {terrain.status === 'DERIVED_CONTEXT' ? <><div className="flex flex-wrap gap-x-6 gap-y-2 text-sm mt-2"><p>Elevation <strong>≈ {Math.round(terrain.elevation_m)} m</strong></p><p>Surface slope <strong>≈ {terrain.slope_degrees.toFixed(1)}°</strong></p></div>
        <p className="text-xs text-muted mt-2">Copernicus 30 m surface model. Buildings and vegetation affect these values; roadside drainage is unresolved.</p>
        <ContextDetails profile={terrain} technical={technical} /></> : <p className="text-sm text-muted mt-2">{terrain.reason}</p>}
    </section>
    <section><h3 className="font-semibold text-sm">Vegetation context</h3>
      {vegetation.value != null ? <><p className="text-sm mt-2">NDVI <strong>{vegetation.value.toFixed(3)}</strong> · {vegetation.acquired_at_utc.slice(0, 10)}</p>
        <p className="text-xs text-muted mt-2">One Sentinel-2 pixel at the reference point. Lower values indicate less green vegetation in that pixel; this is not a flood-risk score.</p>
        <ContextDetails profile={vegetation} technical={technical} /></> : <><p className="text-sm text-muted mt-2">{vegetation.status === 'WITHHELD_QUALITY' ? 'Withheld: the pixel did not pass the declared vegetation quality checks.' : vegetation.reason}</p>
        {vegetation.source && <ContextDetails profile={vegetation} technical={technical} />}</>}
    </section>
    <section><h3 className="font-semibold text-sm">Drainage context</h3>
      {nearest ? <><p className="text-sm mt-2">Nearest mapped waterway in the reviewed extract: {nearest.name}, approximately {Math.round(nearest.distance_m)} m from the reference point.</p>
        {drainage.mapped_culverts.length > 0 && <p className="text-xs text-muted mt-2">{drainage.mapped_culverts.length} mapped culvert segments in this extract; capacity and condition are unknown.</p>}</>
        : <p className="text-sm text-muted mt-2">{drainage.status === 'NOT_MAPPED_IN_EXTRACT' ? 'No waterway was mapped in this bounded extract. Local drains may still exist.' : drainage.reason}</p>}
      <p className="text-xs text-muted mt-2">Drain condition, blockage and capacity need a field or county drainage survey.</p>
      {drainage.source && <ContextDetails profile={drainage} technical={technical} />}
    </section>
    {site.landcover?.status === 'DERIVED_CONTEXT' && <section><h3 className="font-semibold text-sm">Land-cover context · 2021</h3>
      <p className="text-sm mt-2">Built-up cover <strong>{(site.landcover.built_up_fraction*100).toFixed(1)}%</strong> · Vegetation cover <strong>{(site.landcover.vegetation_fraction*100).toFixed(1)}%</strong></p>
      <p className="text-xs text-muted mt-2">ESA WorldCover, 500 m context box. Built-up cover approximates development; it does not measure sealed surface or drain capacity.</p>
      <ContextDetails profile={site.landcover} technical={technical} />
    </section>}
    <p className="border-t border-border pt-3 text-xs text-muted">This profile provides historical evidence and geographic context. It does not report current flooding, flood probability, inundation extent or depth.</p>
  </article>
}
