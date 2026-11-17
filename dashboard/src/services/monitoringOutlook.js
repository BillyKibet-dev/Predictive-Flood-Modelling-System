import { translate } from '../i18n/strings.js'
import { API_BASE_URL } from './api.js'

const HOUR=3600000
const eatDate=t=>new Date(t+3*HOUR).toISOString().slice(0,10)
export const CLASSES=['Low','Moderate','High','Extreme']
export const TOMORROW_MM=[5,20,40]
export const ACCUMULATION_MM=[25,80,150]
const METHODS=['stage2_xgboost_guarded','observed_plus_forecast_rule','observed_plus_forecast_rule_lower_bound']
const RISK_FIELDS={method:null,class_driver:null,issue_day_forecast_mm:null,missing_issue_day_hours:null,antecedent_observed_mm:null,accumulation_7d_mm:null,accumulation_complete:null,antecedent_cell:null,fallback_reasons:[],rule_class:null,model_version:null,model_scores:null,guard_applied:false,model_status:null}
const level=(mm,cuts)=>cuts.filter(t=>mm>=t).length
const nonNegative=v=>Number.isFinite(v)&&v>=0

// Stage 1 rule (the v1 training label applied to live inputs): the higher of tomorrow's
// forecast class and the 7-day (observed + forecast) accumulation class.
export function ruleClass(tomorrow, accumulation) {
  const daily=level(tomorrow,TOMORROW_MM)
  if (accumulation===null) return {proxy_class:CLASSES[daily],class_driver:'tomorrow_only'}
  const accumulated=level(accumulation,ACCUMULATION_MM)
  return {proxy_class:CLASSES[Math.max(daily,accumulated)],class_driver:accumulated>daily?'accumulation':'tomorrow'}
}

export function expireOutlook(data, now=Date.now()) {
  if (!data) return data
  const areas=data.areas.map(area => {
    if (area.status !== 'AVAILABLE' || now<Date.parse(area.expires_at)) return area
    return {...area,...RISK_FIELDS,status:'UNAVAILABLE',rainfall_mm:null,proxy_class:null,reason:'STALE_SOURCE_RECEIPT'}
  })
  const count=areas.filter(a=>a.status==='AVAILABLE').length
  return {...data,areas,available_count:count,status:count===data.located_count?'AVAILABLE':count?'PARTIAL':'UNAVAILABLE'}
}

// The Stage 1 rule class is always re-derived here from the reported amounts. Exact 7-day
// total when every component is present; otherwise a flagged lower bound (rain cannot be
// negative). Where inputs are complete the Stage 2 guarded XGBoost class may replace it:
// it must equal the arg-max of the reported scores, except that Extreme becomes High
// when the rule is below High (the guard).
function validRisk(a, modelVersion) {
  if (!METHODS.includes(a.method) || !Array.isArray(a.fallback_reasons) || typeof a.antecedent_cell!=='string') return false
  const expected=ruleClass(a.rainfall_mm,a.accumulation_7d_mm)
  if (!nonNegative(a.accumulation_7d_mm) || !nonNegative(a.issue_day_forecast_mm) || !Number.isInteger(a.missing_issue_day_hours) ||
      a.missing_issue_day_hours<0 || a.missing_issue_day_hours>21 || !(a.antecedent_observed_mm===null || nonNegative(a.antecedent_observed_mm)) ||
      expected.proxy_class!==a.rule_class || expected.class_driver!==a.class_driver ||
      Math.abs(a.accumulation_7d_mm-((a.antecedent_observed_mm ?? 0)+a.issue_day_forecast_mm+a.rainfall_mm))>=1e-3) return false
  const complete=a.antecedent_observed_mm!==null && a.missing_issue_day_hours===0
  if (a.accumulation_complete!==complete || complete!==(a.fallback_reasons.length===0)) return false
  if (a.method==='stage2_xgboost_guarded') {
    const s=a.model_scores
    if (!complete || a.model_status!=='APPLIED' || typeof modelVersion!=='string' || a.model_version!==modelVersion || !s ||
        CLASSES.some(c=>!(Number.isFinite(s[c])&&s[c]>=0&&s[c]<=1)) || Math.abs(CLASSES.reduce((t,c)=>t+s[c],0)-1)>1e-3) return false
    const top=CLASSES.reduce((best,c,i)=>s[c]>s[CLASSES[best]]?i:best,0)
    const guarded=top===3 && CLASSES.indexOf(a.rule_class)<2
    return a.guard_applied===guarded && a.proxy_class===CLASSES[guarded?2:top]
  }
  return a.proxy_class===a.rule_class && a.model_scores===null && a.model_version===null && a.guard_applied===false &&
    complete===(a.method==='observed_plus_forecast_rule')
}

