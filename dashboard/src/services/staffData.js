// Staff-only views: model card, rainfall history and CSV downloads. Payloads are checked
// before anything is drawn, so a changed or partial response is never shown as fact.

const num = value => typeof value === 'number' && Number.isFinite(value)
const fail = what => { throw new Error(`${what} could not be verified.`) }

function metrics(block) {
  const ok = block && num(block.rows) && num(block.macro_f1) &&
    ['csi', 'pod', 'far'].every(k => num(block.high_or_above?.[k])) &&
    ['csi', 'pod'].every(k => num(block.extreme?.[k]))
  if (!ok) fail('Model metrics')
  return block
}

export function parseModelCard(payload) {
  if (payload?.contract_version !== 'model-card-v1' || !/^[0-9a-f]{64}$/.test(payload.live?.model_sha256 ?? '') ||
      typeof payload.adoption?.adopted !== 'boolean' || !Array.isArray(payload.validation?.seasons) ||
      payload.calibration?.calibrated !== false || !Array.isArray(payload.retained) || !Array.isArray(payload.limitations))
    fail('Model records')
  for (const key of ['rule', 'model', 'forward_rule', 'forward_model']) metrics(payload.validation[key])
  for (const s of payload.validation.seasons)
    if (typeof s.season !== 'string' || !num(s.rule_csi) || !num(s.model_csi)) fail('Season results')
  return payload
}

export function parseRainfallHistory(payload) {
  if (payload?.contract_version !== 'rainfall-history-v1' || !/^[0-9a-f]{64}$/.test(payload.source_sha256 ?? '') ||
      !Array.isArray(payload.monthly) || payload.monthly_average?.length !== 12 || !Array.isArray(payload.yearly) ||
      !Array.isArray(payload.wettest_days))
    fail('Rainfall history')
  if (payload.monthly.some(m => !/^\d{4}-\d{2}$/.test(m.month) || !num(m.total_mm) || m.total_mm < 0) ||
      payload.yearly.some(y => !Number.isInteger(y.year) || !num(y.total_mm) || typeof y.complete !== 'boolean') ||
      payload.wettest_days.some(d => !/^\d{4}-\d{2}-\d{2}$/.test(d.date) || !num(d.mean_mm)))
    fail('Rainfall history')
  return payload
}

// "Average" vs one chosen year, month by month.
export function monthlyComparison(history, year) {
  const totals = Object.fromEntries(history.monthly.filter(m => m.month.startsWith(`${year}-`)).map(m => [Number(m.month.slice(5)), m.total_mm]))
  return history.monthly_average.map(m => ({ month: MONTHS[m.month - 1], average: m.average_mm, year: totals[m.month] ?? null }))
}

export function historyHighlights(history) {
  const complete = history.yearly.filter(y => y.complete)
  const wettestYear = complete.reduce((a, b) => (b.total_mm > a.total_mm ? b : a), complete[0])
  const mean = list => list.reduce((s, v) => s + v, 0) / list.length
  return {
    averageYear: Math.round(mean(complete.map(y => y.total_mm))),
    wettestYear,
    wettestDay: history.wettest_days[0],
    heavyDaysPerYear: Math.round(mean(complete.map(y => y.heavy_days))),
  }
}

// ---- Live track record: each past day's categories against the rain that fell ----

const ratioOrNull = v => v === null || (num(v) && v >= 0 && v <= 1)
function verifiedScores(s, classes) {
  const counts = ['n', 'hits', 'misses', 'false_alarms', 'correct_quiet'].every(k => Number.isInteger(s?.[k]) && s[k] >= 0)
  if (!counts || !['pod', 'far', 'csi', 'exact', 'within_one'].every(k => ratioOrNull(s[k])) ||
      s.hits + s.misses + s.false_alarms + s.correct_quiet !== s.n || !Array.isArray(s.confusion) || s.confusion.length !== classes.length ||
      s.confusion.flat().reduce((a, b) => a + b, 0) !== s.n || !s.wet || !Number.isInteger(s.wet.hits))
    fail('Live track record')
}

export function parseVerification(payload) {
  if (payload?.contract_version !== 'live-verification-v1' || !Array.isArray(payload.daily) || !Array.isArray(payload.classes) ||
      !Number.isInteger(payload.place_days) || !Number.isInteger(payload.days_verified) || !payload.amounts)
    fail('Live track record')
  for (const key of ['shown', 'rule', 'model_only']) verifiedScores(payload[key], payload.classes)
  if (payload.shown.n !== payload.place_days || payload.rule.n !== payload.place_days) fail('Live track record')
  return payload
}

// "3 of 4" style counts read better than a percentage on a small sample.
export const share = (part, whole) => whole ? `${part} of ${whole}` : '—'

