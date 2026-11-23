import L from 'leaflet'
import { useEffect, useMemo } from 'react'
import { CircleMarker, Pane, useMap } from 'react-leaflet'
import { groupAreaPoints } from '../services/monitoringAreas'
import { pointCategory } from '../services/monitoringOutlook'
import { riskColor } from '../constants/colors'
import { pointSusceptibility } from '../services/susceptibility'

const NO_OUTLOOK='#94a3b8', RING='#111827', SELECTED='#2563eb'

// Bring the selected pin into the part of the map the card leaves visible:
// above the bottom sheet on phones, left of the side card on wider screens.
// (Re-run when the outlines arrive: fitting the county must not undo the focus.)
function FocusSelected({ point, revision }) {
  const map=useMap()
  useEffect(() => {
    if (!point) return
    map.setView([point.lat,point.lon],Math.max(map.getZoom(),15),{ animate:false })
    const { x, y }=map.getSize()
    map.panBy(x < 768 ? [0, Math.round(y*0.24)] : [Math.min(212, Math.round(x*0.18)), 0],{ animate:false })
  },[map,point,revision])
  return null
}

// Pins are coloured by the rainfall-risk category; grey when no fresh outlook exists.
// One tap opens the place's card (no intermediate popup).
export default function MonitoringAreaMapLayer({ sites, selectedId, visible, boundaryRevision, onInspect, outlook, susceptibility, when = 'tomorrow' }) {
  const points=useMemo(() => groupAreaPoints(sites),[sites])
  const selected=points.find(p => p.sites.some(s => s.id === selectedId))
  if (!visible) return null
  return <>
    <FocusSelected point={selected?.point} revision={boundaryRevision} />
    <Pane name="monitored-areas" style={{ zIndex:450 }}>
      {selected && <CircleMarker key={`halo-${selected.key}`} center={[selected.point.lat,selected.point.lon]} radius={18} interactive={false}
        className="selected-area-halo" pathOptions={{ color:SELECTED, weight:2.5, fillColor:SELECTED, fillOpacity:0.16 }} />}
      {points.map(point => {
        const first=point.sites[0], approximate=!['LANDMARK_REFERENCE','USER_REPORTED_LOCATION'].includes(first.reference_kind)
        const category=pointCategory(outlook,point.sites.map(s=>s.id)), color=category ? riskColor(category) : NO_OUTLOOK
        // A dark ring marks places that flood more easily than most (terrain, rivers, past flooding).
        const local=pointSusceptibility(susceptibility,point.sites.map(s=>s.id)), ringed=local?.level==='Higher'
        const isSelected=point === selected
        const open=event => { if (event) L.DomEvent.stopPropagation(event); onInspect?.(first.id) }
        // Keyed by category so the pin's class and accessible label update when the outlook arrives or expires.
        return <CircleMarker key={`${point.key}-${when}-${category||'none'}-${local?.level||'none'}-${isSelected}`}
          center={[point.point.lat,point.point.lon]} radius={(point.sites.length > 1 ? 10 : 8) + (isSelected ? 2 : 0)}
          className={`monitored-area risk-${(category||'none').toLowerCase()}${ringed ? ' susceptibility-higher' : ''}${isSelected ? ' selected-area' : ''}`}
          pathOptions={{ color:isSelected ? '#ffffff' : ringed ? RING : '#ffffff',fillColor:color,fillOpacity:approximate ? .7 : .95,weight:ringed || isSelected ? 3.5 : 2,dashArray:approximate && !isSelected ? '3 2' : undefined }}
          attribution='Reference locations: user-supplied coordinate lookup and <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors / ODbL</a>'
          eventHandlers={{ click:open, add:event => {
            const element=event.target.getElement()
            element?.setAttribute('tabindex','0');element?.setAttribute('role','button')
            element?.setAttribute('aria-label',`${first.display_name}, ${first.parent_zone_name}: ${category ? `${category} rainfall risk ${when === 'today' ? 'today' : 'tomorrow'}` : 'no current rainfall outlook'}${ringed ? ', floods more easily than most' : ''}${point.sites.length>1 ? `, ${point.sites.length} records at this reference` : ''}`)
            if (element) element.onkeydown=key => { if (['Enter',' '].includes(key.key)) { key.preventDefault();open() } }
          } }} />
      })}
    </Pane>
  </>
}
