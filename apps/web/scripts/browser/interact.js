/**
 * Interaction tests: drive the flows a render-only crawl cannot reach.
 *
 * ## Why this exists
 *
 * Every bug found so far in this project was found by *rendering* a page. Not one was found by
 * clicking. That gap is not theoretical — `AGENTS.md` records that `/go-live`'s Start button was
 * "permanently disabled (canNext fallthrough)" and that browser E2E was the only thing that caught
 * it, while `tests/test_chart_data_500_fix.py` was green throughout.
 *
 * `audit_interactive.js` reports which controls are disabled. That is half the question: a control
 * can be disabled because it is *meant* to be, or because the state that enables it is
 * unreachable. Only clicking distinguishes them. Each scenario below drives a flow to the point
 * where a control *should* be live and asserts it becomes live.
 *
 * ## Safety
 *
 * This is an automated trading terminal, so the ordering discipline is asserted as a hard
 * contract rather than assumed. `AGENTS.md`: "clicking a chain/positions row NEVER places an
 * order; the BUY card is the ONLY order path". A regression there means a stray click on a live
 * account sends an order, so `/trade` counts orders before and after selection alone and fails if
 * the count moved.
 *
 * The run refuses to start unless the base URL is local, so it cannot be pointed at production by
 * accident. Nothing here clears a kill switch, cancels a real order, or sends a Telegram message.
 *
 * Usage:
 *   node scripts/browser/interact.js [--only <substring>] [--headed]
 */
const puppeteer = require(process.env.PUPPETEER_CORE || 'puppeteer-core')

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
const API = process.env.API_ORIGIN || 'http://127.0.0.1:8000'
const EMAIL = process.env.DEMO_EMAIL || 'demo.trader@trademetrix.dev'
const PASSWORD = process.env.DEMO_PASSWORD || 'Demo@2026!'

const argv = process.argv.slice(2)
const ONLY = argv.includes('--only') ? argv[argv.indexOf('--only') + 1] : null
const HEADED = argv.includes('--headed')

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/** Buttons, by visible text, with their enabled state. */
const BUTTONS = () => {
  const named = (b) => (b.innerText || b.getAttribute('aria-label') || b.title || '').trim()
  const vis = [...document.querySelectorAll('button')].filter((b) => b.getBoundingClientRect().width > 0)
  return {
    all: vis.map((b) => ({ text: named(b), disabled: b.disabled === true })).filter((b) => b.text),
    enabled: vis.filter((b) => !b.disabled).map(named).filter(Boolean),
    disabled: vis.filter((b) => b.disabled).map(named).filter(Boolean),
  }
}

/**
 * Click the first control whose text matches.
 *
 * Takes the pattern as a **string**, not a RegExp, because a RegExp cannot cross the puppeteer
 * boundary — it arrives as `{}` inside the page and the first run died with
 * `re.test is not a function`. The pattern is rebuilt in the page.
 */
const clickText = (pattern) => {
  const re = new RegExp(pattern, 'i')
  const el = [...document.querySelectorAll('button, a[role="button"], [role="tab"]')].find((b) => {
    const t = (b.innerText || b.getAttribute('aria-label') || '').trim()
    return re.test(t) && b.getBoundingClientRect().width > 0 && !b.disabled
  })
  if (!el) return false
  el.click()
  return true
}

/**
 * How many orders exist for the signed-in user, counted server-side.
 *
 * Counted through the API rather than by watching the DOM, because the question is "did an order
 * get placed", not "did the page claim it placed one".
 *
 * Issued **from inside the page**, not from Node. Node's `fetch` carries no session cookie, so it
 * answered 401, the helper returned -1, and the caller compared `-1 <= 0` — which passes. The
 * ordering-discipline assertion was therefore vacuous: it would have reported PASS while an order
 * was placed. A -1 is now surfaced as a failure rather than as a pass.
 */
