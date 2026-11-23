import { useMemo, useState } from 'react'
import { Route as RouteIcon, MessageSquarePlus, X } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import BoundaryControls from '../components/BoundaryControls'
import MapView from '../components/MapView'
import TopNav from '../components/TopNav'
import useBoundaries from '../hooks/useBoundaries'
import useHistoricalFloods from '../hooks/useHistoricalFloods'
import HistoricalFloodControls from '../components/HistoricalFloodControls'
import useMonitoringAreas from '../hooks/useMonitoringAreas'
import MonitoringAreaControls from '../components/MonitoringAreaControls'
import MonitoringAreaProfile from '../components/MonitoringAreaProfile'
import { filterMonitoringAreas, groupAreaPoints } from '../services/monitoringAreas'
import useMonitoringOutlook from '../hooks/useMonitoringOutlook'
import { outlookPoint } from '../services/monitoringOutlook'
import PointForecastContext from '../components/PointForecastContext'
import NearbyCommunityReports from '../components/NearbyCommunityReports'
import AreaRiskSummary from '../components/AreaRiskSummary'
import SusceptibilityDetails from '../components/SusceptibilityDetails'
import RainfallLegend from '../components/RainfallLegend'
import AdvisoryLayer, { AdvisoryBanner } from '../components/AdvisoryLayer'
import useAdvisories from '../hooks/useAdvisories'
import useTodayOutlook from '../hooks/useTodayOutlook'
import { todayAsOutlook, todayPoint } from '../services/todayOutlook'
import { useLanguage } from '../context/LanguageContext'
import useSusceptibility from '../hooks/useSusceptibility'
import useCommunityReports from '../hooks/useCommunityReports'

