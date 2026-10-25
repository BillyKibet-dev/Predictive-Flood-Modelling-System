import { Fragment, useEffect, useMemo, useRef } from 'react'
import { CircleMarker, GeoJSON, MapContainer, Pane, Popup, TileLayer, useMap } from 'react-leaflet'
import { useNavigate } from 'react-router-dom'
import { RISK_OPACITY, RISK_RADIUS, riskColor } from '../constants/colors'
import { getBoundaryBounds, safeSourceUrl, summarizeBoundary } from '../services/boundaries'
import { formatConfidence, formatPredictionTime, isPredictionStale } from '../services/predictions'
import RiskBadge from './RiskBadge'

function MapExtent({ bounds, fitRequest }) {
  const map = useMap()
  const fitted = useRef(false)
  const previousRequest = useRef(fitRequest)
  useEffect(() => {
    if (bounds && (!fitted.current || previousRequest.current !== fitRequest)) {
      map.invalidateSize()
      map.fitBounds(bounds, { padding: [20, 20], maxZoom: 12 })
      fitted.current = true
    }
    previousRequest.current = fitRequest
  }, [map, bounds, fitRequest])
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(map.getContainer())
    return () => observer.disconnect()
  }, [map])
  return null
}

function accessibleBoundary(feature, layer) {
  layer.on('add', () => {
    const element = layer.getElement()
    element?.setAttribute('tabindex', '0')
    element?.setAttribute('role', 'button')
    element?.setAttribute('aria-label', `${feature.properties.name} sub-county: show monitored risk`)
    if (element) element.onkeydown = (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        layer.fire('click', { latlng: layer.getBounds().getCenter() }, true)
      }
    }
  })
}

function BoundaryPopup({ feature, summary, viewDetails }) {
  const { properties } = feature
  const sourceUrl = safeSourceUrl(properties.source_url)
  return (
    <div className="p-4 space-y-2">
      <h3 className="text-base font-semibold text-ink">{properties.name}</h3>
      <p className="text-xs text-muted">Sub-county · {properties.source_year} boundary</p>
      <RiskBadge risk={summary.risk} size="sm" />
      <p className="text-xs text-muted">
        {summary.monitoringCount ? 'Highest available risk among monitoring points in this boundary.' : 'No monitoring point in this boundary. Risk is unknown.'}
      </p>
      {summary.missingCount > 0 && <p className="text-xs text-risk-mod">{summary.missingCount} monitoring point(s) have no prediction available.</p>}
      {summary.stale && <p className="text-xs text-risk-mod">Includes predictions older than expected. Check update times below.</p>}
      {summary.monitoredZones.map((zone) => (
        <div key={zone.id} className="border-t border-border pt-2 space-y-1">
          <button type="button" onClick={() => viewDetails(zone.id)} className="text-sm font-semibold text-ink underline">{zone.name}</button>
          <div><RiskBadge risk={zone.risk} size="sm" /></div>
          <p className="text-xs text-muted">Model score: {formatConfidence(zone.confidence)}</p>
          <p className="text-xs text-muted">Updated: {formatPredictionTime(zone.timestamp)}</p>
        </div>
      ))}
      <p className="text-xs text-muted border-t border-border pt-2">
        Source: {sourceUrl ? <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="underline">{properties.source}</a> : properties.source}
        {' · '}{properties.source_license}
      </p>
    </div>
  )
}

