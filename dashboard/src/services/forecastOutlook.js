// Weather forecasts only. This module never calls a model or prediction endpoint.
export const OUTLOOK_PATH = '/api/v1/weather-outlook'
export const snapshotPath = id => id ? OUTLOOK_PATH + '?' + new URLSearchParams({ snapshot_id: id }) : OUTLOOK_PATH
const aware = value => typeof value === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value))
const number = value => typeof value === 'number' && Number.isFinite(value)
const uuid = value => typeof value === 'string' && /^[a-f0-9-]{36}$/i.test(value)
const periods = ['NOT_YET_ISSUED', 'ARCHIVED', 'CURRENT_PERIOD', 'UPCOMING_PERIOD']
export function nairobiTime(value) {
  return aware(value) ? new Date(value).toLocaleString('en-GB', { timeZone: 'Africa/Nairobi', dateStyle: 'medium', timeStyle: 'short' }) + ' EAT' : 'Unavailable'
}
export function rainfallText(value) {
  return number(value) && value >= 0 ? value.toFixed(2) + ' mm' : 'Unavailable'
}
export function periodLabel(status) {
  return { ARCHIVED: 'Archived weather forecast', CURRENT_PERIOD: 'Stored forecast for the current day', UPCOMING_PERIOD: 'Stored forecast for an upcoming day', NOT_YET_ISSUED: 'Stored forecast before its issue cutoff' }[status] ?? 'Weather forecast unavailable'
}
function validSummary(item) {
  return uuid(item?.snapshot_id) && item.source_model === 'ecmwf_ifs' &&
    ['forecast_initialization', 'issue_cutoff', 'target_start', 'target_end'].every(key => aware(item[key])) &&
    Date.parse(item.target_end) - Date.parse(item.target_start) === 86400000 && periods.includes(item.period_status)
}
function periodAt(item, at) {
  if (Date.parse(item.issue_cutoff) > Date.parse(at)) return 'NOT_YET_ISSUED'
  if (Date.parse(item.target_end) <= Date.parse(at)) return 'ARCHIVED'
  return Date.parse(item.target_start) <= Date.parse(at) ? 'CURRENT_PERIOD' : 'UPCOMING_PERIOD'
}
export function validateSnapshots(body) {
  if (!Array.isArray(body?.items) || !Number.isInteger(body.total) || body.total < body.items.length ||
    !aware(body.checked_at) || body.items.some(item => !validSummary(item) || periodAt(item, body.checked_at) !== item.period_status)) throw new Error('Invalid forecast catalogue. No forecast confirmed.')
  return body
}
export function validateOutlook(body, requestedId = '') {
  const fail = () => { throw new Error('Invalid weather outlook. No forecast values confirmed.') }
  if (body?.information_type !== 'numerical_weather_forecast' || body.model_inference_performed !== false ||
    body.collection_automatic !== false || body.timezone !== 'Africa/Nairobi' || !aware(body.checked_at) ||
    body.selection !== (requestedId ? 'explicit_snapshot' : 'current_or_upcoming') ||
    !['AVAILABLE', 'NO_CURRENT_FORECAST', 'UNAVAILABLE'].includes(body.status) ||
    !Array.isArray(body.limitations) || typeof body.explanation !== 'string') fail()
  if (body.status !== 'AVAILABLE') {
    if (body.snapshot !== null) fail()
    return body
  }
  const s = body.snapshot
  if (!validSummary(s) || periodAt(s, body.checked_at) !== s.period_status || (requestedId && s.snapshot_id !== requestedId) ||
    (!requestedId && !['CURRENT_PERIOD', 'UPCOMING_PERIOD'].includes(s.period_status)) ||
    s.effective_readiness !== 'READY_FOR_SHADOW_SNAPSHOT' || s.target_quality !== 'PASSED' ||
    !['PASSED', 'PARTIAL'].includes(s.source_quality) || !aware(s.source_received_at) ||
    !aware(s.source_request_started_at) || !aware(s.source_stored_at) ||
    (s.source_publication_at !== null && !aware(s.source_publication_at)) ||
    !number(s.receipt_age_hours) || s.receipt_age_hours < 0 || !number(s.run_age_hours) || s.run_age_hours < 0 ||
    s.weather_units?.precipitation !== 'mm' || s.weather_units?.temperature_2m !== '°C' ||
    s.weather_units?.relative_humidity_2m !== '%' || s.weather_units?.wind_speed_10m !== 'km/h' ||
    s.weather_units?.soil_moisture_0_to_7cm !== 'm³/m³' ||
    !Array.isArray(s.zones) || s.zones.length !== 8 || new Set(s.zones.map(z => z.zone_id)).size !== 8) fail()
  const ids = s.zones.map(z => z.zone_id)
  for (const z of s.zones) {
    if (typeof z.name !== 'string' || !number(z.rainfall_mm) || z.rainfall_mm < 0 ||
      !['PASSED', 'PARTIAL'].includes(z.source_quality) || z.target_quality !== 'PASSED' ||
      !Array.isArray(z.warnings) || z.valid_rainfall_intervals !== 24 ||
      !Array.isArray(z.hourly_rainfall) || z.hourly_rainfall.length !== 24 ||
      !Array.isArray(z.hourly_weather) || z.hourly_weather.length !== 24 ||
      !number(z.returned_elevation_m)) fail()
    for (const point of [z.monitoring_point, z.returned_grid_point]) {
      if (!number(point?.latitude) || Math.abs(point.latitude) > 90 || !number(point?.longitude) || Math.abs(point.longitude) > 180) fail()
    }
    for (const group of [z.shared_grid_zone_ids, z.identical_weather_zone_ids]) {
      if (!Array.isArray(group) || !group.includes(z.zone_id) || group.some(id => !ids.includes(id))) fail()
    }
    z.hourly_rainfall.forEach((row, i) => {
      if (!aware(row.interval_start) || !aware(row.interval_end) ||
        Date.parse(row.interval_start) !== Date.parse(s.target_start) + i * 3600000 ||
        Date.parse(row.interval_end) !== Date.parse(row.interval_start) + 3600000 ||
        !number(row.precipitation_mm) || row.precipitation_mm < 0) fail()
    })
    const total = z.hourly_rainfall.reduce((sum, r) => sum + r.precipitation_mm, 0)
    if (Math.abs(total - z.rainfall_mm) > 1e-8 * Math.max(1, total)) fail()
    z.hourly_weather.forEach((r, i) => {
      if (!aware(r.valid_at) || Date.parse(r.valid_at) !== Date.parse(s.target_start) + i * 3600000 ||
        !number(r.temperature_2m) || !number(r.relative_humidity_2m) || r.relative_humidity_2m < 0 || r.relative_humidity_2m > 100 ||
        !number(r.wind_speed_10m) || r.wind_speed_10m < 0 ||
        !number(r.soil_moisture_0_to_7cm) || r.soil_moisture_0_to_7cm < 0 || r.soil_moisture_0_to_7cm > 1) fail()
    })
  }
  return body
}
