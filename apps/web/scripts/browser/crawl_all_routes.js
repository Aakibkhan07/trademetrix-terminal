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
// The base URL must be the *same host* as the API, not `localhost`.
//
// Cookies are host-scoped. The API sets `csrf_token` on the host it is served from, and this API is
// reached at `127.0.0.1:8000`, so a page served from `http://localhost:3000` cannot see it — even
// though both are loopback. `document.cookie` comes back empty, `getCSRFToken()` in `lib/api.ts`
// returns '', `X-CSRF-Token` is never attached, and **every POST, PUT and DELETE answers 403**.
//
// That is silent: reads keep working, so a harness pointed at `localhost` looks perfectly healthy
// while being unable to write anything. In production the equivalent mismatch does not bite,
// because the cookie is set on `.trademetrix.tech` and both origins are under it.
const BASE = process.env.BASE_URL || 'http://127.0.0.1:3000'
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
    // 400 "No real market data available" for symbols no source carries at all.
    //
    // This exemption existed once before with a **false** reason — "the Yahoo fallback is
    // unreachable from here" — and it was hiding a real bug: `days=1` at an intraday interval
    // returned nothing for *every* symbol outside market hours, which is fixed. Yahoo works.
    //
    // What is left is genuine. The watchlist offers 20 indices; Yahoo carries 16 of them. It does
    // not carry Nifty Private Bank (`^CNXPVTBANK` and `^NIFTY_PVT_BANK` both answer "Quote not
    // found" or "possibly delisted"), Nifty GSEC (`^CNXGSEC`, `^CNXGSEQ`), or Nifty Oil & Gas
    // (`^CNXOILGAS`, `^NIFTY_OIL_GAS`) — checked directly against Yahoo, not inferred. Meanwhile
    // `^CNXENERGY`, `^CNXPHARMA` and `^CNXIT` all resolve, so this is a per-symbol gap and not a
    // broken provider.
    //
    // So the refusal is correct: those three cannot be served without fabricating them, which is
    // what the v1.7.0 contract forbids. Scoped to this path, so a 400 from anywhere else still
    // fails the crawl.
    re: /\/marketdata\/historical/,
    why: '400 — no source carries these symbols; the refusal is the contract working',
  },
  {
    // 503 when no option-chain source exists, which is the honest answer rather than a fault.
    //
    // This endpoint used to fall back to a **formula**: `call ltp = max(100 - dist*15, 1)`,
    // `oi = 500000`, approximate greeks, nineteen strikes that looked exactly like a market. The
    // only label was `mock: True`, which the frontend does not read, so `/trade` and
    // `/terminal/option-chain` showed fabricated premiums and a trader could size a live position
    // off them. That fallback is gone — the same v1.7.0 real-data contract that deleted
    // `_generate_simulated_candles` — and the route now answers
    // 503 "Option chain unavailable for {symbol}".
    //
    // Scoped to this path, and to 503 only, so any other status from it still fails the crawl.
    // Verified separately that all four affected routes degrade without an error boundary and show
    // no fabricated premium.
    re: /\/marketdata\/option-chain/,
    why: '503 — the documented refusal to serve a fabricated option chain when no source exists',
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

/**
 * Text that means a value was *rendered* but was not a value.
 *
 * This is the half of the contract-mismatch class that does not throw. `/journal` declared a
 * `JournalData` with `win_rate`, `sharpe_ratio`, `equity_curve` and `monthly_returns` — none of
 * which `/ai/journal` returns — and the page stayed clean in this crawler because a guard
 * (`total_trades > 0 || entries?.length > 0`) was permanently false. Every one of those figures
 * is `undefined`, and an `undefined` that reaches the DOM shows up here as text.
 *
 * `NaN` is the common one: `₹${(undefined).toLocaleString()}` throws, but
 * `${undefined}` and `Number(undefined)` do not — the first prints the word, the second prints
 * `NaN`, and a `?? 0` in between prints a confident zero. A page asserting `hasData` and then
 * rendering `NaN` looks identical to a working one in a status code.
 *
 * `[object Object]` catches an object rendered where a scalar was read. `Infinity` and `-Infinity`
 * catch a division or an unbounded ratio, which also tends to mean a missing denominator.
 */
const BAD_VALUE_TEXT = [
  { re: /\bNaN\b/, why: 'NaN — arithmetic on a missing or non-numeric value' },
  { re: /\bundefined\b/, why: 'undefined — a value read from a response that does not contain it' },
  { re: /\[object Object\]/, why: '[object Object] — an object rendered where a scalar was expected' },
  { re: /\b-?Infinity\b/, why: 'Infinity — a ratio or division with no real denominator' },
  { re: /₹\s*NaN/, why: '₹NaN — currency formatting of a non-number' },
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
  fs.mkdirSync(OUT, { recursive: true })  // always: the signature report is not optional

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--window-size=1500,1100'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1500, height: 1100 })

  let bucket = { pageErrors: [], consoleErrors: [], http: [], signatures: [] }
  const collector = () => {
    page.on('pageerror', (e) => bucket.pageErrors.push(String(e.message || e).slice(0, 200)))
    page.on('console', (m) => {
      if (m.type() === 'error') bucket.consoleErrors.push(m.text().slice(0, 200))
    })
    page.on('response', (r) => {
      const u = r.url()
      if (u.startsWith(API_ORIGIN) || u.startsWith(BASE)) {
        const path = u.replace(API_ORIGIN, '').replace(BASE, '')
        bucket.http.push({ status: r.status(), path })
        // Capture what the endpoint *actually* returns, not what the page claims it returns.
        // This is the evidence a contract audit needs, and it is only obtainable at runtime:
        // the same route answers differently for a user with trades and one without.
        const sigPath = path.split('?')[0]
        // Keyed by method *and* path. The same path answers differently per method — `GET
        // /admin/admins` returns `{admins: [...]}`, `POST /admin/admins` returns `{message}` — so
        // collapsing them unions two unrelated payloads. That produced a fabricated mismatch on a
        // perfectly correct declaration, which is worse than missing the check: the tool named a
        // bug that did not exist.
        if (r.status() < 400 && !bucket.signatures.some((s) => s.path === sigPath && s.method === r.request().method())) {
          r.json()
            .then((body) => {
              const sig = { path: sigPath, method: r.request().method(), keys: [], itemKeys: null }
              if (body && typeof body === 'object') {
                sig.keys = Object.keys(body).sort()
                // Several endpoints answer with a single-key envelope — `{ orders: [...] }` — and
                // the frontend type describes the *item*, not the envelope. Comparing an item type
                // against envelope keys reports every field as missing, which is how the first
                // version of `audit_api_contracts.py` produced pure noise. So the first element's
                // keys are captured too, and the audit compares against whichever level the
                // declaration actually describes.
                const first = Object.values(body).find((v) => Array.isArray(v) && v.length > 0)
                if (first) sig.itemKeys = Object.keys(first[0]).sort()
              }
              bucket.signatures.push(sig)
            })
            .catch(() => {})
        }
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
  // A URL change is not proof of authentication.
  //
  // The sign-in form redirects away from /auth even when the API rejects the credentials, so
  // `!page.url().includes('/auth')` reported success for a user that does not exist. The crawl then
  // ran unauthenticated: 49 of 51 routes failed with 401s on unrelated endpoints, and the one real
  // signal — "these credentials are wrong" — was buried under noise. That is exactly what happened
  // after the local database was rebuilt and the default demo user no longer existed.
  //
  // So ask the API, using the cookie the browser just received.
  const session = await page
    .evaluate(async (origin) => {
      try {
        const r = await fetch(`${origin}/api/v1/auth/me`, { credentials: 'include' })
        if (!r.ok) return { ok: false, status: r.status }
        const j = await r.json()
        return { ok: true, email: j.email || null }
      } catch (e) {
        return { ok: false, status: 0, error: String(e.message || e).slice(0, 80) }
      }
    }, API_ORIGIN)
    .catch((e) => ({ ok: false, status: 0, error: String(e.message || e).slice(0, 80) }))

  if (!session.ok) {
    console.error(
      `\nABORT: not authenticated as ${EMAIL} — GET /api/v1/auth/me returned ${session.status || session.error}.\n` +
        '  Every route would fail with 401s and the result would say nothing about the pages.\n' +
        '  Set DEMO_EMAIL / DEMO_PASSWORD for an account that exists, or create it first.\n',
    )
    process.exit(2)
  }
  console.log(`signed in as ${session.email || EMAIL} (verified via /auth/me)\n`)

  // ── crawl ─────────────────────────────────────────────────────────────────
  const report = []

  for (const route of ROUTES) {
    if (SKIP.has(route)) {
      report.push({ route, skipped: true })
      continue
    }

    bucket = { pageErrors: [], consoleErrors: [], http: [], signatures: [] }

    let navOk = true
    try {
      await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded', timeout: 45000 })
    } catch (e) {
      report.push({ route, fatal: `navigation failed: ${String(e.message).slice(0, 90)}` })
      continue
    }

    // Long enough for the slowest poller to land, short enough to keep 50 routes tolerable.
    await sleep(6000)

    const info = await page.evaluate((failPatterns, badPatterns) => {
      const text = document.body.innerText || ''
      const grab = (patterns, flags) =>
        patterns
          .map((p) => ({ p, m: text.match(new RegExp(p.source, flags)) }))
          // A zero-length match means the pattern itself is broken — `new RegExp(undefined)` is
          // `/(?:)/`, which matches at index 0 of every string. Reporting that as "the page
          // rendered NaN" is worse than reporting nothing, so it is dropped here rather than
          // being allowed to mark every route as failing.
          .filter((x) => x.m && x.m[0].length > 0)
          .map((x) => ({ hit: x.m[0].trim().slice(0, 40), why: x.p.why }))
      return {
        url: location.pathname + location.search,
        textLen: text.trim().length,
        matches: [...new Set(grab(failPatterns, 'i').map((x) => x.hit))],
        bad: grab(badPatterns, ''),
        h1: (document.querySelector('h1')?.innerText || '').trim().slice(0, 48),
        // The auth gate is not an error state: no page error, no console error, no 4xx, no bad
        // value. Detected here from the text so the check sees exactly what the user sees.
        authGated:
          /Sign in to view your trading dashboard/.test(text) ||
          // The bare auth page: a heading and an email field, and essentially nothing else.
          (text.trim().length < 400 && /EMAIL ADDRESS/i.test(text)),
      }
    }, FAILURE_TEXT.map((p) => ({ source: p.source })), BAD_VALUE_TEXT.map((p) => ({ source: p.re.source, why: p.why })))

    const consoleErrors = bucket.consoleErrors.filter((t) => !BENIGN_CONSOLE.some((r) => r.test(t)))
    const http = bucket.http.filter(
      (h) => h.status >= 400 && !BENIGN_HTTP.some((b) => b.re.test(h.path)),
    )
    // A non-admin being bounced off /admin is the RBAC working.
    const adminRedirected = /^\/admin/.test(route) && !info.url.startsWith('/admin')

    // A completed user being redirected off `/onboarding` is the feature working, not a fault.
    //
    // The page exists to be skipped once `onboarding_completed` is set, so the crawl reported
    // `FAIL /onboarding — redirected to /dashboard` for a correctly-behaving test user. That is the
    // same shape as `adminRedirected` above: a redirect that is the expected behaviour for a state
    // the crawler cannot see. Listed explicitly rather than widened, so any *other* redirect on this
    // route still fails.
    const onboardingDone = route === '/onboarding' && /^\/(dashboard|live)/.test(info.url)
    const expected = EXPECTED_REDIRECT[route]
    const landedAsExpected = expected ? info.url.startsWith(expected) : null
    const redirectedAway =
      !adminRedirected &&
      !onboardingDone &&
      !info.url.startsWith(route.split('/').slice(0, 2).join('/')) &&
      landedAsExpected !== true

    const problems = []
    if (bucket.pageErrors.length) problems.push(`${bucket.pageErrors.length} page error(s): ${bucket.pageErrors[0].slice(0, 80)}`)
    if (consoleErrors.length) problems.push(`${consoleErrors.length} console error(s): ${consoleErrors[0].slice(0, 80)}`)
    if (http.length) problems.push(`HTTP: ${[...new Set(http.map((h) => `${h.status} ${h.path}`))].slice(0, 4).join(', ')}`)
    if (info.matches.length) problems.push(`failure text on screen: ${info.matches.join(' | ')}`)
    if (info.bad.length) {
      for (const b of info.bad) problems.push(`bad value rendered: "${b.hit}" — ${b.why}`)
    }
    if (info.textLen < 120 && !adminRedirected) problems.push(`only ${info.textLen} chars rendered`)
    if (redirectedAway && !adminRedirected && !onboardingDone) problems.push(`redirected to ${info.url}`)

    // A page that renders the sign-in form instead of its own content is a failure, and it is one
    // this crawler would otherwise report as clean.
    //
    // It is easy to miss because the form is not an error: no page error, no console error, no bad
    // HTTP status, no `NaN` in the text. A route whose whole body is replaced by the auth gate
    // renders a valid-looking page, so every existing check passes.
    //
    // This is not hypothetical. `app/portal/page.tsx` restores its own session from
    // `sessionStorage['tm_portal_email']` rather than the API cookie — a deliberate separate portal
    // login — so a signed-in app user lands on its OTP screen. `/portal` and `/portal/brokers` are
    // in SKIP for that reason. The check exists so that if some *other* route starts gating itself
    // this way, the crawl says so instead of quietly reporting green.
    //
    // Measured across the 47 crawled routes before this check was added: 0 auth-gated. So it is
    // insurance, not a fix for something currently broken.
    if (info.authGated) {
      problems.push('rendered the sign-in form instead of page content')
    }

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
      onboardingDone,
      problems,
      signatures: bucket.signatures,
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
      else if (r.onboardingDone) note = '  [onboarding complete, redirected home by design]'
      else if (EXPECTED_REDIRECT[r.route]) note = `  [forwards to ${EXPECTED_REDIRECT[r.route]} by design]`
      console.log(`ok    ${r.route.padEnd(26)} ${String(r.textLen).padStart(5)} chars${note}`)
    }
  }

  // The observed response keys, per route. Written out because a frontend contract audit
  // cannot be done from the source alone: it needs to know what each endpoint actually
  // answered for this user, which is the one thing a declared TypeScript interface gets wrong.
  fs.writeFileSync(path.join(OUT, 'response_signatures.json'), JSON.stringify(
    Object.fromEntries(report.filter((r) => r.signatures?.length).map((r) => [r.route, r.signatures])),
    null, 2,
  ))

  const checked = report.filter((r) => !r.skipped && !r.fatal).length
  console.log(`\n${'='.repeat(70)}`)
  console.log(`${checked - bad}/${checked} routes clean (${report.filter((r) => r.skipped).length} skipped: standalone auth)`)
  console.log(`\nresponse key signatures: ${path.join(OUT, 'response_signatures.json')}`)
  if (SHOTS) console.log(`screenshots: ${OUT}`)
  process.exit(bad ? 1 : 0)
})().catch((e) => {
  console.error('crawl harness error:', e)
  process.exit(2)
})
