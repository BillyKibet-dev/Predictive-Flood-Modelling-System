import L from 'leaflet'
import { Link } from 'react-router-dom'
import { Marker, Pane, Popup } from 'react-leaflet'
import { timeAgo } from '../services/communityReports'
import { useLanguage } from '../context/LanguageContext'

// A triangle, unlike the round rainfall-risk pins, so the two never read as the same thing.
export const REPORT_ICON_SVG = '<svg viewBox="0 0 24 22" width="22" height="20" aria-hidden="true"><path d="M12 1 23 21H1z" fill="#7c3aed" stroke="#fff" stroke-width="2" stroke-linejoin="round"/><path d="M12 8v6M12 16.5v1.5" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/></svg>'
const icon = L.divIcon({ className: 'community-report-icon', html: REPORT_ICON_SVG, iconSize: [22, 20], iconAnchor: [11, 18], popupAnchor: [0, -16] })

export default function CommunityReportLayer({ reports, visible }) {
  const { lang, t } = useLanguage()
  if (!visible || !reports?.length) return null
  return <Pane name="community-reports" style={{ zIndex: 460 }}>
    {reports.map(r => <Marker key={r.id} position={[r.latitude, r.longitude]} icon={icon} keyboard
      title={`Community report: ${r.observed_condition}, ${timeAgo(r.reported_at)}`}
      alt={`Community report: ${r.observed_condition}`}
      eventHandlers={{ add: event => event.target.getElement()?.classList.add('community-report') }}>
      <Popup maxHeight={260}><div className="p-3 space-y-2 text-ink">
        <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: '#7c3aed' }}>{t('report.popupTitle')}</p>
        <h3 className="font-semibold">{t(`condition.${r.observed_condition}`)} · {t(`severity.${r.perceived_severity}`)}</h3>
        {r.location_description && <p className="text-sm">{r.location_description}</p>}
        <p className="text-xs text-muted">{t('report.reported',{ago:timeAgo(r.reported_at, Date.now(), lang)})}</p>
        <p className="text-xs">{t('report.notWarning')}</p>
        <Link className="text-xs text-brand underline" to="/citizen#report">{t('report.seeFlooding')}</Link>
      </div></Popup>
    </Marker>)}
  </Pane>
}
