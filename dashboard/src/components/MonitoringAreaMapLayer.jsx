import { useEffect, useMemo, useRef } from 'react'
import { CircleMarker, Pane, Popup, useMap } from 'react-leaflet'
import { groupAreaPoints } from '../services/monitoringAreas'
import { outlookPoint, plainSummary, pointCategory } from '../services/monitoringOutlook'
import { todayPoint, windowLabel } from '../services/todayOutlook'
import { riskColor } from '../constants/colors'
import RiskBadge from './RiskBadge'
import { useLanguage } from '../context/LanguageContext'
import { pointSusceptibility, susceptibilityText, watchClosely } from '../services/susceptibility'

const NO_OUTLOOK='#94a3b8', RING='#111827'

// Pins are coloured by tomorrow's rainfall-risk category; grey when no fresh outlook exists.
export default function MonitoringAreaMapLayer({ sites, selectedId, visible, boundaryRevision, onInspect, outlook, susceptibility, when = 'tomorrow', today = null }) {
  const map=useMap(), markers=useRef({}), { lang, t }=useLanguage()
  const points=useMemo(() => groupAreaPoints(sites),[sites])
  const selected=points.find(p => p.sites.some(s => s.id === selectedId))
  // The selected pin is re-created when its category changes, so its popup must be reopened then too.
  const selectedCategory=selected ? pointCategory(outlook,selected.sites.map(s => s.id)) : null
  // Likewise when the susceptibility ring arrives (it is part of the pin's key).
  const selectedLocal=selected ? pointSusceptibility(susceptibility,selected.sites.map(s => s.id))?.level ?? null : null
  // Close only this layer's popups, never another layer's (e.g. a community report).
  useEffect(() => { if (!selectedId) Object.values(markers.current).forEach(m => m.closePopup()) },[selectedId])
  useEffect(() => {
    if (!visible || !selected) return
    map.setView([selected.point.lat,selected.point.lon],16,{ animate:false })
    markers.current[selected.key]?.openPopup()
  },[map,selected,visible,boundaryRevision,selectedCategory,selectedLocal,when])
  if (!visible) return null
  return <Pane name="monitored-areas" style={{ zIndex:450 }}>
    {points.map(point => {
      const first=point.sites[0], approximate=!['LANDMARK_REFERENCE','USER_REPORTED_LOCATION'].includes(first.reference_kind)
      const category=pointCategory(outlook,point.sites.map(s=>s.id)), color=category ? riskColor(category) : NO_OUTLOOK
      // A dark ring marks places that flood more easily than most (terrain, rivers, past flooding).
      const local=pointSusceptibility(susceptibility,point.sites.map(s=>s.id)), ringed=local?.level==='Higher'
      // Keyed by category so the pin's class and accessible label update when the outlook arrives or expires.
      return <CircleMarker key={`${point.key}-${when}-${category||'none'}-${local?.level||'none'}`} ref={marker => { if (marker) markers.current[point.key]=marker; else delete markers.current[point.key] }}
        center={[point.point.lat,point.point.lon]} radius={point.sites.length > 1 ? 10 : 8} className={`monitored-area risk-${(category||'none').toLowerCase()}${ringed ? ' susceptibility-higher' : ''}`}
        pathOptions={{ color:ringed ? RING : '#ffffff',fillColor:color,fillOpacity:approximate ? .7 : .95,weight:ringed ? 3.5 : 2,dashArray:approximate ? '3 2' : undefined }}
        attribution='Reference locations: user-supplied coordinate lookup and <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors / ODbL</a>'
        eventHandlers={{ add:event => {
          const element=event.target.getElement()
          element?.setAttribute('tabindex','0');element?.setAttribute('role','button')
          element?.setAttribute('aria-label',`${first.display_name}, ${first.parent_zone_name}: ${category ? `${category} rainfall risk ${when === 'today' ? 'today' : 'tomorrow'}` : 'no current rainfall outlook'}${ringed ? ', floods more easily than most' : ''}${point.sites.length>1 ? `, ${point.sites.length} records at this reference` : ''}`)
          if (element) element.onkeydown=key => { if (['Enter',' '].includes(key.key)) { key.preventDefault();event.target.openPopup() } }
        } }}>
        <Popup maxHeight={300}><div className="p-3 space-y-2 text-ink">
          <h3 className="font-semibold">{first.display_name}</h3>
          <p className="text-xs text-muted">{t('area.subCounty',{name:first.parent_zone_name})}</p>
          {category ? <><p className="text-sm"><RiskBadge risk={category} size="sm" label={t(`category.${category}`)} /> {t(when === 'today' ? 'map.riskToday' : 'map.riskTomorrow')}</p>
            {point.sites.length===1 && when !== 'today' && <p className="text-xs">{plainSummary(outlookPoint(outlook,first.id), lang)}</p>}
            {when === 'today' && todayPoint(today,first.id)?.windows.filter(w => w.rain_mm !== null).map(w => <p key={w.window} className="text-xs">{windowLabel(w)} · {t(`now.${w.intensity}`)}{w.rain_mm >= 0.2 ? ` · ${t('now.amount',{mm:w.rain_mm})}` : ''}</p>)}</>
            : <p className="text-xs">{t('map.noOutlookPlace')}</p>}
          {local && <p className={`text-xs ${watchClosely(category,local) ? 'font-semibold' : 'text-muted'}`}>{watchClosely(category,local) ? `${t('area.watchClosely')} ` : ''}{susceptibilityText(local, lang)}</p>}
          {point.sites.length>1 && <p className="text-xs">{t('map.sharePlace',{count:point.sites.length})}</p>}
          {point.sites.map(site => <button key={site.id} className="block text-brand underline text-xs text-left" onClick={() => onInspect?.(site.id)}>
            {point.sites.length>1 ? site.name : t('map.viewDetails')} →
          </button>)}
        </div></Popup>
      </CircleMarker>
    })}
  </Pane>
}
