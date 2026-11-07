export const SOURCE_OPTIONS = ['chirps-zones', 'era5-daily-zones', 'era5-hourly-cbd', 'terrain-static']
export const WINDOWS = [3, 6, 12, 24, 48, 168]
export function observedWindows(resolution) {
  return resolution === 'daily' ? WINDOWS.filter(hours => hours % 24 === 0) : resolution === 'hourly' ? WINDOWS : []
}
export function observationPath(dataset, zone, offset = 0) {
  return '/api/v1/environmental-data/observations?' + new URLSearchParams({ dataset_id: dataset, zone_id: zone, variable: 'rainfall', limit: '200', offset: String(offset) })
}
export function rainfallPath(dataset, zone, end, hours) {
  return '/api/v1/environmental-data/rainfall?' + new URLSearchParams({ dataset_id: dataset, zone_id: zone, end_at: end, window_hours: String(hours) })
}
export function chartRows(items) {
  return items.flatMap((row, index) => {
    const point = { time: row.observed_at, rainfall: typeof row.value === 'number' && Number.isFinite(row.value) ? row.value : null }
    // Break the line across absent source bins without inventing observations.
    return row.bin_end_at && items[index + 1] && Date.parse(row.bin_end_at) < Date.parse(items[index + 1].observed_at)
      ? [point, { time: row.bin_end_at, rainfall: null }] : [point]
  })
}
export function rainfallLabel(result) {
  return result?.status === 'AVAILABLE_HISTORICAL' && typeof result.rainfall_mm === 'number' && Number.isFinite(result.rainfall_mm) ? `${result.rainfall_mm.toFixed(2)} mm` : 'Insufficient data'
}

const awareTime = value => typeof value === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value))
export function validateRegistry(sources, listing) {
  if (!Array.isArray(sources) || !Array.isArray(listing?.items) || !Number.isInteger(listing.total) || listing.total < listing.items.length ||
      sources.some(source => !SOURCE_OPTIONS.includes(source.id) || !['daily','hourly','static'].includes(source.temporal_resolution)) ||
      listing.items.some(item => !/^[a-f0-9]{64}$/.test(item.id) || !sources.some(source => source.id === item.source_id) ||
        !Array.isArray(item.provenance?.zone_ids) || item.provenance.zone_ids.some(id => typeof id !== 'string') ||
        !['HISTORICAL_ONLY','STATIC_UNVERIFIED'].includes(item.freshness?.status) ||
        item.freshness.operational_freshness !== 'NOT_ESTABLISHED' ||
        (item.end_at !== null && !awareTime(item.end_at)))) throw new Error('Invalid environmental registry response. No source data confirmed.')
  return listing.items
}
export function validateObservations(body, dataset, zone) {
  if (body?.dataset_id !== dataset || !Array.isArray(body.items) || !Number.isInteger(body.total) || body.total < body.items.length ||
      body.items.some(row => row.zone_id !== zone || row.variable !== 'rainfall' || row.unit !== 'mm' ||
        !awareTime(row.observed_at) || !awareTime(row.bin_end_at) || Date.parse(row.bin_end_at) <= Date.parse(row.observed_at) ||
        (row.value !== null && (typeof row.value !== 'number' || !Number.isFinite(row.value) || row.value < 0)) ||
        !Array.isArray(row.quality_flags))) throw new Error('Invalid rainfall-bin response. No readings confirmed.')
  return body
}
export function validateRainfall(body, dataset, zone, end, hours) {
  if (body?.dataset_id !== dataset || body.zone_id !== zone || body.window_hours !== hours ||
      !awareTime(body.window_end) || Date.parse(body.window_end) !== Date.parse(end) || body.supports_operational_issue !== false ||
      !Array.isArray(body.reason_codes) || !['AVAILABLE_HISTORICAL','INSUFFICIENT_DATA'].includes(body.status) ||
      (body.status === 'INSUFFICIENT_DATA' ? body.rainfall_mm !== null :
        typeof body.rainfall_mm !== 'number' || !Number.isFinite(body.rainfall_mm) || body.rainfall_mm < 0)) throw new Error('Invalid rainfall-window response. No total confirmed.')
  return body
}