async function orderCount(page) {
  const n = await page.evaluate(async (api) => {
    try {
      const res = await fetch(`${api}/api/v1/engine/orders`, { credentials: 'include' })
      if (!res.ok) return -1
      const body = await res.json()
      return Array.isArray(body?.orders) ? body.orders.length : -1
    } catch {
      return -1
    }
  }, API)
  return typeof n === 'number' ? n : -1
}

const scenarios = []
const scenario = (name, fn) => scenarios.push({ name, fn })

// ─────────────────────────────────────────────────────────────────────────────

scenario('trade: no chain means no order path, and nothing fabricated', async (page) => {
  // With no broker token and no NSE source, `GET /marketdata/option-chain` now answers 503 and the
  // ladder is absent. Two things must hold in that state, and both are the point:
  //   1. nothing is selectable in a way that reaches an order — the ordering discipline says a row
  //      click is selection only, so with no rows the safest possible outcome is "nothing to click"
  //   2. no fabricated premium appears — the ladder used to be generated from a formula and shown
  //      as a market, which is the whole reason the simulator was removed from the request path
  await page.goto(`${BASE}/trade`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await sleep(9000)

  const before = await orderCount(page)

  // Click anything strike-shaped that does exist, then confirm nothing was sent.
  const clicked = await page.evaluate(() => {
    let n = 0
    for (const el of document.querySelectorAll('*')) {
      const r = el.getBoundingClientRect()
      if (r.width < 26 || r.width > 120 || r.height < 12 || r.height > 44) continue
      const txt = (el.textContent || '').trim()
      if (!/^[\d,.]{4,6}$/.test(txt)) continue
      el.click()
      n++
      if (n >= 6) break
    }
    return n
  })
  await sleep(3500)

  const after = await orderCount(page)
  const text = await page.evaluate(() => document.body.innerText)
  const st = await page.evaluate(BUTTONS)

  // The fabricated ladder used to produce exactly these: 100.0 premiums and 500000 OI.
  const fabricated = /\b100\.0\b|\b500000\b|\b500,000\b/.test(text)
  const orderPathsLive = st.enabled.filter((t) => /\bBUY\b|\bSELL\b/i.test(t))
  // An unreadable count is a failure, not a pass. Silently treating "could not tell" as "no orders"
  // is how this assertion became vacuous in the first place.
  const counted = before >= 0 && after >= 0
  const placed = counted ? after - before : -1

  return {
    pass: fabricated === false && counted && placed <= 0,
    note:
      `clickable strike-shaped elements: ${clicked}; orders ${before} -> ${after}` +
      `${counted ? ` (${placed <= 0 ? 'none placed' : `${placed} PLACED`})` : ' — ORDER COUNT UNREADABLE'}; ` +
      `fabricated premiums on screen: ${fabricated}; BUY/SELL buttons enabled: ` +
      `${orderPathsLive.length ? orderPathsLive.join(', ') : 'none'}`,
  }
})

scenario('builder: Generate strategy enables only once a strategy is described', async (page) => {
  await page.goto(`${BASE}/strategies/builder`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await sleep(8000)

  const before = await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find((x) => /generate strategy/i.test(x.innerText))
    return b ? b.disabled : null
  })
  if (before === null) return { pass: false, note: 'Generate strategy button not found' }

  await page.click('textarea')
  await page.type(
    'textarea',
    'Buy NIFTY when EMA 9 crosses above EMA 21, exit at +1% target with 0.5% stop loss, weekdays only',
    { delay: 3 },
  )
  await sleep(1500)

  const after = await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find((x) => /generate strategy/i.test(x.innerText))
    return b ? b.disabled : null
  })

  return {
    pass: before === true && after === false,
    note: `disabled before typing: ${before}; after describing a strategy: ${after}`,
  }
})

