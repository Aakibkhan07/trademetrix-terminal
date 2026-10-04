/**
 * Does the paper page count running strategies, or strategies it has ever started?
 *
 * ## The bug
 *
 * `/builder/dashboard` answers `{"running": [...], "total_running": N}`. The list holds every
 * strategy this account has started, each carrying its own `status`; `total_running` counts only
 * the ones with `status == "running"`. A stopped strategy stays in the list — measured: after a
 * stop the entry is still returned, with `status: "stopped"` and `stopped_at` set.
 *
 * Both pages read the list and treat its length as the running count:
 *
 *     app/paper/page.tsx:124       setRunning((dash as { running: RuntimeEntry[] }).running || [])
 *     app/paper/page.tsx:255       <span>{running.length} running</span>
 *     app/paper/page.tsx:241       disabled={... || running.length >= 5}
 *     app/strategies/page.tsx:78   setRunning((d as { running: RuntimeEntry[] }).running || [])
 *     app/strategies/page.tsx:282  <span>{running.length} running</span>
 *
 * So the badge counts stopped strategies, and the five-strategy cap counts distinct strategies
 * ever started. Past that, Start Paper Trading is disabled with nothing running.
 *
 * ## Why this script starts things
 *
 * The cap only becomes visible once an account has started five distinct strategies, and the list
 * is keyed per strategy rather than per run — six start/stop cycles of one strategy leave `listed`
 * at 1. So proving the cap means starting five different ones. That is safe: paper mode, no orders,
 * and each one is stopped again immediately. Anything left running is stopped at the end.
 *
 * It asserts on the *rendered badge against the server's own count*, not on the code, and it is
 * mutation-tested: reverting the filter must make it fail.
 */
const puppeteer = require('/Users/aakib/node_modules/puppeteer-core');

