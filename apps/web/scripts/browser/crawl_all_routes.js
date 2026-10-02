/**
 * Crawls every route the app defines and reports what actually breaks.
 *
 * The existing tooling could answer "does the endpoint return the right shape" and "does the
 * helper compute the right number". Neither answers "does this page work". Three of the bugs
 * fixed in this batch were invisible to both: a session that died on every page load, a CSP
 * that stopped hydration before a single request was made, and a data hook that never
 * resolved. All three presented as a page that rendered *something* and was quietly wrong.
 *
 * What counts as a failure, per route:
 *   - an uncaught page error
 *   - a console error that is not on the known-benign list
 *   - an unexpected HTTP >= 400
 *   - rendered text that matches an error boundary or a "Failed to load" message
 *   - a suspiciously short body, which is what a blanked-out tree looks like
 *
 * Known-benign, each with the reason it is excluded rather than a blanket filter:
 *   /auth/me            401 — the anonymous pre-login probe; also polled after sign-out
 *   /analytics/track-batch 403 — posted via sendBeacon, which cannot carry the CSRF header
 *   /marketdata/ws      403 — the WebSocket handshake fails in this local setup
 *
 * Admin routes redirect a non-admin to /live, which is correct rather than broken, so a
 * redirect off an /admin path is recorded as expected.
 *
 * Usage:
 *   node scripts/browser/crawl_all_routes.js [--shots] [--out DIR]
 */
const puppeteer = require(process.env.PUPPETEER_CORE || 'puppeteer-core')
const fs = require('fs')
const path = require('path')

const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.BASE_URL || 'http://localhost:3000'
const API_ORIGIN = process.env.API_ORIGIN || 'http://127.0.0.1:8000'
const EMAIL = process.env.DEMO_EMAIL || 'demo.trader@trademetrix.dev'
const PASSWORD = process.env.DEMO_PASSWORD || 'Demo@2026!'

const argv = process.argv.slice(2)
const SHOTS = argv.includes('--shots')
const OUT = (() => {
  const i = argv.indexOf('--out')
  return i >= 0 && argv[i + 1] ? argv[i + 1] : '/tmp/route_crawl'
})()

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const BENIGN_HTTP = [
  { re: /\/auth\/me/, why: '401 — anonymous pre-login probe, also polled after sign-out' },
  { re: /\/analytics\/track-batch/, why: '403 — sendBeacon cannot carry the CSRF header (AGENTS.md)' },
  { re: /\/marketdata\/ws/, why: '403 — WebSocket handshake fails in this local setup' },
  {
    // Narrowly scoped on purpose. This endpoint answers 400 by design when it cannot get real
    // candles — "No real market data available … backtests never run on fabricated candles" —
    // which is the v1.7.0 honesty contract working, not a fault. Locally there is no data
    // source at all: no broker token, and the Yahoo fallback is unreachable from here.
    //
    // Scoped to this path rather than to 400s generally, so a genuine 400 anywhere else still
    // fails the crawl. Verified separately that `/workspace` absorbs it: no raw error string
    // reaches the page and its error boundary is not triggered.
    re: /\/marketdata\/historical/,
    why: '400 — the documented refusal to serve fabricated candles when no data source exists',
  },
]
const BENIGN_CONSOLE = [
  /Failed to load resource/i,
  /401|Unauthorized/i,
  /WebSocket connection to/i,
  /startFeed|not authenticated/i,
  /ERR_CONNECTION_REFUSED/i,
]

// Text that means the page gave up rather than rendered.
const FAILURE_TEXT = [
  /Failed to load/i,
  /Something went wrong/i,
  /Application error/i,
  /This page could not be found/i,
  /Internal Server Error/i,
  /Unexpected Application Error/i,
]

const ROUTES = `/
/account
/admin
/admin/admins
/admin/beta
/admin/broadcast
/ai
/alerts
/analytics
/backtest
/brokers
/changelog
/copilot
/dashboard
/feedback
/forward-test
/funds
/go-live
/help
/journal
/legal
/legal/disclaimer
/legal/privacy
/legal/refund
/legal/risk-disclosure
/legal/terms
/live
/margin
/marketdata
/marketplace
/onboarding
/orders
/paper
/portfolio
/positions
/pricing
/reports/daily
/risk
/settings
/status
/strategies
/strategies/builder
/strategies/catalog
/strategies/multi-leg
/terminal
/terminal/builder
/terminal/option-chain
/trade
/transparency
/visual-builder
/workspace`.split(/\s+/).filter(Boolean)

// Standalone pages render their own auth UI and are covered by their own flow.
const SKIP = new Set(['/auth', '/auth/callback', '/portal', '/portal/brokers'])

// Routes that deliberately forward elsewhere. Recorded rather than guessed, because the first
// crawl reported three of these as failures and they are not: `/orders` was moved to
// `/positions`, `/copilot` to `/ai`, and `/dashboard` bounces a non-admin to `/live`. The RBAC
// bounce is the guard working, so a redirect is the expected outcome, not a fault.
const EXPECTED_REDIRECT = {
  '/orders': '/positions',
  '/copilot': '/ai',
  '/dashboard': '/live',
  // The completed-onboarding guard. A first visit stays put and flips the flag; every visit
  // after that forwards to /live, which is the guard working rather than a fault. Verified by
  // resetting `onboarding_completed` to false and visiting as a new user: the page held.
  '/onboarding': '/live',
}

