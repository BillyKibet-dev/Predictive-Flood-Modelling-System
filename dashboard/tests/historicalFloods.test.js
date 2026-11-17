import test from 'node:test'
import assert from 'node:assert/strict'
import { fetchHistoricalEvidence, validateHistoricalDataset, validateHistoricalLayer, HISTORICAL_STYLES, POINT_LABELS, HISTORICAL_PATH } from '../src/services/historicalFloods.js'
import { RISK_COLORS } from '../src/constants/colors.js'

// Synthetic shapes remain isolated fixtures, never production historical observations.
const meta = () => ({ dataset_id:'unosat-20240501-nairobi-kiambu', information_type:'historical_satellite_observation',
  acquired_at:'2024-05-01T08:06:00Z', provider:'UNITAR-UNOSAT', product_id:'3833', limitations:[], administrative_context:[],
  monitoring_points:Array.from({length:8},(_,i)=>({zone_id:'test'+i,latitude:-1.2,longitude:36.8,
    observation_state:i%2?'CLOUD_OBSCURED':'OUTSIDE_ANALYSIS',confirmed_flood_free:null})) })
const layer = kind => ({ ...meta(), type:'FeatureCollection', layer_kind:kind, features:[{type:'Feature',id:kind,
  properties:{layer_kind:kind,acquired_at:'2024-05-01T08:06:00Z'},geometry:{type:'Polygon',coordinates:[[[36.8,-1.3],[36.9,-1.3],[36.9,-1.2],[36.8,-1.2],[36.8,-1.3]]]}}] })

test('authentic identity/date required; unknown is never flood-free',()=>{
  assert.equal(validateHistoricalDataset(meta()).monitoring_points[0].confirmed_flood_free,null)
  for(const mutate of [m=>m.information_type='flood_prediction',m=>m.acquired_at='2024-05-03T08:06:00Z',
    m=>m.monitoring_points[0].confirmed_flood_free=true,m=>m.monitoring_points[0].observation_state='NO_FLOOD',m=>m.monitoring_points.pop()]){
    const m=meta();mutate(m);assert.throws(()=>validateHistoricalDataset(m))
  }
  assert.match(POINT_LABELS.NO_DETECTION_REPORTED,/absence is unconfirmed/)
  assert.match(POINT_LABELS.CLOUD_OBSCURED,/Unknown/)
})
test('all three distinct historical geometry kinds validate independently',()=>{
  for(const kind of Object.keys(HISTORICAL_STYLES))assert.equal(validateHistoricalLayer(layer(kind),kind,meta()).layer_kind,kind)
  assert.notEqual(HISTORICAL_STYLES.flood.fillColor,HISTORICAL_STYLES.cloud.fillColor)
  const riskPalette=Object.values(RISK_COLORS).map(c=>c.toLowerCase())
  assert.ok(Object.values(HISTORICAL_STYLES).every(style=>!riskPalette.includes(style.color.toLowerCase())))
  assert.ok(HISTORICAL_STYLES.coverage.dashArray)
})
test('empty, malformed, projected or mismatched source cannot reach Leaflet',()=>{
  for(const mutate of [d=>d.features=[],d=>d.features[0].geometry=null,d=>d.features[0].geometry.type='Point',
    d=>d.features[0].geometry.coordinates[0][0]=[250000,9850000],d=>d.features[0].geometry.coordinates[0].pop(),
    d=>d.layer_kind='cloud',d=>d.information_type='proxy_prediction',d=>d.acquired_at='2024-05-02T08:06:00Z']){
    const d=layer('flood');mutate(d);assert.throws(()=>validateHistoricalLayer(d,'flood',meta()))
  }
})
test('authorized reads load an atomic complete source bundle, no weather or model endpoints',async()=>{
  const calls=[]
  const request=async(path,options)=>{calls.push({path,options});return path===HISTORICAL_PATH?meta():layer(path.split('/').at(-1))}
  const controller=new AbortController()
  const result=await fetchHistoricalEvidence(request,controller.signal)
  assert.equal(calls.length,4);assert.equal(Object.keys(result.layers).length,3)
  assert.ok(calls.every(c=>c.path.startsWith(HISTORICAL_PATH)&&c.options.signal===controller.signal))
  await assert.rejects(fetchHistoricalEvidence(async path=>{if(path.endsWith('/cloud'))throw Error('unavailable');return request(path,{})}),/unavailable/)
})
