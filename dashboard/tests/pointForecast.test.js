import test from 'node:test'
import assert from 'node:assert/strict'
import { parsePointForecast } from '../src/services/pointForecast.js'

const now=Date.parse('2026-11-12T10:00Z')
function response(){return {contract_version:'monitored-point-context-v1',weather_source:{received_at_utc:'2026-11-12T09:00Z',forecast_initialization_utc:'2026-11-12T00:00Z'},rows:[{area_id:'NFW-S037',weather:{returned_grid_point:{latitude:-1.3,longitude:36.8},shared_grid_area_ids:['NFW-S003','NFW-S037']},forecast_proxy_context:{contract_version:'request-time-forecast-proxy-context-v1',status:'AVAILABLE_FORECAST_RULE_CONTEXT',method:'forecast_daily_rainfall_threshold_rule',model_version:null,flood_probability:null,proxy_class:'Moderate',daily_forecast_rainfall_mm:8,target_start:'2026-11-12T21:00Z'}}]}}
test('forecast proxy carries method, dates and shared grid without a model probability',()=>{
  const p=parsePointForecast(response(),'NFW-S037',now)
  assert.equal(p.proxy_class,'Moderate');assert.equal(p.shared.length,2);assert.equal(p.model_version,null)
})
test('wrong methods, probability claims, categories and expired sources are withheld',()=>{
  for(const edit of [p=>p.rows[0].forecast_proxy_context.model_version='v1',p=>p.rows[0].forecast_proxy_context.flood_probability=.8,p=>p.rows[0].forecast_proxy_context.proxy_class='Extreme',p=>p.weather_source.received_at_utc='2026-11-11T09:00Z',p=>p.rows[0].forecast_proxy_context.target_start='2026-11-11T21:00Z']){
    const p=response();edit(p);assert.throws(()=>parsePointForecast(p,'NFW-S037',now))
  }
})
test('a point without forecast coverage remains unavailable and cannot inherit another point',()=>{
  assert.throws(()=>parsePointForecast(response(),'NFW-S040',now))
  const p=response();Object.assign(p.rows[0].forecast_proxy_context,{status:'UNAVAILABLE',proxy_class:null,daily_forecast_rainfall_mm:null})
  assert.equal(parsePointForecast(p,'NFW-S037',now).status,'UNAVAILABLE')
})