// One plain sentence for the headline, honest about small samples and dry spells.
export function trackRecordHeadline(v) {
  if (!v.days_verified) return 'No days checked yet. The first result appears once the satellite rain for a forecast day is in (about two days later).'
  const heavyDays = v.shown.hits + v.shown.misses
  const days = `${v.days_verified} day${v.days_verified === 1 ? '' : 's'}`
  if (!heavyDays && !v.shown.false_alarms) return `${days} checked. No heavy rain fell and none was forecast, so heavy-rain skill cannot be judged yet.`
  if (!heavyDays) return `${days} checked. No heavy rain fell; heavy rain was forecast for ${v.shown.false_alarms} place-days (false alarms).`
  return `${days} checked. Heavy rain fell on ${heavyDays} place-days and the map had flagged ${v.shown.hits} of them.`
}

// ---- Rainfall the system collected (NASA IMERG Early), growing by one day each day ----

const isDay = v => /^\d{4}-\d{2}-\d{2}$/.test(v)
const mmOrNull = v => v === null || (num(v) && v >= 0)

export function parseObservedRainfall(payload) {
  if (payload?.contract_version !== 'observed-rainfall-v1' || !Array.isArray(payload.daily) || !payload.daily.length ||
      !Array.isArray(payload.areas) || !Array.isArray(payload.monthly) || !num(payload.thresholds_mm?.heavy) ||
      !isDay(payload.first_day) || !isDay(payload.last_day))
    fail('Collected rainfall')
  for (const d of payload.daily)
    if (!isDay(d.date) || !mmOrNull(d.nairobi_mm) || !(d.by_area === null || (Array.isArray(d.by_area) && d.by_area.length === payload.areas.length && d.by_area.every(mmOrNull))))
      fail('Collected rainfall')
  return payload
}

const DAY = 86400000
const addDays = (iso, n) => new Date(Date.parse(iso + 'T00:00:00Z') + n * DAY).toISOString().slice(0, 10)
const sum = values => values.reduce((s, v) => s + v, 0)

// The last `days` calendar days up to the newest collected day; days never collected are gaps (null).
export function dailyWindow(data, days) {
  const byDate = new Map(data.daily.map(d => [d.date, d]))
  const count = days ?? Math.round((Date.parse(data.last_day) - Date.parse(data.first_day)) / DAY) + 1
  return Array.from({ length: count }, (_, i) => {
    const date = addDays(data.last_day, i - count + 1)
    return { date, mm: byDate.get(date)?.nairobi_mm ?? null, collected: byDate.has(date) }
  })
}

// Tiles: newest day, recent totals and the time since the last heavy-rain day.
export function recentStats(data) {
  const heavy = data.thresholds_mm.heavy
  const known = data.daily.filter(d => d.nairobi_mm !== null)
  const latest = known.at(-1) ?? null
  const total = n => { const w = dailyWindow(data, n).filter(d => d.mm !== null); return { mm: sum(w.map(d => d.mm)), days: w.length, of: n } }
  const lastHeavy = [...known].reverse().find(d => d.nairobi_mm >= heavy) ?? null
  const wettest = known.reduce((a, b) => (b.nairobi_mm > (a?.nairobi_mm ?? -1) ? b : a), null)
  return {
    latest, week: total(7), month: total(30), lastHeavy, wettest,
    daysSinceHeavy: lastHeavy ? Math.round((Date.parse(data.last_day) - Date.parse(lastHeavy.date)) / DAY) : null,
    rainyDays30: dailyWindow(data, 30).filter(d => d.mm !== null && d.mm >= 1).length,
  }
}

// Collected months next to the long-term (2016–2025) average for the same calendar month.
export function collectedMonthly(data) {
  const average = Object.fromEntries((data.climatology ?? []).map(m => [m.month, m.average_mm]))
  return data.monthly.map(m => {
    const [year, month] = m.month.split('-').map(Number)
    const inMonth = new Date(Date.UTC(year, month, 0)).getUTCDate()
    return { key: m.month, label: `${MONTHS[month - 1]} ’${String(year).slice(2)}`, collected: m.total_mm, average: average[month] ?? null,
      complete: m.days >= inMonth, days: m.days }
  })
}

// Sub-county × day grid for the most recent days that carry per-area values; wettest areas first.
export function areaGrid(data, days = 14) {
  const recent = data.daily.filter(d => Array.isArray(d.by_area)).slice(-days)
  const rows = data.areas.map((area, i) => ({ ...area, values: recent.map(d => d.by_area[i]) }))
    .map(r => ({ ...r, total: sum(r.values.filter(v => v !== null)) }))
    .sort((a, b) => b.total - a.total || a.name.localeCompare(b.name))
  return { dates: recent.map(d => d.date), rows }
}

export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export const percent = value => `${Math.round(value * 100)}%`

// Query string for a download; empty fields are left out.
export function exportPath(base, fields) {
  const query = new URLSearchParams(Object.entries(fields).filter(([, v]) => v))
  return query.size ? `${base}?${query}` : base
}

export function saveFile({ blob, filename }) {
  const url = URL.createObjectURL(blob)
  const link = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(link); link.click(); link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
