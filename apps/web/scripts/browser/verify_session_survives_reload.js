/**
 * The session-survival regression, driven through a real browser.
 *
 * `app/auth/page.tsx`'s submit handler used to clear `tm_auth_token` in a `finally` block,
 * which ran after a successful sign-in as well as a failed one — deleting the token
 * `signin()` had just written. `lib/auth-context.tsx` decides whether to restore a session on
 * load by looking for exactly that key, so every full page load bounced the user back to
 * /auth while every API call still returned 200.
 *
 * A unit test cannot show this: nothing throws, nothing 4xx's, and the cookie is valid
 * throughout. It is only visible as a rendered outcome — "log in, then load a fresh URL" —
 * so it is tested that way.
 *
 * Two wait strategies, deliberately different:
 *
 *   /auth  → networkidle2. The page is static once loaded, and `waitForSelector` alone is not
 *            enough: the input exists in the server-rendered HTML before React attaches its
 *            handlers, so typing into it does nothing and the run fails at the first check for
 *            reasons that have nothing to do with the bug.
 *   the app → domcontentloaded. Every authenticated page polls on an interval, so the network
 *            never reaches idle and `networkidle2` times out on a perfectly healthy page.
 *
 * Run:  node verify_session_survives_reload.js
 */
const puppeteer = require(process.env.PUPPETEER_CORE || 'puppeteer-core')

// 127.0.0.1, not localhost: cookies are host-scoped and the API sets its session cookie for the
// host it is called from, so a suite running against `localhost` cannot read a session the API
// minted for `127.0.0.1`. That mismatch fails the reload checks for a reason unrelated to what they
// test. Hard-coded rather than env-driven so the point of it is not configurable away.
const BASE = 'http://127.0.0.1:3000'
const API = process.env.API_ORIGIN || 'http://127.0.0.1:8000'
const EMAIL = process.env.DEMO_EMAIL || 'demo.trader@trademetrix.dev'
const PASSWORD = process.env.DEMO_PASSWORD || 'Demo@2026!'
const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const results = []
const check = (name, ok, detail) => {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}`)
  if (detail) console.log(`      ${detail}`)
}

;(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--window-size=1500,1000'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1500, height: 1000 })

  // ── sign in ───────────────────────────────────────────────────────────────
  await page.goto(`${BASE}/auth`, { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForSelector('input[type=email]', { timeout: 20000 })
  // Give hydration a moment to attach handlers; networkidle2 usually implies it, but a bare
  // selector match does not.
  await sleep(700)
  await page.type('input[type=email]', EMAIL, { delay: 10 })
  const pwd = await page.$('input[type=password]')
  if (!pwd) throw new Error('password input not found')
  await pwd.type(PASSWORD, { delay: 10 })
  await page.click('button[type="submit"]')
  await sleep(8000)

  check('sign-in lands away from /auth', !page.url().includes('/auth'), `url ${page.url()}`)

  // Landing away from /auth is not proof of authentication — the form redirects even when the API
  // rejects the credentials. This suite exists to prove the session survives a reload, which is
  // meaningless if there was never a session, so the check has to be a real one.
  const whoami = await page
    .evaluate(async (origin) => {
      try {
        const r = await fetch(`${origin}/api/v1/auth/me`, { credentials: 'include' })
        return r.ok ? { ok: true } : { ok: false, status: r.status }
      } catch (e) {
        return { ok: false, status: 0 }
      }
    }, API)
    .catch(() => ({ ok: false, status: 0 }))
  check('session is actually valid (GET /auth/me 200)', whoami.ok, `status ${whoami.status || 'no response'}`)
  if (!whoami.ok) {
    console.error(`ABORT: not authenticated as ${EMAIL} — set DEMO_EMAIL / DEMO_PASSWORD.\n`)
    process.exit(2)
  }

  const token = await page.evaluate(() => window.localStorage.getItem('tm_auth_token') || '')
  check(
    'tm_auth_token is persisted after sign-in',
    token.length > 20,
    `${token.length} chars in localStorage`,
  )

  // ── the regression: a full page load, not a client-side navigation ────────
  await page.goto(`${BASE}/paper`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await sleep(8000)
  check('session survives a full page load', !page.url().includes('/auth'), `url ${page.url()}`)

  const rowCount = await page.evaluate(() => document.querySelectorAll('table tbody tr').length)
  check(
    '/paper renders the seeded positions after a fresh load',
    rowCount >= 3,
    `${rowCount} table rows`,
  )

  // ── and a browser refresh, which is what a user actually does ─────────────
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 })
  await sleep(7000)
  check('session survives a browser refresh', !page.url().includes('/auth'), `url ${page.url()}`)

  // ── and a third page, to be sure it is not one route behaving ─────────────
  await page.goto(`${BASE}/funds`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await sleep(7000)
  check('session survives navigating to another page', !page.url().includes('/auth'), `url ${page.url()}`)

  await browser.close()

  const failed = results.filter((r) => !r.ok)
  console.log(`\n${'='.repeat(60)}`)
  console.log(`${results.length - failed.length}/${results.length} checks passed`)
  if (failed.length) {
    console.log('\nFAILED:')
    failed.forEach((f) => console.log(`  - ${f.name}: ${f.detail}`))
  }
  process.exit(failed.length ? 1 : 0)
})().catch((e) => {
  console.error('harness error:', e)
  process.exit(2)
})
