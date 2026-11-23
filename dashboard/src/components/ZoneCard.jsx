import { useState } from 'react'
import { riskColor } from '../constants/colors'
import { useLanguage } from '../context/LanguageContext'
import { CLASSES, pointCategory } from '../services/monitoringOutlook'
import { safeSourceUrl } from '../services/boundaries'
import { AdvisoryList } from './AdvisoryLayer'

const NONE = '#94a3b8'
const SHOWN = 6

// A sub-county at a glance: how many monitored places, how their rainfall risk splits, and
// the places themselves (highest risk first), each one tap away from its own card.
export default function ZoneCard({ feature, sites, outlook, when, advisories, onSelectArea }) {
  const { t } = useLanguage()
  const [all, setAll] = useState(false)
  const p = feature.properties, source = safeSourceUrl(p.source_url)
  const located = sites.filter(s => s.point)
  const rows = located.map(s => ({ site: s, category: pointCategory(outlook, [s.id]) }))
    .sort((a, b) => CLASSES.indexOf(b.category) - CLASSES.indexOf(a.category) || a.site.display_name.localeCompare(b.site.display_name))
  const counts = [...CLASSES].reverse().map(c => ({ c, n: rows.filter(r => r.category === c).length })).filter(x => x.n)
  const unknown = rows.filter(r => !r.category).length
  const here = advisories.filter(a => a.area_id === feature.id)
  const shown = all ? rows : rows.slice(0, SHOWN)
  return <section className="space-y-4">
    <div className="pr-12">
      <p className="eyebrow">{t('zone.kind')}</p>
      <h2 className="text-xl font-semibold tracking-tight mt-0.5">{p.name}</h2>
      <p className="text-sm text-muted mt-0.5">{located.length ? t('zone.places', { count: located.length }) : t('zone.noPlaces')}</p>
    </div>
    {here.length > 0 && <AdvisoryList items={here} />}
    {rows.length > 0 && <div className="space-y-2">
      <p className="text-xs font-semibold text-muted">{when === 'today' ? t('legend.titleToday') : t('legend.title')}</p>
      {/* One bar split by category: the shape reads at a glance, the chips give the numbers. */}
      <div className="flex h-2.5 rounded-full overflow-hidden glass-inset" role="img"
        aria-label={[...counts.map(x => `${x.n} ${t(`category.${x.c}`)}`), unknown ? `${unknown} ${t('category.none')}` : ''].filter(Boolean).join(', ')}>
        {counts.map(x => <span key={x.c} style={{ width: `${(x.n / rows.length) * 100}%`, background: riskColor(x.c) }} />)}
        {unknown > 0 && <span style={{ width: `${(unknown / rows.length) * 100}%`, background: NONE }} />}
      </div>
      <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
        {counts.map(x => <span key={x.c} className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: riskColor(x.c) }} aria-hidden="true" /><span className="tabular font-semibold">{x.n}</span> {t(`category.${x.c}`)}</span>)}
        {unknown > 0 && <span className="inline-flex items-center gap-1.5 text-muted"><span className="w-2 h-2 rounded-full" style={{ background: NONE }} aria-hidden="true" /><span className="tabular">{unknown}</span> {t('category.none')}</span>}
      </p>
    </div>}
    {rows.length > 0 && <ul className="rounded-[14px] glass-inset divide-y divide-border overflow-hidden" aria-label={t('zone.placeList')}>
      {shown.map(({ site, category }) => <li key={site.id}>
        <button type="button" onClick={() => onSelectArea(site.id)} className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left text-sm hover:bg-surface-2">
          <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: category ? riskColor(category) : NONE }} aria-hidden="true" />
          <span className="flex-1 min-w-0 truncate">{site.display_name}</span>
          <span className="text-xs text-muted shrink-0">{category ? t(`category.${category}`) : '—'}</span>
        </button></li>)}
    </ul>}
    {rows.length > SHOWN && <button type="button" className="text-sm font-medium text-accent" onClick={() => setAll(v => !v)}>
      {all ? t('zone.showFewer') : t('zone.showAll', { count: rows.length })}</button>}
    <p className="text-xs text-muted">{t('zone.outline', { year: p.source_year })} {source && <a href={source} target="_blank" rel="noopener noreferrer" className="underline">{p.source}</a>}</p>
  </section>
}
