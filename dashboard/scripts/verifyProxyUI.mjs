// Browser acceptance with synthetic API fixtures; never a production/model accuracy result.
// Run from repo root after building: node dashboard/scripts/verifyProxyUI.mjs
import { createServer } from 'node:http'
import { readFile, mkdtemp, writeFile, access } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve, extname, sep } from 'node:path'
import { spawn } from 'node:child_process'
import assert from 'node:assert/strict'

const root = process.cwd()
const actual = process.argv[2] ? JSON.parse(await readFile(process.argv[2], 'utf8')) : null
const dist = resolve(root, 'dashboard/dist')
const evidence = await mkdtemp(join(tmpdir(), 'floodhub-v1-ui-'))
const profile = join(evidence, 'profile')
const names = ['Low', 'Moderate', 'High', 'Extreme']
const raw = [
 ['mathare', 'Mathare', 'Starehe', -1.260, 36.860], ['kibera', 'Kibera', 'Langata', -1.314, 36.784],
 ['westlands', 'Westlands', 'Westlands', -1.264, 36.807], ['cbd', 'CBD', 'Kilimani', -1.286, 36.817],
 ['kasarani', 'Kasarani', 'Kasarani', -1.221, 36.897], ['embakasi', 'Embakasi', 'Embakasi East', -1.320, 36.895],
 ['dagoretti', 'Dagoretti', 'Dagoretti North', -1.295, 36.754], ['ruaraka', 'Ruaraka', 'Ruaraka', -1.241, 36.876],
]
const zones = raw.map(([id,name,sub_county,latitude,longitude]) => ({id,name,sub_county,latitude,longitude}))
const registry = JSON.parse(await readFile(join(root, 'src/modeling/v1/package_manifest.json'), 'utf8'))
const model = actual?.model ?? {model_version:registry.model_version,model_task_type:registry.model_task_type,
 artifact_hash:registry.files[registry.artifact_filename].sha256,loaded:true,status:'AVAILABLE',feature_count:20,classes:names,
 evaluation:registry.evaluation,operational_status:'INSUFFICIENT_DATA',
 blockers:['CHIRPS_PUBLICATION_DELAY','FULL_DAY_METEO_UNVERIFIED','NO_VALIDATED_LIVE_TERRAIN_ADAPTER'],
 limitations:registry.evaluation.limitations,emergency_alert_delivery_enabled:false,
 runtime:{python:'3.12.1',xgboost:'3.1.3',numpy:'1.26.4'}}
