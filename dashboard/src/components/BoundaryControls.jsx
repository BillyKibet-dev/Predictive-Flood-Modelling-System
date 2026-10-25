export default function BoundaryControls({ boundaries, showPolygons, setShowPolygons, showMarkers, setShowMarkers, fitCounty }) {
  const { data, error, isLoading, reload } = boundaries
  const subcounties = data?.features.filter((feature) => feature.properties.admin_level === 2) ?? []
  let message = `${subcounties.length} sub-counties · Colours show highest monitored risk.`
  if (!data) message = isLoading ? 'Loading administrative boundaries...' : 'Boundaries unavailable. Monitoring points remain available.'
  else if (error) message = 'Could not refresh boundaries. Showing saved outlines.'
  else if (!data.features.length) message = 'No administrative boundaries loaded.'
  else if (!subcounties.length) message = 'County outline only. Sub-county boundaries have not been loaded.'

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
      <p role="status" className={error ? 'text-risk-mod' : 'text-muted'}>{message}</p>
      <div className="flex flex-wrap items-center gap-3 sm:ml-auto">
        <label className="flex items-center gap-1.5 text-ink">
          <input type="checkbox" checked={showPolygons} onChange={(event) => setShowPolygons(event.target.checked)} disabled={!subcounties.length} />
          Sub-county risk
        </label>
        <label className="flex items-center gap-1.5 text-ink">
          <input type="checkbox" checked={showMarkers} onChange={(event) => setShowMarkers(event.target.checked)} />
          Monitoring points
        </label>
        <button type="button" onClick={fitCounty} disabled={!data?.features.length} className="rounded-btn border border-border px-2 py-1.5 text-ink disabled:opacity-50">Fit county</button>
        <button type="button" onClick={reload} disabled={isLoading} className="rounded-btn border border-border px-2 py-1.5 text-ink disabled:opacity-50">
          {isLoading ? 'Loading outlines...' : error ? 'Retry boundaries' : 'Reload boundaries'}
        </button>
      </div>
    </div>
  )
}
