import { useEffect, useMemo, useRef } from 'react'
import { CircleMarker, GeoJSON, MapContainer, Pane, Popup, TileLayer, useMap } from 'react-leaflet'
import { Link } from 'react-router-dom'
import { riskColor } from '../constants/colors'
import { getBoundaryBounds, safeSourceUrl } from '../services/boundaries'
import { formatPredictionTime } from '../services/predictions'
import { isZonePredictionStale, PROXY_TASK } from '../services/proxyPredictions'
import ProxyForecastDetails from './ProxyForecastDetails'
import RiskBadge from './RiskBadge'
import { HISTORICAL_STYLES } from '../services/historicalFloods'
import MonitoringAreaMapLayer from './MonitoringAreaMapLayer'
import CommunityReportLayer from './CommunityReportLayer'

function PopupCloseGuard({ onDismissArea }) {
  const map=useMap()
  useEffect(() => {
    // Stop the native event BEFORE Leaflet removes its target from the DOM.
    // Otherwise the same click can be handled by an underlying vector layer.
    const container=map.getContainer()
    const close=event => {
      if (!event.target.closest?.('.leaflet-popup-close-button')) return
      event.stopPropagation()
      if (event.type === 'click') { event.preventDefault();map.closePopup();onDismissArea?.() }
    }
    const events=['click','mousedown','pointerdown','touchstart','dblclick']
    for (const name of events) container.addEventListener(name,close,true)
    return () => { for (const name of events) container.removeEventListener(name,close,true) }
  },[map,onDismissArea])
  return null
}

function MapExtent({ bounds, fitRequest }) {
  const map = useMap()
  const fitted = useRef(false), previous = useRef(fitRequest)
  useEffect(() => {
    if (bounds && (!fitted.current || previous.current !== fitRequest)) {
      map.invalidateSize(); map.fitBounds(bounds, { padding: [20, 20], maxZoom: 12 }); fitted.current = true
    }
    previous.current = fitRequest
  }, [map, bounds, fitRequest])
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(map.getContainer())
    return () => observer.disconnect()
  }, [map])
  return null
}

function HistoricalExtent({ historical }) {
  const map = useMap(), previous = useRef(0)
  useEffect(() => {
    if (!historical?.data || !historical.fitRequest || previous.current === historical.fitRequest) return
    const bounds = getBoundaryBounds(historical.data.layers.coverage)
    if (bounds) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 13 })
    previous.current = historical.fitRequest
  }, [map, historical?.data, historical?.fitRequest])
  return null
}

function accessibleBoundary(feature, layer) {
  layer.on('add', () => {
    const element = layer.getElement()
    element?.setAttribute('tabindex', '0'); element?.setAttribute('role', 'button')
    element?.setAttribute('aria-label', `${feature.properties.name} sub-county boundary`)
    if (element) element.onkeydown = event => {
      if (['Enter', ' '].includes(event.key)) { event.preventDefault(); layer.openPopup(layer.getBounds().getCenter()) }
    }
  })
}

function BoundaryPopup({ feature, zones, monitoringAreas }) {
  const p = feature.properties, source = safeSourceUrl(p.source_url)
  const points = zones.filter(z => p.monitoring_zone_ids.includes(z.id))
  return <div className="p-3 space-y-2 text-ink">
    <h3 className="font-semibold">{p.name}</h3>
    <p className="text-xs">Sub-county (constituency) outline · OpenStreetMap, {p.source_year}</p>
    <p className="text-xs">This outline provides geographic context. It is not a flood boundary or a model prediction.</p>
    {monitoringAreas ? <><p className="text-xs">Monitored area records: {monitoringAreas.filter(a => a.parent_zone_id === feature.id).length}.</p>
      <Link className="text-xs underline text-brand" to={`/?zone=${encodeURIComponent(feature.id)}`}>Explore monitored areas in {p.name} →</Link></>
      : <p className="text-xs">Monitoring locations: {points.map(z => z.name).join(', ') || 'None loaded in this boundary'}.</p>}
    <p className="text-xs text-muted">Source: {source ? <a href={source} target="_blank" rel="noopener noreferrer" className="underline">{p.source}</a> : p.source} · {p.source_license}</p>
  </div>
}