export function parseMonitoringOutlook(payload, now=Date.now()) {
  if (payload?.contract_version !== 'monitoring-rainfall-outlook-v3' || !Array.isArray(payload.areas) || !Number.isInteger(payload.located_count) || payload.located_count<0 || typeof payload.collection_automatic!=='boolean' || payload.collection_automatic!==payload.automation_configured || (payload.collection_automatic ? !Number.isFinite(Date.parse(payload.next_collection_at)) : payload.next_collection_at!==null) || typeof payload.automation_configured!=='boolean' || (payload.automation_configured ? (!Number.isInteger(payload.configured_interval_hours)||payload.configured_interval_hours<1||payload.configured_interval_hours>24) : payload.configured_interval_hours!==null)) throw new Error('Invalid monitoring outlook')
  const ids=new Set(payload.areas.map(a=>a.area_id))
  if (ids.size!==payload.areas.length || [...ids].some(id=>!/^NFW-S\d{3}$/.test(id))) throw new Error('Invalid monitoring identity')
  for (const a of payload.areas) {
    if (!['AVAILABLE','UNAVAILABLE'].includes(a.status)) throw new Error('Invalid outlook status')
    if (a.status==='UNAVAILABLE') {
      if (a.rainfall_mm!==null || a.proxy_class!==null || (a.accumulation_7d_mm ?? null)!==null) throw new Error('Unavailable weather contains a category')
      continue
    }
    const source=payload.collection
    if (!source || source.method!=='stage2_xgboost_with_rule_fallback' || !(source.model_version===null || /^stage2-xgb-[0-9a-f]{12}$/.test(source.model_version)) || source.flood_probability!==null || source.publication_at!==null ||
        JSON.stringify(source.thresholds?.tomorrow_mm)!==JSON.stringify(TOMORROW_MM) || JSON.stringify(source.thresholds?.accumulation_mm)!==JSON.stringify(ACCUMULATION_MM)) throw new Error('Unsupported rainfall method')
    const [received,run,stored,requested,start,end,expiry]=[a.received_at,a.run_at,source.stored_at,source.requested_at,a.target_start,a.target_end,a.expires_at].map(Date.parse)
    if (![received,run,stored,requested,start,end,expiry].every(Number.isFinite) || !(run<=requested&&requested<=received&&received<=stored&&stored<=now) || end-start!==24*HOUR || eatDate(end)!==eatDate(start+24*HOUR) || (start+3*HOUR)%(24*HOUR)!==0) throw new Error('Unverified forecast times')
    if (expiry!==Math.min(received+6*HOUR,run+24*HOUR,start)) throw new Error('Invalid forecast expiry')
    if (!nonNegative(a.rainfall_mm) || !validRisk(a,source.model_version) || !Array.isArray(a.shared_area_ids) || !a.shared_area_ids.includes(a.area_id) || a.shared_area_ids.some(id=>!ids.has(id)) || !Number.isFinite(a.source_grid_point?.latitude) || !Number.isFinite(a.source_grid_point?.longitude) || Math.abs(a.source_grid_point.latitude)>90 || Math.abs(a.source_grid_point.longitude)>180) throw new Error('Invalid rainfall or shared grid')
    if (a.received_at!==source.received_at || a.run_at!==source.run_at || a.target_start!==source.target_start || a.target_end!==source.target_end || a.expires_at!==source.expires_at) throw new Error('Forecast source mismatch')
    if (expiry>now && eatDate(start)!==eatDate(now+24*HOUR)) throw new Error('Forecast is not for the next Nairobi day')
  }
  if (payload.available_count!==payload.areas.filter(a=>a.status==='AVAILABLE').length || payload.available_count>payload.located_count) throw new Error('Forecast coverage mismatch')
  return expireOutlook(payload,now)
}

export async function fetchMonitoringOutlook({signal}={}) {
  const response=await fetch(`${API_BASE_URL}/monitoring-areas/outlook`,{signal,cache:'no-store'})
  if (!response.ok) throw new Error('Forecast outlook unavailable')
  return parseMonitoringOutlook(await response.json())
}

