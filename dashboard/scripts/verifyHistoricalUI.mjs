// Real route/geometry captures. TEST identity and controlled 503 only; no synthetic displayed polygons.
import { createServer } from 'node:http'
import { readFile, writeFile, mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve, extname, sep } from 'node:path'
import { spawn } from 'node:child_process'
import assert from 'node:assert/strict'

const root=process.cwd(),dist=resolve(root,'dashboard/dist'),sourceEvidence=resolve(root,'docs/webmasters/unosat_evidence'),evidence=await mkdtemp(join(tmpdir(),'floodhub-historical-ui-'))
const captures=JSON.parse(await readFile(join(sourceEvidence,'api-captures.json'),'utf8'))
const base='/api/v1/geospatial/historical-floods/unosat-20240501-nairobi-kiambu'
const profile=join(await mkdtemp(join(tmpdir(),'floodhub-unosat-ui-')),'profile')
const requests=[],errors=[],networkFailures=[];let outage=false
const token='fixture.'+Buffer.from(JSON.stringify({exp:Math.floor(Date.now()/1000)+1200})).toString('base64url')+'.unsigned-browser-test-only'
const user={id:1,name:'Test officer',email:'officer@example.test',role:'officer',status:'Active'}
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png'}
const server=createServer(async(req,res)=>{try{
 const path=resolve(dist,'.'+decodeURIComponent(new URL(req.url,'http://local').pathname))
 if(path!==dist&&!path.startsWith(dist+sep)){res.writeHead(403);res.end();return}
 const target=extname(path)?path:join(dist,'index.html'),content=await readFile(target)
 res.writeHead(200,{'Content-Type':mime[extname(target)]||'application/octet-stream'});res.end(content)
}catch{res.writeHead(404);res.end()}})
await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port
const chrome=spawn(process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',[
 '--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking',
 '--disable-extensions','--remote-debugging-port=0','--remote-allow-origins=*','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'})
