// Controlled browser workflow fixtures. Actual FastAPI/PostgreSQL persistence is tested separately.
import { createServer } from 'node:http'
import { readFile, mkdtemp, writeFile, access } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve, extname, sep } from 'node:path'
import { spawn } from 'node:child_process'
import assert from 'node:assert/strict'

const root = process.cwd(),
  dist = resolve(root, 'dashboard/dist')
const evidence = await mkdtemp(join(tmpdir(), 'floodhub-staff-ui-')),
  profile = join(evidence, 'profile')
const requests = [],
  errors = []
const timestamp = new Date().toISOString()
const staffData = JSON.parse(await readFile(resolve(root, 'dashboard/scripts/fixtures/staff_data.json'), 'utf8'))
const exportRequests = []
const susceptibilityFixture = JSON.parse(await readFile(resolve(root, 'src/api/data/monitoring_susceptibility.json'), 'utf8'))
const advisories = []
// Same-day fixture: today High everywhere, light rain now, heavy rain later this afternoon.
const todayFixture = () => {
  const now = new Date(Date.now() + 3 * 3600000), hour = now.getUTCHours(), day = now.toISOString().slice(0, 10)
  const label = h => `${day}T${String(h % 24).padStart(2, '0')}:00`
  const windows = [{ window:'next_3h', start:label(hour), end:label(hour + 3) }, { window:'next_3_6h', start:label(hour + 3), end:label(hour + 6) }]
  const located = areaInventory.sites.filter(s => s.geometry)
  return { contract_version:'today-rainfall-outlook-v1', checked_at:new Date().toISOString(), today:day, timezone:'Africa/Nairobi', windows,
    forecast:{ run_at:new Date().toISOString(), received_at:new Date().toISOString(), base_run_at:null }, model_version:'fixture',
    available_count:located.length, located_count:located.length,
    areas: located.map(s => ({ area_id:s.id, status:'AVAILABLE', category:'High', rule_category:'High', method:'stage2_xgboost_guarded',
      model_status:'APPLIED', guard_applied:false, inputs_complete:true, rest_of_today_mm:14.2,
      windows:[{ ...windows[0], rain_mm:1.2, peak_mm_per_hour:0.8, intensity:'light' }, { ...windows[1], rain_mm:12.4, peak_mm_per_hour:9.1, intensity:'heavy' }] })) }
}
const publicAdvisory = a => ({ id:a.id, area_id:a.area_id, area_name:a.area_name, place_label:a.place_label, latitude:a.latitude, longitude:a.longitude,
  message:a.message, level:a.level, issued_at:a.issued_at, expires_at:a.expires_at })
const areaInventory = JSON.parse(await readFile(resolve(root, 'src/api/data/monitoring_areas.json'), 'utf8'))
const areaEnrichment = JSON.parse(await readFile(resolve(root, 'src/api/data/monitoring_point_enrichment.json'), 'utf8'))
for (const row of areaEnrichment.rows) {
  const site=areaInventory.sites.find(s => s.id === row.area_id)
  site.vegetation=row.vegetation;site.landcover=row.landcover
}
const boundaryFixture=JSON.parse(await readFile(resolve(root,'data/boundaries/nairobi_subcounties.geojson'),'utf8'))
for (const feature of boundaryFixture.features) feature.properties.monitoring_zone_ids=[]
let areaUnavailable = false
let outlookUnavailable=false, outlookExpired=false
let manualLatest=null, manualAckLost=false
const manualRecords=new Map(),manualRequestIds=[]
function manualStatusFixture() {
  return {contract_version:'manual-point-weather-1',automatic:false,next_collection_at:null,automation_configured:false,configured_interval_hours:null,cooldown_seconds:900,
    checked_at:new Date().toISOString(),latest:manualLatest,
    next_manual_at:manualLatest?new Date(Date.parse(manualLatest.started_at)+900000).toISOString():null}
}
const genuineOutlook=process.env.GENUINE_MONITORING_OUTLOOK?JSON.parse(await readFile(process.env.GENUINE_MONITORING_OUTLOOK,'utf8')):null
const pointRainText=`Tomorrow (forecast): ${(genuineOutlook?.areas.find(a=>a.area_id==='NFW-S037')?.rainfall_mm ?? 8).toFixed(1)} mm`
function outlookFixture() {
  if(genuineOutlook && !outlookExpired)return genuineOutlook
  const hour=3600000,now=Date.now(),candidate=new Date(now-6*hour)
  candidate.setUTCHours(Math.floor(candidate.getUTCHours()/12)*12,0,0,0)
  const target=new Date(Date.parse(new Date(now+3*hour).toISOString().slice(0,10)+'T00:00:00+03:00')+24*hour).toISOString()
  const received=new Date(now-(outlookExpired?7*hour:3000)).toISOString()
  const source={method:'stage2_xgboost_with_rule_fallback',model_version:'stage2-xgb-ad9614eb6e85',flood_probability:null,publication_at:null,
    thresholds:{tomorrow_mm:[5,20,40],accumulation_mm:[25,80,150],accumulation_window_hours:165},
    requested_at:new Date(Date.parse(received)-1000).toISOString(),received_at:received,stored_at:new Date(Date.parse(received)+1000).toISOString(),
    run_at:candidate.toISOString(),target_start:target,target_end:new Date(Date.parse(target)+24*hour).toISOString(),
    expires_at:new Date(Math.min(Date.parse(received)+6*hour,candidate.getTime()+24*hour,Date.parse(target))).toISOString()}
  const mapped=areaInventory.sites.filter(s=>s.geometry).map(s=>s.id)
  return {contract_version:'monitoring-rainfall-outlook-v3',status:outlookExpired?'UNAVAILABLE':'AVAILABLE',
    collection:source,collection_automatic:false,next_collection_at:null,automation_configured:false,configured_interval_hours:null,available_count:outlookExpired?0:36,located_count:36,
    areas:areaInventory.sites.map(s=>({area_id:s.id,status:s.geometry&&!outlookExpired?'AVAILABLE':'UNAVAILABLE',
      rainfall_mm:s.geometry&&!outlookExpired?8:null,proxy_class:s.geometry&&!outlookExpired?'High':null,
      // Rule High (8 mm + 6 mm + 70 mm observed = 84 mm); model agrees (arg-max High), no guard needed.
      // 8 mm tomorrow + 6 mm rest of today + 70 mm observed = 84 mm over 7 days: High, raised by accumulation.
      ...(s.geometry&&!outlookExpired?{method:'stage2_xgboost_guarded',class_driver:'accumulation',antecedent_observed_mm:70,issue_day_forecast_mm:6,missing_issue_day_hours:0,accumulation_7d_mm:84,accumulation_complete:true,antecedent_cell:'lat887_lon2168',fallback_reasons:[],rule_class:'High',model_version:'stage2-xgb-ad9614eb6e85',model_scores:{Low:0.05,Moderate:0.15,High:0.55,Extreme:0.25},guard_applied:false,model_status:'APPLIED'}
        :{method:null,class_driver:null,antecedent_observed_mm:null,issue_day_forecast_mm:null,missing_issue_day_hours:null,accumulation_7d_mm:null,accumulation_complete:null,antecedent_cell:null,fallback_reasons:[],rule_class:null,model_version:null,model_scores:null,guard_applied:false,model_status:null}),
      received_at:source.received_at,run_at:source.run_at,target_start:source.target_start,target_end:source.target_end,
      expires_at:source.expires_at,shared_area_ids:s.geometry?mapped:[],source_grid_point:s.geometry?{latitude:-1.3005272,longitude:36.824646}:null}))}
}
const zone = {
  id: 'mathare',
  name: 'Mathare',
  sub_county: 'Starehe',
  latitude: -1.26,
  longitude: 36.86,
}
const token =
  'fixture.' +
  Buffer.from(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 600 })).toString('base64url') +
  '.unsigned-test-only'
