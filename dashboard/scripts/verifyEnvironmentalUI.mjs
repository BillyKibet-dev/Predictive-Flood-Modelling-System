// Controlled browser fixtures for auth and historical-source UI, not operational evidence.
import { createServer } from 'node:http'
import { readFile, mkdtemp, writeFile, access } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve, extname, sep } from 'node:path'
import { spawn } from 'node:child_process'
import assert from 'node:assert/strict'


const root=process.cwd(), dist=resolve(root,'dashboard/dist')
const evidence=await mkdtemp(join(tmpdir(),'floodhub-environmental-ui-')), profile=join(evidence,'profile')
const requests=[], errors=[]
let expire=false
const token='fixture.'+Buffer.from(JSON.stringify({exp:Math.floor(Date.now()/1000)+600})).toString('base64url')+'.unsigned-test-only'
const user={id:1,name:'Fixture officer',email:'officer@example.test',role:'officer',status:'Active'}
const dataset={id:'a'.repeat(64),source_id:'era5-hourly-cbd',source_sha256:'b'.repeat(64),recipe_version:'fixture-only',
 imported_at:'2026-11-06T12:00:00Z',start_at:'2024-05-01T00:00:00Z',end_at:'2024-05-01T03:00:00Z',
 row_count:3,observation_count:15,qc_summary:{missing_or_invalid_values:1},
 provenance:{zone_ids:['cbd'],bin_timezone:'Africa/Nairobi',window_semantics:'Source timestamp bins, not a forecast horizon',data_available_at:null,fixture:true},
 freshness:{status:'HISTORICAL_ONLY',latest_bin_end_at:'2024-05-01T03:00:00Z',age_hours:22000,data_available_at:null,operational_freshness:'NOT_ESTABLISHED'}}
