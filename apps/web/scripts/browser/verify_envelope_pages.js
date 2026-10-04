/**
 * Every endpoint that answers `{ key: [...] }`, checked by loading the page that consumes it.
 *
 * ## Why this exists
 *
 * Three pages lost their data to the same mistake: reading a scalar off an envelope.
 * `GET /engine/orders` answers `{ orders: [...] }`, `GET /forward-test/` answers `{ items: [...] }`,
 * and `GET /risk/settings` answers `{ settings: [...] }`. In each case the page read
 * `res.max_daily_loss` or `res.someField` off the top-level object, got `undefined`, and fell back
 * to a default that then hid or overwrote real values. The `/risk` one shipped a page showing a
 * daily-loss cap of 0 for an account capped at 2000.
 *
 * One instance in eleven was actually broken. Establishing that took three attempts at automated
 * consumer analysis, all of which produced confident nonsense and were thrown away:
 *
 *   - Keying by the outer object read the *page* path as an endpoint, and every page's first
 *     signature is the PWA manifest, so `/account` came back with a wrapper of `orders`.
 *   - Finding consumers by grepping for the wrapper name matched local variables — 246 "suspects",
 *     none real.
 *   - Demanding a subscript missed the correct and more common form, `data.plans || []`, and
 *     flagged six correct call sites.
 *
 * The lesson is not that grep is hard here. It is that this is a data-flow question, and pattern
 * matching over a text window cannot answer it. So this script does the only thing that is
 * trustworthy: it fetches each endpoint to confirm the shape, loads the page, and looks for content
 * that can only be there if the array rendered.
 *
 * Run with DEMO_EMAIL / DEMO_PASSWORD set. Exits non-zero if any page fails to render its list.
 */
const puppeteer = require('/Users/aakib/node_modules/puppeteer-core');

const WEB = process.env.WEB_ORIGIN || 'http://127.0.0.1:3000';
const API = process.env.API_ORIGIN
  ? `${process.env.API_ORIGIN}/api/v1`
  : 'http://127.0.0.1:8000/api/v1';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// [page, endpoint, pattern that can only match if the array reached the DOM]
//
// A note on how strong this is. A marker *word* proves the page rendered, not that the array
// populated it: `/risk` originally matched on /daily|loss|limit|risk/i, all of which appear in the
// page's own labels, so the check still passed with the envelope unwrap removed — verified by
// mutation. `/risk` is therefore asserted on the exact value rather than a word, and the remaining
// entries are a smoke test: the endpoint's item count is fetched and reported, but "the list
// reached the DOM" is inferred from page content, not proven per row.
const CHECKS = [
  ['/journal', '/engine/orders', /trade|fill|entry|journal/i],
  ['/positions', '/engine/positions', /position|qty|quantity|net|open/i],
  ['/transparency', '/engine/runs', /run|order|trade/i],
  ['/pricing', '/subscriptions/plans/', /free|pro|enterprise|starter/i],
  ['/go-live', '/strategies/list-builtin', /strateg|iron|buyer|choose|select/i],
  ['/strategies', '/strategies/', /strateg|buyer|swing|select/i],
  ['/marketplace', '/strategies/marketplace', /strateg|buyer|install|market|choose/i],
  ['/alerts', '/alerts/', /alert|rule/i],
  ['/brokers', '/brokers/metadata', /fyers|dhan|angel|zerodha|connect/i],
  ['/admin/admins', '/admin/admins', /admin|user|role|email|invite/i],
  ['/risk', '/risk/settings', /daily|loss|limit|risk/i],
];

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: 'new',
    args: ['--no-sandbox'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1500, height: 1300 });

  await page.goto(`${WEB}/auth`, { waitUntil: 'networkidle2' });
  await sleep(900);
  await page.type('input[type=email]', process.env.DEMO_EMAIL);
  await page.type('input[type=password]', process.env.DEMO_PASSWORD);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 45000 }).catch(() => {}),
    page.click('button[type=submit]'),
  ]);
  await sleep(2500);

  const signIn = await page.evaluate(async (api) => {
    const tok = (document.cookie.match(/(^|; )csrf_token=([^;]*)/) || [])[2] || '';
    const r = await fetch(`${api}/auth/me`, { credentials: 'include', headers: { 'X-CSRF-Token': tok } });
    return r.status;
  }, API);
  if (signIn !== 200) {
    console.error(`not authenticated (GET /auth/me returned ${signIn}) — set DEMO_EMAIL / DEMO_PASSWORD`);
    process.exit(2);
  }

  console.log('');
  let fail = 0;
  for (const [pagePath, endpoint, marker] of CHECKS) {
    const shape = await page.evaluate(async (api, ep) => {
      const tok = (document.cookie.match(/(^|; )csrf_token=([^;]*)/) || [])[2] || '';
      try {
        const r = await fetch(api + ep, { credentials: 'include', headers: { 'X-CSRF-Token': tok } });
        const j = await r.json();
        const key = Object.keys(j || {})[0];
        return { status: r.status, key, count: Array.isArray(j?.[key]) ? j[key].length : null };
      } catch (e) {
        return { error: String(e).slice(0, 50) };
      }
    }, API, endpoint);

    await page.goto(`${WEB}${pagePath}`, { waitUntil: 'domcontentloaded' });
    await sleep(6000);
    const info = await page.evaluate((src) => {
      const txt = document.body.innerText;
      return { chars: txt.length, matched: new RegExp(src, 'i').test(txt) };
    }, marker.source);

    const envelope = shape.key && shape.count !== null;
    let ok = info.matched && envelope;
    let detail = '';

    // Exact assertion where a regression is known. The page heading contains "Risk" and the labels
    // contain "Daily Loss", so a word test cannot distinguish 0 from 2000 — which is precisely the
    // bug. Read the stored value and the value the form shows, and compare them.
    if (endpoint === '/risk/settings') {
      const stored = await page.evaluate(async (api) => {
        const tok = (document.cookie.match(/(^|; )csrf_token=([^;]*)/) || [])[2] || '';
        const r = await fetch(`${api}/risk/settings`, { credentials: 'include', headers: { 'X-CSRF-Token': tok } });
        const j = await r.json();
        const row = Array.isArray(j?.settings) ? j.settings[0] : j;
        return row?.max_daily_loss;
      }, API);
      const shown = await page.evaluate(() => {
        const edit = [...document.querySelectorAll('button')]
          .filter((b) => b.offsetParent !== null)
          .find((b) => /^(edit|modify|change)$/i.test((b.innerText || '').trim()));
        if (edit) edit.click();
        return true;
      });
      if (shown) {
        await sleep(1500);
        const value = await page.evaluate(() => {
          const n = [...document.querySelectorAll('input')]
            .filter((i) => i.offsetParent !== null)
            .map((i) => Number(i.value));
          return n.length ? n[0] : null;
        });
        ok = stored != null && value === Number(stored);
        detail = ok
          ? ` (limit ${value} matches stored ${stored})`
          : ` (form shows ${value}, stored ${stored})`;
      }
    }

    if (!ok) fail++;
    const verdict = ok
      ? `renders${detail}`
      : `NOT RENDERING (endpoint ${shape.status}, ${shape.count} item(s), page ${info.chars} chars)${detail}`;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${pagePath.padEnd(15)} ${endpoint.padEnd(27)} ${verdict}`);
  }

  await browser.close();
  console.log('');
  console.log(`${CHECKS.length - fail}/${CHECKS.length} envelope-shaped endpoints reached the page`);
  process.exit(fail ? 1 : 0);
})();