;(async () => {
  if (SHOTS) fs.mkdirSync(OUT, { recursive: true })

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--window-size=1500,1100'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1500, height: 1100 })

  let bucket = { pageErrors: [], consoleErrors: [], http: [] }
  const collector = () => {
    page.on('pageerror', (e) => bucket.pageErrors.push(String(e.message || e).slice(0, 200)))
    page.on('console', (m) => {
      if (m.type() === 'error') bucket.consoleErrors.push(m.text().slice(0, 200))
    })
    page.on('response', (r) => {
      const u = r.url()
      if (u.startsWith(API_ORIGIN) || u.startsWith(BASE)) {
        bucket.http.push({ status: r.status(), path: u.replace(API_ORIGIN, '').replace(BASE, '') })
      }
    })
  }
  collector()

  // ── sign in ───────────────────────────────────────────────────────────────
  await page.goto(`${BASE}/auth`, { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForSelector('input[type=email]', { timeout: 25000 })
  await sleep(800)
  await page.type('input[type=email]', EMAIL, { delay: 8 })
  const pwd = await page.$('input[type=password]')
  if (!pwd) {
    console.error('could not find the password field — cannot sign in')
    process.exit(2)
  }
  await pwd.type(PASSWORD, { delay: 8 })
  await page.click('button[type="submit"]')
  await sleep(8000)
  const signedIn = !page.url().includes('/auth')
  console.log(signedIn ? `signed in as ${EMAIL}\n` : `NOT signed in (${page.url()}) — results will be unreliable\n`)

  // ── crawl ─────────────────────────────────────────────────────────────────
  const report = []

  for (const route of ROUTES) {
    if (SKIP.has(route)) {
      report.push({ route, skipped: true })
      continue
    }

    bucket = { pageErrors: [], consoleErrors: [], http: [] }

    let navOk = true
    try {
      await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded', timeout: 45000 })
    } catch (e) {
      report.push({ route, fatal: `navigation failed: ${String(e.message).slice(0, 90)}` })
      continue
    }

    // Long enough for the slowest poller to land, short enough to keep 50 routes tolerable.
    await sleep(6000)

    const info = await page.evaluate((failPatterns) => {
      const text = document.body.innerText || ''
      const matches = failPatterns
        .map((p) => ({ p, m: text.match(new RegExp(p.source, 'i')) }))
        .filter((x) => x.m)
        .map((x) => x.m[0].trim().slice(0, 60))
      return {
        url: location.pathname + location.search,
        textLen: text.trim().length,
        matches: [...new Set(matches)],
        h1: (document.querySelector('h1')?.innerText || '').trim().slice(0, 48),
      }
    }, FAILURE_TEXT.map((p) => ({ source: p.source })))

    const consoleErrors = bucket.consoleErrors.filter((t) => !BENIGN_CONSOLE.some((r) => r.test(t)))
    const http = bucket.http.filter(
      (h) => h.status >= 400 && !BENIGN_HTTP.some((b) => b.re.test(h.path)),
    )
    // A non-admin being bounced off /admin is the RBAC working.
    const adminRedirected = /^\/admin/.test(route) && !info.url.startsWith('/admin')
    const expected = EXPECTED_REDIRECT[route]
    const landedAsExpected = expected ? info.url.startsWith(expected) : null
    const redirectedAway =
      !adminRedirected &&
      !info.url.startsWith(route.split('/').slice(0, 2).join('/')) &&
      landedAsExpected !== true

    const problems = []
    if (bucket.pageErrors.length) problems.push(`${bucket.pageErrors.length} page error(s): ${bucket.pageErrors[0].slice(0, 80)}`)
    if (consoleErrors.length) problems.push(`${consoleErrors.length} console error(s): ${consoleErrors[0].slice(0, 80)}`)
    if (http.length) problems.push(`HTTP: ${[...new Set(http.map((h) => `${h.status} ${h.path}`))].slice(0, 4).join(', ')}`)
    if (info.matches.length) problems.push(`failure text on screen: ${info.matches.join(' | ')}`)
    if (info.textLen < 120 && !adminRedirected) problems.push(`only ${info.textLen} chars rendered`)
    if (redirectedAway && !adminRedirected) problems.push(`redirected to ${info.url}`)

    if (SHOTS && (problems.length || info.textLen < 200)) {
      const name = route === '/' ? 'root' : route.replace(/\//g, '_').replace(/^_/, '')
      await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true }).catch(() => {})
    }

    report.push({
      route,
      finalPath: info.url,
      textLen: info.textLen,
      h1: info.h1,
      adminRedirected,
      problems,
    })
  }

  await browser.close()

  // ── output ────────────────────────────────────────────────────────────────
  let bad = 0
  for (const r of report) {
    if (r.skipped) {
      console.log(`SKIP  ${r.route}`)
      continue
    }
    if (r.fatal) {
      bad++
      console.log(`FAIL  ${r.route}  — ${r.fatal}`)
      continue
    }
    if (r.problems.length) {
      bad++
      console.log(`FAIL  ${r.route}  (${r.textLen} chars${r.h1 ? `, "${r.h1}"` : ''})`)
      r.problems.forEach((p) => console.log(`        ${p}`))
    } else {
      let note = ''
      if (r.adminRedirected) note = '  [admin route, non-admin bounced — RBAC working]'
      else if (EXPECTED_REDIRECT[r.route]) note = `  [forwards to ${EXPECTED_REDIRECT[r.route]} by design]`
      console.log(`ok    ${r.route.padEnd(26)} ${String(r.textLen).padStart(5)} chars${note}`)
    }
  }

  const checked = report.filter((r) => !r.skipped && !r.fatal).length
  console.log(`\n${'='.repeat(70)}`)
  console.log(`${checked - bad}/${checked} routes clean (${report.filter((r) => r.skipped).length} skipped: standalone auth)`)
  if (SHOTS) console.log(`screenshots: ${OUT}`)
  process.exit(bad ? 1 : 0)
})().catch((e) => {
  console.error('crawl harness error:', e)
  process.exit(2)
})
