import test from 'node:test'
import assert from 'node:assert/strict'
import { expireOutlook,parseMonitoringOutlook,outlookPoint,fetchMonitoringOutlook,ruleClass,classExplanation,plainSummary,pointCategory,outlookCounts,CATEGORY_ADVICE } from '../src/services/monitoringOutlook.js'

const now=Date.parse('2026-11-13T10:00Z')
const VERSION='stage2-xgb-ad9614eb6e85'
function fixture(){
  const source={method:'stage2_xgboost_with_rule_fallback',model_version:VERSION,flood_probability:null,publication_at:null,
    thresholds:{tomorrow_mm:[5,20,40],accumulation_mm:[25,80,150],accumulation_window_hours:165},
    requested_at:'2026-11-13T09:00:00Z',received_at:'2026-11-13T09:00:01Z',stored_at:'2026-11-13T09:00:02Z',run_at:'2026-11-13T00:00:00Z',
    target_start:'2026-11-13T21:00:00Z',target_end:'2026-11-14T21:00:00Z',expires_at:'2026-11-13T15:00:01.000Z'}
  const common={status:'AVAILABLE',received_at:source.received_at,run_at:source.run_at,target_start:source.target_start,target_end:source.target_end,expires_at:source.expires_at,source_grid_point:{latitude:-1.3,longitude:36.8},
    missing_issue_day_hours:0,accumulation_complete:true,fallback_reasons:[],model_status:'APPLIED',model_version:VERSION}
  return {contract_version:'monitoring-rainfall-outlook-v3',status:'AVAILABLE',available_count:3,located_count:3,collection:source,collection_automatic:false,next_collection_at:null,automation_configured:false,configured_interval_hours:null,
    areas:[
      // Rule: 8 mm tomorrow (Moderate), 70 + 6 + 8 = 84 mm over 7 days (High). Model: Extreme; rule reaches High so no guard.
      {...common,area_id:'NFW-S037',rainfall_mm:8,proxy_class:'Extreme',rule_class:'High',method:'stage2_xgboost_guarded',class_driver:'accumulation',
       antecedent_observed_mm:70,issue_day_forecast_mm:6,accumulation_7d_mm:84,antecedent_cell:'lat887_lon2168',
       model_scores:{Low:0.05,Moderate:0.1,High:0.25,Extreme:0.6},guard_applied:false,shared_area_ids:['NFW-S037']},
      // Rule Moderate (6 mm tomorrow; 10 + 2 + 6 = 18 mm). Model leans Extreme -> guard holds it at High.
      {...common,area_id:'NFW-S011',rainfall_mm:6,proxy_class:'High',rule_class:'Moderate',method:'stage2_xgboost_guarded',class_driver:'tomorrow',
       antecedent_observed_mm:10,issue_day_forecast_mm:2,accumulation_7d_mm:18,antecedent_cell:'lat887_lon2169',
       model_scores:{Low:0.1,Moderate:0.2,High:0.3,Extreme:0.4},guard_applied:true,shared_area_ids:['NFW-S011']},
      // Observed satellite days missing: rule only, 2 + 3 = at least 5 mm over 7 days.
      {...common,area_id:'NFW-S002',rainfall_mm:3,proxy_class:'Low',rule_class:'Low',method:'observed_plus_forecast_rule_lower_bound',class_driver:'tomorrow',
       antecedent_observed_mm:null,issue_day_forecast_mm:2,accumulation_7d_mm:5,accumulation_complete:false,antecedent_cell:'lat887_lon2167',
       fallback_reasons:['IMERG_DAYS_MISSING:2026-11-12'],model_status:'INPUTS_INCOMPLETE',model_version:null,model_scores:null,guard_applied:false,shared_area_ids:['NFW-S002']}]}
}

test('the rule is the higher of tomorrow and 7-day classes, matching the v1 label thresholds',()=>{
  assert.deepEqual(ruleClass(4.9,24.9),{proxy_class:'Low',class_driver:'tomorrow'})
  assert.deepEqual(ruleClass(0,25),{proxy_class:'Moderate',class_driver:'accumulation'})
  assert.deepEqual(ruleClass(20,80),{proxy_class:'High',class_driver:'tomorrow'})
  assert.deepEqual(ruleClass(0,150),{proxy_class:'Extreme',class_driver:'accumulation'})
  assert.deepEqual(ruleClass(40,null),{proxy_class:'Extreme',class_driver:'tomorrow_only'})
})

test('a coherent v3 outlook validates the model, the guard and the rule fallback',()=>{
  const doc=parseMonitoringOutlook(fixture(),now)
  assert.equal(doc.available_count,3)
  const model=outlookPoint(doc,'NFW-S037')
  assert.equal(model.proxy_class,'Extreme');assert.equal(model.ruleClass,'High');assert.equal(model.accumulation7dMm,84)
  assert.match(classExplanation(model),/XGBoost model.*rule alone would give High/)
  assert.match(classExplanation(outlookPoint(doc,'NFW-S011')),/only shown when the rainfall rule also reaches High/)
  assert.match(classExplanation(outlookPoint(doc,'NFW-S002')),/minimum because recent satellite rainfall is not yet available/)
  assert.equal(outlookPoint(doc,'NFW-S999').status,'UNAVAILABLE')
})