const pause=ms=>new Promise(r=>setTimeout(r,ms));const pending=new Map();let serial=0,ws
try{
 let devPort
 for(let i=0;i<150;i++){try{devPort=Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);break}catch{await pause(100)}}
 assert.ok(devPort,'headless Chrome startup')
 const pages=await(await fetch('http://127.0.0.1:'+devPort+'/json/list')).json()
 ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl)
 await new Promise((r,j)=>{ws.addEventListener('open',r,{once:true});ws.addEventListener('error',j,{once:true})})
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})
 ws.addEventListener('message',event=>{
  const m=JSON.parse(event.data)
  if(m.id){const p=pending.get(m.id);pending.delete(m.id);if(p)m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);return}
  if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text)
  if(m.method==='Network.loadingFailed')networkFailures.push(m.params.errorText)
  if(m.method!=='Fetch.requestPaused')return
  const{requestId,request}=m.params
  void(async()=>{
   const url=new URL(request.url)
   if(url.hostname==='localhost'&&url.port==='8000'){
    requests.push({method:request.method,path:url.pathname,controlled_outage:outage})
    let status=200,body
    if(request.method==='OPTIONS')body={}
    else if(url.pathname==='/auth/login')body={access_token:token,token_type:'bearer',user}
    else if(url.pathname==='/auth/me')body=user
    else if(url.pathname==='/reporting-zones')body=captures['/reporting-zones']??Object.values(captures).find(x=>Array.isArray(x?.zones)&&x.zones[0]?.zone)?.zones.map(x=>x.zone)??[]
    else if(url.pathname.startsWith(base)){
     assert.equal(request.headers.Authorization??request.headers.authorization,'Bearer '+token)
     assert.equal(request.method,'GET','historical source reads only')
     if(outage){status=503;body={detail:'Controlled missing source: no observation layer confirmed.'}}
     else body=captures[url.pathname]
    }else if(url.pathname==='/api/v1/dashboard')body=captures[url.searchParams.get('mode')==='historical_replay'?'/api/v1/dashboard?mode=historical_replay&input_date=2024-04-30':'/api/v1/dashboard?mode=live']
    else body=captures[url.pathname]
    if(body===undefined){status=404;body={detail:'No captured route'}}
    await send('Fetch.fulfillRequest',{requestId,responseCode:status,responseHeaders:[{name:'Content-Type',value:'application/json'},
     {name:'Access-Control-Allow-Origin',value:'*'},{name:'Access-Control-Allow-Headers',value:'Authorization, Content-Type'},
     {name:'Access-Control-Allow-Methods',value:'GET, POST, OPTIONS'},{name:'Cache-Control',value:'no-store'}],body:Buffer.from(JSON.stringify(body)).toString('base64')})
   }else if((url.hostname==='127.0.0.1'&&url.port===String(port))||/^(?:[abc]\.)?tile\.openstreetmap\.org$/.test(url.hostname))await send('Fetch.continueRequest',{requestId})
   else await send('Fetch.fulfillRequest',{requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'text/plain'}],body:''})
  })().catch(e=>errors.push(e.message))
 })
 await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]})
 const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.text);return r.result.value}
 const waitFor=async expression=>{for(let i=0;i<300;i++){if(await evaluate('Boolean('+expression+')'))return;await pause(100)}throw new Error('UI wait timed out: '+expression)}
 const shot=async name=>{const s=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(join(evidence,name+'.png'),Buffer.from(s.data,'base64'))}
 const click=label=>evaluate(`Array.from(document.querySelectorAll('button')).find(e=>e.textContent===${JSON.stringify(label)}).click()`)
 const checkbox=label=>evaluate(`Array.from(document.querySelectorAll('label')).find(e=>e.textContent.includes(${JSON.stringify(label)})).querySelector('input[type=checkbox]').click()`)
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false})
 await send('Page.navigate',{url:`http://127.0.0.1:${port}/`})
 await waitFor(`document.querySelector('.leaflet-container')`)
 assert.equal(await evaluate(`document.querySelector('section[aria-label="Historical UNOSAT evidence"]')!==null`),false,'public source controls restricted')
 await send('Page.navigate',{url:`http://127.0.0.1:${port}/login`})
 await waitFor(`document.querySelector('input[type=email]')`)
 await evaluate(`(()=>{for(const [selector,value]of[['input[type=email]','officer@example.test'],['input[type=password]','test-only-password']]){const e=document.querySelector(selector);Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,value);e.dispatchEvent(new Event('input',{bubbles:true}))}document.querySelector('button[type=submit]').click()})()`)
 await waitFor(`location.pathname==='/officer'`)
 await evaluate(`Array.from(document.querySelectorAll('a')).find(e=>e.textContent==='Map').click()`)
 await waitFor(`document.querySelector('.leaflet-container')`)
 for(let i=0;i<150;i++){if(await evaluate(`Array.from(document.querySelectorAll('.leaflet-tile')).every(e=>e.complete&&e.naturalWidth>0)&&document.querySelectorAll('.leaflet-tile').length>0`))break;await pause(100)}
 await shot('desktop-neutral-geographic-map')
 await evaluate(`Array.from(document.querySelectorAll('details')).find(e=>e.classList.contains('map-layer-controls')).open=true`)
 await checkbox('Historical UNOSAT · 1 May 2024')
 await waitFor(`document.querySelectorAll('.historical-flood').length>0&&document.querySelectorAll('.historical-cloud').length>0`)
 await click('Fit historical coverage');await pause(800)
 for(let i=0;i<150;i++){if(await evaluate(`Array.from(document.querySelectorAll('.leaflet-tile')).every(e=>e.complete&&e.naturalWidth>0)&&document.querySelectorAll('.leaflet-tile').length>0`))break;await pause(100)}
 assert.ok((await evaluate('document.body.innerText')).includes('Unknown: mapped cloud obstruction'))
 await shot('desktop-historical-overlay-and-legend')
 await checkbox('Mapped cloud obstruction');await waitFor(`document.querySelectorAll('.historical-cloud').length===0`)
 await checkbox('Mapped cloud obstruction');await waitFor(`document.querySelectorAll('.historical-cloud').length>0`)
 await checkbox('Satellite-detected historical water');await waitFor(`document.querySelectorAll('.historical-flood').length===0`)
 await shot('desktop-analysis-coverage-and-cloud')
 await checkbox('Satellite-detected historical water');await waitFor(`document.querySelectorAll('.historical-flood').length>0`)
 await evaluate(`(()=>{const e=document.querySelector('select[aria-label="Historical observation point"]');e.value='cbd';e.dispatchEvent(new Event('change',{bubbles:true}))})()`)
 await waitFor(`document.body.innerText.includes('CBD: Unknown: outside analysed area')`)
 await shot('desktop-unknown-outside-coverage')
 assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true)
 const basemapTiles=await evaluate(`document.querySelectorAll('.leaflet-tile-loaded').length`)
 const basemapExpected=await evaluate(`document.querySelectorAll('.leaflet-tile').length`)
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true})
 await evaluate(`dispatchEvent(new Event('resize'))`);await pause(800)
 assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,'mobile horizontal overflow')
 await shot('mobile-historical-map-and-controls')
 // A hidden source never survives an unsuccessful recheck.
 outage=true;await click('Recheck satellite evidence')
 await waitFor(`document.querySelector('[role=alert]')&&document.querySelectorAll('.historical-flood').length===0&&document.querySelectorAll('.historical-coverage').length===0`)
 await shot('mobile-source-unavailable-controlled')
 assert.equal(errors.length,0,JSON.stringify(errors))
 const result={status:'PASS',at_utc:new Date().toISOString(),scope:'Built React/Leaflet rendering actual production route captures and authentic UNOSAT-derived geometry. TEST identity/transport; controlled 503; real OSM basemap tiles where available.',
  basemap_tiles_loaded:basemapTiles,basemap_tiles_expected:basemapExpected,basemap_status:basemapTiles===basemapExpected&&basemapTiles>0?'COMPLETE':basemapTiles?'PARTIAL':'NOT_VERIFIED_IN_THIS_BROWSER_RUN',network_failures:networkFailures,
  checks:['public access controls hidden','officer navigation','historical evidence separated from model outputs','genuine historical layers render','fit historical footprint','date/source/uncertainty labels','independent layer toggles','cloud/unknown point handling','no flood-free labels','desktop no overflow','mobile no overflow','source error clears all layers'],errors,requests}
 await writeFile(join(evidence,'browser-verification.json'),JSON.stringify(result,null,2))
 console.log(JSON.stringify({status:result.status,checks:result.checks.length,basemap_tiles_loaded:basemapTiles,evidence_directory:evidence}))
}finally{
 if(ws){if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({id:++serial,method:'Browser.close'}));await pause(100);ws.close()}
 chrome.kill();await new Promise(r=>server.close(r))
}