export default function MapPage() {
  const { user,authorizedRequest } = useAuth()
  const [params,setParams]=useSearchParams(), areas=useMonitoringAreas()
  const boundaries=useBoundaries(), historical=useHistoricalFloods()
  const [showPolygons,setShowPolygons]=useState(true), [showAreas,setShowAreas]=useState(true)
  const [fitRequest,setFitRequest]=useState(0), [query,setQuery]=useState('')
  const zone=params.get('zone') || '', selectedId=params.get('area') || params.get('hotspot')
  const sites=useMemo(() => filterMonitoringAreas(areas.data?.sites || [],{zone,query}),[areas.data,zone,query])
  const selected=areas.data?.sites.find(s => s.id === selectedId)
  const historicalVisible=historical.data && Object.values(historical.visible).some(Boolean)
  const distinctPoints=groupAreaPoints(sites).length, unlocated=sites.filter(s => !s.point).length
  const outlook=useMonitoringOutlook(), communityReports=useCommunityReports(), susceptibility=useSusceptibility(), advisories=useAdvisories()
  const { t }=useLanguage(), activeAdvisories=advisories.data?.items ?? []
  // Pins and legend show today (default) or tomorrow; today falls back to tomorrow if unavailable.
  const today=useTodayOutlook(), [when,setWhen]=useState('today')
  const showingToday=when==='today'&&Boolean(today.data)
  const pinOutlook=showingToday ? todayAsOutlook(today.data,outlook.data) : outlook.data
  const legendOutlook=showingToday ? { data:pinOutlook, loading:false, refresh:() => { today.refresh();outlook.refresh() } } : outlook
  const [showReports,setShowReports]=useState(true)
  const pointForecast={loading:outlook.loading,data:outlookPoint(outlook.data,selectedId)}
  function selectArea(id) {
    setShowAreas(true)
    setParams(previous => { previous.set('area',id);previous.set('inspect','1');previous.delete('hotspot');return previous })
  }
  function setZone(id) {
    setParams(previous => { if (id) previous.set('zone',id);else previous.delete('zone');previous.delete('area');previous.delete('inspect');previous.delete('hotspot');return previous })
  }
  function closeArea(event) {
    event?.preventDefault(); event?.stopPropagation()
    setParams(previous => { const next=new URLSearchParams(previous);next.delete('area');next.delete('hotspot');next.delete('inspect');return next })
  }
  return <div className="h-screen h-[100dvh] flex flex-col page-transition">
    <TopNav variant="public" />
    <main className="relative flex-1 min-h-0" aria-label="Nairobi monitoring map">
      <MapView boundaries={boundaries.data} boundaryRevision={boundaries.revision} showMarkers={false}
        showPolygons={showPolygons} fitRequest={fitRequest} historical={historical}
        monitoringAreas={sites} showMonitoringAreas={showAreas} selectedAreaId={selectedId} onInspectArea={selectArea} onDismissArea={closeArea}
        monitoringOutlook={pinOutlook} outlookDay={showingToday ? 'today' : 'tomorrow'} todayOutlook={today.data} susceptibility={susceptibility.data} communityReports={communityReports.data?.items} showCommunityReports={showReports}>
        <AdvisoryLayer advisories={activeAdvisories} />
      </MapView>
      <AdvisoryBanner advisories={activeAdvisories} />
      <div className="absolute top-3 right-3 z-[1000] flex flex-col items-end gap-2 max-w-[calc(100%-76px)]">
        <MonitoringAreaControls inventory={areas} sites={sites} zone={zone} setZone={setZone}
          query={query} setQuery={setQuery} onSelect={selectArea} selectedId={selectedId} />
        <details className="map-layer-controls bg-surface border border-border shadow-card-hover rounded-card text-xs text-ink max-w-80">
          <summary className="cursor-pointer px-4 py-3 font-semibold">{t('map.layers')}</summary>
          <div className="p-3 pt-0 max-h-[45dvh] overflow-y-auto space-y-3">
            <BoundaryControls boundaries={boundaries} showPolygons={showPolygons} setShowPolygons={setShowPolygons}
              showMarkers={showAreas} setShowMarkers={setShowAreas} markerLabel="Monitored areas"
              fitCounty={() => { setZone('');setQuery('');setFitRequest(n => n+1) }} />
            <label className="flex items-start gap-2"><input type="checkbox" className="mt-0.5" checked={showReports} onChange={e => setShowReports(e.target.checked)} />
              <span>{t('map.reportsLayer')}<span className="block text-muted">{t('map.reportsLayerHint')}{communityReports.data ? ` · ${t('map.now',{count:communityReports.data.items.length})}` : ''}</span></span></label>
            <HistoricalFloodControls historical={historical} />
          </div>
        </details>
        {historicalVisible && <p role="status" className="rounded-card bg-surface border border-border p-2 text-xs text-ink max-w-64">
          Historical satellite evidence · 1 May 2024. Not current flooding.
        </p>}
        {areas.error && <p role="alert" className="bg-surface border border-border rounded-card p-3 text-xs text-ink max-w-64">
          Monitored areas unavailable. <button className="underline" onClick={areas.refresh}>Retry areas</button>
        </p>}
        {zone && <p role="status" className="rounded-card bg-surface border border-border px-3 py-2 text-xs text-ink max-w-64">
          Zone: {areas.data?.groups.find(g => g.id === zone)?.name || 'Not found'} <button className="underline ml-2" onClick={() => setZone('')}>Show all</button>
        </p>}
      </div>
      {params.has('inspect') && <aside aria-label="Selected monitored area" onPointerDown={event => event.stopPropagation()} onClick={event => event.stopPropagation()} className="absolute z-[1050] bottom-20 left-3 right-3 md:bottom-auto md:top-3 md:left-auto md:w-96 max-h-[45dvh] md:max-h-[calc(100%-100px)] overflow-y-auto bg-surface text-ink border border-border rounded-card shadow-card-hover p-4">
        <button type="button" aria-label={t('map.closeArea')} className="sticky z-10 top-0 float-right bg-surface p-2 rounded-btn ml-2" onClick={closeArea}><X size={18} /></button>
        {selected ? <>
          <AreaRiskSummary site={selected} state={pointForecast} showReportLink={!user} local={susceptibility.data?.byArea[selected.id]} advisories={activeAdvisories}
            today={todayPoint(today.data,selected.id)} todayReceived={today.data?.forecast.received_at} />
          {user && <NearbyCommunityReports areaId={selected.id} authorizedRequest={authorizedRequest} />}
          {/* Citizens see the short summary first; staff get the full detail open by default. */}
          <details key={selected.id} className="area-more-details mt-4 border-t border-border pt-3" open={Boolean(user)}>
            <summary className="cursor-pointer text-sm font-semibold">{t('map.moreDetails')}</summary>
            <div className="mt-3 space-y-5"><PointForecastContext state={pointForecast} />
              <SusceptibilityDetails row={susceptibility.data?.byArea[selected.id]} />
              <MonitoringAreaProfile site={selected} sources={areas.data.sources} technical={Boolean(user)} /></div>
          </details>
        </> : <p role="status">{areas.loading ? t('map.loadingArea') : areas.error ? t('map.areaUnavailable') : t('map.areaNotFound')}</p>}
      </aside>}
      <RainfallLegend outlook={legendOutlook} when={showingToday ? 'today' : 'tomorrow'} setWhen={setWhen} todayAvailable={Boolean(today.data)} showRing={Boolean(susceptibility.data)} advisoryCount={activeAdvisories.length} hiddenOnMobile={params.has('inspect')} reportCount={showReports ? communityReports.data?.items.length ?? 0 : 0} />

      {/* Phones: round icon buttons (named for screen readers) so the legend keeps its width. */}
      {!user && <Link to="/route" aria-label={t('nav.route')} title={t('nav.route')} className={`${params.has('inspect') ? 'hidden' : 'grid'} md:hidden absolute z-[1000] bottom-[84px] right-3 w-12 h-12 place-items-center bg-surface text-ink shadow-card-hover border border-border rounded-full`}>
        <RouteIcon size={19} aria-hidden="true" />
      </Link>}
      <Link to={user ? '/officer/reports' : '/citizen#report'} aria-label={user ? 'Review reports' : t('nav.report')}
        className={`${params.has('inspect') ? 'hidden md:flex' : 'flex'} absolute z-[1000] bottom-8 right-3 max-md:w-12 h-12 md:h-11 max-md:justify-center md:px-4 items-center gap-2 text-sm font-semibold rounded-full shadow-card-hover border ${user ? 'bg-surface text-ink border-border' : 'bg-brand text-white border-brand'}`}>
        <MessageSquarePlus size={18} aria-hidden="true" /><span className="hidden md:inline">{user ? 'Review reports' : t('nav.report')}</span>
      </Link>
    </main>
    <footer className="shrink-0 border-t border-border bg-surface text-ink px-4 py-2 flex flex-wrap justify-between gap-x-4 gap-y-1 text-xs">
      <p>{areas.data ? `${t('map.locations',{count:distinctPoints})}${unlocated ? ` · ${unlocated} records awaiting location review` : ''}` : areas.loading ? 'Loading monitored areas…' : 'Monitored areas unavailable'} · {t('map.outlines')}</p>
      {user ? <Link to="/research" className="text-brand underline">Experimental model results →</Link>
        : <p className="text-muted">{t('map.footerPins')}</p>}
    </footer>
  </div>
}
