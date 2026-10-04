/**
 * The Fyers token panel must not report success where it checked nothing, and must not colour a
 * failure like a pass.
 *
 * `app/dashboard/admin-content.tsx` held `msg` as a bare string and picked its colour by substring:
 *
 *     line 758   msg.includes('expired') ? red : green
 *     line 1319  msg.includes('fail')    ? red : green
 *     line 638   msg.includes('saved') || msg.includes('success') ? green : red
 *
 * Every `catch` block does `setMsg(e.message)`, so a failure whose wording does not contain "fail" —
 * "Could not reach broker", a 401 body — was rendered **green**. And a filter over an empty array is
 * empty, so with zero Fyers credentials `expired.length === 0` fell through to "All tokens valid",
 * in green, directly above the page's own "No Fyers credentials found."
 *
 * This reads the rendered colour rather than the source, because the source was never wrong about
 * what it wrote — it was wrong about which colour that text implied. A test on the string alone would
 * have passed on the original code.
 *
 * Needs an account with no Fyers credentials, which is what the demo user has.
 */
const puppeteer = require('/Users/aakib/node_modules/puppeteer-core');

const WEB = process.env.WEB_ORIGIN || 'http://127.0.0.1:3000';
const API = process.env.API_ORIGIN
  ? `${process.env.API_ORIGIN}/api/v1`
  : 'http://127.0.0.1:8000/api/v1';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** `var(--green)` and `var(--red)` are resolved by the browser, so compare resolved rgb. */
const GREENISH = /rgb\(\s*(\d+),\s*(\d+),\s*(\d+)\s*\)/;

function isGreenish(colour) {
  const m = colour.match(GREENISH);
  if (!m) return false;
  const [, r, g, b] = m.map(Number);
  return g > r + 20 && g > b + 20;
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: 'new', args: ['--no-sandbox'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1400 });

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

  // the ground truth the panel should be reporting against
  const truth = await page.evaluate(async (api) => {
    const tok = (document.cookie.match(/(^|; )csrf_token=([^;]*)/) || [])[2] || '';
    const r = await fetch(`${api}/admin/brokers/fyers/validate`, {
      method: 'POST', credentials: 'include', headers: { 'X-CSRF-Token': tok },
    });
    const j = await r.json();
    return { status: r.status, count: (j.results || []).length };
  }, API);
  console.log('');
  console.log(`  POST /admin/brokers/fyers/validate -> ${truth.status}, ${truth.count} result(s)`);

  await page.goto(`${WEB}/dashboard?tab=brokers`, { waitUntil: 'domcontentloaded' });
  await sleep(7000);

  const clicked = await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')]
      .find((x) => /validate all tokens/i.test(x.innerText || '') && x.offsetParent);
    if (!b) return false;
    b.click();
    return true;
  });
  if (!clicked) {
    console.error('  no "Validate All Tokens" button on /dashboard?tab=brokers');
    await browser.close();
    process.exit(1);
  }
  await sleep(5000);

  const shown = await page.evaluate(() => {
    // the message is the paragraph inside the Fyers panel, next to its heading
    const heading = [...document.querySelectorAll('h3')]
      .find((h) => /Fyers Token Management/i.test(h.innerText || ''));
    // Walk up until a container actually holds the message. `closest('div')` lands on the header
    // wrapper one level too shallow — the first version of this check reported "no message rendered"
    // against a page that was rendering it correctly, which is the same class of error as calling a
    // working dashboard stale.
    let node = heading ? heading.parentElement : null;
    let candidates = [];
    for (let i = 0; i < 6 && node; i++) {
      candidates = [...node.querySelectorAll('p')]
        .filter((p) => p.offsetParent && (p.innerText || '').trim());
      if (candidates.length >= 2) break;
      node = node.parentElement;
    }
    const msg = candidates.find((p) => !/credentials found/i.test(p.innerText || '')) || candidates[0];
    const emptyLine = candidates.find((p) => /no fyers credentials/i.test(p.innerText || ''));
    return msg
      ? {
          text: (msg.innerText || '').trim(),
          colour: getComputedStyle(msg).color,
          emptyLine: emptyLine ? (emptyLine.innerText || '').trim() : null,
        }
      : null;
  });

  if (!shown) {
    console.error('  no message rendered after clicking Validate All Tokens');
    await browser.close();
    process.exit(1);
  }

  console.log(`  rendered: "${shown.text}"  (${shown.colour})`);
  console.log('');

  let fail = 0;
  const check = (label, ok, detail) => {
    if (!ok) fail++;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ` — ${detail}` : ''}`);
  };

  check(
    'does not claim tokens are valid when it validated none',
    !(truth.count === 0 && /all .*valid/i.test(shown.text)),
    truth.count === 0 ? `validated ${truth.count}, said "${shown.text}"` : `${truth.count} validated`,
  );
  check(
    'nothing-to-check is not coloured as a pass',
    !(truth.count === 0 && isGreenish(shown.colour)),
    truth.count === 0 ? shown.colour : 'n/a — there was something to check',
  );
  // The original code put a green "All tokens valid" directly above the page's own "No Fyers
  // credentials found." — two lines on one screen saying opposite things.
  check(
    'does not contradict the empty-state line beneath it',
    !(shown.emptyLine && /all .*valid/i.test(shown.text)),
    shown.emptyLine ? `said "${shown.text}" while also showing "${shown.emptyLine}"` : 'no empty-state line shown',
  );

  console.log('');
  console.log(fail ? `${fail} check(s) failed` : 'the panel reports what it actually did');
  await browser.close();
  process.exit(fail ? 1 : 0);
})();