// Geography is neutral by default. Only the dedicated research screen opts into model markers.
export default function MapView({ zones = [], boundaries, boundaryRevision, showPolygons = true, showMarkers = true,
  fitRequest = 0, height = '100%', historical, showModelOutputs = false, pointHref, pointActionLabel = 'Open report inbox',
  monitoringAreas, showMonitoringAreas = false, selectedAreaId, onInspectArea, onDismissArea, monitoringOutlook, susceptibility, outlookDay = 'tomorrow', todayOutlook = null,
  communityReports, showCommunityReports = false, children }) {
  const bounds = useMemo(() => getBoundaryBounds(boundaries), [boundaries])
  const features = boundaries?.features ?? []
  const subcounties = features.filter(f => f.properties.admin_level === 2)
  return <MapContainer center={[-1.286, 36.817]} zoom={12} zoomAnimation={false} style={{ height, width: '100%' }}>
    <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
    <MapExtent bounds={bounds} fitRequest={fitRequest} /><HistoricalExtent historical={historical} />
    <PopupCloseGuard onDismissArea={onDismissArea} />
    <Pane name="subcounties" style={{ zIndex: 390 }}>
      {showPolygons && subcounties.map(feature => <GeoJSON key={`${feature.id}-${boundaryRevision}`} data={feature}
        className="subcounty-boundary" style={{ color: '#64748b', weight: 1.5, fillColor: '#64748b', fillOpacity: 0.035 }}
        onEachFeature={accessibleBoundary}
        attribution='Sub-county and county outlines: <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> (ODbL)'>
        <Popup maxHeight={260}><BoundaryPopup feature={feature} zones={zones} monitoringAreas={monitoringAreas} /></Popup>
      </GeoJSON>)}
    </Pane>
    <Pane name="county" style={{ zIndex: 395, pointerEvents: 'none' }}>
      {features.filter(f => f.properties.admin_level === 1).map(feature => <GeoJSON key={`${feature.id}-${boundaryRevision}`}
        data={feature} interactive={false} className="county-boundary" style={{ color: '#334155', weight: 2.5, fill: false }}
        attribution='Sub-county and county outlines: <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> (ODbL)' />)}
    </Pane>
    {historical?.data && ['coverage', 'flood', 'cloud'].map((kind, i) => <Pane key={kind} name={'historical-' + kind} style={{ zIndex: 405 + i * 5 }}>
      {historical.visible[kind] && <GeoJSON data={historical.data.layers[kind]} className={'historical-' + kind} style={HISTORICAL_STYLES[kind]}
        attribution='Historical vectors: <a href="https://unosat.org/products/3833">UNITAR-UNOSAT / Pléiades, 1 May 2024</a>'
        onEachFeature={(feature, layer) => layer.on('add', () => {
          const el = layer.getElement(); el?.setAttribute('tabindex', '0'); el?.setAttribute('role', 'button')
          el?.setAttribute('aria-label', `Historical UNOSAT ${kind}, 1 May 2024; show source and limitations`)
          if (el) el.onkeydown = event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); layer.openPopup(layer.getBounds().getCenter()) } }
        })}>
        <Popup maxHeight={240}><div className="p-3 space-y-2">
          <strong>Historical satellite {kind === 'flood' ? 'water detection' : kind === 'coverage' ? 'analysis footprint' : 'cloud obstruction'}</strong>
          <p>1 May 2024, 11:06 EAT / 08:06 UTC. UNITAR-UNOSAT / Pléiades.</p>
          <p>Preliminary; not field validated. Outside coverage or under cloud is unknown. No detection does not mean flood-free.</p>
          <p>This is historical evidence. It is not a current flood observation or predicted extent. No depth is provided.</p>
          <a href="https://unosat.org/products/3833" target="_blank" rel="noopener noreferrer">Official source · product 3833</a>
        </div></Popup>
      </GeoJSON>}
    </Pane>)}
    {showMarkers && zones.map(zone => {
      const stale = showModelOutputs && isZonePredictionStale(zone)
      const displayedRisk = stale && zone.modelTaskType !== PROXY_TASK ? 'Unknown' : zone.risk
      const color = showModelOutputs ? riskColor(displayedRisk) : '#2563eb'
      const boundaryName = subcounties.find(f => f.properties.monitoring_zone_ids.includes(zone.id))?.properties.name
      return <CircleMarker key={zone.id} center={[zone.lat, zone.lon]} radius={showModelOutputs ? 9 : 7}
        className="monitoring-point" pathOptions={{ color, fillColor: color, fillOpacity: 0.85, weight: 1.5 }}
        eventHandlers={{ add: event => {
          const el = event.target.getElement()
          el?.setAttribute('tabindex', '0'); el?.setAttribute('role', 'button'); el?.setAttribute('aria-label', `${zone.name} monitoring location`)
          if (el) el.onkeydown = key => { if (['Enter', ' '].includes(key.key)) { key.preventDefault(); event.target.openPopup() } }
        } }}>
        <Popup maxHeight={300}><div className="p-3 space-y-2 text-ink">
          <h3 className="font-semibold">{zone.name}</h3>
          <p className="text-xs text-muted">Monitoring location{boundaryName ? ` · ${boundaryName} sub-county` : ''}</p>
          <p className="text-xs">{zone.lat.toFixed(5)}, {zone.lon.toFixed(5)}</p>
          {showModelOutputs ? <>
            <p className="text-xs font-semibold">Experimental model output · not a flood warning</p>
            <RiskBadge risk={displayedRisk} size="sm" />
            {stale && <p className="text-xs">Expired saved result; no current class is confirmed.</p>}
            {zone.modelTaskType === PROXY_TASK && <ProxyForecastDetails zone={zone} />}
            <p className="text-xs text-muted">Saved issue: {formatPredictionTime(zone.timestamp)}</p>
          </> : <p className="text-xs">This pin marks a study location. It does not indicate flooding or that the area is safe.</p>}
          {pointHref && <Link className="text-xs text-brand underline block" to={pointHref(zone.id)}>{pointActionLabel}</Link>}
        </div></Popup>
      </CircleMarker>
    })}
    <CommunityReportLayer reports={communityReports} visible={showCommunityReports} />
    <MonitoringAreaMapLayer sites={monitoringAreas || []} visible={showMonitoringAreas} selectedId={selectedAreaId} boundaryRevision={boundaryRevision} onInspect={onInspectArea} outlook={monitoringOutlook} susceptibility={susceptibility} when={outlookDay} today={todayOutlook} />
    {children}
  </MapContainer>
}
