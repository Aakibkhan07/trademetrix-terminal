/**
 * Browser verification of the local demo stack — session behaviour and the three money-page
 * rendering fixes, in one run.
 *
 * This exists because every one of those fixes was invisible to the tooling that had been
 * available. `curl` against the API proves the endpoint returns what the code expects; a
 * TypeScript assertion proves the helper computes the right number. Neither proves the browser
 * paints it. And two of the bugs found this way could not have been found any other way:
 *
 *   1. **The session did not survive a page load.** `app/auth/page.tsx`'s `finally` block
 *      cleared `tm_auth_token` after a *successful* sign-in, and
 *      `lib/auth-context.tsx` gates session restore on that key. Nothing throws, nothing 4xx's,
 *      and the httponly cookie is valid throughout — every API call returned 200 while the app
 *      sat on /auth. Only a rendered outcome shows it.
 *   2. **The CSP made local development impossible.** `next.config.js` omitted
 *      `'unsafe-eval'`, which the dev runtime needs, so hydration threw, the client bundle
 *      never took over, and pages sat on skeleton loaders making *zero* network requests. It
 *      reads as a data-loading bug and is not one.
 *
 * Wait strategy, and it is not uniform on purpose:
 *
 *   /auth → `networkidle2`, plus a short settle. `waitForSelector` alone is not enough — the
 *           email input is in the server-rendered HTML before React attaches its handlers, so
 *           typing into it silently does nothing and the run fails at the first check for
 *           reasons unrelated to what is being tested.
 *   app   → `domcontentloaded`. Every authenticated page polls on an interval, so the network
 *           never goes idle and `networkidle2` times out against a perfectly healthy page.
 *
 * Colour is judged by hue, not by hex: `--text-green` is `#34d399` in dark and `#0f7a5a` in
 * light, and the theme depends on localStorage, so `getComputedStyle` is read and the green
 * and red channels compared. Green has g > r in both themes.
 *
 * Run:  node verify_local_demo.js
 */
const puppeteer = require(process.env.PUPPETEER_CORE || 'puppeteer-core')
const fs = require('fs')

const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = 'http://localhost:3000'
const API = 'http://127.0.0.1:8000/api/v1'
const EMAIL = process.env.DEMO_EMAIL || 'demo.trader@trademetrix.dev'
const PASSWORD = process.env.DEMO_PASSWORD || 'Demo@2026!'
const OUT = '/tmp/local_demo_shots'