const county = JSON.parse(await readFile(join(root,'data/boundaries/nairobi_county.geojson'),'utf8'))
const sub = JSON.parse(await readFile(join(root,'data/boundaries/nairobi_subcounties.geojson'),'utf8'))
const boundaries = actual?.boundaries ?? {type:'FeatureCollection',features:[...county.features,...sub.features].map(f => ({...f,properties:{...f.properties,monitoring_zone_ids:f.properties.admin_level===2 ? zones.filter(z=>z.sub_county===f.properties.name).map(z=>z.id):[]}}))}
const legacy = actual?.legacy ?? {zones:zones.map((zone,index)=>({zone,risk_level:names[index%4],risk_class:index%4,confidence_score:.7,timestamp:new Date().toISOString()})),last_updated:new Date().toISOString(),active_alerts:0,highest_risk:'Extreme',prediction_context:{spatial_scope:'shared_nairobi_weather',label_basis:'rainfall_soil_moisture_proxy',temporal_scope:'current_conditions',location_specific:false,confidence_interpretation:'uncalibrated_class_score'}}
const requests=[]
let failNext=false
function proxy(url) {
 if(actual) return structuredClone(url.searchParams.get('mode')==='historical_replay'?actual.replay:actual.live)
 const mode=url.searchParams.get('mode') || 'live'
 const input_date=mode==='historical_replay'?url.searchParams.get('input_date'):'2026-11-05'
 const forecast_target_date=new Date(Date.parse(input_date+'T00:00:00Z')+86400000).toISOString().slice(0,10)
 const issued_at=mode==='historical_replay'?forecast_target_date+'T00:00:00+03:00':null
 const executed_at=mode==='historical_replay'?'2026-11-06T15:00:00+03:00':null
 const common={issued_at,executed_at,input_date,forecast_target_date,forecast_horizon:'next_calendar_day',data_as_of:null}
 return {mode,status:mode==='historical_replay'?'SUCCESS':'INSUFFICIENT_DATA',model_version:model.model_version,model_task_type:'next_day_proxy_risk',...common,blockers:model.blockers,limitation_flags:['NOT_OBSERVED_FLOOD_LABELS'],zones:zones.map((zone,index)=>{
 const cls=index%4
 return {zone,status:mode==='historical_replay'?'SUCCESS':'INSUFFICIENT_DATA',reason_codes:mode==='historical_replay'?[]:['CHIRPS_RELEASE_TIMES_UNVERIFIED','MISSING_PRODUCTION_FEATURES'],risk_class:mode==='historical_replay'?cls:null,risk_level:mode==='historical_replay'?names[cls]:'Unknown',model_class_score:mode==='historical_replay'?.7:null,proxy_class_scores:mode==='historical_replay'?Object.fromEntries(names.map((n,i)=>[n,i===cls?.7:.1])):null,flood_probability:null,flood_probability_reason:'NOT_CALIBRATED_TO_OBSERVED_FLOODS',...common,freshness:mode==='historical_replay'?'HISTORICAL_REPLAY':'UNAVAILABLE',source_metadata:{fixture:true},limitation_flags:['COARSE_WEATHER_GRID','STATIC_TERRAIN_PROXY']}
 })}
}
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png'}
const server=createServer(async(req,res)=>{
 try {
 const uri=new URL(req.url,'http://local')
 const path=resolve(dist,'.'+decodeURIComponent(uri.pathname))
 if(path!==dist&&!path.startsWith(dist+sep)){res.writeHead(403);res.end();return}
 const target=extname(path)?path:join(dist,'index.html')
 const body=await readFile(target)
 res.writeHead(200,{'Content-Type':mime[extname(target)]||'application/octet-stream'});res.end(body)
 }catch{res.writeHead(404);res.end()}
})
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
const port=server.address().port
const chrome=spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-extensions','--remote-debugging-port=0','--remote-allow-origins=*','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'})
let ws
const pending=new Map();let serial=0
const pause=ms=>new Promise(r=>setTimeout(r,ms))
try {
 let devPort
 for(let i=0;i<150;i++){try{devPort=Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);break}catch{await pause(100)}}
 assert.ok(devPort,'headless Chrome devtools startup')
 const pages=await (await fetch('http://127.0.0.1:'+devPort+'/json/list')).json()
 ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl)
 await new Promise((r,j)=>{ws.addEventListener('open',r,{once:true});ws.addEventListener('error',j,{once:true})})
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})
 ws.addEventListener('message',event=>{
  const message=JSON.parse(event.data)
  if(message.id){const p=pending.get(message.id);pending.delete(message.id);if(!p)return;if(message.error)p.reject(new Error(JSON.stringify(message.error)));else p.resolve(message.result);return}
  if(message.method==='Fetch.requestPaused'){
   const {requestId,request}=message.params
   void(async()=>{
    const url=new URL(request.url)
    if(url.hostname==='localhost'&&url.port==='8000'){
     requests.push({method:request.method,path:url.pathname,query:url.search})
     let status=200,body
     if(request.method!=='GET'){status=405;body={detail:'Fixture browser test blocks all writes'}}
     else if(failNext&&url.pathname==='/api/v1/dashboard'){failNext=false;status=503;body={detail:'Injected fixture outage'}}
     else if(url.pathname==='/dashboard')body=legacy
     else if(url.pathname==='/api/v1/dashboard')body=proxy(url)
     else if(url.pathname==='/api/v1/model')body=model
     else if(url.pathname==='/boundaries')body=boundaries
     else {status=404;body={detail:'Fixture route not defined'}}
     await send('Fetch.fulfillRequest',{requestId,responseCode:status,responseHeaders:[{name:'Content-Type',value:'application/json'},{name:'Access-Control-Allow-Origin',value:'*'},{name:'Cache-Control',value:'no-store'}],body:Buffer.from(JSON.stringify(body)).toString('base64')})
    }else if(url.hostname==='127.0.0.1'&&url.port===String(port))await send('Fetch.continueRequest',{requestId})
    else await send('Fetch.fulfillRequest',{requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'text/plain'}],body:''})
   })().catch(error=>{console.error('Fixture interception error:',error.message)})
  }
 })
 await send('Page.enable');await send('Runtime.enable');await send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]})
 const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.text);return r.result.value}
 const waitFor=async expression=>{for(let i=0;i<150;i++){if(await evaluate(expression))return;await pause(100)}throw new Error('UI condition timed out: '+expression)}
 const stats=()=>evaluate(`({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,subcountyPaths:document.querySelectorAll('path.subcounty-boundary').length,markers:document.querySelectorAll('path.monitoring-point').length,text:document.body.innerText})`)
 const screenshot=async name=>{const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(join(evidence,name+'.png'),Buffer.from(shot.data,'base64'))}
 const select=async value=>evaluate(`(()=>{const e=document.querySelector('select[id$="-view"]');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('change',{bubbles:true}));return e.value})()`)
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false})
 await send('Page.navigate',{url:`http://127.0.0.1:${port}/`})
 await waitFor(`document.querySelectorAll('path.subcounty-boundary').length===17&&document.querySelectorAll('path.monitoring-point').length===8`)
 const legacyStats=await stats();assert.ok(legacyStats.scrollWidth<=1440)
 await screenshot('desktop-legacy')
 await select('v1_live')
 await waitFor(`document.body.innerText.includes('operational predictions are unavailable')`)
 await evaluate(`Array.from(document.querySelectorAll('details')).find(e=>e.querySelector('summary')?.textContent.includes('Output times')).open=true`)
 const live=await stats();assert.ok(live.text.includes('Execution status: Insufficient data'));assert.equal(live.subcountyPaths,17);assert.equal(live.markers,8);assert.ok(live.scrollWidth<=1440);assert.ok(live.text.includes('EMERGENCY DELIVERY DISABLED'))
 const liveColours=await evaluate(`Array.from(document.querySelectorAll('path.monitoring-point')).map(e=>e.getAttribute('fill'))`)
 assert.ok(liveColours.every(c=>c.toLowerCase()==='#64748b'))
 await screenshot('desktop-v1-live-unavailable')
 await select('v1_replay')
 await waitFor(`document.body.innerText.includes('Historical research replay · target 01 May 2024')&&document.querySelectorAll('path.monitoring-point').length===8`)
 const replay=await stats();assert.ok(replay.scrollWidth<=1440);assert.ok(replay.text.includes('This is not a current warning.'));assert.equal(replay.subcountyPaths,17)
 await screenshot('desktop-v1-replay')
 failNext=true
 await evaluate(`Array.from(document.querySelectorAll('button')).find(e=>e.textContent.includes('Refresh predictions')).click()`)
 await waitFor(`document.body.innerText.includes('Could not refresh v1 data. Showing the last fetched research snapshot.')`)
 const failed=await stats();assert.ok(failed.text.includes('Target: 01 May 2024'));assert.ok(failed.text.includes('Historical proxy-class legend'))
 await screenshot('desktop-v1-replay-retained-after-error')
 await evaluate(`Array.from(document.querySelectorAll('details')).filter(e=>e.querySelector('summary')?.textContent.includes('Output times')).forEach(e=>e.open=false)`)
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true})
 await evaluate(`dispatchEvent(new Event('resize'))`);await pause(600)
 const mobile=await stats();assert.ok(mobile.scrollWidth<=390);assert.equal(mobile.markers,8);assert.equal(mobile.subcountyPaths,17)
 await screenshot('mobile-v1-replay')
 await evaluate(`document.querySelector('select[id$="-view"]').scrollIntoView()`)
 await select('v1_live')
 await waitFor(`document.body.innerText.includes('operational predictions are unavailable')`)
 const mobileLive=await stats();assert.ok(mobileLive.scrollWidth<=390)
 await screenshot('mobile-v1-live-unavailable')
 assert.ok(requests.every(r=>r.method==='GET'))
 const result={status:'passed',evidence_directory:evidence,kind:actual?'browser with captured real local model/PostgreSQL/FastAPI reads; simulated outage; writes blocked':'controlled synthetic API browser fixtures, not real model/DB end-to-end',desktop:{width:1440,height:1000,no_horizontal_overflow:true,subcounty_paths:17,markers:8},mobile:{width:390,height:844,no_horizontal_overflow:true,subcounty_paths:17,markers:8},checks:['legacy selectable','live Unknown/no scores/no emergency delivery','explicit historical target 01 May 2024','replay not current warning','retains same replay after injected HTTP503','switching to live clears replay','all writes blocked'],requests}
 await writeFile(join(evidence,'verification.json'),JSON.stringify(result,null,2))
 console.log(JSON.stringify(result,null,2))
} finally {
 if(ws) { if(ws.readyState===WebSocket.OPEN) ws.send(JSON.stringify({id:++serial,method:"Browser.close"})); await pause(100); ws.close() }
 chrome.kill()
 await new Promise(resolve=>server.close(resolve))
}
