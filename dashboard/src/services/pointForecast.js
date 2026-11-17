export function parsePointForecast(payload, areaId, now=Date.now()) {
  if (payload?.contract_version !== 'monitored-point-context-v1' || !Array.isArray(payload.rows)) throw new Error('Unverified point forecast response')
  const row=payload.rows.find(r => r.area_id === areaId), source=payload.weather_source
  if (!row || !source) throw new Error('Point forecast is unavailable')
  const proxy=row.forecast_proxy_context
  if (!proxy || proxy.contract_version !== 'request-time-forecast-proxy-context-v1' || proxy.method !== 'forecast_daily_rainfall_threshold_rule' || proxy.model_version !== null || proxy.flood_probability !== null) throw new Error('Unsupported proxy method')
  if (proxy.status !== 'AVAILABLE_FORECAST_RULE_CONTEXT') {
    if (proxy.proxy_class !== null || proxy.daily_forecast_rainfall_mm !== null) throw new Error('Unavailable forecast contains a category')
    return { status:'UNAVAILABLE' }
  }
  const received=Date.parse(source.received_at_utc),run=Date.parse(source.forecast_initialization_utc),start=Date.parse(proxy.target_start)
  if (!Number.isFinite(received) || received>now || now-received>6*3600000 || !Number.isFinite(run) || run>received || now-run>24*3600000 || !(start>now)) throw new Error('Point forecast has expired')
  const amount=proxy.daily_forecast_rainfall_mm
  const expected=amount>=40?'Extreme':amount>=20?'High':amount>=5?'Moderate':'Low'
  if (!Number.isFinite(amount) || amount<0 || proxy.proxy_class !== expected || !row.weather?.returned_grid_point || !Array.isArray(row.weather.shared_grid_area_ids) || !row.weather.shared_grid_area_ids.includes(areaId)) throw new Error('Invalid point proxy evidence')
  return { ...proxy, receivedAt:source.received_at_utc, runAt:source.forecast_initialization_utc, shared:row.weather.shared_grid_area_ids }
}
