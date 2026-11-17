import test from 'node:test'
import assert from 'node:assert/strict'
import {collectionStatus,requestWeatherCollection} from '../src/services/weatherCollection.js'

const id='8c14f4dc-475b-459f-b789-96bbaf7f6c7a'
const started='2026-11-14T06:00:00.000Z'
const attempt={request_id:id,status:'COMPLETE',started_at:started,finished_at:'2026-11-14T06:00:05Z',
  requested_count:29,complete_target_count:29,outcome:'COMPLETE_TARGETS',receipt_sha256:'a'.repeat(64)}
const response={contract_version:'manual-point-weather-1',automatic:false,next_collection_at:null,
  automation_configured:false,configured_interval_hours:null,
  checked_at:started,cooldown_seconds:900,next_manual_at:'2026-11-14T06:15:00Z',latest:attempt}

test('status distinguishes manual request limit from automatic collection',()=>{
  assert.equal(collectionStatus(response).latest.complete_target_count,29)
  assert.equal(collectionStatus({...response,latest:null,next_manual_at:null}).latest,null)
  const auto={...response,automatic:true,automation_configured:true,configured_interval_hours:1,next_collection_at:'2026-11-14T07:05:00Z',
    latest_automatic:{started_at:'2026-11-14T06:05:00Z',finished_at:'2026-11-14T06:05:09Z',outcome:'COMPLETE_TARGETS',requested_count:36,complete_target_count:36}}
  assert.equal(collectionStatus(auto).latest_automatic.complete_target_count,36)
  assert.equal(collectionStatus({...auto,latest_automatic:null}).latest_automatic,null)
  for(const change of [{next_collection_at:null},{automation_configured:false,configured_interval_hours:null},{latest_automatic:{...auto.latest_automatic,outcome:'MAYBE'}}])
    assert.throws(()=>collectionStatus({...auto,...change}))
  for(const change of [{automatic:true},{next_collection_at:started},{cooldown_seconds:1},{automation_configured:true,configured_interval_hours:4},
    {next_manual_at:'2026-11-14T06:10:00Z'},{automation_configured:true,configured_interval_hours:null},{automation_configured:false,configured_interval_hours:4},{latest:{...attempt,complete_target_count:40}},
    {latest:{...attempt,complete_target_count:0}},{latest:{...attempt,receipt_sha256:'z'.repeat(64)}}])
    assert.throws(()=>collectionStatus({...response,...change}))
})

test('explicit collection submits only UUID with a bounded longer timeout and no automatic retries',async()=>{
  const calls=[]
  const saved=await requestWeatherCollection(async(path,options)=>{
    calls.push({path,options});return {contract_version:response.contract_version,reused:false,attempt}
  },id)
  assert.equal(saved.attempt.outcome,'COMPLETE_TARGETS')
  assert.equal(calls.length,1)
  assert.equal(calls[0].path,'/monitoring-areas/collection')
  assert.equal(calls[0].options.timeoutMs,75000)
  assert.deepEqual(JSON.parse(calls[0].options.body),{request_id:id})
  await assert.rejects(requestWeatherCollection(async()=>{throw new Error('uncertain response')},id),/uncertain/)
})

test('wrong request identity and unconfirmed completion never become success',async()=>{
  for(const value of [{contract_version:response.contract_version,reused:false,attempt:{...attempt,request_id:'wrong'}},
    {contract_version:response.contract_version,reused:false,attempt:{...attempt,status:'REQUESTING'}}])
    await assert.rejects(requestWeatherCollection(async()=>value,id),/completion/)
  await assert.rejects(requestWeatherCollection(()=>assert.fail('No request for invalid UUID'),'../path'),/valid collection/)
})