export function outlookPoint(data,id) {
  const a=data?.areas.find(row=>row.area_id===id)
  if (!a || a.status!=='AVAILABLE') return {status:'UNAVAILABLE'}
  return {status:'AVAILABLE_FORECAST_RULE_CONTEXT',proxy_class:a.proxy_class,
    daily_forecast_rainfall_mm:a.rainfall_mm,target_start:a.target_start,target_end:a.target_end,
    receivedAt:a.received_at,runAt:a.run_at,shared:a.shared_area_ids,
    method:a.method,classDriver:a.class_driver,accumulation7dMm:a.accumulation_7d_mm,accumulationComplete:a.accumulation_complete,
    observedMm:a.antecedent_observed_mm,issueDayForecastMm:a.issue_day_forecast_mm,missingIssueDayHours:a.missing_issue_day_hours,
    fallbackReasons:a.fallback_reasons,ruleClass:a.rule_class,modelVersion:a.model_version,modelScores:a.model_scores,
    guardApplied:a.guard_applied,modelStatus:a.model_status}
}

// Plain-language reason a category was reached, for map popups and tables.
export function classExplanation(point) {
  if (!point || point.status!=='AVAILABLE_FORECAST_RULE_CONTEXT') return ''
  if (point.method==='stage2_xgboost_guarded') {
    const agree=point.proxy_class===point.ruleClass
    const guard=point.guardApplied?' The model leaned towards Extreme, but Extreme is only shown when the rainfall rule also reaches High.':''
    return `Category from the XGBoost model trained on 2024–2026 forecasts, satellite rainfall and observed outcomes. ${agree?'The fixed rainfall rule gives the same category.':`The fixed rainfall rule alone would give ${point.ruleClass}.`}${guard}`
  }
  const base=point.classDriver==='accumulation'
    ? 'Raised by the 7-day rainfall total (recent observed rain plus forecast), not tomorrow\'s rain alone.'
    : 'Set by tomorrow\'s forecast rainfall; the 7-day total does not raise it further.'
  if (point.accumulationComplete) return base
  const gaps=[point.observedMm===null&&'recent satellite rainfall is not yet available',
    point.missingIssueDayHours>0&&`${point.missingIssueDayHours} earlier hours of today are outside the latest forecast run`].filter(Boolean).join(' and ')
  return `${base} The 7-day total is a minimum because ${gaps}, so this category may understate wet conditions.`
}

// ── Citizen-facing summaries (main map) ────────────────────────────────────────────
// Short, cautious advice per category. Rainfall categories are not flood warnings.
export const CATEGORY_ADVICE={
  Low:'Little rain is expected. Flooding can still happen from blocked drains or rain upstream, so stay alert.',
  Moderate:'Some rain is expected. Keep drains clear and watch low-lying spots and river banks.',
  High:'Heavy rain is likely. Do not walk or drive through flowing water, and keep away from river banks.',
  Extreme:'Very heavy rain is likely. Be ready to move to higher ground, avoid rivers and flooded roads, and follow official warnings.',
}
export const OFFICIAL_WARNINGS='Follow official warnings from the Kenya Meteorological Department and Nairobi County.'

const roundMm=mm=>mm<1?mm.toFixed(1):String(Math.round(mm))

// One plain sentence describing the rain behind a category, in English or Kiswahili.
export function plainSummary(point, lang='en') {
  if (!point || point.status!=='AVAILABLE_FORECAST_RULE_CONTEXT') return ''
  const t=(key,values)=>translate(lang,key,values)
  const tomorrow=point.daily_forecast_rainfall_mm
  const first=tomorrow>=TOMORROW_MM[1] ? t('rain.heavy',{mm:roundMm(tomorrow)})
    : tomorrow<0.5 ? t('rain.none') : t('rain.some',{mm:roundMm(tomorrow)})
  const week=point.accumulation7dMm
  if (!Number.isFinite(week)) return first
  const wet=week>=ACCUMULATION_MM[0]?t('rain.wetWeek'):''
  return t('rain.week',{first,wet,about:t(point.accumulationComplete?'rain.about':'rain.atLeast'),week:roundMm(week)})
}

// Category to colour a map pin; several records may share one pin (highest wins).
// null when no fresh outlook is available for any of them.
export function pointCategory(data, ids) {
  const found=ids.map(id=>data?.areas.find(a=>a.area_id===id)).filter(a=>a?.status==='AVAILABLE'&&CLASSES.includes(a.proxy_class))
  return found.length ? CLASSES[Math.max(...found.map(a=>CLASSES.indexOf(a.proxy_class)))] : null
}

// Counts per category for the map summary line, highest category first.
export function outlookCounts(data) {
  const counts=Object.fromEntries(CLASSES.map(c=>[c,0]))
  for (const a of data?.areas||[]) if (a.status==='AVAILABLE'&&counts[a.proxy_class]!==undefined) counts[a.proxy_class]++
  return [...CLASSES].reverse().filter(c=>counts[c]).map(c=>({category:c,count:counts[c]}))
}
