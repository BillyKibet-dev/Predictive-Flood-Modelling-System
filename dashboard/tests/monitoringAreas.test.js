import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parseMonitoringAreas,filterMonitoringAreas,groupAreaPoints,fetchMonitoringAreas,nearbyWaterSummary } from '../src/services/monitoringAreas.js'

const raw=JSON.parse(readFileSync(new URL('../../src/api/data/monitoring_areas.json',import.meta.url)))

test('36 mapped records form 34 physical points; T-Mall has an actual Langata parent',() => {
  const data=parseMonitoringAreas(raw)
  assert.equal(data.sites.length,36)
  assert.equal(data.sites.filter(s => s.point).length,36)
  assert.equal(groupAreaPoints(data.sites).length,34)
  const gumba=data.sites.find(s => s.id==='NFW-S032')
  assert.deepEqual(gumba.point,{lon:36.860388889,lat:-1.261944444})
  assert.equal(gumba.reference_kind,'USER_REPORTED_LOCATION')
  assert.equal(data.sites.find(s => s.id==='NFW-S009'),undefined)
  const tmall=data.sites.find(s => s.id==='NFW-S037')
  assert.equal(tmall.parent_zone_id,'nairobi-subcounty-langata')
  assert.equal(tmall.parent_zone_name,'Langata')
  assert.equal(tmall.zone_id,null)
  assert.deepEqual(tmall.point,{lon:36.817166667,lat:-1.310944444})
  assert.equal(tmall.reference_kind,'USER_REPORTED_LOCATION')
  assert.equal(tmall.vegetation.status,'DERIVED_CONTEXT')
  assert.equal(tmall.vegetation.value,0.08518)
  const uhuru=data.sites.find(s => s.id==='NFW-S003')
  assert.deepEqual(uhuru.point,{lon:36.821388889,lat:-1.294305556})
  assert.equal(uhuru.parent_zone_name,'Starehe')
  assert.equal(uhuru.vegetation.value,0.12607)
  assert.equal(filterMonitoringAreas(data.sites,{zone:'nairobi-subcounty-langata'}).length,5)
  assert.equal(filterMonitoringAreas(data.sites,{location:'unlocated'}).length,0)
  assert.equal(filterMonitoringAreas(data.sites,{query:'electrical substation'})[0].display_name,'South C suburb')
  assert.equal(filterMonitoringAreas(data.sites,{query:'T-Mall'})[0].id,'NFW-S037')
  const dandora=filterMonitoringAreas(data.sites,{query:'Dandora Area 3'})
  assert.equal(dandora.length,2)
  assert.equal(groupAreaPoints(dandora).length,1)
  assert.equal(groupAreaPoints(dandora)[0].sites.length,2)
})

test('dated nearby-water context preserves unknown coverage and rejects stale coordinates',() => {
  const data=parseMonitoringAreas(raw),tmall=data.sites.find(s => s.id==='NFW-S037'),gatoto=data.sites.find(s => s.id==='NFW-S007')
  assert.match(nearbyWaterSummary(tmall.nearby_water_reference),/outside the historical scene/)
  assert.match(nearbyWaterSummary(gatoto.nearby_water_reference),/141 m/)
  for (const mutate of [
    c => { c.observation_date='2026-11-11' },
    c => { c.operational_use_allowed=true },
    c => { c.distance_m=-1 },
    c => { c.status='REFERENCE_IN_2024_CLOUD' },
  ]) { const c=structuredClone(gatoto.nearby_water_reference);mutate(c);assert.throws(() => nearbyWaterSummary(c)) }
  const changed=structuredClone(raw);changed.sites[0].nearby_water_reference.reference_coordinates=[0,0]
  assert.throws(() => parseMonitoringAreas(changed))
})

test('invalid coordinates, model scores and inconsistent parents cannot become area pins',() => {
  for (const mutate of [
    d => { d.sites.push(d.sites[0]) },
    d => { d.sites[0].geometry.coordinates=[NaN,0] },
    d => { d.sites[0].geometry.type='Polygon' },
    d => { d.sites[0].parent_zone_id='nairobi-subcounty-langata' },
    d => { d.sites[0].risk_score=.5 },
    d => { d.sites[0].geometry=null },
  ]) { const doc=structuredClone(raw);mutate(doc);assert.throws(() => parseMonitoringAreas(doc)) }
})

test('monitoring reads use the new API and preserve cancellation/error handling',async () => {
  const original=globalThis.fetch,controller=new AbortController()
  try {
    globalThis.fetch=async (url,options) => { assert.match(url,/\/monitoring-areas$/);assert.equal(options.signal,controller.signal);return {ok:true,json:async()=>raw} }
    assert.equal((await fetchMonitoringAreas({signal:controller.signal})).sites.length,36)
    globalThis.fetch=async()=>({ok:false})
    await assert.rejects(fetchMonitoringAreas(),/could not be loaded/)
  } finally { globalThis.fetch=original }
})
