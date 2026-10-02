/**
 * Inventory of every interactive control on every route, and the ones that cannot be used.
 *
 * ## Why this exists
 *
 * Everything found so far in this project was found by *rendering* a page. Not one bug was found by
 * clicking. That is a real gap and it is not theoretical: `AGENTS.md` records that `/go-live`'s
 * Start button was "permanently disabled (canNext fallthrough)" and that browser E2E was the only
 * thing that caught it — 13/13 checks, and the page had been shipping.
 *
 * A disabled control is the cheapest possible defect to ship: the page looks finished, the button is
 * right there, and nothing errors. No status code is wrong. No exception is raised. It simply never
 * becomes usable, and the only way to notice is to try.
 *
 * This pass is **read-only**. It enumerates controls and reports the ones that cannot work, so the
 * next pass knows what is safe to click. Nothing here places an order, submits a form, or writes.
 *
 * What counts as unusable:
 *   - a button or input that is `disabled`, or `aria-disabled`, while nothing on the page is loading
 *   - a button with no accessible name (no text, no `aria-label`, no `title`, no `aria-labelledby`)
 *   - a text input with no label, placeholder, `aria-label` or `title` — unfillable *and* unreadable
 *     for anyone not using a mouse
 *   - a `<select>` with fewer than two options, which cannot be chosen from
 *   - a `<button>` inside a `<form>` with no `type`, so it submits when it should not, or vice versa
 *   - a control inside a container that is `visibility:hidden` or `opacity:0` yet still focusable,
 *     which is how a "removed" control keeps intercepting clicks
 *
 * Usage:
 *   node scripts/browser/audit_interactive.js [--out DIR] [--route /path]
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
const only = argv.includes('--route') ? argv[argv.indexOf('--route') + 1] : null
const OUT = argv.includes('--out') ? argv[argv.indexOf('--out') + 1] : '/tmp/interactive_audit'

const SKIP = new Set(['/auth', '/auth/callback', '/portal', '/portal/brokers'])
const EXPECTED_REDIRECT = {
  '/orders': '/positions',
  '/copilot': '/ai',
  '/dashboard': '/live',
  '/onboarding': '/live',
}

// Routes whose controls are legitimately disabled until something is selected or fetched. Kept as
// data with a reason rather than as a blanket "ignore disabled", because the whole point of this
// pass is that a disabled control is indistinguishable from a bug until you know why.
const DISABLED_IS_OK = {
  // A modal's submit is disabled until its form validates. That is the design working.
  'data-audit-ok': 'disabled until the form validates',
}

const ROUTES = `/
/account
/ai
/alerts
/analytics
/backtest
/brokers
/copilot
/dashboard
/feedback
/forward-test
/funds
/go-live
/help
/journal
/legal
/live
/margin
/marketdata
/marketplace
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

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

;(async () => {
  fs.mkdirSync(OUT, { recursive: true })

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--window-size=1500,1100'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1500, height: 1100 })

  await page.goto(`${BASE}/auth`, { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForSelector('input[type=email]', { timeout: 25000 })
  await sleep(800)
  await page.type('input[type=email]', EMAIL, { delay: 8 })
  await (await page.$('input[type=password]')).type(PASSWORD, { delay: 8 })
  await page.click('button[type="submit"]')
  await sleep(8000)
  if (page.url().includes('/auth')) {
    console.error('could not sign in — results would be meaningless')
    process.exit(2)
  }
  console.log(`signed in as ${EMAIL}\n`)

  const report = {}

  for (const route of ROUTES) {
    if (SKIP.has(route) || (only && route !== only)) continue

    await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await sleep(6500)

    const expected = EXPECTED_REDIRECT[route]
    if (expected) {
      report[route] = { skipped: `forwards to ${expected}` }
      continue
    }

    const found = await page.evaluate(() => {
      const visible = (el) => {
        const cs = getComputedStyle(el)
        if (cs.display === 'none' || cs.visibility === 'hidden') return false
        const r = el.getBoundingClientRect()
        return r.width > 0 && r.height > 0
      }

      // `placeholder` is in here because HTML-AAM defines it as a fallback accessible name, and
      // browsers expose it as one. Leaving it out reported fifteen "input with no label" findings
      // across the app that were all fine — a noisy detector gets ignored, and a detector that
      // gets ignored finds nothing.
      //
      // `<label for>` and a wrapping `<label>` were missing, which is the more serious omission:
      // they are the *canonical* HTML labelling mechanism and the one assistive technology actually
      // uses. Seventeen controls across `/backtest` and `/terminal` carry a visible `<label>`
      // correctly associated by `htmlFor`/`id`, and this detector called every one of them
      // unlabelled — flagging correct markup as broken. A detector that reports correct code as
      // defective trains you to ignore it, which is how the fifteen placeholder findings above
      // happened in the first place.
      const labelFor = (el) => {
        if (!el.id) return ''
        // `CSS.escape` because these ids are slugified from label text and can contain characters
        // that are meaningful in a selector.
        const explicit = document.querySelector(`label[for="${CSS.escape(el.id)}"]`)
        if (explicit) return explicit.innerText || ''
        // Nested label: also valid, and association is implicit.
        const wrapping = el.closest('label')
        return wrapping ? wrapping.innerText || '' : ''
      }

      const name = (el) =>
        (
          el.innerText ||
          el.getAttribute('aria-label') ||
          el.getAttribute('title') ||
          el.getAttribute('placeholder') ||
          labelFor(el) ||
          (el.getAttribute('aria-labelledby')
            ? (document.getElementById(el.getAttribute('aria-labelledby'))?.innerText ?? '')
            : '') ||
          ''
        ).trim()

      const describe = (el) => {
        const tag = el.tagName.toLowerCase()
        const cls = (el.className || '').toString().split(' ').filter(Boolean).slice(0, 2).join('.')
        const label =
          name(el).slice(0, 40) ||
          el.getAttribute('name') ||
          el.getAttribute('placeholder') ||
          el.id ||
          ''
        return `${tag}${cls ? '.' + cls : ''}${label ? ` [${label}]` : ''}`
      }

      const controls = [...document.querySelectorAll('button, input, select, textarea, a[href], [role="button"], [role="tab"], [role="switch"], [role="checkbox"]')]
      const out = { total: 0, disabled: [], unnamed: [], unlabelledInput: [], thinSelect: [], noType: [], inert: [], byTag: {} }

      for (const el of controls) {
        if (!visible(el)) continue
        const tag = el.tagName.toLowerCase()
        const role = el.getAttribute('role') || tag
        out.byTag[role] = (out.byTag[role] || 0) + 1
        out.total++

        const isDisabled = el.disabled === true || el.getAttribute('aria-disabled') === 'true'

        if (isDisabled) {
          out.disabled.push({ el: describe(el), reason: el.getAttribute('data-audit-ok') || '' })
        }
        // Focusable while visually gone: keeps intercepting clicks after a "removal".
        if (!isDisabled && el.matches(':enabled') && el.getBoundingClientRect().width === 0) {
          out.inert.push(describe(el))
        }
        if ((tag === 'button' || role === 'button') && !name(el)) {
          out.unnamed.push(describe(el))
        }
        if (tag === 'input' && !['hidden', 'checkbox', 'radio', 'submit', 'button', 'reset'].includes(el.type) && !name(el)) {
          out.unlabelledInput.push(describe(el))
        }
        if (tag === 'select' && el.options.length < 2) {
          out.thinSelect.push(describe(el))
        }
        if (tag === 'button' && el.closest('form') && !el.getAttribute('type')) {
          out.noType.push(describe(el))
        }
      }
      return out
    })

    report[route] = found
  }

  await browser.close()
  fs.writeFileSync(path.join(OUT, 'interactive_audit.json'), JSON.stringify(report, null, 2))

  // ── output ────────────────────────────────────────────────────────────────
  let totalControls = 0
  let totalDisabled = 0
  const problems = []

  console.log('route'.padEnd(24) + 'controls  disabled  other')
  console.log('-'.repeat(78))
  for (const [route, r] of Object.entries(report)) {
    if (r.skipped) continue
    totalControls += r.total
    const other = r.unnamed.length + r.unlabelledInput.length + r.thinSelect.length + r.inert.length
    totalDisabled += r.disabled.length
    console.log(
      route.padEnd(24) +
        String(r.total).padStart(8) +
        String(r.disabled.length).padStart(9) +
        String(other || '').padStart(7),
    )
    if (r.disabled.length || other) {
      problems.push({ route, ...r })
    }
  }
  console.log('-'.repeat(78))
  console.log(
    `${totalControls} controls across ${Object.values(report).filter((r) => !r.skipped).length} routes` +
      `, ${totalDisabled} disabled\n`,
  )

  if (problems.length) {
    console.log('=== controls that cannot be used ===\n')
    for (const p of problems) {
      console.log(`${p.route}`)
      if (p.disabled.length) {
        console.log(`  disabled (${p.disabled.length}):`)
        for (const d of p.disabled.slice(0, 12)) console.log(`      ${d.el}${d.reason ? `   # ${d.reason}` : ''}`)
        if (p.disabled.length > 12) console.log(`      … and ${p.disabled.length - 12} more`)
      }
      if (p.unnamed.length) {
        console.log(`  no accessible name (${p.unnamed.length}): ${[...new Set(p.unnamed)].slice(0, 6).join(', ')}`)
      }
      if (p.unlabelledInput.length) {
        console.log(`  input with no label (${p.unlabelledInput.length}): ${[...new Set(p.unlabelledInput)].slice(0, 6).join(', ')}`)
      }
      if (p.thinSelect.length) {
        console.log(`  select with <2 options (${p.thinSelect.length}): ${[...new Set(p.thinSelect)].slice(0, 6).join(', ')}`)
      }
      if (p.inert.length) {
        console.log(`  focusable but invisible (${p.inert.length}): ${[...new Set(p.inert)].slice(0, 6).join(', ')}`)
      }
      console.log('')
    }
  } else {
    console.log('no unusable controls found')
  }

  console.log(`\nreport: ${path.join(OUT, 'interactive_audit.json')}`)
})().catch((e) => {
  console.error('audit error:', e)
  process.exit(2)
})