import assert from 'node:assert/strict'
import test from 'node:test'
import { createAuthSession } from '../src/services/auth.js'
const now=1700000000000
const token='fixture.'+Buffer.from(JSON.stringify({exp:now/1000+60})).toString('base64url')+'.unsigned-test-fixture'
const active={id:1,role:'officer',status:'Active',email:'fixture@example.test'}
const reply=(body,status=200)=>({ok:status>=200&&status<300,status,json:async()=>body})

test('sign-in verifies backend user, uses bearer only after login and logout clears it', async()=>{
  const calls=[],changes=[]
  const session=createAuthSession({now:()=>now,fetchImpl:async(path,options)=>{
    calls.push({path,options})
    return reply(path.endsWith('/auth/login')?{access_token:token,token_type:'bearer'}:active)
  }})
  session.subscribe(user=>changes.push(user))
  try {
    assert.equal(await session.login('fixture@example.test','fixture-password'), 'officer')
    assert.equal(calls[0].options.headers.Authorization,undefined)
    assert.equal(calls[1].options.headers.Authorization,'Bearer '+token)
    await session.authorizedRequest('/api/v1/environmental-data')
    assert.equal(calls[2].options.headers.Authorization,'Bearer '+token)
    assert.equal(changes.at(-1).role,'officer')
    session.logout()
    await assert.rejects(session.authorizedRequest('/anything'),/Sign in/)
    assert.equal(changes.at(-1),null)
  } finally {session.logout()}
})
test('rejected credentials and inactive or unknown roles never grant a session', async()=>{
  for(const user of [null,{...active,status:'Inactive'},{...active,role:'unapproved'}]) {
    const session=createAuthSession({now:()=>now,fetchImpl:async path=>path.endsWith('/auth/login')?
      reply({access_token:token,token_type:'bearer'}):reply(user??{},user?200:401)})
    await assert.rejects(session.login('fixture@example.test','fixture-password'))
    await assert.rejects(session.authorizedRequest('/anything'),/Sign in/)
    session.logout()
  }
})
test('401 and expiry clear memory, 403 never pretends success', async()=>{
  let clock=now,status=200
  const session=createAuthSession({now:()=>clock,fetchImpl:async path=>reply(path.endsWith('/auth/login')?{access_token:token,token_type:'bearer'}:active,path.includes('/api/')?status:200)})
  try {
    await session.login('fixture@example.test','fixture-password')
    status=403
    await assert.rejects(session.authorizedRequest('/api/action'),/cannot perform/)
    status=401
    await assert.rejects(session.authorizedRequest('/api/action'),/expired/)
    await assert.rejects(session.authorizedRequest('/api/action'),/Sign in/)
    await session.login('fixture@example.test','fixture-password')
    clock=now+61000
    await assert.rejects(session.authorizedRequest('/api/action'),/Sign in/)
  } finally {session.logout()}
})
test('logout during a pending login cancels the late response', async()=>{
  let release
  const blocked=new Promise(resolve=>{release=resolve})
  const session=createAuthSession({now:()=>now,fetchImpl:async path=>{
    if(path.endsWith('/auth/login')) {await blocked;return reply({access_token:token,token_type:'bearer'})}
    return reply(active)
  }})
  const login=session.login('fixture@example.test','fixture-password')
  session.logout();release()
  await assert.rejects(login,/cancelled/)
  await assert.rejects(session.authorizedRequest('/anything'),/Sign in/)
})
test('never sends bearer to an arbitrary URL', async()=>{
  const session=createAuthSession({now:()=>now,fetchImpl:async path=>reply(path.endsWith('/auth/login')?{access_token:token,token_type:'bearer'}:active)})
  try {
    await session.login('fixture@example.test','fixture-password')
    await assert.rejects(session.authorizedRequest('https://untrusted.test'),/Invalid API path/)
    await assert.rejects(session.authorizedRequest('//untrusted.test'),/Invalid API path/)
  } finally {session.logout()}
})
