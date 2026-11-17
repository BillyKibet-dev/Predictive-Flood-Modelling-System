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
      errors.push(message.params.exceptionDetails.text)
    if (message.method === 'Page.javascriptDialogOpening')
      void send('Page.handleJavaScriptDialog', { accept: true })
    if (message.method === 'Fetch.requestPaused') {
      const { requestId, request } = message.params
      void (async () => {
        const url = new URL(request.url)
        if (url.hostname === 'localhost' && url.port === '8000') {
          requests.push({ method: request.method, path: url.pathname })
          let status = 200,
            body
          const payload = request.postData ? JSON.parse(request.postData) : {}
          const path = url.pathname
          if (request.method === 'OPTIONS') body = {}
          else if (path === '/dashboard')
            body = {
              zones: [
                { zone, risk_level: 'High', risk_class: 2, confidence_score: 0.7, timestamp },
              ],
              last_updated: timestamp,
              highest_risk: 'High',
              active_alerts: advisory.acknowledged_status ? 0 : 1,
              prediction_context: {
                spatial_scope: 'shared_nairobi_weather',
                label_basis: 'rainfall_soil_moisture_proxy',
                temporal_scope: 'current_conditions',
                location_specific: false,
                confidence_interpretation: 'uncalibrated_class_score',
              },
            }
          else if (path === '/reporting-zones') body = [zone]
          else if (path === '/boundaries') body = { type: 'FeatureCollection', features: [] }
          else if (path === '/citizen-report' && request.method === 'POST') {
            report = {
              ...payload,
              id: 101,
              zone_name: 'Mathare',
              timestamp,
              review_status: 'New',
              review_version: 0,
              reviewed_by_name: null,
              review_note: null,
              reviewed_at: null,
            }
            status = 201
            body = report
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
              { name: 'Content-Type', value: 'application/json' },
              { name: 'Access-Control-Allow-Origin', value: '*' },
              { name: 'Access-Control-Allow-Headers', value: 'Authorization, Content-Type' },
              {
                name: 'Access-Control-Allow-Methods',
                value: 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
              },
              { name: 'Cache-Control', value: 'no-store' },
            ],
            body: Buffer.from(JSON.stringify(body)).toString('base64'),
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
      })().catch((error) => errors.push(error.message))
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
  await send('Page.navigate', { url: `http://127.0.0.1:${port}/citizen#report` })
  await waitFor(`document.querySelector('#report-zone_id option[value=mathare]')`)
  await set('#report-zone_id', 'mathare')
  await set('#report-location_description', 'Outside Tmall near Strathmore')
  await evaluate(`document.querySelector('#report-latitude').closest('details').open=true`)
  await set('#report-latitude', '-1.31')
  await set('#report-longitude', '36.81')
  await evaluate(`document.querySelector('#report form button[type=submit]').click()`)
  await waitFor(`document.querySelector('#report-success')`)
  assert.equal(report.location_description, 'Outside Tmall near Strathmore')
  assert.equal(report.latitude, -1.31)
  await shot('citizen-report-confirmed')
  await login('officer')
  assert.equal(
    await evaluate(`document.querySelector('[aria-label="Map prediction controls"]')===null`),
    true
  )
  await link('/officer/reports')
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
  await click('Save decision')
  await waitFor(
    `document.body.innerText.includes('Decision saved.')&&document.body.innerText.includes('Action needed')`
  )
  assert.equal(report.review_note, 'Site inspection needed (fixture)')
  assert.equal(report.review_version, 1)
  await shot('officer-report-review')
  await link('/')
  await waitFor(`document.querySelector('a[href="/citizen"]')`)
  await link('/citizen')
  await waitFor(`location.pathname==='/citizen'`)
  assert.equal(
    await evaluate(`document.querySelector('#report form')===null`),
    true,
    'staff cannot see citizen submission form'
  )
  await login('admin')
  await click('User Accounts')
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
  await link('/officer/alerts')
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
  await set('select[aria-label="Staff navigation"]', '/officer/reports')
  await waitFor(`location.pathname==='/officer/reports'`)
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
  await set('select[aria-label="Staff navigation"]', '/admin')
  await waitFor(`document.querySelector('select[aria-label="Admin section"]')`)
  await set('select[aria-label="Admin section"]', 'users')
  await waitFor(`document.body.innerText.includes('Fixture officer')`)
  assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,'mobile admin horizontal overflow')
  await shot('mobile-admin-user-management')

  assert.deepEqual(errors, [])
  const result = {
    status: 'passed',
    kind: 'controlled browser fixtures; real native PostgreSQL/FastAPI workflows tested separately',
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
    ],
    requests,
    evidence_directory: evidence,
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
