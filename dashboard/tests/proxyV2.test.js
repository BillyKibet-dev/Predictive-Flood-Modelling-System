import assert from 'node:assert/strict'
import test from 'node:test'
import { V2_FEATURE_ORDER,V2_FEATURE_UNITS,validateV2Features,validateV2Status } from '../src/services/proxyV2.js'

// Synthetic transport-contract fixture only; never a model or training-data artifact.
function fixture(){return {
  status:'AVAILABLE_SHADOW_FEATURES', information_type:'forecast_weather_features_not_flood_predictions',model_inference_performed:false,
  feature_contract:{contract_version:'ifs-eat-nextday-10-v1',ordered_features:[...V2_FEATURE_ORDER],units:Object.fromEntries(V2_FEATURE_ORDER.map((n,i)=>[n,V2_FEATURE_UNITS[i]]))},
  checked_at:'2026-11-09T07:00:00Z',target_start_utc:'2026-11-08T21:00:00Z',target_end_utc:'2026-11-09T21:00:00Z',
  vintage_status:'PROSPECTIVE_CAPTURED',target_quality:'PASSED',source_context:'PREVIOUS_ISSUE_CURRENT_TARGET_PREVIEW_ONLY',eligible_for_new_issue_inference:false,
  zones:['cbd','dagoretti','embakasi','kasarani','kibera','mathare','ruaraka','westlands'].map(zone_id=>({zone_id,feature_complete:true,features:Object.fromEntries(V2_FEATURE_ORDER.map(n=>[n,0]))})),
}}
test('unavailable and unapproved models always retain execution and alert gates',()=>{
  for(const status of ['MODEL_UNAVAILABLE','AVAILABLE_UNAPPROVED'])assert.equal(validateV2Status({status,shadow_execution_enabled:false,public_alerts_enabled:false}).status,status)
  for(const b of [{status:'AVAILABLE'},{status:'MODEL_UNAVAILABLE',shadow_execution_enabled:true},{status:'AVAILABLE_UNAPPROVED',shadow_execution_enabled:false,public_alerts_enabled:true}])assert.throws(()=>validateV2Status(b))
})
test('exact ordered features and units accept a dated previous-issue inspection',()=>{
  const body=fixture();assert.equal(validateV2Features(body).zones.length,8)
  assert.equal(body.eligible_for_new_issue_inference,false)
})
test('missing, reordered, substituted or nonfinite features fail closed',()=>{
  for(const mutate of [
    b=>b.feature_contract.ordered_features.reverse(),
    b=>b.feature_contract.ordered_features[0]='observed_target_rain',
    b=>b.feature_contract.units.rainfall_total_mm='mm/h',
    b=>b.zones[0].features.rainfall_total_mm=null,
    b=>b.zones[0].features.rainfall_total_mm=NaN,
    b=>delete b.zones[0].features.rainy_hours,
    b=>b.zones.pop(),b=>b.zones[1].zone_id='cbd',b=>b.model_inference_performed=true,
  ]){const b=fixture();mutate(b);assert.throws(()=>validateV2Features(b))}
})
test('expired or wrongly promoted source cannot carry an available vector',()=>{
  for(const mutate of [
    b=>b.checked_at=b.target_end_utc,b=>b.checked_at='invalid',
    b=>b.target_quality='FAILED',b=>b.vintage_status='AS_ISSUED_VERIFIED',
    b=>b.eligible_for_new_issue_inference=true,
    b=>b.source_context='ARCHIVED',
  ]){const b=fixture();mutate(b);assert.throws(()=>validateV2Features(b))}
})
