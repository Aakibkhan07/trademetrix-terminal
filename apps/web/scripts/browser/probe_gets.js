/**
 * Exercise the read endpoints no page visit reaches, and record what they actually return.
 *
 * ## Why
 *
 * `audit_api_contracts.py` can only check a declared type against a response it has *observed*, and
 * the crawler observes what happens when a route is loaded. Of the declarations the audit listed as
 * "never exercised", a large share are plain GETs that no crawled page happens to call — admin tabs
 * the crawler does not open, endpoints behind a tab it does not click, sections behind a query
 * parameter.
 *
 * Those are the *safest* endpoints to exercise. Nothing here mutates state, so the list can be
 * driven directly without the care a write needs, and each response feeds straight back into the
 * contract audit as a signature.
 *
 * This is deliberately read-only. Writes are excluded wholesale rather than sampled: a probe body is
 * not a safe input for an endpoint that places an order, cancels one, or stops trading.
 *
 * ## Output
 *
 * Writes signatures in the same shape `crawl_all_routes.js` produces, so the two can be merged:
 *
 *     { "<path>": [ { path, method, keys, itemKeys } ] }
 *
 * Pass `--out DIR` for the JSON, and the merged set is written to `DIR/response_signatures.json`.
 *
 * ## Honesty about what this does and does not prove
 *
 * A GET that answers 401 or 500 is *observed* and therefore audited, and the audit will report the
 * shape it saw. A GET that fails is not a pass — it is reported separately below so a probe that
 * could not reach an endpoint never reads as an endpoint that was verified.
 */
const fs = require('fs')
const path = require('path')

const puppeteer = require('/Users/aakib/node_modules/puppeteer-core')

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3000'
const API_ORIGIN = process.env.API_ORIGIN || 'http://127.0.0.1:8000'
const EMAIL = process.env.DEMO_EMAIL || 'demo.trader@trademetrix.dev'
const PASSWORD = process.env.DEMO_PASSWORD || 'Demo@2026!'
const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const args = process.argv.slice(2)
const outArg = args.indexOf('--out')
const OUT = outArg >= 0 ? args[outArg + 1] : '/tmp/get_probe'
const listArg = args.indexOf('--list')
const LIST_FILE = listArg >= 0 ? args[listArg + 1] : '/tmp/get_targets.txt'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/** Same shape the crawler emits, so the two signature sets merge. */
function signature(pathname, method, body) {
  const sig = { path: pathname, method, keys: [], itemKeys: null }
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    sig.keys = Object.keys(body).sort()
    // Several endpoints answer with a single-key envelope — `{ orders: [...] }` — and the declared
    // type describes the *item*. Capture the first element's keys so the audit can compare against
    // whichever level the declaration actually names.
    for (const k of sig.keys) {
      const v = body[k]
      if (Array.isArray(v) && v.length && v[0] && typeof v[0] === 'object' && !Array.isArray(v[0])) {
        sig.itemKeys = Object.keys(v[0]).sort()
        break
      }
    }
  } else if (Array.isArray(body) && body.length && body[0] && typeof body[0] === 'object') {
    // A bare array: the item shape *is* the payload shape.
    sig.keys = Object.keys(body[0]).sort()
    sig.itemKeys = sig.keys.slice()
  }
  return sig
}

;(async () => {
  if (!fs.existsSync(LIST_FILE)) {
    console.error(`no target list at ${LIST_FILE} — see the header comment for how to build it`)
    process.exit(2)
  }
  const targets = fs
    .readFileSync(LIST_FILE, 'utf8')
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)

  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
  const page = await browser.newPage()

  // Sign in. As with the crawler, a URL change is not proof — confirm with the API, or an
  // unauthenticated probe would report 401 bodies as "verified shapes".
  await page.goto(`${BASE}/auth`, { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForSelector('input[type=email]', { timeout: 25000 })
  await sleep(800)
  await page.type('input[type=email]', EMAIL, { delay: 8 })
  const pwd = await page.$('input[type=password]')
  if (!pwd) { console.error('password field not found'); process.exit(2) }
  await pwd.type(PASSWORD, { delay: 8 })
  await page.click('button[type="submit"]')
  await sleep(8000)

  const who = await page
    .evaluate(async (origin) => {
      try {
        const r = await fetch(`${origin}/api/v1/auth/me`, { credentials: 'include' })
        return r.ok ? { ok: true, email: (await r.json()).email } : { ok: false, status: r.status }
      } catch (e) { return { ok: false, status: 0 } }
    }, API_ORIGIN)
    .catch(() => ({ ok: false, status: 0 }))

  if (!who.ok) {
    console.error(
      `\nABORT: not authenticated as ${EMAIL} — GET /api/v1/auth/me returned ${who.status}.\n` +
        '  Every probe would record a 401 body as a verified shape.\n' +
        '  Set DEMO_EMAIL / DEMO_PASSWORD for an account that exists.\n',
    )
    process.exit(2)
  }
  console.log(`signed in as ${who.email} (verified via /auth/me)`)
  console.log(`probing ${targets.length} read endpoint(s)\n`)

  const sigs = {}
  const failed = []

  for (const t of targets) {
    const r = await page
      .evaluate(
        async (origin, p) => {
          try {
            const res = await fetch(`${origin}/api/v1${p}`, { credentials: 'include' })
            const text = await res.text()
            let body = null
            try { body = JSON.parse(text) } catch { /* not json — nothing to audit */ }
            return { status: res.status, body }
          } catch (e) { return { status: 0, error: String(e.message || e).slice(0, 80) } }
        },
        API_ORIGIN,
        t,
      )
      .catch((e) => ({ status: 0, error: String(e.message || e).slice(0, 80) }))

    if (r.status >= 400 || r.status === 0) {
      failed.push(`${String(r.status).padStart(3)}  GET ${t}${r.error ? `  (${r.error})` : ''}`)
      continue
    }
    const sig = signature(t, 'GET', r.body)
    if (!sig.keys.length) {
      failed.push(`200  GET ${t}  (no JSON object keys — nothing to compare)`)
      continue
    }
    sigs[`${t}`] = [sig]
    console.log(`  200  GET ${t.padEnd(42)} ${sig.keys.length} keys${sig.itemKeys ? `, item ${sig.itemKeys.length}` : ''}`)
  }

  fs.mkdirSync(OUT, { recursive: true })

  // Merge with whatever the crawl already recorded, so one file feeds the audit.
  const merged = {}
  const existing = path.join(OUT, 'response_signatures.json')
  if (fs.existsSync(existing)) {
    try { Object.assign(merged, JSON.parse(fs.readFileSync(existing, 'utf8'))) } catch { /* start clean */ }
  }
  for (const [k, v] of Object.entries(sigs)) {
    const prev = (merged[k] || []).filter((s) => s.method !== 'GET')
    merged[k] = [...prev, ...v]
  }
  fs.writeFileSync(existing, JSON.stringify(merged, null, 1))

  console.log(`\nsignatures written : ${path.join(OUT, 'response_signatures.json')}`)
  console.log(`newly observed     : ${Object.keys(sigs).length}`)
  console.log(`could not be probed: ${failed.length}`)
  for (const f of failed) console.log(`  ${f}`)

  await browser.close()
  // Not an error: a 403 on an admin route for a non-admin is information, not a failed audit.
  process.exit(0)
})().catch((e) => {
  console.error('probe crashed:', e && e.message ? e.message : e)
  process.exit(1)
})