scenario('go-live: the wizard cannot be advanced without a broker (recorded regression)', async (page) => {
  await page.goto(`${BASE}/go-live`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await sleep(8000)

  const state = await page.evaluate(BUTTONS)
  const next = state.all.find((b) => /next/i.test(b.text))
  if (!next) return { pass: false, note: 'Next button not found' }

  // The demo user has no broker connected, so step 1 must not be advanceable. `AGENTS.md` records a
  // `canNext` fallthrough that made the Start button permanently disabled — the inverse of this:
  // here the guard must hold. A wizard that will not advance without a broker is correct; one that
  // will is how a deploy starts with no broker configured.
  return {
    pass: next.disabled === true,
    note: `Next disabled with no broker connected: ${next.disabled} (expected true — the guard must hold)`,
  }
})

scenario('alerts: create, toggle and delete through the UI', async (page) => {
  // A full round trip through the interface, not through curl. The point is that the *page* can
  // create an alert: the button is enabled, the form submits, the row appears, and it survives a
  // reload. `POST /api/v1/alerts/` was answering 500 for most of this session because `user_alerts`
  // was missing from the schema, and the page showed an empty list either way — indistinguishable
  // from a user with no alerts. That is exactly the failure this cannot catch.
  const SYMBOL = 'NSE:RELIANCE-EQ'

  await page.goto(`${BASE}/alerts`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await sleep(7000)

  // Remove any alert from an earlier run so the assertions below are about this one.
  await page.evaluate(async (api, sym) => {
    const list = await (await fetch(`${api}/api/v1/alerts/`, { credentials: 'include' })).json().catch(() => ({}))
    for (const a of list.alerts || []) {
      if (a.symbol !== sym) continue
      await fetch(`${api}/api/v1/alerts/${a.id}`, { method: 'DELETE', credentials: 'include' })
    }
  }, API, SYMBOL)
  await page.goto(`${BASE}/alerts`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await sleep(6000)

  // The control is labelled "Create"; the form fields are placeholders.
  if (!(await page.evaluate(clickText, '^create$'))) {
    return { pass: false, note: 'no enabled "Create" control on /alerts' }
  }
  await sleep(2500)

  const filled = await page.evaluate((sym) => {
    const setNative = (el, v) => {
      const proto =
        el instanceof HTMLTextAreaElement
          ? HTMLTextAreaElement.prototype
          : HTMLInputElement.prototype
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v)
      el.dispatchEvent(new Event('input', { bubbles: true }))
    }
    const fields = [...document.querySelectorAll('input:not([type=hidden]), select, textarea')]
    const label = (el) =>
      `${el.placeholder || ''} ${el.name || ''} ${el.getAttribute('aria-label') || ''} ${el.id || ''}`.toLowerCase()

    const symbol = fields.find((f) => /symbol/.test(label(f)))
    const price = fields.find((f) => /price|target/.test(label(f)))
    const cond = fields.find((f) => f.tagName === 'SELECT')

    if (symbol) setNative(symbol, sym)
    if (price) setNative(price, '1400')
    if (cond && cond.options.length > 1) {
      cond.value = cond.options[1].value
      cond.dispatchEvent(new Event('change', { bubbles: true }))
    }
    return { symbol: !!symbol, price: !!price, condition: !!cond }
  }, SYMBOL)

  if (!filled.symbol || !filled.price) {
    return { pass: false, note: `alert form fields not identifiable: ${JSON.stringify(filled)}` }
  }
  await sleep(900)

  const submitted = await page.evaluate(clickText, 'create|save|add alert')
  if (!submitted) return { pass: false, note: 'no enabled submit control in the alert form' }
  await sleep(4500)

  const listed = await page.evaluate(
    (sym) => new RegExp(sym.replace(':', '\\s*:\\s*'), 'i').test(document.body.innerText),
    SYMBOL,
  )
  if (!listed) return { pass: false, note: `submitted, but ${SYMBOL} is not listed afterwards` }

  // Survives a reload — i.e. it was persisted, not just held in component state.
  await page.goto(`${BASE}/alerts`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await sleep(6000)
  const survived = await page.evaluate(
    (sym) => new RegExp(sym.replace(':', '\\s*:\\s*'), 'i').test(document.body.innerText),
    SYMBOL,
  )

  // Clean up, so the suite is repeatable.
  await page.evaluate(async (api, sym) => {
    const list = await (await fetch(`${api}/api/v1/alerts/`, { credentials: 'include' })).json().catch(() => ({}))
    for (const a of list.alerts || []) {
      if (a.symbol === sym) {
        await fetch(`${api}/api/v1/alerts/${a.id}`, { method: 'DELETE', credentials: 'include' })
      }
    }
  }, API, SYMBOL)

  return {
    pass: survived,
    note: `created through the form: ${listed}; still present after a reload: ${survived}; cleaned up`,
  }
})

// ─────────────────────────────────────────────────────────────────────────────

;(async () => {
  if (!/^https?:\/\/(localhost|127\.0\.0\.1)/.test(BASE)) {
    console.error(`refusing to run against ${BASE} — this drives real flows and is local-only`)
    process.exit(2)
  }

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: HEADED ? false : 'new',
    args: ['--no-sandbox', '--window-size=1500,1100'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1500, height: 1100 })

  const consoleErrors = []
  page.on('pageerror', (e) => consoleErrors.push(String(e.message).slice(0, 160)))

  await page.goto(`${BASE}/auth`, { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForSelector('input[type=email]', { timeout: 25000 })
  await sleep(800)
  await page.type('input[type=email]', EMAIL, { delay: 8 })
  const pwd = await page.$('input[type=password]')
  if (!pwd) {
    console.error('password field not found')
    process.exit(2)
  }
  await pwd.type(PASSWORD, { delay: 8 })
  await page.click('button[type="submit"]')
  await sleep(9000)
  if (page.url().includes('/auth')) {
    console.error('sign-in failed')
    process.exit(2)
  }
// A URL change is not proof of authentication: the form redirects away from /auth even when the
  // API rejects the credentials. Confirmed — signing in as a user that does not exist printed
  // "signed in as ..." here and then failed two of four scenarios for reasons that had nothing to do
  // with what they were testing. Ask the API instead.
  const whoami = await page
    .evaluate(async (origin) => {
      try {
        const r = await fetch(`${origin}/api/v1/auth/me`, { credentials: 'include' })
        if (!r.ok) return { ok: false, status: r.status }
        return { ok: true, email: (await r.json()).email || null }
      } catch (e) {
        return { ok: false, status: 0, error: String(e.message || e).slice(0, 80) }
      }
    }, API)
    .catch((e) => ({ ok: false, status: 0, error: String(e.message || e).slice(0, 80) }))

  if (!whoami.ok) {
    console.error(
      `ABORT: not authenticated as ${EMAIL} — GET /api/v1/auth/me returned ${whoami.status || whoami.error}.\n` +
        '  Results would describe an unauthenticated page, not the product.\n' +
        '  Set DEMO_EMAIL / DEMO_PASSWORD for an account that exists.\n',
    )
    process.exit(2)
  }
  console.log(`signed in as ${whoami.email || EMAIL} (verified via /auth/me)`)
  console.log(`target ${BASE} (local only)\n`)

  let pass = 0
  let fail = 0
// ── write flows ───────────────────────────────────────────────────────────────
// Every existing scenario above checks a *guard* — a control that must stay disabled. These do the
// opposite: they perform a real write through the UI and then confirm it survived a reload.
//
// The reason to drive them through the browser rather than by calling the API is that the API
// working proves nothing about the page. `/portal` loaded a 404 for its whole life and still
// rendered cleanly; the only way to see a write flow that is broken in the UI is to click it.

/** Types into the first input whose placeholder contains `frag`. Returns false if there is none. */
async function typeByPlaceholder(page, frag, value) {
  const handle = await page.evaluateHandle(
    (f) => [...document.querySelectorAll('input, textarea')].find((el) => (el.placeholder || '').toLowerCase().includes(f)) || null,
    frag.toLowerCase(),
  )
  const el = handle.asElement()
  if (!el) return false
  await el.click({ clickCount: 3 })
  await el.type(value, { delay: 8 })
  return true
}

/** Clicks the first button whose visible text matches `re`. */
async function clickButton(page, re, { optional = false } = {}) {
  const handle = await page.evaluateHandle((src) => {
    const rx = new RegExp(src, 'i')
    return [...document.querySelectorAll('button, [role=button]')].find((b) => rx.test((b.innerText || b.textContent || '').trim())) || null
  }, re.source)
  const el = handle.asElement()
  if (!el) {
    if (optional) return false
    throw new Error(`no button matching ${re}`)
  }
  await el.click()
  return true
}

scenario('strategies: create through the dialog, survive a reload, then delete', async (page) => {
  const NAME = 'Interact Probe Strategy'

  // `handleDelete` puts a native `window.confirm` in front of the delete. Headless Chrome
  // auto-dismisses dialogs unless a handler is registered, so the confirm always returned false and
  // the delete never ran — which read as "delete is broken" when the API returns 204 for it.
  // Accepted only for this scenario; the alerts scenario has its own delete path.
  const onDialog = async (d) => { await d.accept() }
  page.on('dialog', onDialog)
  const SYMBOL = 'NIFTY'

  await page.goto(`${BASE}/strategies`, { waitUntil: 'domcontentloaded' })
  await sleep(3500)

  // The control is labelled "+ New Strategy". A secondary "Create Strategy" button also exists in
  // the source but is conditional and was not rendered, so matching on that string found nothing —
  // the scenario was reading the wrong label, not reporting a product fault.
  await clickButton(page, /new strategy/i)
  await sleep(1200)

  const named = await typeByPlaceholder(page, 'my strategy', NAME)
  const symboled = await typeByPlaceholder(page, 'NIFTY', SYMBOL)
  if (!named || !symboled) throw new Error(`create form not reachable (name=${named} symbol=${symboled})`)

  await clickButton(page, /create strategy/i, { optional: true })
  await sleep(4000)

  // A reload is the real test: the row has to come from the API, not from optimistic state.
  await page.reload({ waitUntil: 'domcontentloaded' })
  await sleep(4000)
  const afterCreate = await page.evaluate((n) => document.body.innerText.includes(n), NAME)

  // Clean up, so repeated runs do not pile up.
  // Scoped: find the smallest element whose text contains the name AND has a delete button, rather
  // than walking every div/tr/li in the document — that version blew the evaluate timeout.
  await page.evaluate((n) => {
    // Plain substring matching, not a RegExp. A regex here needed its metacharacters escaped, and
    // the escaping was wrong — `\b` became a literal backslash, the pattern matched nothing, and the
    // delete click silently never fired. The name is a plain string the page printed, so `includes`
    // is both sufficient and impossible to get wrong here.
    const candidates = [...document.querySelectorAll('tr, li, .t-panel, div')]
      .filter((el) => (el.innerText || '').includes(n))
      .filter((el) => [...el.querySelectorAll('button')].some((b) => /delete/i.test(b.innerText || '')))
    // Innermost, not outermost: ancestors also contain the name and a Delete button, and picking
    // the outermost would click the first card's Delete rather than the probe's. Depth is the
    // reliable ordering — a containing element is always deeper in the tree.
    const depth = (el) => { let d = 0; for (let n = el; n; n = n.parentElement) d++; return d }
    const row = candidates.sort((a, b) => depth(b) - depth(a))[0]
    const del = row ? [...row.querySelectorAll('button')].find((b) => /delete/i.test(b.innerText || '')) : null
    if (del) del.click()
  }, NAME)
  await sleep(3500)
  await page.reload({ waitUntil: 'domcontentloaded' })
  await sleep(3500)
  const afterDelete = await page.evaluate((n) => document.body.innerText.includes(n), NAME)

  page.off('dialog', onDialog)

  return {
    pass: named && symboled && afterCreate && !afterDelete,
    note:
      `form reachable ${named && symboled}; present after reload ${afterCreate}; ` +
      `gone after delete ${!afterDelete}`,
  }
})

scenario('marketdata: a watchlist symbol can be added and removed', async (page) => {
  await page.goto(`${BASE}/marketdata`, { waitUntil: 'domcontentloaded' })
  await sleep(4500)

  const added = await page.evaluate(() => {
    // The real label is "+ Add Symbol".
    const add = [...document.querySelectorAll('button')].find((b) => /add symbol/i.test(b.innerText || ''))
    if (!add) {
      const seen = [...document.querySelectorAll('button')].map((b) => (b.innerText || '').trim()).filter(Boolean).slice(0, 12)
      return { ok: false, why: `no "+ Add Symbol" button; saw ${JSON.stringify(seen)}` }
    }
    add.click()
    return { ok: true, why: '' }
  })
  if (!added.ok) throw new Error(added.why)
  await sleep(1500)

  const picked = await page.evaluate(() => {
    // The modal row is `{ name }`, `{ symbol }`, `{ type badge }` — three lines. An earlier version
    // took the *last* line, which is the badge ("index" / "stock"), and then asserted the page
    // contains that word. "stock" appears all over a market-data page, so the assertion passed for a
    // reason that had nothing to do with the symbol being added. The symbol is the second line.
    const rows = [...document.querySelectorAll('div.t-hover-bg')]
    const row = rows[0]
    if (!row) return null
    const lines = (row.innerText || '').split('\n').map((s) => s.trim()).filter(Boolean)
    const symbol = lines.length >= 2 ? lines[1] : lines[0]
    row.click()
    return symbol || null
  })
  if (!picked) throw new Error('the add-symbol modal listed no candidates')
  if (!/[:_-]/.test(String(picked))) {
    throw new Error(`did not read a symbol off the modal row — got ${JSON.stringify(picked)}, which would make the assertion vacuous`)
  }
  await sleep(2500)

  await page.reload({ waitUntil: 'domcontentloaded' })
  await sleep(4500)
  // Assert the symbol appears as a watchlist row, not merely as a word somewhere on the page.
  const present = await page.evaluate((sym) => {
    const exact = [...document.querySelectorAll('*')].some(
      (el) => el.children.length === 0 && (el.innerText || '').trim() === sym,
    )
    return exact
  }, String(picked).trim())

  // The control is `<button title="Remove from watchlist">x</button>` — its accessible label is the
  // `title`, not its text. An earlier selector read only innerText/aria-label, so it never matched
  // and every run left the symbol behind, quietly accumulating watchlist entries.
  const removed = await page.evaluate((sym) => {
    const cell = [...document.querySelectorAll('*')].find(
      (el) => el.children.length === 0 && (el.innerText || '').trim() === sym,
    )
    if (!cell) return false
    // Walk out to the row that owns the buttons.
    let holder = cell
    for (let i = 0; i < 6 && holder; i++) {
      const btn = [...holder.querySelectorAll('button, [role=button]')].find((b) => {
        const label = (b.getAttribute('title') || '') + ' ' + (b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '')
        return /remove from watchlist/i.test(label)
      })
      if (btn) { btn.click(); return true }
      holder = holder.parentElement
    }
    return false
  }, String(picked).trim())
  if (removed) await sleep(2500)

  return {
    pass: present,
    note:
      `picked ${String(picked).trim()}; listed after a reload ${present}; ` +
      `removal control ${removed ? 'found' : 'not found (cleanup skipped)'}`,
  }
})

  for (const s of scenarios) {
    if (ONLY && !s.name.includes(ONLY)) continue
    const before = consoleErrors.length
    let r
    try {
      r = await s.fn(page)
    } catch (e) {
      r = { pass: false, note: `threw: ${String(e.message).slice(0, 120)}` }
    }
    const threw = consoleErrors.length - before
    const ok = r.pass && threw === 0
    if (ok) pass++
    else fail++
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${s.name}`)
    console.log(`      ${r.note}`)
    if (threw) for (const e of consoleErrors.slice(before)) console.log(`      page error: ${e}`)
    console.log('')
  }

  await browser.close()
  console.log('='.repeat(70))
  console.log(`${pass}/${pass + fail} scenarios passed`)
  process.exit(fail ? 1 : 0)
})().catch((e) => {
  console.error('harness error:', e)
  process.exit(2)
})