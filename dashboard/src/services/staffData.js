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
