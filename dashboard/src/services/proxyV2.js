export const V2_MODEL_PATH='/api/v2/model'
export const V2_FEATURES_PATH='/api/v2/features'
export const V2_FEATURE_ORDER=['rainfall_total_mm','rainfall_max_3h_mm','rainfall_max_6h_mm','rainy_hours','temp_mean_c','humidity_mean_pct','wind_max_kmh','soil_moisture_mean_m3m3','target_month_sin','target_month_cos']
export const V2_FEATURE_UNITS=['mm','mm','mm','hours','degC','percent','km/h','m3/m3','dimensionless','dimensionless']
export function validateV2Status(body){
  if(!['MODEL_UNAVAILABLE','AVAILABLE_UNAPPROVED'].includes(body?.status)||body.shadow_execution_enabled!==false||body.public_alerts_enabled!==false)throw Error('Unverified v2 model status')
  return body
}
export function validateV2Features(body){
  if(body?.status!=='AVAILABLE_SHADOW_FEATURES'||body.information_type!=='forecast_weather_features_not_flood_predictions'||body.model_inference_performed!==false||
    !Array.isArray(body.zones)||body.zones.length!==8||new Set(body.zones.map(z=>z.zone_id)).size!==8||
    body.feature_contract?.contract_version!=='ifs-eat-nextday-10-v1'||
    body.feature_contract.ordered_features?.join('|')!==V2_FEATURE_ORDER.join('|')||
    V2_FEATURE_ORDER.some((name,i)=>body.feature_contract.units?.[name]!==V2_FEATURE_UNITS[i]))throw Error('Unverified v2 feature response')
  const order=body.feature_contract.ordered_features
  if(body.zones.some(z=>!z.feature_complete||Object.keys(z.features).join('|')!==order.join('|')||Object.values(z.features).some(v=>typeof v!=='number'||!Number.isFinite(v))))throw Error('Invalid v2 feature vector')
  const checked=Date.parse(body.checked_at),start=Date.parse(body.target_start_utc),end=Date.parse(body.target_end_utc)
  if(![checked,start,end].every(Number.isFinite)||end-start!==86400000||checked>=end||
    body.vintage_status!=='PROSPECTIVE_CAPTURED'||body.target_quality!=='PASSED'||
    !['CURRENT_ISSUE','PREVIOUS_ISSUE_CURRENT_TARGET_PREVIEW_ONLY'].includes(body.source_context)||
    typeof body.eligible_for_new_issue_inference!=='boolean'||
    (body.source_context==='PREVIOUS_ISSUE_CURRENT_TARGET_PREVIEW_ONLY'&&body.eligible_for_new_issue_inference))throw Error('Stale or incompatible v2 source context')
  return body
}
