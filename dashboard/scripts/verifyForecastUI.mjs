// Browser screenshots use genuine captured weather API responses. Identity, expiry,
// provider-file outage and future-clock archive scenarios are controlled test fixtures.
import { createServer } from 'node:http'
import { readFile, mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve, extname, sep } from 'node:path'
import { spawn } from 'node:child_process'
import assert from 'node:assert/strict'

const root = process.cwd(), dist = resolve(root, 'dashboard/dist')
const sourceEvidence = resolve(root, 'docs/webmasters/forecast_dashboard_evidence')
const evidence = await mkdtemp(join(tmpdir(), 'floodhub-weather-check-'))
const profile = join(await mkdtemp(join(tmpdir(), 'floodhub-weather-ui-')), 'profile')
const captures = JSON.parse(await readFile(join(sourceEvidence, 'api-captures.json'), 'utf8'))
const requests = [], errors = []
let scenario = 'current'
const token = 'fixture.' + Buffer.from(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 1200 })).toString('base64url') + '.unsigned-browser-test-only'
const user = { id: 1, name: 'Test officer', email: 'officer@example.test', role: 'officer', status: 'Active' }
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png' }
const server = createServer(async (req, res) => {
  try {
    const uri = new URL(req.url, 'http://local'), path = resolve(dist, '.' + decodeURIComponent(uri.pathname))
    if (path !== dist && !path.startsWith(dist + sep)) { res.writeHead(403); res.end(); return }
    const target = extname(path) ? path : join(dist, 'index.html')
    const content = await readFile(target)
    res.writeHead(200, { 'Content-Type': mime[extname(target)] || 'application/octet-stream' })
    res.end(content)
  } catch { res.writeHead(404); res.end() }
})
await new Promise(r => server.listen(0, '127.0.0.1', r))
const port = server.address().port
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
  '--disable-extensions', '--remote-debugging-port=0', '--remote-allow-origins=*', '--user-data-dir=' + profile, 'about:blank',
], { windowsHide: true, stdio: 'ignore' })
let ws, serial = 0
const pending = new Map(), pause = ms => new Promise(r => setTimeout(r, ms))
try {
  let devPort
  for (let i = 0; i < 150; i++) { try { devPort = Number((await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break } catch { await pause(100) } }
  assert.ok(devPort, 'headless Chrome startup')
  const pages = await (await fetch('http://127.0.0.1:' + devPort + '/json/list')).json()
  ws = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl)
  await new Promise((r, j) => { ws.addEventListener('open', r, { once: true }); ws.addEventListener('error', j, { once: true }) })
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++serial; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })) })
  ws.addEventListener('message', event => {
    const message = JSON.parse(event.data)
    if (message.id) {
      const p = pending.get(message.id); pending.delete(message.id)
      if (p) message.error ? p.reject(new Error(JSON.stringify(message.error))) : p.resolve(message.result)
      return
    }
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
    if (message.method !== 'Fetch.requestPaused') return
    const { requestId, request } = message.params
    void (async () => {
      const url = new URL(request.url)
      if (url.hostname === 'localhost' && url.port === '8000') {
        requests.push({ method: request.method, path: url.pathname, scenario }) // No bodies, auth or tokens logged.
        let status = 200, body
        if (request.method === 'OPTIONS') body = {}
        else if (url.pathname === '/auth/login' && request.method === 'POST') body = { access_token: token, token_type: 'bearer', user }
        else if (url.pathname === '/auth/me') body = user
        else if (url.pathname.startsWith('/api/v1/weather-outlook')) {
          assert.equal(request.headers.Authorization ?? request.headers.authorization, 'Bearer ' + token)
          assert.equal(request.method, 'GET', 'weather reads only')
          if (scenario === 'expired') { status = 401; body = { detail: 'Controlled session expiry' } }
          else if (scenario === 'outage') { status = 503; body = { detail: 'Forecast storage or verified source content is unavailable. No forecast values confirmed.' } }
          else if (url.pathname.endsWith('/snapshots')) body = ['archive', 'no_current'].includes(scenario) ? captures.catalogue_after_expiry : captures.catalogue
          else if (url.searchParams.has('snapshot_id')) body = scenario === 'archive' ? captures.archived : captures.explicit_now
          else body = scenario === 'no_current' ? captures.no_current : captures.current
        } else if (url.pathname === '/dashboard') body = { zones: [], last_updated: null, active_alerts: 0, highest_risk: 'Unknown' }
        else if (url.pathname === '/boundaries') body = { type: 'FeatureCollection', features: [] }
        else { status = 404; body = { detail: 'No test route' } }
        await send('Fetch.fulfillRequest', { requestId, responseCode: status, responseHeaders: [
          { name: 'Content-Type', value: 'application/json' }, { name: 'Access-Control-Allow-Origin', value: '*' },
          { name: 'Access-Control-Allow-Headers', value: 'Authorization, Content-Type' },
          { name: 'Access-Control-Allow-Methods', value: 'GET, POST, OPTIONS' }, { name: 'Cache-Control', value: 'no-store' },
        ], body: Buffer.from(JSON.stringify(body)).toString('base64') })
      } else if (url.hostname === '127.0.0.1' && url.port === String(port)) await send('Fetch.continueRequest', { requestId })
      else await send('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'text/plain' }], body: '' })
    })().catch(error => errors.push(error.message))
  })
  await send('Page.enable'); await send('Runtime.enable'); await send('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] })
  const evaluate = async expression => { const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value }
  const waitFor = async expression => { for (let i = 0; i < 150; i++) { if (await evaluate('Boolean(' + expression + ')')) return; await pause(100) } throw new Error('UI wait timed out: ' + expression) }
  const screenshot = async name => { const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }); await writeFile(join(evidence, name + '.png'), Buffer.from(shot.data, 'base64')) }
  const refresh = () => evaluate(`Array.from(document.querySelectorAll('button')).find(e=>e.textContent==='Refresh stored data').click()`)
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false })
  await send('Page.navigate', { url: `http://127.0.0.1:${port}/weather-outlook` })
  await waitFor(`location.pathname==='/login'&&document.querySelector('input[type=email]')`)
  await evaluate(`(()=>{for(const [selector,value] of [['input[type=email]','officer@example.test'],['input[type=password]','test-only-password']]){const e=document.querySelector(selector);Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,value);e.dispatchEvent(new Event('input',{bubbles:true}))}document.querySelector('button[type=submit]').click()})()`)
  await waitFor(`location.pathname==='/officer'`)
  await evaluate(`document.querySelector('a[href="/weather-outlook"]').click()`)
  await waitFor(`Array.from(document.querySelectorAll('button')).some(e=>e.textContent==='Open original eight-zone forecast archive')`)
  await evaluate(`Array.from(document.querySelectorAll('button')).find(e=>e.textContent==='Open original eight-zone forecast archive').click()`)
  await waitFor(`document.querySelectorAll('[aria-pressed]').length===8`)
  const text = await evaluate('document.body.innerText')
  for (const phrase of ['10.30 mm', '13.20 mm', 'Stored forecast for the current day', 'Experimental models', 'Shared returned grid point']) assert.ok(text.includes(phrase), phrase)
  await evaluate(`Array.from(document.querySelectorAll('details')).find(e=>e.querySelector('summary')?.textContent.startsWith('Source provenance')).open=true`)
  const details = await evaluate('document.body.innerText')
  assert.ok(details.includes('Unknown; initialization'), 'unknown publication remains disclosed')
  assert.ok(details.includes('Whole-source quality: PARTIAL'), 'partial whole-source quality remains disclosed')
  await evaluate(`Array.from(document.querySelectorAll('details')).find(e=>e.querySelector('summary')?.textContent.startsWith('Source provenance')).open=false`)
  const cards = await evaluate(`Array.from(document.querySelectorAll('[aria-pressed]')).map(e=>e.innerText)`)
  captures.current.snapshot.zones.forEach((z, i) => {
    assert.ok(cards[i].includes(z.name), z.zone_id + ' name')
    assert.ok(cards[i].includes(z.rainfall_mm.toFixed(2) + ' mm'), z.zone_id + ' genuine amount')
  })
  assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'), true)
  await screenshot('desktop-source-backed-weather')
  await evaluate(`document.querySelector('select[aria-label="Monitoring zone"]').value='dagoretti';document.querySelector('select[aria-label="Monitoring zone"]').dispatchEvent(new Event('change',{bubbles:true}))`)
  await waitFor(`document.querySelector('select[aria-label="Monitoring zone"]').value==='dagoretti'`)
  await evaluate(`Array.from(document.querySelectorAll('details')).find(e=>e.querySelector('summary')?.textContent.startsWith('Exact rainfall')).open=true`)
  await waitFor(`document.querySelectorAll('tbody tr').length===24`)
  assert.ok((await evaluate('document.body.innerText')).includes('Soil moisture (m³/m³)'))
  await evaluate(`document.querySelector('[aria-label="Hourly forecast precipitation chart"]').scrollIntoView({block:'start'})`)
  await screenshot('desktop-hourly-source-detail')
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  await evaluate(`scrollTo(0,0);dispatchEvent(new Event('resize'))`); await pause(500)
  assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'), true, 'mobile page overflow')
  await screenshot('mobile-source-backed-weather')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false })
  scenario = 'no_current'; await refresh()
  await waitFor(`document.body.innerText.includes('No current forecast')&&!document.querySelector('[aria-pressed]')`)
  await screenshot('no-current-forecast-controlled-expiry')
  scenario = 'archive'
  await evaluate(`(()=>{const e=document.querySelector('select[aria-label="Forecast snapshot"]');e.value=e.options[1].value;e.dispatchEvent(new Event('change',{bubbles:true}))})()`)
  await waitFor(`document.body.innerText.includes('Archived forecast; its target period has ended.')&&document.querySelectorAll('[aria-pressed]').length===8`)
  await screenshot('archived-forecast-controlled-clock')
  scenario = 'outage'; await refresh()
  await waitFor(`document.querySelector('[role=alert]')&&!document.querySelector('[aria-pressed]')`)
  await screenshot('source-unavailable-controlled-outage')
  scenario = 'expired'; await refresh(); await waitFor(`location.pathname==='/login'`)
  assert.equal(errors.length, 0, JSON.stringify(errors))
  const result = { status: 'PASS', completed_at: new Date().toISOString(), scope: captures.scope,
    screenshot_source: 'Built React app rendering actual API captures; TEST auth/provider transport interception. No public data changed.',
    controlled_scenarios: ['future clock for archived/no-current', '503 source outage', '401 session expiry'],
    checks: ['protected navigation', 'authorized GET-only weather reads', 'all eight genuine rainfall totals', '24 hourly records', 'partial source complete target', 'zone selection', 'shared values disclosed', 'EAT dates', 'desktop and mobile no overflow', 'archive explicit', 'no-current no stale values', 'outage clears values', '401 sign-in redirect'],
    errors, requests }
  await writeFile(join(evidence, 'browser-verification.json'), JSON.stringify(result, null, 2))
  console.log(JSON.stringify({ status: result.status, checks: result.checks.length, evidence_directory: evidence }))
} finally {
  if (ws) { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ id: ++serial, method: 'Browser.close' })); await pause(100); ws.close() }
  chrome.kill(); await new Promise(r => server.close(r))
}
