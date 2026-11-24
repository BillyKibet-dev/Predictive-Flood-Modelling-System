import { useEffect, useRef } from 'react'
import { riskColor } from '../constants/colors'
import { CLASSES, outlookCounts } from '../services/monitoringOutlook'
import { REPORT_ICON_SVG } from './CommunityReportLayer'
import { formatNairobi, useLanguage } from '../context/LanguageContext'


function Swatch({ color, label }) {
  return <span className="inline-flex items-center gap-1 whitespace-nowrap"><span aria-hidden="true" className="inline-block w-2.5 h-2.5 rounded-full border border-white" style={{ backgroundColor:color }} />{label}</span>
}

// Map key for the coloured monitoring pins, with a one-line summary of tomorrow's outlook.
// hiddenOnMobile: the selected-area panel covers the bottom of small screens.
export default function RainfallLegend({ outlook, hiddenOnMobile = false, reportCount = 0, showRing = false, advisoryCount = 0, when = 'tomorrow', setWhen, todayAvailable = false }) {
  const { lang, t }=useLanguage()
  const day=value=>formatNairobi(lang,value,{weekday:'short',day:'numeric',month:'short'})
  const time=value=>formatNairobi(lang,value,{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})
  const panel=useRef(null)
  // Open by default on wider screens; collapsed on phones so the map stays visible.
  useEffect(() => { if (panel.current) panel.current.open=window.matchMedia?.('(min-width: 768px)').matches ?? true },[])
  const data=outlook.data, available=data?.available_count>0
  const counts=outlookCounts(data)
  return <details ref={panel} className={`rainfall-legend ${hiddenOnMobile ? 'hidden md:block' : ''} absolute bottom-8 left-3 z-[1000] bg-surface border border-border rounded-card text-xs text-ink max-w-[calc(100%-5.5rem)] md:max-w-[min(20rem,calc(100%-13rem))] max-h-[calc(100%-7rem)] overflow-y-auto shadow-card-hover`}>
    <summary className="cursor-pointer px-3 py-2 font-semibold">{when === 'today' ? t('legend.titleToday') : t('legend.title')}{available ? ` · ${day(data.collection.target_start)}` : ''}</summary>
    <div className="px-3 pb-3 space-y-2" aria-label="Forecast collection status">
      {setWhen && <div role="group" aria-label={t('when.label')} className="grid grid-cols-2 p-0.5 rounded-btn bg-surface-2 font-semibold">
        {['today', 'tomorrow'].map(day => <button key={day} type="button" aria-pressed={when === day} disabled={day === 'today' && !todayAvailable}
          onClick={() => setWhen(day)} className={`h-7 rounded-[6px] disabled:opacity-40 ${when === day ? 'bg-surface text-ink shadow-card-rest' : 'text-muted hover:text-ink'}`}>{t(`when.${day}`)}</button>)}
      </div>}
      <p className="flex flex-wrap gap-x-3 gap-y-1">{CLASSES.map(c => <Swatch key={c} color={riskColor(c)} label={t(`category.${c}`)} />)}<Swatch color="#94a3b8" label={t('category.none')} /></p>
      {outlook.loading ? <p>{t('legend.checking')}</p> : available ? <>
        <p className="font-semibold">{counts.map(({ category, count }) => `${count} ${t(`category.${category}`)}`).join(' · ')}{data.available_count < data.located_count ? ` · ${t('legend.noOutlookCount',{count:data.located_count - data.available_count})}` : ''}</p>
        <p className="text-muted">{t('legend.updated',{time:time(data.collection.received_at)})}{data.collection_automatic ? ` · ${data.configured_interval_hours===1 ? t('legend.everyHour') : t('legend.everyHours',{hours:data.configured_interval_hours})}` : ''}</p>
      </> : <p>{t('legend.unavailable')}</p>}
      <p className="text-muted">{t('legend.caveat')}</p>
      {showRing && <p className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block w-3 h-3 rounded-full" style={{ background:'#94a3b8', boxShadow:'0 0 0 2px #111827' }} />{t('legend.ring')}</p>}
      <p className="text-muted">{t('legend.dashed')}</p>
      {reportCount > 0 && <p className="flex items-center gap-1"><span aria-hidden="true" className="inline-flex w-3.5" dangerouslySetInnerHTML={{ __html: REPORT_ICON_SVG.replace('width="22" height="20"', 'width="14" height="13"') }} />{reportCount === 1 ? t('legend.report') : t('legend.reports',{count:reportCount})}</p>}
      {advisoryCount > 0 && <p className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block w-2.5 h-2.5 rotate-45" style={{ background:'#b45309' }} />{advisoryCount === 1 ? t('legend.advisory') : t('legend.advisories',{count:advisoryCount})}</p>}
      <button className="underline disabled:opacity-50" disabled={outlook.loading} onClick={outlook.refresh}>{t('legend.refresh')}</button>
    </div>
  </details>
}
