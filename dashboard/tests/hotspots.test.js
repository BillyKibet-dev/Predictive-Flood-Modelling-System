import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parseHotspots, filterHotspots, fetchHotspots } from '../src/services/hotspots.js'

const raw = JSON.parse(readFileSync(new URL('../../src/api/data/hotspots.json',import.meta.url)))

test('actual inventory preserves unlocated sites and separate Langata grouping', () => {
  const data = parseHotspots(raw)
  assert.equal(data.sites.length,40)
  assert.equal(data.sites.filter(s => s.point).length,4)
  assert.equal(data.sites.find(s => s.id === 'NFW-S001').point,null)
  const tmall = data.sites.find(s => s.id === 'NFW-S037')
  assert.equal(tmall.zone_id,null)
  assert.deepEqual(tmall.point,{lat:-1.3126653,lon:36.8158078})
  assert.equal(filterHotspots(data.sites,{group:'CBD'}).length,4)
  assert.equal(filterHotspots(data.sites,{location:'unlocated'}).length,36)
  assert.equal(filterHotspots(data.sites,{query:'  t-mall  '})[0].id,'NFW-S037')
  assert.equal(filterHotspots(data.sites,{group:'Mathare',location:'located'})[0].id,'NFW-S028')
})

test('invalid map coordinates, synthetic scores and unlocated features fail closed', () => {
  for (const mutate of [
    d => { d.sites.push(d.sites[0]) },
    d => { d.sites[1].geometry.coordinates = [NaN,0] },
    d => { d.sites[1].geometry.type = 'Polygon' },
    d => { d.sites[1].risk_score = .9 },
    d => { d.sites[1].location.coordinates = [0,0] },
    d => { d.sites[0].terrain.status = 'DERIVED_CONTEXT' },
  ]) { const data=structuredClone(raw); mutate(data); assert.throws(() => parseHotspots(data)) }
})

test('inventory fetch passes cancellation and surfaces failures without generated fallback', async () => {
  const original=globalThis.fetch, controller=new AbortController()
  try {
    globalThis.fetch=async (url,options) => { assert.match(url,/\/hotspots$/); assert.equal(options.signal,controller.signal); return {ok:true,json:async()=>raw} }
    assert.equal((await fetchHotspots({signal:controller.signal})).sites.length,40)
    globalThis.fetch=async()=>({ok:false,status:503})
    await assert.rejects(fetchHotspots(),/could not be loaded/)
  } finally { globalThis.fetch=original }
})
