/**
 * Probe: the risk page's two writes.
 *
 * The kill switch is the highest-stakes control in the product. If enabling it fails quietly the
 * user believes they are protected and is not, so the assertion is that the request is issued and
 * that the page's own state agrees afterwards — not merely that a button exists.
 *
 * Risk limits are the second write, and they go through a different endpoint (`POST /risk/settings`),
 * so both are covered.
 */
const puppeteer = require('/Users/aakib/node_modules/puppeteer-core');

const WEB = 'http://127.0.0.1:3000';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: 'new', args: ['--no-sandbox'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1500, height: 1300 });

  const posts = [];
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().includes(':8000/api/v1/risk/')) {
      posts.push(`${r.url().replace('http://127.0.0.1:8000/api/v1', '')}  body=${(r.postData() || '(none)').slice(0, 200)}`);
    }
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

  await page.goto(`${WEB}/risk`, { waitUntil: 'domcontentloaded' });
  await sleep(5000);

  const structure = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')]
      .filter((b) => b.offsetParent !== null)
      .map((b) => (b.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 46));
    const inputs = [...document.querySelectorAll('input')]
      .filter((i) => i.offsetParent !== null)
      .map((i) => ({ type: i.type, ph: i.placeholder || '(none)' }));
    return {
      buttons: [...new Set(btns)],
      inputs,
      mentionsKillSwitch: /kill switch/i.test(document.body.innerText),
      toggles: [...document.querySelectorAll('[role=switch], input[type=checkbox]')]
        .filter((e) => e.offsetParent !== null).length,
    };
  });

  console.log('  page mentions kill switch :', structure.mentionsKillSwitch);
  console.log('  switch/checkbox elements  :', structure.toggles);
  console.log('  buttons                   :', JSON.stringify(structure.buttons.slice(0, 14)));
  console.log('  inputs                    :', JSON.stringify(structure.inputs.slice(0, 8)));

  // ── kill switch ────────────────────────────────────────────────────────────
  posts.length = 0;
  const before = await page.evaluate(() => document.body.innerText.match(/kill switch[^\n]{0,60}/i)?.[0] || '');
  // The control is a plain button labelled Enable/Disable, not a switch element — the panel
  // heading is "Kill Switch" and the button beside it carries the state.
  const toggled = await page.evaluate(() => {
    const el = [...document.querySelectorAll('button')]
      .filter((b) => b.offsetParent !== null)
      .find((b) => /^(enable|disable)$/i.test((b.innerText || '').trim()));
    if (!el) return false;
    el.click();
    return true;
  });
  await sleep(3000);
  const after = await page.evaluate(() => document.body.innerText.match(/kill switch[^\n]{0,60}/i)?.[0] || '');
  console.log('  --- kill switch ---');
  console.log('  toggle found              :', toggled);
  console.log('  POST issued               :', JSON.stringify([...new Set(posts)]));
  console.log('  text before               :', JSON.stringify(before.slice(0, 60)));
  console.log('  text after                :', JSON.stringify(after.slice(0, 60)));
  console.log('  requests seen             :', posts.length);

  // ── risk limits ────────────────────────────────────────────────────────────
  posts.length = 0;
  // Limits are read-only until Edit is pressed; without that there is no Save button to find.
  const enteredEdit = await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')]
      .filter((x) => x.offsetParent !== null)
      .find((x) => /^(edit|modify|change)$/i.test((x.innerText || '').trim()));
    if (!b) return false;
    b.click();
    return true;
  });
  await sleep(1500);
  const inEdit = await page.evaluate(() => [...document.querySelectorAll('input')]
    .filter((i) => i.offsetParent !== null).length);
  const filledLimits = await page.evaluate(() => {
    const inputs = [...document.querySelectorAll('input')].filter((i) => i.offsetParent !== null);
    return inputs.map((i) => ({ ph: i.placeholder || '(none)', value: i.value, type: i.type }));
  });
  console.log('  limit inputs as shown     :', JSON.stringify(filledLimits));
  const saveClicked = await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')]
      .filter((x) => x.offsetParent !== null)
      .find((x) => /^(save|update|apply)/i.test((x.innerText || '').trim()));
    if (!b) return false;
    b.click();
    return true;
  });
  await sleep(3000);
  console.log('  --- risk limits ---');
  console.log('  entered edit mode         :', `${enteredEdit} (${inEdit} inputs visible)`);
  console.log('  save button clicked       :', saveClicked);
  console.log('  POST issued               :', JSON.stringify([...new Set(posts)]));

  await browser.close();
})();