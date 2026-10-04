/**
 * Read the cron hint the way a user would: off the rendered page.
 *
 * The hint was wrong three ways at once. It omitted `-X POST` on a POST endpoint, named
 * `http://127.0.0.1:8000` — a port production compose never publishes — and the copy on the page
 * disagreed with the copy in the API's own response about quoting. Chasing it further turned up a
 * fourth: the endpoint sat behind the CSRF middleware, which wants a `csrf_token` cookie, so a cron
 * could not have called it however the command was spelled.
 *
 * This checks the rendered string, not the source, so a hardcoded URL reintroduced in JSX is caught
 * the same as one left in the build.
 */
const puppeteer = require('/Users/aakib/node_modules/puppeteer-core');

const WEB = process.env.WEB_ORIGIN || 'http://127.0.0.1:3000';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: 'new', args: ['--no-sandbox'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1500, height: 1300 });

  // The API base the page really uses, captured from its own traffic. Asserting "the hint is not
  // localhost" was the first version and it was wrong: locally `API_BASE` *is* 127.0.0.1:8000, so a
  // correctly derived hint and a hardcoded one rendered identically. The question is not whether the
  // text says localhost, it is whether the hint agrees with where the page sends everything else.
  const seenApiOrigins = new Set();
  page.on('request', (r) => {
    const m = r.url().match(/^(https?:\/\/[^/]+)\/api\/v1/);
    if (m) seenApiOrigins.add(m[1]);
  });

  await page.goto(`${WEB}/auth`, { waitUntil: 'networkidle2' });
  await sleep(900);
  await page.type('input[type=email]', process.env.DEMO_EMAIL);
  await page.type('input[type=password]', process.env.DEMO_PASSWORD);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 45000 }).catch(() => {}),
    page.click('button[type=submit]'),
  ]);
  await sleep(2500);

  // The API URL comes from Node, not from `process.env` inside the page: `page.evaluate` runs in
  // the browser, where `process` does not exist, and reading it there throws before the check runs.
  const API = process.env.API_ORIGIN
    ? `${process.env.API_ORIGIN}/api/v1`
    : 'http://127.0.0.1:8000/api/v1';
  const me = await page.evaluate(async (api) => {
    const tok = (document.cookie.match(/(^|; )csrf_token=([^;]*)/) || [])[2] || '';
    const r = await fetch(`${api}/auth/me`, { credentials: 'include', headers: { 'X-CSRF-Token': tok } });
    return r.status;
  }, API);
  if (me !== 200) {
    console.error(`not authenticated (GET /auth/me returned ${me}) — set DEMO_EMAIL / DEMO_PASSWORD`);
    process.exit(2);
  }

  await page.goto(`${WEB}/reports/daily`, { waitUntil: 'domcontentloaded' });
  await sleep(6500);

  const hint = await page.evaluate(() => {
    const c = [...document.querySelectorAll('code')]
      .map((x) => (x.innerText || '').trim())
      .find((t) => /curl/.test(t));
    return c || null;
  });

  if (!hint) {
    console.error('no curl hint rendered on /reports/daily');
    await browser.close();
    process.exit(1);
  }

  console.log('');
  console.log(`  rendered: ${hint}`);
  console.log(`  api base this page calls: ${[...seenApiOrigins].join(', ') || '(no api traffic seen)'}`);

  const hintUrl = (hint.match(/curl -s -X POST (\S+)/) || [])[1] || '';
  const hintBase = (hintUrl.match(/^(https?:\/\/[^/]+)\/api\/v1/) || [])[1] || '';
  const agrees = seenApiOrigins.size > 0 && seenApiOrigins.has(hintBase);

  const checks = [
    ['uses POST', /-X POST/.test(hint)],
    ['quotes the secret header', /"X-Cron-Secret: \$CRON_SECRET"/.test(hint)],
    ['carries the /api/v1 prefix', /\/api\/v1\/reports\/daily\/send/.test(hint)],
    ['points at the same API base the page itself calls', agrees],
  ];
  let fail = 0;
  for (const [label, ok] of checks) {
    if (!ok) fail++;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${label}`);
  }
  console.log('');
  console.log(fail ? `${fail} check(s) failed` : 'the rendered command is one a cron could run');
  await browser.close();
  process.exit(fail ? 1 : 0);
})();
