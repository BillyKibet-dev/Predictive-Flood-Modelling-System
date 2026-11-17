import { Link } from 'react-router-dom'
import { getRisk } from '../constants/colors'
import { plainSummary } from '../services/monitoringOutlook'
import { formatNairobi, useLanguage } from '../context/LanguageContext'
import { susceptibilityText, watchClosely } from '../services/susceptibility'
import { AdvisoryList } from './AdvisoryLayer'
import { windowLabel } from '../services/todayOutlook'


// The short, plain-language view everyone sees first. Technical detail lives under "More details".
export default function AreaRiskSummary({ site, state, showReportLink = true, local = null, advisories = [], today = null, todayReceived = null }) {
  const { lang, t }=useLanguage()
  const dateTime=value=>formatNairobi(lang,value,{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})
  const day=value=>formatNairobi(lang,value,{weekday:'short',day:'numeric',month:'short'})
  const here=advisories.filter(a => a.area_id===site.parent_zone_id)
  const point=state?.data, available=point?.status==='AVAILABLE_FORECAST_RULE_CONTEXT'
  const risk=available ? getRisk(point.proxy_class) : null
  return <section aria-label="Rainfall risk summary" className="space-y-3">
    <div><h2 className="text-lg font-semibold leading-tight pr-8">{site.display_name}</h2>
      <p className="text-xs text-muted mt-1">{t('area.subCounty',{name:site.parent_zone_name})}</p></div>
    {here.length > 0 && <AdvisoryList items={here} />}
    {today && <NextHours point={today} received={todayReceived} />}
    {state?.loading ? <p role="status" className="text-sm">{t('area.checking')}</p>
      : available ? <>
        <div className="area-risk-category rounded-card border px-3 py-2" style={{ backgroundColor:risk.bg, borderColor:risk.border }}>
          <p className="text-base font-bold" style={{ color:risk.text }}>{t('area.riskTitle',{category:t(`category.${point.proxy_class}`)})}</p>
          <p className="text-xs text-ink">{t('area.forTomorrow',{day:day(point.target_start)})}</p>
        </div>
        <p className="text-sm">{plainSummary(point, lang)}</p>
        {watchClosely(point.proxy_class, local) && <p className="text-sm font-semibold">{t('area.watchClosely')}</p>}
        <p className="text-sm">{t(`advice.${point.proxy_class}`)}</p>
        {['High','Extreme'].includes(point.proxy_class) && <p className="text-sm font-semibold">{t('advice.official')}</p>}
        <p className="text-xs text-muted">{t('area.caveat',{time:dateTime(point.receivedAt)})}</p>
      </> : <p className="text-sm">{t('area.noOutlook')}</p>}
    {local && <p className="text-sm"><span className="font-semibold">{t('area.thisSpot')} </span>{susceptibilityText(local, lang)}</p>}
    {showReportLink && <Link to={`/citizen?area=${encodeURIComponent(site.parent_zone_id ?? '')}#report`} className="inline-flex items-center rounded-btn bg-brand text-white px-3 py-2 text-sm font-semibold">{t('area.reportHere')}</Link>}
  </section>
}

// Today's category from the model, and forecast rain in the next two 3-hour blocks.
const BAR = { none: 'var(--border)', light: '#7dd3fc', moderate: '#0ea5e9', heavy: '#0369a1' }
function NextHours({ point, received }) {
  const { lang, t }=useLanguage()
  const risk=getRisk(point.category)
  return <section aria-label="Next 6 hours" className="rounded-card border border-border p-3 space-y-2">
    <div className="flex items-baseline justify-between gap-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{t('now.title')}</p>
      <span className="text-xs font-semibold px-2 py-0.5 rounded-full" style={{ backgroundColor:risk.bg, color:risk.text }}>{t('now.todayRisk',{category:t(`category.${point.category}`)})}</span>
    </div>
    <ul className="space-y-1.5">{point.windows.map(w => <li key={w.window} className="flex items-center gap-2 text-sm">
      <span className="tabular text-xs text-muted w-[5.5rem] shrink-0">{windowLabel(w)}</span>
      <span aria-hidden="true" className="w-1.5 h-4 rounded-full shrink-0" style={{ background: BAR[w.intensity] ?? 'var(--border)' }} />
      <span className="flex-1">{w.rain_mm === null ? t('now.unknown') : t(`now.${w.intensity}`)}</span>
      {w.rain_mm >= 0.2 && <span className="tabular text-xs text-muted">{t('now.amount',{mm:w.rain_mm})}</span>}
    </li>)}</ul>
    {received && <p className="text-xs text-muted">{t('now.caveat',{time:formatNairobi(lang,received,{hour:'2-digit',minute:'2-digit'})})}</p>}
  </section>
}