export default function MapView({ zones, boundaries, boundaryRevision, showPolygons = true, showMarkers = true, fitRequest = 0, height = '100%' }) {
  const navigate = useNavigate()
  const bounds = useMemo(() => getBoundaryBounds(boundaries), [boundaries])
  const features = boundaries?.features ?? []
  const subcounties = features.filter((feature) => feature.properties.admin_level === 2)
  const viewDetails = (zoneId) => navigate(`/citizen#zone-${zoneId}`)

  function getDirections(lat, lon) {
    window.open(`https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}`, '_blank', 'noopener')
  }

  return (
    <MapContainer center={[-1.286, 36.817]} zoom={12} style={{ height, width: '100%' }}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <MapExtent bounds={bounds} fitRequest={fitRequest} />
      <Pane name="subcounties" style={{ zIndex: 390 }}>
        {showPolygons && subcounties.map((feature) => {
          const summary = summarizeBoundary(feature, zones)
          const color = riskColor(summary.risk)
          return (
            <GeoJSON key={`${feature.id}-${boundaryRevision}`} data={feature} className="subcounty-boundary"
              style={{ color, fillColor: color, weight: 2, fillOpacity: summary.risk === 'Unknown' ? 0.12 : 0.28, dashArray: summary.stale ? '6 4' : null }}
              onEachFeature={accessibleBoundary}
              attribution='Sub-counties: <a href="https://www.geoboundaries.org/">geoBoundaries</a> / IEBC / OCHA ROSEA (<a href="https://creativecommons.org/licenses/by/3.0/igo/">CC BY 3.0 IGO</a>)'>
              <Popup maxHeight={310}><BoundaryPopup feature={feature} summary={summary} viewDetails={viewDetails} /></Popup>
            </GeoJSON>
          )
        })}
      </Pane>
      <Pane name="county" style={{ zIndex: 395, pointerEvents: 'none' }}>
        {features.filter((feature) => feature.properties.admin_level === 1).map((feature) => (
          <GeoJSON key={`${feature.id}-${boundaryRevision}`} data={feature} interactive={false} className="county-boundary"
            style={{ color: '#334155', weight: 2.5, fill: false }}
            attribution='County: RCMRD / Africa GeoPortal via <a href="https://www.geoboundaries.org/">geoBoundaries</a> (Public Domain)' />
        ))}
      </Pane>
      {showMarkers && zones.map((zone) => {
        const color = riskColor(zone.risk)
        const boundaryName = subcounties.find((feature) => feature.properties.monitoring_zone_ids.includes(zone.id))?.properties.name
        return (
          <Fragment key={zone.id}>
            {zone.risk === 'Extreme' && (
              <CircleMarker center={[zone.lat, zone.lon]} radius={RISK_RADIUS[zone.risk] + 10} className="pulse-marker"
                pathOptions={{ color, fillColor: color, fillOpacity: 0.25, weight: 0 }} interactive={false} />
            )}
            <CircleMarker center={[zone.lat, zone.lon]} radius={RISK_RADIUS[zone.risk]} className="monitoring-point"
              pathOptions={{ color, fillColor: color, fillOpacity: RISK_OPACITY[zone.risk], weight: 1.5 }}>
              <Popup>
                <div className="p-4 space-y-2">
                  <div>
                    <h3 className="text-base font-semibold text-ink leading-tight">{zone.name}</h3>
                    <p className="text-xs text-muted">{boundaryName ? `${boundaryName} sub-county` : 'Monitoring location'}</p>
                  </div>
                  <RiskBadge risk={zone.risk} size="sm" />
                  <p className="text-sm text-ink">24h Rainfall: Unavailable</p>
                  <p className="text-sm text-ink">Model score: {formatConfidence(zone.confidence)}</p>
                  <p className="text-xs text-muted">Updated: {formatPredictionTime(zone.timestamp)}</p>
                  {isPredictionStale(zone.timestamp) && <p className="text-xs text-risk-mod">Prediction is older than expected.</p>}
                  <div className="border-t border-border pt-2 flex gap-2">
                    <button onClick={() => viewDetails(zone.id)} className="flex-1 text-xs font-medium border border-border rounded-btn px-2 py-1.5 hover:bg-bg transition-colors">View Details</button>
                    <button onClick={() => getDirections(zone.lat, zone.lon)} className="flex-1 text-xs font-medium rounded-btn px-2 py-1.5 text-brand hover:bg-bg transition-colors">Get Directions</button>
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          </Fragment>
        )
      })}
    </MapContainer>
  )
}