const WEB = process.env.WEB_ORIGIN || 'http://127.0.0.1:3000';
const API = process.env.API_ORIGIN
  ? `${process.env.API_ORIGIN}/api/v1`
  : 'http://127.0.0.1:8000/api/v1';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const CAP = 5;

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: 'new', args: ['--no-sandbox'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1500, height: 1400 });

  await page.goto(`${WEB}/auth`, { waitUntil: 'networkidle2' });
  await sleep(900);
  await page.type('input[type=email]', process.env.DEMO_EMAIL);
  await page.type('input[type=password]', process.env.DEMO_PASSWORD);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 45000 }).catch(() => {}),
    page.click('button[type=submit]'),
  ]);
  await sleep(2500);

  const me = await page.evaluate(async (api) => {
    const tok = (document.cookie.match(/(^|; )csrf_token=([^;]*)/) || [])[2] || '';
    const r = await fetch(`${api}/auth/me`, { credentials: 'include', headers: { 'X-CSRF-Token': tok } });
    return r.status;
  }, API);
  if (me !== 200) {
    console.error(`not authenticated (GET /auth/me returned ${me}) — set DEMO_EMAIL / DEMO_PASSWORD`);
    process.exit(2);
  }

  const dash = () => page.evaluate(async (api) => {
    const tok = (document.cookie.match(/(^|; )csrf_token=([^;]*)/) || [])[2] || '';
    const r = await fetch(`${api}/builder/dashboard`, { credentials: 'include', headers: { 'X-CSRF-Token': tok } });
    const j = await r.json();
    const e = j.running || [];
    return {
      listed: e.length,
      total_running: j.total_running,
      running: e.filter((x) => x.status === 'running').map((x) => x.strategy_id),
    };
  }, API);

  // ── drive enough distinct strategies to make the cap observable ──────────────
  const ids = await page.evaluate(async (api) => {
    const tok = (document.cookie.match(/(^|; )csrf_token=([^;]*)/) || [])[2] || '';
    const r = await fetch(`${api}/builder/strategies`, { credentials: 'include', headers: { 'X-CSRF-Token': tok } });
    const j = await r.json();
    const arr = Array.isArray(j) ? j : (j.strategies || []);
    return arr.filter((s) => s.status === 'ready' || s.status === 'paper').slice(0, 8).map((s) => s.id);
  }, API);

  const drive = page.evaluate.bind(page);
  const startStop = async (sid) => {
    await drive(async (api, id) => {
      const tok = (document.cookie.match(/(^|; )csrf_token=([^;]*)/) || [])[2] || '';
      const h = { 'X-CSRF-Token': tok, 'Content-Type': 'application/json' };
      const s = await fetch(`${api}/builder/strategies/${id}/start`, {
        method: 'POST', credentials: 'include', headers: h,
        body: JSON.stringify({ symbol: 'NIFTY', interval: '15m', mode: 'paper' }),
      });
      if (s.status >= 400) return s.status;
      await new Promise((r) => setTimeout(r, 1200));
      await fetch(`${api}/builder/strategies/${id}/stop`, { method: 'POST', credentials: 'include', headers: h });
      return s.status;
    }, API, sid);
    await sleep(2500);
  };

  // bring the account up to the cap so the failure is observable rather than theoretical
  for (const id of ids) {
    const d = await dash();
    if (d.listed >= CAP) break;
    await startStop(id);
  }

  // leave nothing running
  for (const sid of (await dash()).running) {
    await drive(async (api, id) => {
      const tok = (document.cookie.match(/(^|; )csrf_token=([^;]*)/) || [])[2] || '';
      await fetch(`${api}/builder/strategies/${id}/stop`, {
        method: 'POST', credentials: 'include', headers: { 'X-CSRF-Token': tok },
      });
    }, API, sid);
    await sleep(2000);
  }

  const truth = await dash();
  console.log('');
  console.log(`  server: total_running = ${truth.total_running}, list holds ${truth.listed} entr${truth.listed === 1 ? 'y' : 'ies'}`);

  let fail = 0;
  for (const path of ['/paper', '/strategies']) {
    await page.goto(`${WEB}${path}`, { waitUntil: 'domcontentloaded' });
    await sleep(6000);
    const ui = await page.evaluate(() => {
      const badge = [...document.querySelectorAll('span')]
        .map((s) => (s.innerText || '').trim())
        .find((t) => /^\d+ running$/.test(t)) || null;
      const btn = [...document.querySelectorAll('button')]
        .find((b) => /start paper trading/i.test(b.innerText || ''));
      const sel = document.querySelector('select');
      return {
        badge,
        shown: badge ? parseInt(badge, 10) : null,
        startDisabled: btn ? btn.disabled : null,
        selected: sel && sel.value ? sel.value : null,
      };
    });

    // The two pages differ in what they show when nothing is running, and both are right:
    // `/paper` always renders the badge in its panel header, so it reads "0 running"; `/strategies`
    // hides the entire "Execution Dashboard" panel when `running.length === 0`, so no badge
    // exists. The rule that covers both is therefore not "the badge equals N" but "the badge never
    // contradicts N" — absent, or exactly N. Asserting equality alone failed a correct page.
    const badgeOk = ui.badge === null || ui.shown === truth.total_running;
    // with nothing running and a strategy selected, the cap must not be what disables Start
    const capWrong = truth.total_running < CAP && ui.selected && ui.startDisabled === true;
    const ok = badgeOk && !capWrong;
    if (!ok) fail++;

    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${path.padEnd(12)} badge=${String(ui.shown).padEnd(4)} `
      + `server=${String(truth.total_running).padEnd(4)} startDisabled=${String(ui.startDisabled).padEnd(6)}`);
    if (!badgeOk) {
      console.log(`        badge reads ${JSON.stringify(ui.badge)}, ${truth.total_running} running (list holds stopped entries)`);
    }
    if (capWrong) console.log(`        Start is disabled with ${truth.total_running} running — the cap counted all ${truth.listed} entries ever started`);
  }

  console.log('');
  console.log(fail ? `${fail}/2 pages miscount` : '2/2 pages report the running count');
  await browser.close();
  process.exit(fail ? 1 : 0);
})();
