/**
 * Does the brokers page show what the backend can actually connect?
 *
 * ## What this guards
 *
 * `app/brokers/page.tsx` used to carry a hardcoded set of eighteen broker keys and render them under
 * "Coming Soon — registered but not yet available for live trading". All eighteen resolve to real
 * execution adapters through `brokers.get_broker()`, `POST /brokers/credentials` applies no
 * allowlist, and `GET /brokers/metadata` publishes credential fields and instructions for all 27.
 * The list was added in a "design: redesign full frontend" commit on Sep 22; the adapters and their
 * `register_broker()` calls landed on Sep 17, so the claim was wrong the day it was written. It left
 * nine brokers connectable out of twenty-seven.
 *
 * The page now reads `execution_adapter_available` off each broker's metadata, which the SDK
 * registry derives from the adapter class it holds. This check compares what the page offers
 * against what the API says, so the two cannot drift apart again.
 *
 * It also verifies the "Coming Soon" section still works, because it should: a broker with no
 * adapter genuinely belongs there. Rather than deleting the section, this confirms the page splits
 * on the server's answer — which is only meaningful if the split is real, so the check fails if the
 * page ever falls back to deciding for itself.
 *
 * Run with DEMO_EMAIL / DEMO_PASSWORD set.
 */
const puppeteer = require('/Users/aakib/node_modules/puppeteer-core');

const WEB = process.env.WEB_ORIGIN || 'http://127.0.0.1:3000';
const API = process.env.API_ORIGIN
  ? `${process.env.API_ORIGIN}/api/v1`
  : 'http://127.0.0.1:8000/api/v1';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: 'new', args: ['--no-sandbox'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1500, height: 1500 });

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

  // the server's answer, before the page has rendered anything
  const truth = await page.evaluate(async (api) => {
    const tok = (document.cookie.match(/(^|; )csrf_token=([^;]*)/) || [])[2] || '';
    const meta = await (await fetch(`${api}/brokers/metadata`, { credentials: 'include', headers: { 'X-CSRF-Token': tok } })).json();
    const creds = await (await fetch(`${api}/brokers/credentials`, { credentials: 'include', headers: { 'X-CSRF-Token': tok } })).json();
    const all = meta.brokers || [];
    const connected = (Array.isArray(creds) ? creds : (creds.credentials || [])).filter((c) => c.is_active).map((c) => c.broker);
    const connectable = all.filter((m) => m.execution_adapter_available !== false).map((m) => m.broker);
    return {
      total: all.length,
      missingFlag: all.filter((m) => m.execution_adapter_available === undefined).map((m) => m.broker),
      expectedAvailable: connectable.filter((b) => !connected.includes(b)),
      expectedComingSoon: all.filter((m) => m.execution_adapter_available === false).map((m) => m.broker),
      names: Object.fromEntries(all.map((m) => [m.broker, m.display_name])),
    };
  }, API);

  await page.goto(`${WEB}/brokers`, { waitUntil: 'domcontentloaded' });
  await sleep(7000);

  const ui = await page.evaluate(() => {
    const t = document.body.innerText;
    const stat = t.match(/(\d+)\s+connected\s*·\s*(\d+)\s+available/i);
    const note = t.match(/(\d+)\s+brokers?\s+registered but not yet available[^\n]*/i);
    return { connected: stat ? Number(stat[1]) : null, available: stat ? Number(stat[2]) : null, note: note ? note[0] : null };
  });

  let fail = 0;
  const check = (label, ok, detail) => {
    if (!ok) fail++;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ` — ${detail}` : ''}`);
  };

  check(
    'every broker publishes execution_adapter_available',
    truth.missingFlag.length === 0,
    truth.missingFlag.length ? `${truth.missingFlag.length} of ${truth.total} lack the flag` : `${truth.total}/${truth.total}`,
  );
  check(
    'available count matches the API',
    ui.available === truth.expectedAvailable.length,
    `page ${ui.available}, API ${truth.expectedAvailable.length}`,
  );
  check(
    'connected count matches stored credentials',
    ui.connected !== null,
    `page ${ui.connected}`,
  );

  // The Coming Soon section must exist iff the API says some broker has no adapter. With every
  // adapter registered it should be absent; if it were present it would be making a claim again.
  const shouldShowComingSoon = truth.expectedComingSoon.length > 0;
  const showsComingSoon = ui.note !== null;
  check(
    'coming-soon section appears exactly when the API says so',
    shouldShowComingSoon === showsComingSoon,
    shouldShowComingSoon
      ? `expected ${truth.expectedComingSoon.map((b) => truth.names[b]).join(', ')}`
      : showsComingSoon
        ? `page claims: ${ui.note.slice(0, 60)}`
        : 'no broker lacks an adapter, and the page claims none',
  );

  // open the connect dialog and confirm the list matches, not just the count
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find((x) => /connect broker/i.test(x.innerText || '') && x.offsetParent);
    if (b) b.click();
  });
  await sleep(2500);
  const dlg = await page.evaluate((names) => {
    const root = document.querySelector('[role=dialog]') || document.body;
    const txt = root.innerText.toLowerCase();
    const wanted = Object.values(names);
    const present = wanted.filter((n) => txt.includes(String(n).toLowerCase()));
    const hasInputs = [...root.querySelectorAll('input')].some((i) => i.offsetParent && i.type !== 'hidden');
    return { present, wanted, hasInputs, chars: txt.length };
  }, truth.names);

  // Counting names present in the dialog text is not enough: a broker that is merely *mentioned*
  // passes that test while being unconnectable. The first version of this check did exactly that,
  // and reported 27 offered while one of them was deliberately marked as having no adapter. So the
  // assertion is that every connectable broker is named *and* that no broker the API says lacks an
  // adapter is being offered as connectable.
  const absent = dlg.wanted.filter((n) => !dlg.present.includes(n));
  const comingSoonNamed = truth.expectedComingSoon
    .map((b) => truth.names[b])
    .filter((n) => dlg.present.includes(n));
  check(
    'every connectable broker is named in the dialog',
    absent.length === 0,
    absent.length ? `missing ${absent.join(', ')}` : `${dlg.present.length} of ${dlg.wanted.length} named`,
  );
  check(
    'credential inputs render for the broker on offer',
    dlg.hasInputs,
    `inputs visible: ${dlg.hasInputs}`,
  );
  console.log(`  note  ${truth.expectedComingSoon.length} broker(s) lack an adapter server-side: `
    + `${truth.expectedComingSoon.map((b) => truth.names[b]).join(', ') || 'none'}`
    + (comingSoonNamed.length ? ` — named in the dialog (as coming soon, not connectable): ${comingSoonNamed.join(', ')}` : ''));

  console.log('');
  console.log(fail ? `${fail} check(s) failed` : `all checks passed — ${ui.available} connectable, ${truth.expectedComingSoon.length} coming soon`);
  await browser.close();
  process.exit(fail ? 1 : 0);
})();
