import { useRef } from 'react'
import { REFERENCE_LABELS } from '../services/monitoringAreas'
import { useLanguage } from '../context/LanguageContext'

// Choosing a sub-county here opens its card on the map (MapPage), so the list closes itself.
export default function MonitoringAreaControls({ inventory, sites, zone, setZone, query, setQuery, onSelect, selectedId }) {
  const panel=useRef(null), { t }=useLanguage()
  return <details ref={panel} className="monitored-area-controls bg-surface border border-border shadow-card-hover rounded-card text-xs text-ink w-80 max-w-full">
    <summary className="cursor-pointer px-4 py-3 font-semibold">{t('areas.title')}{inventory.data ? ` (${inventory.data.sites.length})` : ''}</summary>
    <div className="px-3 pb-3 space-y-3 max-h-[50dvh] overflow-y-auto">
      {inventory.loading && <p role="status">{t('areas.loading')}</p>}
      {inventory.error && <p role="alert">{inventory.error}. <button className="underline" onClick={inventory.refresh}>{t('areas.retry')}</button></p>}
      {inventory.data && <>
        <label className="block">{t('areas.subCounty')}<select aria-label="Parent monitoring zone" className="block w-full border border-border rounded-btn bg-surface p-2 mt-1" value={zone} onChange={e => { setZone(e.target.value); if (e.target.value && panel.current) panel.current.open=false }}>
          <option value="">{t('areas.all')}</option>{inventory.data.groups.map(g => <option key={g.id} value={g.id}>{g.name}{g.id.startsWith('review-') ? ' · location review' : ''} ({g.site_count})</option>)}</select></label>
        <label className="block">{t('areas.find')}<input aria-label="Search monitored areas" value={query} onChange={e => setQuery(e.target.value)} placeholder={t('areas.placeholder')} className="block w-full border border-border rounded-btn bg-surface p-2 mt-1" /></label>
        <p role="status" className="text-muted">{t('areas.count',{records:sites.length,mapped:sites.filter(s => s.point).length})}</p>
        <div aria-label="Monitored area list">{inventory.data.groups.map(group => {
          const members=sites.filter(s => s.parent_zone_id === group.id)
          return members.length>0 && <section key={group.id} className="mb-3"><h2 className="font-semibold mb-1">{group.name}{group.id.startsWith('review-') ? ' · tentative' : ''}</h2>
            {members.map(site => <button key={site.id} data-area-id={site.id} className={`block w-full text-left p-2 mb-1 rounded-btn border ${selectedId === site.id ? 'border-brand bg-surface-2' : 'border-transparent hover:bg-bg'}`} aria-pressed={selectedId === site.id} onClick={event => { event.currentTarget.closest('details').open=false;onSelect(site.id) }}>
              <span className="block">{site.display_name}</span><span className="text-muted block mt-1">{REFERENCE_LABELS[site.reference_kind]}</span>
            </button>)}
          </section>
        })}</div>
        <p className="text-muted">{t('areas.note')}</p>
      </>}
    </div>
  </details>
}
