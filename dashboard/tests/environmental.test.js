import assert from 'node:assert/strict'
import test from 'node:test'
import { chartRows, observedWindows, observationPath, rainfallPath, rainfallLabel, validateRegistry, validateObservations, validateRainfall } from '../src/services/environmental.js'

test('source resolution restricts observed accumulation windows', () => {
  assert.deepEqual(observedWindows('daily'), [24,48,168])
  assert.deepEqual(observedWindows('hourly'), [3,6,12,24,48,168])
  assert.deepEqual(observedWindows('static'), [])
})
test('null bins remain null while true zero remains zero', () => {
  assert.deepEqual(chartRows([{observed_at:'a',value:0},{observed_at:'b',value:null},{observed_at:'c',value:NaN}]), [
    {time:'a',rainfall:0},{time:'b',rainfall:null},{time:'c',rainfall:null}])
  assert.equal(rainfallLabel({status:'AVAILABLE_HISTORICAL',rainfall_mm:0}), '0.00 mm')
  assert.equal(rainfallLabel({status:'INSUFFICIENT_DATA',rainfall_mm:null}), 'Insufficient data')
})
test('queries isolate dataset and zone and encode timezone offsets', () => {
  const params=new URLSearchParams(observationPath('version','a&b',200).split('?')[1])
  assert.equal(params.get('zone_id'),'a&b'); assert.equal(params.get('offset'),'200')
  assert.equal(params.get('limit'),'200'); assert.equal(params.get('variable'),'rainfall')
  const rain=new URLSearchParams(rainfallPath('version','cbd','2024-05-02T00:00:00+03:00',24).split('?')[1])
  assert.equal(rain.get('end_at'),'2024-05-02T00:00:00+03:00')
})
test('absent source bins break the chart line without inventing rainfall', () => {
  const points=chartRows([{observed_at:'2024-05-01T00:00:00Z',bin_end_at:'2024-05-01T01:00:00Z',value:1},
    {observed_at:'2024-05-01T02:00:00Z',bin_end_at:'2024-05-01T03:00:00Z',value:2}])
  assert.equal(points.length,3); assert.equal(points[1].rainfall,null)
})
test('malformed or mismatched API data cannot appear as confirmed readings', () => {
  assert.throws(()=>validateRegistry([],{}),/Invalid environmental registry/)
  assert.throws(()=>validateObservations({dataset_id:'other',items:[],total:0},'wanted','cbd'),/Invalid rainfall-bin/)
  const row={zone_id:'cbd',variable:'rainfall',observed_at:'2024-05-01T00:00:00Z',bin_end_at:'2024-05-01T01:00:00Z',value:0,unit:'mm',quality_flags:[]}
  assert.equal(validateObservations({dataset_id:'wanted',items:[row],total:1},'wanted','cbd').items[0].value,0)
  for(const change of [{value:'0'},{unit:'m'},{value:Infinity},{observed_at:'2024-05-01'}]) {
    assert.throws(()=>validateObservations({dataset_id:'wanted',items:[{...row,...change}],total:1},'wanted','cbd'),/Invalid rainfall-bin/)
  }
})
test('window response must match requested source/zone/time and missing cannot be zero', () => {
  const result={dataset_id:'version',zone_id:'cbd',window_hours:24,window_end:'2024-05-02T00:00:00Z',supports_operational_issue:false,reason_codes:[],status:'AVAILABLE_HISTORICAL',rainfall_mm:0}
  assert.equal(validateRainfall(result,'version','cbd',result.window_end,24).rainfall_mm,0)
  for(const change of [{zone_id:'other'},{window_hours:6},{supports_operational_issue:true},{status:'INSUFFICIENT_DATA'},{rainfall_mm:NaN}]) {
    assert.throws(()=>validateRainfall({...result,...change},'version','cbd',result.window_end,24),/Invalid rainfall-window/)
  }
})