const results = []
const check = (name, ok, detail) => {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}`)
  if (detail) console.log(`      ${detail}`)
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const hue = (css) => {
  const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(css || '')
  return m ? { r: Number(m[1]), g: Number(m[2]), b: Number(m[3]) } : null
}

;(async () => {
  fs.mkdirSync(OUT, { recursive: true })
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--window-size=1500,1100'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1500, height: 1100 })

  const pageErrors = []
  const consoleErrors = []
  const badResponses = []
  page.on('pageerror', (e) => pageErrors.push(String(e.message || e).slice(0, 160)))
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 160))
  })
  page.on('response', (r) => {
    if (r.status() >= 400) badResponses.push(`${r.status()} ${r.url().replace(API, '').replace(BASE, '')}`)
  })

  // ── sign in ───────────────────────────────────────────────────────────────
  await page.goto(`${BASE}/auth`, { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForSelector('input[type=email]', { timeout: 25000 })
  await sleep(800)
  await page.type('input[type=email]', EMAIL, { delay: 10 })
  const pwd = await page.$('input[type=password]')
  if (!pwd) throw new Error('password input not found — is /auth on the Password tab?')
  await pwd.type(PASSWORD, { delay: 10 })
  await page.click('button[type="submit"]')
  await sleep(8000)

  check('sign-in lands away from /auth', !page.url().includes('/auth'), `url ${page.url()}`)

  const storedToken = await page.evaluate(() => window.localStorage.getItem('tm_auth_token') || '')
  check(
    'tm_auth_token is persisted after sign-in',
    storedToken.length > 20,
    `${storedToken.length} chars in localStorage`,
  )

  // ── the session regression, twice over ────────────────────────────────────
  await page.goto(`${BASE}/paper`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await sleep(8000)
  check('session survives a full page load', !page.url().includes('/auth'), `url ${page.url()}`)

  await page.screenshot({ path: `${OUT}/paper.png`, fullPage: true })

  const rowCount = await page.evaluate(() => document.querySelectorAll('table tbody tr').length)
  check('/paper renders the seeded positions', rowCount >= 3, `${rowCount} table rows`)

  // ── /paper: the side colour and the short P&L ─────────────────────────────
  const table = await page.evaluate(() => {
    const headers = [...document.querySelectorAll('table thead th')].map((th) => (th.innerText || '').trim())
    const rows = [...document.querySelectorAll('table tbody tr')].map((tr) =>
      [...tr.querySelectorAll('td')].map((td) => ({
        text: (td.innerText || '').trim(),
        colour: getComputedStyle(td).color,
      })),
    )
    return { headers, rows }
  })

  const sideIdx = table.headers.findIndex((h) => /side/i.test(h))
  const pnlIdx = table.headers.findIndex((h) => /p&l|pnl|unreal/i.test(h))
  check('/paper exposes a Side and a P&L column', sideIdx >= 0 && pnlIdx >= 0, `headers: ${table.headers.join(' | ')}`)

  const rowFor = (sym) => table.rows.find((r) => r.some((c) => c.text.includes(sym)))

  const longRow = rowFor('NIFTY50-INDEX')
  if (longRow && sideIdx >= 0) {
    const cell = longRow[sideIdx]
    const h = hue(cell.colour)
    check(
      '/paper renders a LONG position in green, not red',
      Boolean(h && h.g > h.r),
      `text ${JSON.stringify(cell.text)} colour ${cell.colour} (r=${h?.r} g=${h?.g})`,
    )
  }

  const shortRow = rowFor('BANKNIFTY-INDEX')
  if (shortRow && pnlIdx >= 0) {
    const cell = shortRow[pnlIdx]
    const n = Number(cell.text.replace(/[^0-9.\-]/g, ''))
    check(
      '/paper renders a profitable SHORT as a positive P&L',
      Number.isFinite(n) && n > 0,
      `rendered ${JSON.stringify(cell.text)}`,
    )
    check(
      '/paper SHORT is not the old formula\'s six-figure loss',
      !(Number.isFinite(n) && n < -100000),
      `the long-only formula gave -610,200 on this data; rendered ${n}`,
    )
  }

  const losingShort = rowFor('FINNIFTY-INDEX')
  if (losingShort && pnlIdx >= 0) {
    const n = Number(losingShort[pnlIdx].text.replace(/[^0-9.\-]/g, ''))
    check(
      '/paper renders a LOSING short as negative — the sign flip works both ways',
      Number.isFinite(n) && n < 0,
      `rendered ${JSON.stringify(losingShort[pnlIdx].text)}`,
    )
  }

  // ── refresh, which is what a user actually does ───────────────────────────
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 })
  await sleep(7000)
  check('session survives a browser refresh', !page.url().includes('/auth'), `url ${page.url()}`)

  // ── /funds ────────────────────────────────────────────────────────────────
  await page.goto(`${BASE}/funds`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await sleep(7000)
  await page.screenshot({ path: `${OUT}/funds.png`, fullPage: true })

  const funds = await page.evaluate(() => {
    const body = document.body.innerText
    const after = (label) => {
      const i = body.indexOf(label)
      if (i < 0) return null
      return body.slice(i + label.length, i + label.length + 40).trim().split('\n').filter(Boolean)[0] || null
    }
    return {
      noBrokerCta: /No broker connected/i.test(body),
      hasMargin: /500,?000/.test(body),
      today: after('TODAY (REALIZED)'),
      realized: after('REALIZED'),
      unrealized: after('UNREALIZED'),
      bodyLen: body.length,
    }
  })

  check('/funds is past the "no broker connected" state', !funds.noBrokerCta, 'the PAPER run resolves a PaperBroker')
  check('/funds renders a margin figure', funds.hasMargin, 'expected the 500,000 paper margin')
  check(
    '/funds cumulative tiles are not a fabricated zero',
    !/^[\s₹]*0(\.0+)?$/.test(String(funds.realized).trim()) &&
      !/^[\s₹]*0(\.0+)?$/.test(String(funds.unrealized).trim()),
    `REALIZED=${JSON.stringify(funds.realized)} UNREALIZED=${JSON.stringify(funds.unrealized)} (a dash is correct here: no live broker means no PortfolioPnL)`,
  )

  // ── /terminal and /portal: the same long-only formula lived there too ─────
  for (const route of ['terminal', 'portal']) {
    await page.goto(`${BASE}/${route}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await sleep(7000)
    await page.screenshot({ path: `${OUT}/${route}.png`, fullPage: true })
    const text = await page.evaluate(() => document.body.innerText)
    check(`/${route} renders content`, text.length > 300, `${text.length} chars of body text`)
    check(
      `/${route} shows no fabricated six-figure loss`,
      !/-6[0-9]{2},[0-9]{3}/.test(text) && !/-4[0-9]{2},[0-9]{3}/.test(text),
      'the old formula produced -610,200 and -471,200 on this data',
    )
  }

  // ── hygiene ───────────────────────────────────────────────────────────────
  // The analytics beacon posts through `sendBeacon`, which cannot carry the CSRF header, so
  // `track-batch` answering 403 is a documented limitation rather than a regression.
  const realConsole = consoleErrors.filter(
    (t) => !/401|Unauthorized|auth\/me|Failed to load resource|WebSocket connection|startFeed|not authenticated/i.test(t),
  )
  const realHttp = badResponses.filter((r) => !/\/auth\/me|track-batch|marketdata\/ws/i.test(r))

  check('no uncaught page errors', pageErrors.length === 0, pageErrors.length ? pageErrors.slice(0, 3).join(' ; ') : 'none')
  check('no console errors (auth 401s, WS and the beacon filtered)', realConsole.length === 0, realConsole.length ? realConsole.slice(0, 3).join(' ; ') : 'none')
  check('no unexpected HTTP >= 400', realHttp.length === 0, realHttp.length ? realHttp.slice(0, 6).join(' ; ') : 'none')

  await browser.close()

  const failed = results.filter((r) => !r.ok)
  console.log(`\n${'='.repeat(66)}`)
  console.log(`${results.length - failed.length}/${results.length} checks passed`)
  console.log(`screenshots: ${OUT}`)
  if (failed.length) {
    console.log('\nFAILED:')
    failed.forEach((f) => console.log(`  - ${f.name}${f.detail ? `: ${f.detail}` : ''}`))
  }
  process.exit(failed.length ? 1 : 0)
})().catch((e) => {
  console.error('harness error:', e)
  process.exit(2)
})
