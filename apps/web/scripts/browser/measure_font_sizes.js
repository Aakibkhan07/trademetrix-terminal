/**
 * Measures the rendered font size of real text on every page.
 *
 * Written because "make the text bigger" cannot be verified by reading the diff. The app has
 * two independent size mechanisms and bumping only one leaves most of the UI unchanged:
 *
 *   - 1,051 `var(--text-*)` references plus all stylesheet text, sized in **rem**, so a single
 *     root `font-size` scales them together
 *   - 2,240 inline `fontSize: N` values in JSX, which React emits as **px** and a root font
 *     size cannot touch at all
 *
 * So both have to move, and the only honest way to know whether they did is to read
 * `getComputedStyle` off the live DOM before and after.
 *
 * Samples real text nodes rather than the token values, so it reports what a person actually
 * sees — including anything the cascade overrides.
 *
 * Usage:
 *   node scripts/browser/measure_font_sizes.js          # report
 *   node scripts/browser/measure_font_sizes.js --json   # machine-readable
 */
const puppeteer = require(process.env.PUPPETEER_CORE || 'puppeteer-core')
const fs = require('fs')

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
const EMAIL = process.env.DEMO_EMAIL || 'demo.trader@trademetrix.dev'
const PASSWORD = process.env.DEMO_PASSWORD || 'Demo@2026!'
const AS_JSON = process.argv.includes('--json')
const OUT_FILE = process.env.FONT_REPORT || '/tmp/font-sizes.json'

const ROUTES = [
  '/live', '/paper', '/funds', '/positions', '/portfolio', '/terminal', '/trade',
  '/analytics', '/journal', '/risk', '/marketplace', '/strategies', '/brokers', '/settings',
]

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

;(async () => {
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
  const pwd = await page.$('input[type=password]')
  if (!pwd) throw new Error('password field not found')
  await pwd.type(PASSWORD, { delay: 8 })
  await page.click('button[type="submit"]')
  await sleep(8000)

  const report = {}

  for (const route of ROUTES) {
    await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await sleep(5500)

    const sample = await page.evaluate(() => {
      const rootPx = parseFloat(getComputedStyle(document.documentElement).fontSize)
      const seen = []
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
      let node
      while ((node = walker.nextNode()) && seen.length < 400) {
        const text = (node.textContent || '').trim()
        // Real, visible prose only: a single character is usually an icon or a separator, and
        // hidden content is not what anyone reads.
        if (text.length < 2) continue
        const el = node.parentElement
        if (!el) continue
        const cs = getComputedStyle(el)
        if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0) continue
        const rect = el.getBoundingClientRect()
        if (rect.width < 2 || rect.height < 2) continue
        seen.push({
          px: Math.round(parseFloat(cs.fontSize) * 100) / 100,
          tag: el.tagName.toLowerCase(),
          text: text.slice(0, 24),
        })
      }
      return { rootPx, samples: seen }
    })

    const sizes = sample.samples.map((s) => s.px)
    const unique = [...new Set(sizes)].sort((a, b) => a - b)
    const counts = {}
    sizes.forEach((s) => { counts[s] = (counts[s] || 0) + 1 })
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1])

    report[route] = {
      rootPx: sample.rootPx,
      measured: sizes.length,
      unique,
      // The three sizes most text actually uses, which is what "bigger" should move.
      dominant: sorted.slice(0, 3).map(([px, n]) => ({ px: Number(px), count: n })),
      median: sizes.length ? sizes.slice().sort((a, b) => a - b)[Math.floor(sizes.length / 2)] : null,
      min: unique[0] ?? null,
      max: unique[unique.length - 1] ?? null,
    }
  }

  await browser.close()

  fs.writeFileSync(OUT_FILE, JSON.stringify(report, null, 2))

  if (AS_JSON) {
    console.log(JSON.stringify(report, null, 2))
  } else {
    console.log('root font-size and the text sizes actually rendered\n')
    console.log('route'.padEnd(14) + 'root'.padStart(6) + 'median'.padStart(8) + 'min'.padStart(7) + 'max'.padStart(7) + '   dominant sizes (px x count)')
    console.log('-'.repeat(78))
    for (const [route, r] of Object.entries(report)) {
      const dom = r.dominant.map((d) => `${d.px}×${d.count}`).join('  ')
      console.log(
        `${route.padEnd(14)}${String(r.rootPx).padStart(6)}${String(r.median).padStart(8)}` +
        `${String(r.min).padStart(7)}${String(r.max).padStart(7)}   ${dom}`,
      )
    }
    const meds = Object.values(report).map((r) => r.median).filter((n) => n !== null)
    const avg = meds.reduce((a, b) => a + b, 0) / (meds.length || 1)
    console.log(`\nmedian of medians: ${avg.toFixed(2)}px   (written to ${OUT_FILE})`)
  }
})().catch((e) => {
  console.error('harness error:', e)
  process.exit(2)
})
