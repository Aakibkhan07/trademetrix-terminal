/**
 * Guard: the /trade index strip must not offer an index whose chain can never load.
 *
 * SENSEX is a BSE index. NSE publishes chains for NSE indices only, and BSE's own
 * OptionChain API answers 403 "Access Denied" to this host (measured 2026-10-09),
 * so /marketdata/option-chain returns 503 for SENSEX on every request.
 *
 * The strip used to list all five indices identically, so clicking SENSEX produced an
 * empty workspace with no explanation -- the "quiet failure looks like a dead button"
 * class from AGENTS.md. This asserts the capability is declared in data (not hardcoded
 * in the component) and that the declaration matches the backend's own index set.
 *
 * Written for `node:test` (`npm run test:lib`), which compiles plain .ts with tsc and
 * runs no JSX transform. The component is therefore rendered through
 * `React.createElement` rather than JSX, and the assertions read the RENDERED html.
 * A source-text check was tried first and survived the exact mutation it was written
 * for: replacing the conditional title with a plain `title={i.name}` left every string
 * present in the file, so the test passed against the defect. A guard that cannot fail
 * is worse than none.
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { INDEXES, chainCapableIndexes, indexMeta } from './options-contracts'
import type { IndexKey } from './options-contracts'

// `node --test` runs plain CommonJS and cannot resolve the `@/` alias that
// index-strip.tsx imports. Registering a resolver here rather than rewriting the
// component to relative paths -- the alias is the project convention and changing one
// caller would make it inconsistent with the other ~40.
const Module = require('node:module')
const path = require('node:path')
const APP_ROOT = path.join(__dirname, '..')
const origResolve = Module._resolveFilename
Module._resolveFilename = function (request: string, ...rest: unknown[]) {
  if (request.startsWith('@/')) {
    return origResolve.call(this, path.join(APP_ROOT, request.slice(2)), ...rest)
  }
  return origResolve.call(this, request, ...rest)
}

// Required after the alias is registered.
const { IndexStrip } = require('../components/trade/index-strip') as {
  IndexStrip: (props: {
    index: IndexKey
    onIndexChange: (i: IndexKey) => void
    spot: number | null
    changePct: number | null
    connected: boolean
  }) => unknown
}

/**
 * Locate the repo root by walking up until `apps/api` appears.
 *
 * A fixed `join(__dirname, '..', '..')` is right when the source runs and wrong once
 * tsc has emitted into `dist-test/`, which is how `test:lib` runs it -- the path then
 * resolves to `apps/web/web/...` and every source-reading assertion fails on ENOENT.
 * Resolving from the file's own existence rather than from its depth is what keeps
 * these assertions true in both layouts.
 */
function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 8; i++) {
    if (existsSync(join(dir, 'apps', 'api'))) return dir
    const parent = join(dir, '..')
    if (parent === dir) break
    dir = parent
  }
  throw new Error('could not locate repo root (no apps/api above ' + __dirname + ')')
}

const REPO = repoRoot()

function renderStrip(index: IndexKey): string {
  return renderToStaticMarkup(
    createElement(IndexStrip as never, {
      index,
      onIndexChange: () => {},
      spot: 22520.45,
      changePct: 0.42,
      connected: true,
    }),
  )
}

test('every index declares a chain capability', () => {
  for (const i of INDEXES) {
    // Assert the message last: node:assert.strict.equal is (actual, expected, message),
    // and passing them in the order used elsewhere in this file silently turned the
    // diagnostic into the expected value.
    assert.equal(typeof i.chainAvailable, 'boolean', `${i.key} must declare chainAvailable`)
  }
})

test('an unavailable index explains why', () => {
  for (const i of INDEXES.filter(x => !x.chainAvailable)) {
    assert.ok(i.chainUnavailableReason, `${i.key} needs a reason`)
    assert.ok(i.chainUnavailableReason!.length > 20, `${i.key} reason should be specific`)
  }
})

test('SENSEX is excluded, since NSE does not serve it and BSE blocks this host', () => {
  assert.equal(indexMeta('SENSEX').chainAvailable, false)
  assert.ok(!chainCapableIndexes().map(i => i.key).includes('SENSEX'))
})

test('the four NSE indices stay chain-capable', () => {
  assert.deepEqual(chainCapableIndexes().map(i => i.key).sort(),
    ['BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'NIFTY'])
})

test('the declared list agrees with the backend NSE_INDICES set', () => {
  // An index marked available here but absent there renders a tab that 503s; one
  // marked unavailable here but present there hides a chain that works.
  const backend = readFileSync(join(REPO, 'apps', 'api', 'market', 'option_chain.py'), 'utf8')
  const m = backend.match(/^NSE_INDICES = \{([^}]+)\}/m)
  assert.ok(m, 'could not find NSE_INDICES in market/option_chain.py')
  const backendKeys = [...m![1].matchAll(/"([A-Z]+)"/g)].map(x => x[1]).sort()
  assert.deepEqual(chainCapableIndexes().map(i => i.key).sort(), backendKeys)
})

// ── rendered behaviour, not source text ──────────────────────────────────

test('selecting SENSEX shows the reason in the UI', () => {
  const html = renderStrip('SENSEX')
  assert.ok(html.includes('data-testid="chain-unavailable-reason"'),
    'the reason must be rendered, not only present in the data')
  assert.ok(html.includes('BSE index'),
    `reason must reach the user; got: ${html.slice(0, 400)}`)
  assert.ok(html.includes('NSE does not publish'))
})

test('the SENSEX control carries a descriptive title', () => {
  const html = renderStrip('SENSEX')
  const before = /title="([^"]*)"[^>]*data-kb="index-SENSEX"/.exec(html)
  const after = /data-kb="index-SENSEX"[^>]*title="([^"]*)"/.exec(html)
  const title = before || after
  assert.ok(title, 'SENSEX chip needs a title')
  assert.ok(title![1].includes('BSE'), `title should explain: ${title![1]}`)
})

test('the DOM marks which indices can load a chain', () => {
  assert.ok(renderStrip('SENSEX').includes('data-chain-available="false"'))
  assert.ok(renderStrip('NIFTY').includes('data-chain-available="true"'))
})

test('a working index shows no unavailability banner', () => {
  // A permanent warning next to NIFTY would train users to ignore the strip. This
  // asserts on the banner, not on the string "BSE index" -- that string legitimately
  // appears in SENSEX's title attribute on every render, so a text-only check failed
  // here for the right reason and the wrong reason at once.
  assert.ok(!renderStrip('NIFTY').includes('data-testid="chain-unavailable-reason"'))
})

test('the component does not hardcode SENSEX', () => {
  const src = readFileSync(join(REPO, 'apps', 'web', 'components', 'trade', 'index-strip.tsx'), 'utf8')
  assert.ok(!/'SENSEX'|"SENSEX"/.test(src), 'capability belongs in data, not the component')
})