const users = [
  {
    id: 1,
    name: 'Fixture administrator',
    email: 'admin@example.test',
    role: 'admin',
    status: 'Active',
    created_at: timestamp,
  },
  {
    id: 2,
    name: 'Fixture officer',
    email: 'officer@example.test',
    role: 'officer',
    status: 'Active',
    created_at: timestamp,
  },
]
let actor = null,
  report = null
const advisory = {
  id: 1,
  zone_id: 'mathare',
  zone_name: 'Mathare',
  risk_level: 'High',
  timestamp,
  acknowledged_status: false,
  acknowledged_by_name: null,
  acknowledged_at: null,
}
const mime = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
}
const server = createServer(async (req, res) => {
  try {
    const uri = new URL(req.url, 'http://local')
    const path = resolve(dist, '.' + decodeURIComponent(uri.pathname))
    if (path !== dist && !path.startsWith(dist + sep)) {
      res.writeHead(403)
      res.end()
      return
    }
    const target = extname(path) ? path : join(dist, 'index.html')
    const body = await readFile(target)
    res.writeHead(200, { 'Content-Type': mime[extname(target)] || 'application/octet-stream' })
    res.end(body)
  } catch {
    res.writeHead(404)
    res.end()
  }
})
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
const port = server.address().port
const chrome = spawn(
  process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  [
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-background-networking',
    '--disable-extensions',
    '--remote-debugging-port=0',
    '--remote-allow-origins=*',
    '--user-data-dir=' + profile,
    'about:blank',
  ],
  { windowsHide: true, stdio: 'ignore' }
)
let ws
const pending = new Map()
const cancelledImages = []
let serial = 0
const pause = (ms) => new Promise((r) => setTimeout(r, ms))
try {
  let devPort
  for (let i = 0; i < 150; i++) {
    try {
      devPort = Number((await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0])
      break
    } catch {
      await pause(100)
    }
  }
  assert.ok(devPort, 'headless Chrome devtools startup')
  const pages = await (await fetch('http://127.0.0.1:' + devPort + '/json/list')).json()
  ws = new WebSocket(pages.find((p) => p.type === 'page').webSocketDebuggerUrl)
  await new Promise((r, j) => {
    ws.addEventListener('open', r, { once: true })
    ws.addEventListener('error', j, { once: true })
  })
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = ++serial
      pending.set(id, { resolve, reject })
      ws.send(JSON.stringify({ id, method, params }))
    })
  ws.addEventListener('message', (event) => {
    const message = JSON.parse(event.data)
    if (message.id) {
      const item = pending.get(message.id)
      pending.delete(message.id)
      if (!item) return
      if (message.error) item.reject(new Error(JSON.stringify(message.error)))
      else item.resolve(message.result)
      return
    }
    if (message.method === 'Runtime.exceptionThrown')
      errors.push({text:message.params.exceptionDetails.text,description:message.params.exceptionDetails.exception?.description,stack:message.params.exceptionDetails.stackTrace})
    if (message.method === 'Page.javascriptDialogOpening')
      void send('Page.handleJavaScriptDialog', { accept: true })
    if (message.method === 'Fetch.requestPaused') {
      const { requestId, request } = message.params
      void (async () => {
        const url = new URL(request.url)
        if (url.hostname === 'localhost' && url.port === '8000') {
          requests.push({ method: request.method, path: url.pathname, search: url.search })
          let status = 200,
            body,
            csvName = null
          const payload = request.postData ? JSON.parse(request.postData) : {}
          const path = url.pathname
          if (request.method === 'OPTIONS') body = {}
          else if (path === '/dashboard')
            body = {
              zones: [
                { zone, risk_level: 'Extreme', risk_class: 3, confidence_score: 0.9, timestamp },
              ],
              last_updated: timestamp,
              highest_risk: 'High',
              active_alerts: advisory.acknowledged_status ? 0 : 1,
              prediction_context: { spatial_scope:'shared_nairobi_weather',label_basis:'rainfall_soil_moisture_proxy',
                temporal_scope:'current_conditions',location_specific:false,confidence_interpretation:'uncalibrated_class_score' },
            }
          else if (path === '/reporting-zones') body = [zone]
          else if (path === '/monitoring-areas/susceptibility') body = susceptibilityFixture
          else if (path === '/monitoring-areas/today') body = todayFixture()
          else if (path === '/advisories/active') body = { contract_version:'officer-advisories-v1', checked_at:new Date().toISOString(),
            items: advisories.filter(a => a.state === 'Active').map(publicAdvisory) }
          else if (path === '/citizen-report/status' && request.method === 'POST') {
            if (!report || payload.reference !== report.id || payload.code.replace(/[\s-]/g,'').toUpperCase() !== 'K7Q2M9XD') { status = 404; body = { detail:'That reference and code do not match a report. Check both and try again.' } }
            else body = { reference:report.id, review_status:report.review_status, status_text:'fixture', sub_county:'Langata', observed_condition:report.observed_condition,
              reported_at:report.timestamp, checked_at:report.reviewed_at, on_public_map:Boolean(report.public_visible), photo_attached:false }
          }
          else if (path === '/routes/places' && request.method === 'POST') body = { items: /strath/i.test(payload.text)
            ? [{ label:'Strathmore University, Nairobi', name:'Strathmore University', latitude:-1.3101, longitude:36.8137 }]
            : [{ label:'Kenyatta Avenue, Nairobi', name:'Kenyatta Avenue', latitude:-1.2864, longitude:36.8172 }] }
          else if (path === '/routes/check' && request.method === 'POST') body = { contract_version:'route-check-v1', profile:payload.profile,
            checked_at:new Date().toISOString(), distance_m:4484, duration_s:540, geometry:[[-1.3101,36.8137],[-1.3060,36.8160],[-1.2864,36.8172]],
            avoided:{ requested:payload.avoid_reports, applied:payload.avoid_reports, count:payload.avoid_reports ? 1 : 0 },
            reports: report?.public_visible ? [{ id:report.id, observed_condition:report.observed_condition, perceived_severity:report.perceived_severity, reported_at:report.timestamp, latitude:-1.311, longitude:36.817, distance_m:195 }] : [],
            advisories: advisories.filter(a => a.state === 'Active').map(a => ({ ...publicAdvisory(a), pinned:true, distance_m:40 })),
            crossings:[{ name:'Ngong River', latitude:-1.3075, longitude:36.8155 }],
            places:[{ area_id:'NFW-S037', name:'T-Mall / Langata Road', latitude:-1.3109, longitude:36.8172, category:'High', susceptibility:'Higher', distance_m:151 }] }
          else if (path === '/reporting-areas') body = [{ id:'nairobi-subcounty-kibra', name:'Kibra' }, { id:'nairobi-subcounty-langata', name:'Langata' }, { id:'nairobi-subcounty-starehe', name:'Starehe' }]
          else if (path === '/reporting-areas/locate' && request.method === 'POST') body = Math.abs(payload.latitude + 1.311) < 0.01 ? { id:'nairobi-subcounty-langata', name:'Langata' } : null
          else if (path === '/monitoring-areas') {
            status = areaUnavailable ? 503 : 200
            body = areaUnavailable ? { detail: 'Controlled unavailable inventory' } : areaInventory
          }
          else if (path === '/monitoring-areas/outlook') {
            status=outlookUnavailable?503:200
            body=outlookUnavailable?{detail:'Controlled source failure'}:outlookFixture()
          }
          else if (/^\/monitoring-areas\/NFW-S\d{3}\/reports$/.test(path)) {
            status=actor?200:401
            body=actor?{area_id:path.split('/')[2],status:'AVAILABLE',search_radius_m:500,lookback_days:30,items:report&&path.includes('NFW-S037')?[{
              id:report.id,observed_condition:report.observed_condition,perceived_severity:report.perceived_severity,
              review_status:report.review_status,location_description:report.location_description,
              timestamp:report.timestamp,distance_m:0,reported_accuracy_m:null
            }]:[]}:{detail:'Staff access required'}
          }
          else if (path === '/monitoring-areas/features/weather/current') {
            const tomorrow=new Date(Date.parse(new Date(Date.now()+3*3600000).toISOString().slice(0,10)+'T00:00:00+03:00')+86400000).toISOString()
            body={contract_version:'monitored-point-context-v1',weather_source:{received_at_utc:timestamp,forecast_initialization_utc:new Date(Date.now()-3600000).toISOString()},rows:[{
              area_id:'NFW-S037',weather:{returned_grid_point:{latitude:-1.3005272,longitude:36.824646},shared_grid_area_ids:['NFW-S002','NFW-S003','NFW-S037']},
              forecast_proxy_context:{contract_version:'request-time-forecast-proxy-context-v1',status:'AVAILABLE_FORECAST_RULE_CONTEXT',method:'forecast_daily_rainfall_threshold_rule',model_version:null,flood_probability:null,proxy_class:'Moderate',daily_forecast_rainfall_mm:8,target_start:tomorrow}
            }]}
          }
          else if (path === '/monitoring-areas/collection') {
            if(actor?.role!=='admin'){status=actor?403:401;body={detail:'Administrator required'}}
            else if(request.method==='POST') {
              manualRequestIds.push(payload.request_id)
              const reused=manualRecords.has(payload.request_id)
              if(!reused){
                manualLatest={request_id:payload.request_id,status:'COMPLETE',started_at:new Date().toISOString(),
                  finished_at:new Date().toISOString(),requested_count:36,complete_target_count:36,
                  outcome:'COMPLETE_TARGETS',receipt_sha256:'a'.repeat(64)}
                manualRecords.set(payload.request_id,manualLatest)
              }
              await pause(150)
              if(manualAckLost){manualAckLost=false;status=503;body={detail:'Controlled lost acknowledgement'}}
              else body={contract_version:'manual-point-weather-1',reused,attempt:manualRecords.get(payload.request_id)}
            } else body=manualStatusFixture()
          }
          else if (path === '/health') body = { status:'online', environment:'browser-fixture', binary_rainfall_research:{status:'AVAILABLE',model_version:'nextday-rainfall-binary-v1'} }
          else if (path === '/api/v1/dashboard') {
            const input = url.searchParams.get('input_date') ?? '2024-04-30'
            const target = new Date(Date.parse(input+'T00:00:00Z')+86400000).toISOString().slice(0,10)
            const common = { input_date:input,forecast_target_date:target,forecast_horizon:'next_calendar_day',
              issued_at:target+'T00:00:00+03:00',executed_at:timestamp,data_as_of:null }
            body = { mode:'historical_replay',status:'SUCCESS',model_version:'nairobi_xgboost_nextday_proxy_v1',
              model_task_type:'next_day_proxy_risk',...common,blockers:[],limitation_flags:[],zones:[{
                zone,status:'SUCCESS',risk_class:3,risk_level:'Extreme',model_class_score:0.7,
                proxy_class_scores:{Low:0.1,Moderate:0.1,High:0.1,Extreme:0.7},flood_probability:null,
                flood_probability_reason:'NOT_CALIBRATED_TO_OBSERVED_FLOODS',...common,
                reason_codes:[],freshness:'HISTORICAL_REPLAY',source_metadata:{fixture:true},limitation_flags:[] }] }
          }
          else if (path === '/boundaries') body = boundaryFixture
          else if (path === '/community-reports/recent') {
            const visible = report?.public_visible && Number.isFinite(report.latitude)
            body = { contract_version:'community-reports-public-v1', window_hours:24, location_precision_m:110, checked_at:new Date().toISOString(),
              items: visible ? [{ id:report.id, observed_condition:report.observed_condition, perceived_severity:report.perceived_severity,
                location_description:report.location_description, latitude:Math.round(report.latitude*1000)/1000, longitude:Math.round(report.longitude*1000)/1000,
                reported_at:report.timestamp, checked_at:report.published_at, visible_until:new Date(Date.parse(report.timestamp)+86400000).toISOString() }] : [] }
          }
          else if (path === '/citizen-report' && request.method === 'POST') {
            report = {
              ...payload,
              id: 101,
              zone_id: null,
              zone_name: 'Langata',
              timestamp,
              review_status: 'New',
              review_version: 0,
              reviewed_by_name: null,
              review_note: null,
              reviewed_at: null,
            }
            status = 201
            body = { ...report, tracking_code:'K7Q2-M9XD' }
          } else if (path === '/api/v1/model') {
            status = 503
            body = { detail: 'Model metadata not part of this workflow fixture' }
          } else if (path === '/auth/login' && request.method === 'POST') {
            actor = users.find((user) => user.email === payload.email)
            if (!actor) {
              status = 401
              body = { detail: 'Fixture credentials rejected' }
            } else body = { access_token: token, token_type: 'bearer', user: actor }
          } else {
            assert.equal(
              request.headers.Authorization ?? request.headers.authorization,
              'Bearer ' + token,
              'staff request must carry bearer'
            )
            assert.ok(actor, 'staff session')
            if (path === '/auth/me') body = actor
            else if (path === '/advisories' && request.method === 'GET') body = { items: advisories }
            else if (path === '/advisories' && request.method === 'POST') {
              const now = new Date()
              const advisory = { ...payload, id:advisories.length + 1, area_name:'Langata', issued_at:now.toISOString(),
                expires_at:new Date(now.getTime() + payload.hours * 3600000).toISOString(), state:'Active', issued_by:actor.name, withdrawn_at:null }
              delete advisory.hours
              advisories.unshift(advisory); status = 201; body = advisory
            }
            else if (path === '/staff/model-card') body = staffData.model_card
            else if (path === '/staff/rainfall-history') body = staffData.rainfall_history
            else if (path.startsWith('/exports/')) {
              exportRequests.push(path + url.search)
              csvName = 'nairobifloodwatch-' + path.slice(9, -4) + '-fixture.csv'
              body = '\ufeffreport_id,sub_county\r\n101,Langata\r\n'
            }
            else if (path === '/api/v1/weather-outlook/snapshots') body = { items:[],total:0,checked_at:timestamp }
            else if (path === '/api/v1/weather-outlook') body = {information_type:'numerical_weather_forecast',
              model_inference_performed:false,collection_automatic:false,timezone:'Africa/Nairobi',checked_at:timestamp,
              selection:'current_or_upcoming',status:'NO_CURRENT_FORECAST',snapshot:null,limitations:[],
              explanation:'No current forecast has been captured in this controlled fixture.'}
            else if (path === '/citizen-reports') {
              const items =
                report &&
                (!url.searchParams.get('review_status') ||
                  url.searchParams.get('review_status') === report.review_status)
                  ? [report]
                  : []
              body = { items, total: items.length, limit: 20, offset: 0 }
            } else if (path === '/citizen-reports/101/review' && request.method === 'PATCH') {
              assert.equal(payload.expected_version, report.review_version)
              report = {
                ...report,
                review_status: payload.status,
                review_note: payload.note,
                review_version: report.review_version + 1,
                reviewed_by_name: actor.name,
                reviewed_at: timestamp,
                public_visible: payload.public ?? report.public_visible ?? false,
                published_at: payload.public ? timestamp : null,
              }
              body = report
            } else if (path === '/admin/users' && request.method === 'GET') body = users
            else if (path === '/admin/users' && request.method === 'POST') {
              assert.equal(actor.role, 'admin')
              const { password, ...fields } = payload
              const account = { ...fields, id: 3, status: 'Active', created_at: timestamp }
              users.push(account)
              status = 201
              body = account
            } else if (path === '/admin/users/3' && request.method === 'PUT') {
              assert.equal(actor.role, 'admin')
              const { password, ...fields } = payload
              Object.assign(
                users.find((user) => user.id === 3),
                fields
              )
              body = users.find((user) => user.id === 3)
            } else if (path === '/admin/users/3' && request.method === 'DELETE') {
              users.splice(
                users.findIndex((user) => user.id === 3),
                1
              )
              body = { message: 'User deleted successfully' }
            } else if (path === '/api/research/binary-rainfall/current') {
              body = { status:'UNAVAILABLE', checked_at:timestamp, model:{ status:'AVAILABLE', model_version:'nextday-rainfall-binary-v1' },
                target:'ERA5-estimated next-day rainfall at or above 5 mm (research proxy)',
                output_interpretation:'Uncalibrated research score; not a flood prediction.', source:{}, areas:[],
                reason:'NO_VERIFIED_POINT_FORECAST', limitations:[] }
            } else if (path === '/alerts')
              body = { items: [advisory], total: 1, limit: 50, offset: 0 }
            else if (path === '/alerts/1/acknowledge' && request.method === 'POST') {
              Object.assign(advisory, {
                acknowledged_status: true,
                acknowledged_by_name: actor.name,
                acknowledged_at: timestamp,
              })
              body = advisory
            } else {
              status = 503
              body = { detail: 'Not part of this controlled workflow fixture' }
            }
          }
          await send('Fetch.fulfillRequest', {
            requestId,
            responseCode: status,
            responseHeaders: [
              { name: 'Content-Type', value: csvName ? 'text/csv; charset=utf-8' : 'application/json' },
              ...(csvName ? [{ name: 'Content-Disposition', value: `attachment; filename="${csvName}"` },
                { name: 'Access-Control-Expose-Headers', value: 'Content-Disposition' }] : []),
              { name: 'Access-Control-Allow-Origin', value: '*' },
              { name: 'Access-Control-Allow-Headers', value: 'Authorization, Content-Type' },
              {
                name: 'Access-Control-Allow-Methods',
                value: 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
              },
              { name: 'Cache-Control', value: 'no-store' },
            ],
            body: Buffer.from(csvName ? body : JSON.stringify(body)).toString('base64'),
          })
        } else if (url.hostname === '127.0.0.1' && url.port === String(port))
          await send('Fetch.continueRequest', { requestId })
        else
          await send('Fetch.fulfillRequest', {
            requestId,
            responseCode: 200,
            responseHeaders: [{ name: 'Content-Type', value: 'text/plain' }],
            body: '',
          })
      })().catch((error) => {
        // Leaving a Leaflet page cancels tile requests before the fixture can reply.
        // Record that CDP transport race separately; API and application errors still fail.
        if (message.params.resourceType === 'Image' && error.message.includes('Invalid InterceptionId'))
          cancelledImages.push(request.url)
        else errors.push(error.message)
      })
    }
  })
  await send('Page.enable')
  await send('Runtime.enable')
  await send('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] })
  await send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: evidence })
  const evaluate = async (expression) => {
    const result = await send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    })
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text)
    return result.result.value
  }
  const waitFor = async (expression) => {
    for (let i = 0; i < 150; i++) {
      if (await evaluate('Boolean(' + expression + ')')) return
      await pause(100)
    }
    throw new Error('UI condition timed out: ' + expression)
  }
  const set = async (selector, value) =>
    evaluate(
      `(()=>{const e=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(e.tagName==='SELECT'?HTMLSelectElement.prototype: e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event(e.tagName==='SELECT'?'change':'input',{bubbles:true}))})()`
    )
  const click = async (text) =>
    evaluate(
      `Array.from(document.querySelectorAll('button')).find(e=>e.textContent===${JSON.stringify(text)}).click()`
    )
  const link = async (path) =>
    evaluate(
      `document.querySelector('a[href='+JSON.stringify(${JSON.stringify(path)})+']').click()`
    )
  const shot = async (name) => {
    const result = await send('Page.captureScreenshot', {
      format: 'png',
      captureBeyondViewport: false,
    })
    await writeFile(join(evidence, name + '.png'), Buffer.from(result.data, 'base64'))
  }
  const login = async (role) => {
    await send('Page.navigate', { url: `http://127.0.0.1:${port}/login` })
    await waitFor(`document.querySelector('input[type=email]')`)
    await set('input[type=email]', role + '@example.test')
    await set('input[type=password]', 'fixture-only-password')
    await evaluate(`document.querySelector('button[type=submit]').click()`)
    await waitFor(`location.pathname===${JSON.stringify(role === 'admin' ? '/admin' : '/officer')}`)
  }
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  })
  await send('Page.navigate', { url: `http://127.0.0.1:${port}/research` })
  await waitFor(`location.pathname==='/login'&&document.querySelector('input[type=email]')`)
  assert.ok(!requests.some(r=>r.path.includes('dashboard')||r.path.startsWith('/api/v2')),'anonymous research access cannot load model data')
  await send('Page.navigate', { url: `http://127.0.0.1:${port}/` })
  await waitFor(`document.querySelectorAll('path.monitored-area').length===34`)
  assert.ok(await evaluate(`document.querySelector('.leaflet-container').getBoundingClientRect().height>innerHeight*.8`),'map remains dominant')
  assert.equal(await evaluate(`document.querySelectorAll('path.monitoring-point').length`),0,'old model-zone centres are absent from the public map')
  await waitFor(`Array.from(document.querySelectorAll('path.monitored-area')).every(e=>e.getAttribute('fill')==='#EA580C')`)
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('path.monitored-area')).every(e=>e.getAttribute('tabindex')==='0'&&e.getAttribute('aria-label').includes('High rainfall risk today'))`),true,'pins show the category by colour and accessible label')
  const legend=await evaluate(`document.querySelector('details.rainfall-legend').innerText`)
  assert.ok(legend.includes('Rainfall risk today')&&legend.includes('36 High')&&legend.includes('not flood warnings'),'legend explains colours and summarises tomorrow')
  assert.equal(await evaluate(`document.querySelector('a[href="/hotspots"]')`),null,'removed tab has no navigation link')
  assert.ok(!/hotspot/i.test(await evaluate('document.body.innerText')),'public map has no hotspot terminology')
  assert.ok(!requests.some(r=>r.path.includes('dashboard')||r.path.startsWith('/api/v2')||r.path==='/api/v1/model'),'public map makes no model requests')
  assert.equal(await evaluate(`document.querySelector('[aria-label="Map prediction controls"]')`),null)
  await shot('desktop-monitored-map')
  await evaluate(`document.querySelector('path.monitored-area').dispatchEvent(new MouseEvent('click',{bubbles:true}))`)
  await waitFor(`document.querySelector('.leaflet-popup-content')?.innerText.includes('Heavy rain')`)
  await evaluate(`Array.from(document.querySelectorAll('[aria-label="Show risk for"] button')).find(b=>b.textContent==='Tomorrow').click()`)
  await waitFor(`document.querySelector('details.rainfall-legend').innerText.includes('Rainfall risk for tomorrow')&&document.querySelector('path.monitored-area').getAttribute('aria-label').includes('rainfall risk tomorrow')`)
  await waitFor(`document.querySelectorAll('path.susceptibility-higher').length>0`)
  assert.ok((await evaluate(`document.querySelector('details.rainfall-legend').innerText`)).includes('Dark ring'),'legend explains the susceptibility ring')
  await evaluate(`Array.from(document.querySelectorAll('[aria-label="Language"] button')).find(b=>b.textContent==='SW').click()`)
  await waitFor(`document.documentElement.lang==='sw'&&document.querySelector('details.rainfall-legend').innerText.includes('Hatari ya mvua kesho')&&document.body.innerText.includes('Ripoti mafuriko')`)
  await shot('map-kiswahili')
  await evaluate(`Array.from(document.querySelectorAll('[aria-label="Lugha"] button')).find(b=>b.textContent==='EN').click()`)
  await waitFor(`document.documentElement.lang==='en'&&document.querySelector('details.rainfall-legend').innerText.includes('Rainfall risk for tomorrow')`)
  await evaluate(`document.querySelector('details.map-layer-controls').open=true`)
  await evaluate(`Array.from(document.querySelectorAll('label')).find(e=>e.innerText.trim()==='Monitored areas').querySelector('input').click()`)
  await waitFor(`document.querySelectorAll('path.monitored-area').length===0`)
  await evaluate(`Array.from(document.querySelectorAll('label')).find(e=>e.innerText.trim()==='Monitored areas').querySelector('input').click()`)
  await waitFor(`document.querySelectorAll('path.monitored-area').length===34`)
  await evaluate(`document.querySelector('details.map-layer-controls').open=false;document.querySelector('details.monitored-area-controls').open=true`)
  await set('select[aria-label="Parent monitoring zone"]','nairobi-subcounty-langata')
  await waitFor(`document.querySelectorAll('path.monitored-area').length===5`)
  await set('input[aria-label="Search monitored areas"]','T-Mall')
  await waitFor(`document.querySelectorAll('path.monitored-area').length===1`)
  await evaluate(`document.querySelector('path.monitored-area').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))`)
  await waitFor(`document.querySelector('.leaflet-popup-content')?.innerText.includes('T-Mall')`)
  assert.ok((await evaluate(`document.querySelector('.leaflet-popup-content').innerText`)).includes('Langata'))
  await evaluate(`document.querySelector('button[data-area-id="NFW-S037"]').click()`)
  await waitFor(`document.querySelector('section[aria-label="Rainfall risk summary"]')?.innerText.includes('High rainfall risk')`)
  const citizenSummary=await evaluate(`document.querySelector('aside[aria-label="Selected monitored area"]').innerText`)
  assert.ok(citizenSummary.includes('Heavy rain is likely')&&citizenSummary.includes('Kenya Meteorological Department')&&citizenSummary.includes('Report flooding here'),'citizens see a short category, advice and a report link')
  assert.ok(!citizenSummary.includes('SHA-256')&&!citizenSummary.includes('NDVI'),'technical detail stays collapsed for citizens')
  assert.equal(await evaluate(`document.querySelector('details.area-more-details').open`),false,'More details starts closed for the public')
  await evaluate(`document.querySelector('details.area-more-details').open=true`)
  await waitFor(`document.querySelector('article[aria-label*="T-Mall"]')`)
  const tmallProfile=await evaluate(`document.querySelector('article').innerText`)
  assert.ok(!tmallProfile.includes('SHA-256'),'evidence hashes are staff-only')
  assert.ok(tmallProfile.includes('Surface slope')&&tmallProfile.includes('NDVI 0.085')&&tmallProfile.toLowerCase().includes('ngong river'),'updated terrain/drainage and a genuine new-coordinate NDVI sample')
  assert.ok(tmallProfile.includes('-1.310944, 36.817167')&&tmallProfile.includes('User-supplied monitoring point'),'user-specified T-Mall coordinates and provenance are visible')
  await evaluate(`document.querySelector('details.nearby-water-reference').open=true`)
  await waitFor(`document.querySelector('details.nearby-water-reference').innerText.includes('outside the historical scene')`)
  assert.ok(tmallProfile.includes('Zone: Langata'),'actual Langata parent is visible')
  assert.ok(!/hotspot/i.test(tmallProfile),'area details have no hotspot terminology')
  await shot('desktop-monitored-area-profile')
  await evaluate(`document.querySelector('button[aria-label="Close area details"]').click()`)
  await click('Show all')
  await evaluate(`document.querySelector('details.monitored-area-controls').open=true`)
  await set('input[aria-label="Search monitored areas"]','Gatoto')
  await waitFor(`document.querySelector('button[data-area-id="NFW-S007"]')`)
  await evaluate(`document.querySelector('button[data-area-id="NFW-S007"]').click()`)
  await evaluate(`document.querySelector('details.area-more-details').open=true`)
  await waitFor(`document.querySelector('article')?.innerText.includes('Gatoto')`)
  await evaluate(`document.querySelector('details.nearby-water-reference').open=true`)
  await waitFor(`document.querySelector('details.nearby-water-reference').innerText.includes('141 m')`)
  assert.ok((await evaluate(`document.querySelector('details.nearby-water-reference').innerText`)).includes('1 May 2024'),'nearby-water evidence carries its actual historical date')
  await shot('historical-nearby-water-reference')
  await evaluate(`document.querySelector('button[aria-label="Close area details"]').click();document.querySelector('details.monitored-area-controls').open=true`)
  await set('input[aria-label="Search monitored areas"]','Uhuru Highway')
  await waitFor(`document.querySelector('button[data-area-id="NFW-S003"]')`)
  await evaluate(`document.querySelector('button[data-area-id="NFW-S003"]').click()`)
  await evaluate(`document.querySelector('details.area-more-details').open=true`)
  await waitFor(`document.querySelector('article')?.innerText.includes('-1.294306, 36.821389')`)
  const uhuruProfile=await evaluate(`document.querySelector('article').innerText`)
  assert.ok(uhuruProfile.includes('Zone: Starehe')&&uhuruProfile.includes('NDVI 0.126'),'new Uhuru pin has its own stored-boundary assignment and measured spectral context')
  assert.ok(uhuruProfile.includes('no dated flood observation'),'user-selected point is not upgraded to a dated flood incident')
  await shot('updated-uhuru-monitoring-point')
  const closeRect=await evaluate(`(()=>{const r=document.querySelector('button[aria-label="Close area details"]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`)
  await send('Input.dispatchMouseEvent',{type:'mousePressed',...closeRect,button:'left',clickCount:1})
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',...closeRect,button:'left',clickCount:1})
  await waitFor(`!document.querySelector('aside[aria-label="Selected monitored area"]')&&!location.search.includes('area=')`)
  await waitFor(`document.querySelectorAll('.leaflet-popup').length===0`)
  assert.equal(await evaluate(`document.querySelectorAll('.leaflet-popup').length`),0,'closing details clears selected marker and its popup')
  await evaluate(`document.querySelector('details.monitored-area-controls').open=true;document.querySelector('button[data-area-id="NFW-S003"]').click()`)
  await waitFor(`document.querySelector('.leaflet-popup-close-button')`)
  // Close the side panel first so a real pointer can reach the map popup.
  await evaluate(`history.replaceState({},'',location.pathname+'?area=NFW-S003');dispatchEvent(new PopStateEvent('popstate'))`)
  await waitFor(`!document.querySelector('aside[aria-label="Selected monitored area"]')`)
  const popupClose=await evaluate(`(()=>{const r=document.querySelector('.leaflet-popup-close-button').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`)
  await send('Input.dispatchMouseEvent',{type:'mousePressed',...popupClose,button:'left',clickCount:1})
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',...popupClose,button:'left',clickCount:1})
  await waitFor(`document.querySelectorAll('.leaflet-popup').length===0&&!location.search.includes('area=')`)
  await pause(200)
  assert.equal(await evaluate(`document.querySelectorAll('.leaflet-popup').length`),0,'native popup close does not select the subcounty beneath it or reopen')
  await evaluate(`document.querySelector('details.monitored-area-controls').open=true`)
  await set('input[aria-label="Search monitored areas"]','Dandora Area 3')
  await waitFor(`document.querySelectorAll('path.monitored-area').length===1`)
  await evaluate(`document.querySelector('path.monitored-area').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))`)
  await waitFor(`document.querySelector('.leaflet-popup-content')?.innerText.includes('2 monitored records share this place')`)
  await set('input[aria-label="Search monitored areas"]','Gumba')
  await waitFor(`document.querySelectorAll('path.monitored-area').length===1&&document.querySelector('button[data-area-id="NFW-S032"]')`)
  await evaluate(`document.querySelector('button[data-area-id="NFW-S032"]').click()`)
  await evaluate(`document.querySelector('details.area-more-details').open=true`)
  await waitFor(`document.querySelector('article')?.innerText.includes('User-supplied monitoring point')`)
  assert.equal(await evaluate(`document.querySelectorAll('path.monitored-area').length`),1,'user-located Gumba Bridge has its own pin')
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true})
  assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,'mobile area details have no horizontal overflow')
  await shot('mobile-monitored-area-details')
  areaUnavailable=true
  await send('Page.navigate',{url:`http://127.0.0.1:${port}/`})
  await waitFor(`document.querySelector('[role="alert"]')`)
  assert.equal(await evaluate(`document.querySelectorAll('path.monitored-area').length`),0,'failed inventory does not fall back to model-zone centres')
  areaUnavailable=false
  await click('Retry areas')
  await waitFor(`document.querySelectorAll('path.monitored-area').length===34`)
  await send('Page.navigate',{url:`http://127.0.0.1:${port}/hotspots?site=NFW-S037`})
  await waitFor(`location.pathname==='/'&&location.search.includes('area=NFW-S037')&&document.querySelector('.leaflet-popup-content')?.innerText.includes('T-Mall')`)
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false})
  await link('/citizen#report')
  await waitFor(`document.querySelectorAll('#report-area_id option').length===4`)
  assert.equal(await evaluate(`document.querySelector('#report-latitude').value`),'','reference coordinates are never invented as observation coordinates')
  await set('#report-area_id', 'nairobi-subcounty-kibra')
  await set('#report-location_description', 'Outside Tmall near Strathmore')
  await evaluate(`document.querySelector('#report-latitude').closest('details').open=true`)
  await set('#report-latitude', '-1.310944444')
  await set('#report-longitude', '36.817166667')
  // The pin picks its own sub-county (and corrects a wrong choice) without the URL carrying it.
  await waitFor(`document.querySelector('#report-area_id').value==='nairobi-subcounty-langata'&&document.body.innerText.includes('Filled in from your pin: Langata')`)
  assert.ok(!requests.some(r=>r.path.includes('locate')&&/latitude|-1\.31/.test(r.search||'')),'pin is never sent in a URL')
  await shot('citizen-report-form')
  await evaluate(`document.querySelector('#report form button[type=submit]').click()`)
  await waitFor(`document.querySelector('#report-success')`)
  assert.equal(report.location_description, 'Outside Tmall near Strathmore')
  assert.equal(report.latitude, -1.310944444)
  assert.equal(await evaluate(`document.querySelector('[data-testid="tracking-code"]').textContent`), 'K7Q2-M9XD', 'tracking code is shown once after sending')
  await set('input[aria-label="Reference"]', '101')
  await set('input[aria-label="Tracking code"]', 'k7q2-m9xd')
  await click('Check status')
  await waitFor(`document.querySelector('#check [role=status]')?.innerText.includes('Waiting for an officer')`)
  assert.ok(!requests.some(r=>r.path.includes('status')&&r.search),'status check never puts the code in a URL')
  await shot('citizen-report-confirmed')
  await login('officer')
  await waitFor(`document.body.innerText.includes('Recent community reports')`)
  await waitFor(`document.querySelector('[aria-label="Places by category tomorrow"]')`)
  assert.ok(await evaluate(`document.querySelector('nav[aria-label="Staff"]').innerText.includes('Rainfall history')&&!document.querySelector('nav[aria-label="Staff"]').innerText.includes('Users')`),'officers see grouped navigation without admin tools')
  await shot('officer-overview')
  assert.ok(!(await evaluate('document.body.innerText')).includes('Saved zone indications'))
  assert.ok(!requests.some(r=>r.path.includes('dashboard')||r.path.startsWith('/api/v2')),'officer overview makes no model requests')
  assert.equal(
    await evaluate(`document.querySelector('[aria-label="Map prediction controls"]')===null`),
    true
  )
  await link('/officer/reports?review_status=New')
  await waitFor(`document.querySelector('[aria-label="Report review status filter"] button[aria-pressed="true"]')?.textContent==='New'`)
  await evaluate(`Array.from(document.querySelectorAll('[aria-label="Report review status filter"] button')).find(b=>b.textContent==='All').click()`)
  await waitFor(`location.search===''`)
  await waitFor(`document.body.innerText.includes('Outside Tmall near Strathmore')`)
  await set('select[aria-label="Decision for report 101"]', 'ActionNeeded')
  await set('textarea[aria-label="Review note for report 101"]', 'Site inspection needed (fixture)')
  // A background/manual refresh must preserve an unsaved review note.
  await click('Refresh inbox')
  await pause(300)
  assert.equal(
    await evaluate(`document.querySelector('textarea').value`),
    'Site inspection needed (fixture)'
  )
  assert.ok((await evaluate(`document.querySelector('input[aria-label="Show report 101 on the public map"]').closest('label').innerText`)).includes('never the description'),'staff see what publishing reveals')
  await evaluate(`document.querySelector('input[aria-label="Show report 101 on the public map"]').click()`)
  await click('Save decision')
  await waitFor(
    `document.body.innerText.includes('Decision saved.')&&document.body.innerText.includes('Action needed')`
  )
  assert.equal(report.public_visible, true, 'officer chose to publish the checked report')
  assert.equal(report.review_note, 'Site inspection needed (fixture)')
  assert.equal(report.review_version, 1)
  await shot('officer-report-review')
  // The published report appears on the public map as a separate triangle marker.
  await evaluate(`history.pushState({},'', '/');dispatchEvent(new PopStateEvent('popstate'))`)
  await waitFor(`document.querySelector('.community-report')`)
  await evaluate(`document.querySelector('details.monitored-area-controls').open=false;document.querySelector('details.map-layer-controls').open=false`)
  // The map may still be fitting its view; measure after it settles and retry a real click.
  for (let attempt=0; attempt<3; attempt++) {
    await pause(600)
    const reportPin=await evaluate(`(()=>{const r=document.querySelector('.community-report').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`)
    await send('Input.dispatchMouseEvent',{type:'mousePressed',...reportPin,button:'left',clickCount:1})
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',...reportPin,button:'left',clickCount:1})
    await pause(300)
    if (await evaluate(`Boolean(document.querySelector('.leaflet-popup-content')?.innerText.toLowerCase().includes('checked by staff'))`)) break
  }
  await waitFor(`document.querySelector('.leaflet-popup-content')?.innerText.toLowerCase().includes('checked by staff')`)
  const reportPopup=await evaluate(`document.querySelector('.leaflet-popup-content').innerText`)
  assert.ok(reportPopup.includes('Outside Tmall near Strathmore')&&reportPopup.includes('not an official warning')&&!reportPopup.includes('Site inspection'),'published report shows on the public map without staff notes')
  assert.ok((await evaluate(`document.querySelector('details.rainfall-legend').innerText`)).includes('1 flooding report from residents'),'legend counts checked reports')
  await shot('public-community-report')
  await evaluate(`history.pushState({},'', '/advisories');dispatchEvent(new PopStateEvent('popstate'))`)
  await waitFor(`document.querySelectorAll('select[aria-label="Advisory sub-county"] option').length>1`)
  await set('select[aria-label="Advisory sub-county"]', 'nairobi-subcounty-langata')
  await set('select[aria-label="Advisory type"]', 'Warning')
  await set('input[aria-label="Advisory place"]', 'Outering Road underpass')
  await set('textarea[aria-label="Advisory message"]', 'Avoid the underpass until the water clears.')
  await set('input[aria-label="Advisory latitude"]', '-1.3109')
  await set('input[aria-label="Advisory longitude"]', '36.8172')
  await click('Post advisory')
  await waitFor(`document.body.innerText.includes('Advisory posted')&&document.querySelector('li[aria-label="Advisory 1"]')`)
  assert.equal(advisories[0].latitude, -1.3109, 'pinned advisory saved with its place')
  await shot('staff-advisories')
  await evaluate(`history.pushState({},'', '/');dispatchEvent(new PopStateEvent('popstate'))`)
  await waitFor(`document.querySelector('[aria-label="Officer advisories"]')?.innerText.includes('Outering Road underpass')&&document.querySelector('.officer-advisory')`)
  await shot('public-advisory')
  await evaluate(`history.pushState({},'', '/?area=NFW-S037&inspect=1');dispatchEvent(new PopStateEvent('popstate'))`)
  await waitFor(`document.querySelector('[aria-label="Point forecast rainfall proxy"]')?.innerText.includes(${JSON.stringify(pointRainText)})`)
  await evaluate(`document.querySelector('[aria-label="Point forecast rainfall proxy"] details').open=true`)
  assert.ok((await evaluate(`document.querySelector('[aria-label="Point forecast rainfall proxy"]').innerText`)).includes('not an XGBoost output'),'staff proxy rule is explicitly distinguished from v1 inference')
  await waitFor(`document.querySelector('[aria-label="Nearby community reports"]')?.innerText.includes('Outside Tmall near Strathmore')`)
  assert.ok((await evaluate(`document.querySelector('article').innerText`)).includes('Land-cover context'),'source-linked land cover appears in the point profile')
  await shot('staff-point-forecast-proxy-context')
  outlookExpired=true
  await click('Refresh outlook')
  await waitFor(`document.querySelector('[aria-label="Point forecast rainfall proxy"]')?.innerText.includes('No fresh, complete forecast')`)
  assert.ok(!(await evaluate(`document.querySelector('[aria-label="Point forecast rainfall proxy"]').innerText`)).includes(pointRainText),'expired weather clears old values')
  outlookExpired=false;outlookUnavailable=true
  // Tomorrow's outage is reported when tomorrow is shown; today's outlook is separate.
  await evaluate(`Array.from(document.querySelectorAll('[aria-label="Show risk for"] button')).find(b=>b.textContent==='Tomorrow').click()`)
  await click('Refresh outlook')
  await waitFor(`document.querySelector('[aria-label="Forecast collection status"]').innerText.includes('Fresh rainfall outlook unavailable')`)
  assert.equal(await evaluate(`document.querySelectorAll('path.monitored-area').length`),34,'weather failure preserves geographic monitoring pins')
  outlookUnavailable=false
  await evaluate(`history.pushState({},'', '/weather-outlook');dispatchEvent(new PopStateEvent('popstate'))`)
  await waitFor(`document.querySelector('table[aria-label="Monitored-area rainfall outlook"] tbody tr')`)
  assert.equal(await evaluate(`document.querySelectorAll('table[aria-label="Monitored-area rainfall outlook"] tbody tr').length`),36,'weather page uses the same complete monitored-location inventory')
  await set('select[aria-label="Weather parent zone"]','nairobi-subcounty-langata')
  assert.ok((await evaluate(`document.querySelector('table[aria-label="Monitored-area rainfall outlook"]').innerText`)).includes('T-Mall'),'weather parent filter preserves the correct geographic association')
  await shot('staff-weather')
  await link('/')
  await waitFor(`document.querySelector('.leaflet-container')`)
  await evaluate(`history.pushState({},'', '/citizen');dispatchEvent(new PopStateEvent('popstate'))`)
  await waitFor(`location.pathname==='/citizen'`)
  assert.equal(
    await evaluate(`document.querySelector('#report form')===null`),
    true,
    'staff cannot see citizen submission form'
  )
  await login('admin')
  await waitFor(`document.body.innerText.includes('Responding')`)
  assert.ok(!(await evaluate('document.body.innerText')).includes('Live-data blockers'))
  await waitFor(`Array.from(document.querySelectorAll('button')).some(e=>e.textContent==='Collect latest weather'&&!e.disabled)`)
  await evaluate(`{const b=Array.from(document.querySelectorAll('button')).find(e=>e.textContent==='Collect latest weather');b.click();b.click()}`)
  await waitFor(`document.body.innerText.includes('36/36 target-day records verified.')`)
  assert.equal(manualRequestIds.length,1,'double click creates one explicit collection request')
  assert.ok(await evaluate(`Array.from(document.querySelectorAll('button')).find(e=>e.textContent==='Collect latest weather').disabled`),'cooldown is respected')
  await click('Check collection status')
  await pause(300)
  assert.equal(manualRequestIds.length,1,'status refresh never collects weather')
  await shot('admin-manual-weather-complete')
  manualLatest={...manualLatest,started_at:new Date(Date.now()-960000).toISOString()}
  await click('Check collection status')
  await waitFor(`Array.from(document.querySelectorAll('button')).some(e=>e.textContent==='Collect latest weather'&&!e.disabled)`)
  manualAckLost=true
  await click('Collect latest weather')
  await waitFor(`document.body.innerText.includes('Controlled lost acknowledgement')`)
  assert.equal(manualRequestIds.length,2,'uncertain result is not retried automatically')
  await click('Resume same attempt')
  await waitFor(`document.body.innerText.includes('Saved attempt verified.')`)
  assert.equal(manualRequestIds[1],manualRequestIds[2],'recovery keeps original request identity')
  await shot('admin-manual-weather-recovered')
  await link('/admin/users')
  await waitFor(`document.body.innerText.includes('Fixture officer')`)
  await click('Add user')
  await set('input[aria-label="Account name"]', 'New fixture officer')
  await set('input[aria-label="Account email"]', 'new@example.test')
  await set('input[aria-label="Account password"]', 'fixture-only-password')
  await click('Save account')
  await waitFor(`document.querySelector('article[aria-label="Account 3"]')`)
  await evaluate(
    `Array.from(document.querySelector('article[aria-label="Account 3"]').querySelectorAll('button')).find(e=>e.textContent==='Edit').click()`
  )
  await set('input[aria-label="Account name"]', 'Updated fixture officer')
  await set('select[aria-label="Account status"]', 'Inactive')
  await click('Save account')
  await waitFor(
    `document.querySelector('article[aria-label="Account 3"]').innerText.includes('Inactive')`
  )
  assert.equal(users.find((user) => user.id === 3).name, 'Updated fixture officer')
  await shot('admin-user-management')
  await evaluate(
    `Array.from(document.querySelector('article[aria-label="Account 3"]').querySelectorAll('button')).find(e=>e.textContent==='Remove').click()`
  )
  await waitFor(`!document.querySelector('article[aria-label="Account 3"]')`)
  assert.equal(users.length, 2)
  await link('/admin/models')
  await waitFor(`document.body.innerText.includes('How well it does')&&document.querySelector('.recharts-bar-rectangle')`)
  const modelsText = (await evaluate('document.body.innerText')).toLowerCase()
  for (const phrase of ['36 of 36 places', 'heavy-rain days caught', 'not probabilities', 'research only']) assert.ok(modelsText.includes(phrase), phrase)
  await shot('admin-models')
  await link('/history')
  await waitFor(`document.body.innerText.includes('Wettest days')&&document.querySelectorAll('.recharts-bar-rectangle').length>20`)
  await set('select[aria-label="Year to compare"]', '2018')
  await waitFor(`document.querySelector('[aria-label="Chart legend"]').innerText.includes('2018')`)
  await shot('rainfall-history')
  await link('/downloads')
  await waitFor(`document.body.innerText.includes('Community reports')`)
  await set('select[aria-label="Reports status"]', 'Resolved')
  await evaluate(`document.querySelector('button.press:not([disabled])') && Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Download CSV').click()`)
  let exported
  for (let i = 0; i < 80 && !exported; i++) { try { exported = await readFile(join(evidence, 'nairobifloodwatch-citizen-reports-fixture.csv'), 'utf8') } catch { await pause(100) } }
  assert.ok(exported?.includes('Langata'), 'report CSV downloads with the server file name')
  assert.ok(exportRequests.includes('/exports/citizen-reports.csv?review_status=Resolved'), 'download carries the chosen filter')
  await shot('downloads')
  await evaluate(`history.pushState({},'', '/route');dispatchEvent(new PopStateEvent('popstate'))`)
  await waitFor(`document.querySelector('#route-from')`)
  await set('#route-from', 'Strathmore')
  await evaluate(`document.querySelector('button[aria-label="Search: From"]').click()`)
  await waitFor(`document.querySelector('[aria-label="Choose a place"] button')`)
  await evaluate(`document.querySelector('[aria-label="Choose a place"] button').click()`)
  await set('#route-to', 'Kenyatta')
  await evaluate(`document.querySelector('button[aria-label="Search: To"]').click()`)
  await waitFor(`document.querySelector('[aria-label="Choose a place"] button')`)
  await evaluate(`document.querySelector('[aria-label="Choose a place"] button').click()`)
  await click('Check route')
  await waitFor(`document.querySelector('[aria-label="Route findings"]')?.innerText.includes('Crosses Ngong River')&&document.querySelector('path.checked-route')`)
  const findings = await evaluate(`document.querySelector('[aria-label="Route findings"]').innerText`)
  for (const phrase of ['4.5 km', 'Outering Road underpass', 'T-Mall / Langata Road: High', 'floods easily', 'Never drive or walk through flowing water', 'Route adjusted to avoid 1'])
    assert.ok(findings.includes(phrase), phrase)
  assert.ok(requests.filter(r=>r.path.startsWith('/routes/')).every(r=>!r.search&&['POST','OPTIONS'].includes(r.method)),'route places and coordinates never go in a URL')
  await shot('route-checker')
  await link('/')
  await link('/research')
  await waitFor(`document.body.innerText.includes('Next-day rainfall research')&&document.body.innerText.includes('Historical v1 replay')`)
  await waitFor(`document.body.innerText.includes('Unavailable:')`)
  const researchText = await evaluate('document.body.innerText')
  assert.ok(!researchText.includes('V2 shadow') && !/nowcast|\bv3\b/i.test(researchText), 'retired v2/v3 research views stay removed')
  await waitFor(`document.body.innerText.includes('Historical classifications')&&document.body.innerText.includes('01 May 2024')`)
  await shot('desktop-model-research')
  // The Alerts page has no nav entry in the current TopNav; open it in-app like a typed URL.
  await evaluate(`history.pushState({},'', '/officer/alerts');dispatchEvent(new PopStateEvent('popstate'))`)
  await waitFor(
    `Array.from(document.querySelectorAll('button')).some(e=>e.textContent==='Acknowledge'&&!e.disabled)`
  )
  await click('Acknowledge')
  await waitFor(`document.body.innerText.includes('Reviewed by Fixture administrator')`)
  await click('Export this page')
  let csv
  for (let i = 0; i < 80; i++) {
    try {
      csv = await readFile(join(evidence, 'saved-advisories-page.csv'), 'utf8')
      break
    } catch {
      await pause(100)
    }
  }
  assert.ok(
    csv?.includes('Mathare') && csv.includes('Fixture administrator'),
    'actual CSV download'
  )
  await send('Emulation.setDeviceMetricsOverride', {
    width: 390,
    height: 844,
    deviceScaleFactor: 1,
    mobile: true,
  })
  await evaluate(`document.querySelector('button[aria-label="Open menu"]').click()`)
  await waitFor(`document.querySelector('[role=dialog][aria-label="Menu"]').dataset.open==='true'`)
  await pause(300)
  await shot('mobile-staff-menu')
  await evaluate(`document.querySelector('[role=dialog][aria-label="Menu"] a[href="/officer/reports"]').click()`)
  await waitFor(`location.pathname==='/officer/reports'&&document.querySelector('[role=dialog][aria-label="Menu"]').dataset.open==='false'`)
  await pause(300)
  assert.equal(
    await evaluate('document.documentElement.scrollWidth<=innerWidth'),
    true,
    'mobile horizontal overflow'
  )
  assert.equal(
    await evaluate(`document.querySelector('[aria-label="Map prediction controls"]')===null`),
    true
  )
  assert.ok(!(await evaluate('document.body.innerText')).includes('Emergency delivery'))
  await shot('mobile-staff-report-review')
  await evaluate(`document.querySelector('button[aria-label="Open menu"]').click()`)
  await evaluate(`document.querySelector('[role=dialog][aria-label="Menu"] a[href="/admin/users"]').click()`)
  await waitFor(`document.body.innerText.includes('Fixture officer')`)
  assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,'mobile admin horizontal overflow')
  await shot('mobile-admin-user-management')
  // The retired URL remains a guarded redirect; no obsolete v2 API is polled.
  await evaluate(`history.pushState({},'', '/v2-shadow');dispatchEvent(new PopStateEvent('popstate'))`)
  await waitFor(`location.pathname==='/research'&&location.search==='?retired=v2'&&document.body.innerText.includes('Historical v1 replay')`)
  assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,'mobile research overflow')
  assert.ok(!requests.some(r=>r.path.startsWith('/api/v2')),'retired preview never calls v2 APIs')
  await shot('mobile-model-research')
  await evaluate(`document.querySelector('button[aria-label="Open menu"]').click()`)
  await evaluate(`document.querySelector('[role=dialog][aria-label="Menu"] a[href="/"]').click()`)
  await waitFor(`document.querySelectorAll('path.monitored-area').length===34`)
  // Pins carry only the public outlook colour (fixture: High) or grey; research-model markers never appear.
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('path.monitored-area')).every(e=>['#EA580C','#94a3b8'].includes(e.getAttribute('fill')))&&!document.querySelector('path.monitoring-point')`),true,'research model colours do not leak back to public map')
  assert.ok(await evaluate(`document.querySelector('.leaflet-container').getBoundingClientRect().height>innerHeight*.75`),'mobile map remains visible')
  assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,'mobile map overflow')
  await shot('mobile-outlook-map')

  assert.deepEqual(errors, [])
  const result = {
    status: 'passed',
    kind: genuineOutlook?'genuine CAS-derived public rainfall outlook; controlled report/auth/admin workflow fixtures':'controlled browser fixtures; real native PostgreSQL/FastAPI workflows tested separately',
    checks: [
      'anonymous report with landmark and coordinates',
      'officer inbox receives report',
      'review notes survive refresh',
      'saved decision reflected in inbox',
      'staff has no citizen submission form',
      'no map selector on dashboards',
      'admin create/update/deactivate/delete calls',
      'saved advisory acknowledgement',
      'actual CSV file download',
      'mobile staff navigation and no overflow',
      'public map stays neutral and independent of model APIs',
      'officer workload overview has no model polling',
      'admin status uses actual health response rather than v1 blockers',
      'experimental models and historical replay are staff-only and separate',
      'retired v2 URL redirects without obsolete API calls',
      'removed Hotspots tab redirects old site links to the map and has no visible navigation entry',
      'research model outputs do not leak into the main map; pins use only the public outlook',
      'anonymous research route is guarded before data requests',
      'reference coordinates never become invented citizen-observation coordinates',
      'research page separates binary rainfall research from historical v1 replay, with no retired v2/v3 views',
      'officer workload cards open the matching filtered report queue',
      '36 mapped area records form 34 keyboard-accessible pins coloured by tomorrow\'s rainfall risk, with a legend',
      'citizens see a short risk summary with advice; technical detail and evidence hashes stay collapsed or staff-only',
      'map-based area search and actual parent-zone filtering preserve available GIS context',
      'T-Mall is classified under Langata while model-zone centres stay off the public map',
      'user-supplied T-Mall DMS converts correctly and updated-coordinate NDVI replaces the previous sample',
      'historical nearby-water distances are dated and T-Mall coverage remains explicitly unknown',
      'updated Uhuru DMS has its own NDVI, stored administrative parent and no fabricated incident date',
      'coincident references share a pin and unresolved areas remain unlocated',
      'mobile area details do not overflow; failed reads offer retry without substitute pins',
      'real pointer close clears selection; popup dismissal does not select an underlying subcounty or reopen',
      'staff point profile displays explicit forecast-rule proxy and genuine land-cover context without XGBoost or probability claims',
      'all mapped areas receive a public read-only rainfall outlook; expired/failed sources remove categories without hiding geographic pins',
      'staff point profile shows the submitted and reviewed nearby community report',
      'weather page defaults to the same 36 monitored-location outlook and geographic parent filter',
      'admin explicit weather collection prevents duplicate clicks, respects cooldown and never collects on status refresh',
      'lost collection acknowledgement is recovered with the same UUID without an automatic new attempt',
    ],
    requests,
    evidence_directory: evidence,
    cancelled_image_interceptions: cancelledImages,
  }
  await writeFile(join(evidence, 'verification.json'), JSON.stringify(result, null, 2))
  console.log(JSON.stringify(result, null, 2))
} finally {
  if (ws) {
    if (ws.readyState === WebSocket.OPEN)
      ws.send(JSON.stringify({ id: ++serial, method: 'Browser.close' }))
    await pause(100)
    ws.close()
  }
  chrome.kill()
  await new Promise((resolve) => server.close(resolve))
}