test('the rule-only outlook (model package unavailable) still validates',()=>{
  const p=fixture();p.collection.model_version=null
  p.areas=[p.areas[2]];p.available_count=p.located_count=1
  assert.equal(parseMonitoringOutlook(p,now).available_count,1)
})

test('open pages clear expired categories, amounts and model scores without a new request',()=>{
  const doc=expireOutlook(parseMonitoringOutlook(fixture(),now),Date.parse('2026-11-13T15:00:01Z'))
  assert.equal(doc.available_count,0)
  for (const area of doc.areas) {assert.equal(area.proxy_class,null);assert.equal(area.accumulation_7d_mm,null);assert.equal(area.model_scores,null)}
})

test('tampered model output, guard, rule, sums or provenance fail closed',()=>{
  for(const edit of [
    p=>p.areas[0].proxy_class='High',                         // not the arg-max
    p=>p.areas[1].proxy_class='Extreme',                      // guard bypassed
    p=>p.areas[1].guard_applied=false,
    p=>p.areas[0].rule_class='Moderate',                      // rule must be re-derivable
    p=>p.areas[0].model_scores.Extreme=0.9,                   // scores must sum to 1
    p=>p.areas[0].model_version='stage2-xgb-000000000000',     // must match the collection
    p=>p.collection.model_version='xgboost',
    p=>p.areas[0].model_status='INPUTS_INCOMPLETE',
    p=>{p.areas[2].method='stage2_xgboost_guarded';p.areas[2].model_scores={Low:1,Moderate:0,High:0,Extreme:0}},  // model on incomplete inputs
    p=>p.areas[2].proxy_class='Moderate',                     // fallback must equal the rule
    p=>p.areas[0].accumulation_7d_mm=60,
    p=>p.collection.flood_probability=.9,
    p=>p.contract_version='monitoring-rainfall-outlook-v2',
    p=>p.areas.push(p.areas[0]),p=>p.areas[0].target_end='2026-11-14T20:00Z',p=>p.areas[0].shared_area_ids=['invented'],p=>p.automation_configured=true,p=>p.collection_automatic=true,p=>{p.collection_automatic=true;p.automation_configured=true;p.configured_interval_hours=1}]){
    const p=fixture();edit(p);assert.throws(()=>parseMonitoringOutlook(p,now))
  }
})

test('fetch reads stored weather only, sends no bearer and never invokes collection',async()=>{
  const original=global.fetch
  global.fetch=async(url,options)=>{assert.ok(url.endsWith('/monitoring-areas/outlook'));assert.equal(options.cache,'no-store');assert.equal(options.headers,undefined);return {ok:false}}
  try{await assert.rejects(fetchMonitoringOutlook(),/unavailable/)}finally{global.fetch=original}
})

test('map pins take the highest fresh category; expired or missing areas give none',() => {
  const data={areas:[{area_id:'NFW-S001',status:'AVAILABLE',proxy_class:'Moderate'},{area_id:'NFW-S002',status:'AVAILABLE',proxy_class:'High'},
    {area_id:'NFW-S003',status:'UNAVAILABLE',proxy_class:null}]}
  assert.equal(pointCategory(data,['NFW-S001']),'Moderate')
  assert.equal(pointCategory(data,['NFW-S001','NFW-S002']),'High')
  assert.equal(pointCategory(data,['NFW-S003']),null)
  assert.equal(pointCategory(data,['NFW-S999']),null)
  assert.equal(pointCategory(null,['NFW-S001']),null)
  assert.deepEqual(outlookCounts(data),[{category:'High',count:1},{category:'Moderate',count:1}])
  assert.deepEqual(outlookCounts(null),[])
})

test('plain summaries use simple wording and never present a lower bound as exact',() => {
  const point={status:'AVAILABLE_FORECAST_RULE_CONTEXT',daily_forecast_rainfall_mm:8.1,accumulation7dMm:49.8,accumulationComplete:true}
  assert.equal(plainSummary(point),'About 8 mm of rain is forecast tomorrow. With recent rain, that makes a wet week: about 50 mm over 7 days.')
  assert.match(plainSummary({...point,daily_forecast_rainfall_mm:26}),/^Heavy rain is forecast tomorrow \(about 26 mm\)/)
  assert.match(plainSummary({...point,daily_forecast_rainfall_mm:0.2,accumulation7dMm:3}),/^Little or no rain .* about 3 mm over 7 days\.$/)
  assert.match(plainSummary({...point,accumulationComplete:false}),/at least 50 mm/)
  assert.equal(plainSummary({status:'UNAVAILABLE'}),'')
  for (const c of ['Low','Moderate','High','Extreme']) assert.ok(CATEGORY_ADVICE[c].length>20)
  assert.match(CATEGORY_ADVICE.Low,/still happen/)
})

test('automatic collection is accepted only with its next run time',() => {
  const auto={...fixture(),collection_automatic:true,automation_configured:true,configured_interval_hours:1,next_collection_at:'2026-11-13T11:05:00Z'}
  assert.equal(parseMonitoringOutlook(auto,now).collection_automatic,true)
})
