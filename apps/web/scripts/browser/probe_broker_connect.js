/**
 * Probe: what does connecting Dhan actually do?
 *
 * Answers one question by measurement. Reading `/brokers` suggested the OAuth return path is
 * hardcoded to Fyers:
 *
 *     const authCode = params.get('auth_code')
 *     if (authCode) api.brokers.fyersExchangeCode(authCode)      // -> /brokers/fyers/exchange-code
 *
 * and `fyersExchangeCode` posts to a Fyers path. The backend's `handle_callback` is generic, so a
 * Dhan connect that produces an auth code could be exchanged against Fyers. Worth measuring.
 *
 * Cleanup is not optional here: `Connect` also calls `api.brokers.activate(broker)`, so the probe
 * deletes whatever it created rather than leaving a credential pointing at a fake client id.
 */
const puppeteer = require('/Users/aakib/node_modules/puppeteer-core');

const BROKER = process.env.PROBE_BROKER || 'dhan';
const WEB = 'http://127.0.0.1:3000';
const API = 'http://127.0.0.1:8000/api/v1';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: 'new',
    args: ['--no-sandbox'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1500, height: 1400 });

  const calls = [];
  page.on('request', (r) => {
    const u = r.url();
    if (u.startsWith(API)) calls.push(`${r.method()} ${u.slice(API.length)}`);
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

  await page.goto(`${WEB}/brokers`, { waitUntil: 'domcontentloaded' });
  await sleep(4000);

  const opened = await page.evaluate((broker) => {
    // Innermost match wins. A broad `includes` finds an outer wrapper first for brokers with long
    // descriptions, and clicking that wrapper silently does nothing.
    const needle = broker.toLowerCase();
    const hits = [...document.querySelectorAll('div,button,section')].filter((n) => {
      const t = (n.innerText || '').trim().toLowerCase();
      return t.includes(needle) && n.onclick !== undefined;
    });
    if (!hits.length) return false;
    hits.sort((a, b) => (a.innerText || '').length - (b.innerText || '').length);
    hits[0].click();
    return true;
  }, BROKER);
  await sleep(1800);
  console.log(`  ${BROKER} card clicked            :`, opened);

  // The dialog reassures the user about what is stored. Record it verbatim.
  const copy = await page.evaluate(() => {
    const t = [...document.querySelectorAll('div')]
      .map((d) => (d.innerText || '').trim())
      .find((s) => s.startsWith('Connect Dhan') && s.length < 600);
    return (t || '').split('\n').map((s) => s.trim()).filter(Boolean)[1] || '';
  });
  console.log('  dialog reassurance text     :', copy.slice(0, 100));

  calls.length = 0;
  const filled = await page.evaluate(() => {
    const set = (el, v) => {
      const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      s.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    };
    // Positional, with label fallbacks. The wording is per-broker and inconsistent — Dhan says
    // "Client ID"/"Client Secret", Zerodha "API Key"/"API Secret", Fyers "App ID"/"App Secret" —
    // so matching on wording alone missed Fyers entirely and reported a failure that belonged to
    // the probe rather than the app. The dialog renders identifier first, secret second.
    const byPlaceholder = (frag) =>
      [...document.querySelectorAll('input')].find((i) => (i.placeholder || '').includes(frag));
    const visible = [...document.querySelectorAll('input')].filter((i) => i.offsetParent !== null);
    const id = byPlaceholder('Client ID') || byPlaceholder('API Key')
      || byPlaceholder('App ID') || visible[0];
    const secret = byPlaceholder('Client Secret') || byPlaceholder('API Secret')
      || byPlaceholder('App Secret') || visible[1];
    if (id) set(id, 'probe_primary_0001');
    if (secret) set(secret, 'probe_secret_0001');
    // Deliberately NOT clicking here. Setting a controlled input and clicking in the same tick
    // means the click handler reads the state from before the render, and the submit silently
    // does nothing — which looks exactly like a broken button and is not one.
    return { id: !!id, secret: !!secret };
  });
  await sleep(1500);
  const clicked = await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')]
      .find((b) => (b.innerText || '').trim() === 'Connect' && b.offsetParent !== null);
    if (!btn) return { clicked: false, disabled: null };
    const disabled = btn.disabled;
    btn.click();
    return { clicked: true, disabled };
  });
  await sleep(5000);
  Object.assign(filled, clicked);
  console.log('  filled id/secret, clicked    :', JSON.stringify(filled));

  console.log('  requests on connect          :');
  [...new Set(calls)].forEach((c) => console.log('      ', c));

  const verdict = await page.evaluate(() => {
    const lines = document.body.innerText.split('\n').map((s) => s.trim()).filter(Boolean);
    return {
      fyersExchangeCalled: false,
      messages: lines.filter((l) => /required|fail|error|success|authenticat|connect/i.test(l)).slice(0, 5),
      connectedBanner: lines.find((l) => /connected ·|tokens live/i.test(l)) || '',
    };
  });
  console.log('  page messages                :');
  verdict.messages.forEach((m) => console.log('      ', m.slice(0, 100)));
  console.log('  banner                       :', verdict.connectedBanner.slice(0, 90));

  // cleanup, entirely inside the page so the CSRF cookie is available
  const cleaned = await page.evaluate(async (api, broker) => {
    const tok = (document.cookie.match(/(^|; )csrf_token=([^;]*)/) || [])[2] || '';
    const out = {};
    for (const role of ['execution', 'market_data']) {
      try {
        const r = await fetch(`${api}/brokers/credentials/${broker}?role=${role}`, {
          method: 'DELETE',
          credentials: 'include',
          headers: { 'X-CSRF-Token': tok },
        });
        out[role] = r.status;
      } catch (e) {
        out[role] = `ERR ${e.message}`;
      }
    }
    return out;
  }, API, BROKER);
  console.log('  cleanup DELETE per role      :', JSON.stringify(cleaned));

  await browser.close();
})();