const observations=[0,null,2].map((value,i)=>({zone_id:'cbd',variable:'rainfall',observed_at:`2024-05-01T0${i}:00:00Z`,bin_end_at:`2024-05-01T0${i+1}:00:00Z`,value,unit:'mm',data_available_at:null,quality_flags:value===null?['MISSING_VALUE']:['HISTORICAL_SOURCE']}))
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
  if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails.text)
  if(message.method==='Fetch.requestPaused'){
   const {requestId,request}=message.params
   void(async()=>{
    const url=new URL(request.url)
    if(url.hostname==='localhost'&&url.port==='8000'){
     // Never record passwords, request bodies or bearer strings.
     requests.push({method:request.method,path:url.pathname})
     let status=200,body
     if(request.method==='OPTIONS')body={}
     else if(url.pathname==='/auth/login'&&request.method==='POST')body={access_token:token,token_type:'bearer',user}
     else if(url.pathname==='/auth/me')body=user
     else if(url.pathname.startsWith('/api/v1/environmental-data')){
      assert.equal(request.headers.Authorization??request.headers.authorization,'Bearer '+token)
      if(expire){status=401;body={detail:'Fixture expiry'}}
      else if(request.method!=='GET'){status=405;body={detail:'Writes blocked'}}
      else if(url.pathname.endsWith('/sources'))body=[{id:dataset.source_id,name:'ERA5-Seamless CBD archive',source_kind:'retrospective_reanalysis',temporal_resolution:'hourly',provenance:{}}]
      else if(url.pathname.endsWith('/observations'))body={dataset_id:dataset.id,items:observations,total:3,limit:200,offset:0}
      else if(url.pathname.endsWith('/rainfall'))body={status:'INSUFFICIENT_DATA',rainfall_mm:null,reason_codes:['MISSING_OR_INVALID_RAINFALL'],window_hours:Number(url.searchParams.get('window_hours')),window_end:url.searchParams.get('end_at'),dataset_id:dataset.id,zone_id:'cbd',supports_operational_issue:false}
      else body={items:[dataset],total:1,limit:200,offset:0}
     }
     else if(url.pathname==='/dashboard')body={zones:[],last_updated:null,active_alerts:0,highest_risk:'Unknown'}
     else if(url.pathname==='/boundaries')body={type:'FeatureCollection',features:[]}
     else{status=404;body={detail:'Fixture route unavailable'}}
     await send('Fetch.fulfillRequest',{requestId,responseCode:status,responseHeaders:[{name:'Content-Type',value:'application/json'},{name:'Access-Control-Allow-Origin',value:'*'},{name:'Access-Control-Allow-Headers',value:'Authorization, Content-Type'},{name:'Access-Control-Allow-Methods',value:'GET, POST, OPTIONS'},{name:'Cache-Control',value:'no-store'}],body:Buffer.from(JSON.stringify(body)).toString('base64')})
    }else if(url.hostname==='127.0.0.1'&&url.port===String(port))await send('Fetch.continueRequest',{requestId})
    else await send('Fetch.fulfillRequest',{requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'text/plain'}],body:''})
   })().catch(error=>errors.push(error.message))
  }
 })
 await send('Page.enable');await send('Runtime.enable');await send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]})
 const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.text);return r.result.value}
 const waitFor=async expression=>{for(let i=0;i<150;i++){if(await evaluate('Boolean('+expression+')'))return;await pause(100)}throw new Error('UI condition timed out: '+expression)}
 const screenshot=async name=>{const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(join(evidence,name+'.png'),Buffer.from(shot.data,'base64'))}
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false})
 await send('Page.navigate',{url:`http://127.0.0.1:${port}/environmental-data`})
 await waitFor(`location.pathname==='/login'&&document.querySelector('input[type=email]')`)
 await evaluate(`(()=>{for(const [selector,value] of [['input[type=email]','officer@example.test'],['input[type=password]','fixture-only-password']]){const e=document.querySelector(selector);Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,value);e.dispatchEvent(new Event('input',{bubbles:true}))}document.querySelector('button[type=submit]').click()})()`)
 await waitFor(`location.pathname==='/officer'`)
 await evaluate(`Array.from(document.querySelectorAll('a')).find(e=>e.textContent==='Environmental data').click()`)
 await waitFor(`document.querySelector('table')&&document.body.innerText.includes('Missing / invalid')`)
 const text=await evaluate('document.body.innerText')
 for(const phrase of ['0 mm','Insufficient data','UNAVAILABLE','NOT AVAILABLE','UNKNOWN','HISTORICAL_ONLY','not a forecast horizon'])assert.ok(text.includes(phrase),phrase)
 assert.ok(!text.includes('Import snapshot'),'officer cannot see import control')
 assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true)
 assert.equal(await evaluate(`Object.keys(localStorage).some(k=>/token|auth/i.test(k))||Object.keys(sessionStorage).some(k=>/token|auth/i.test(k))`),false)
 await screenshot('desktop-historical-rainfall')
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true})
 await evaluate(`dispatchEvent(new Event('resize'))`);await pause(600)
 assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,'mobile horizontal overflow')
 assert.ok(await evaluate(`Array.from(document.querySelectorAll('a')).some(e=>e.textContent==='Data'&&e.getBoundingClientRect().width>0)`))
 await screenshot('mobile-historical-rainfall')
 expire=true
 await evaluate(`Array.from(document.querySelectorAll('button')).find(e=>e.textContent==='Refresh registry').click()`)
 await waitFor(`location.pathname==='/login'`)
 assert.equal(errors.length,0,JSON.stringify(errors))
 const result={status:'passed',kind:'Controlled synthetic browser fixtures; PostgreSQL/FastAPI verified separately; not real deployment',desktop:{width:1440,no_horizontal_overflow:true},mobile:{width:390,no_horizontal_overflow:true},checks:['protected route redirects','backend login and me requests','authorized source reads','true zero vs missing','historical/unknown publication labels','water and inundation unavailable','officer import hidden','memory-only session','401 redirects to sign-in'],requests,evidence_directory:evidence}
 await writeFile(join(evidence,'verification.json'),JSON.stringify(result,null,2))
 console.log(JSON.stringify(result,null,2))
}finally{
 if(ws){if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({id:++serial,method:'Browser.close'}));await pause(100);ws.close()}
 chrome.kill();await new Promise(resolve=>server.close(resolve))
}
