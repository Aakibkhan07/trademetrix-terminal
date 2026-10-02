/**
 * Node-run assertions for `lib/pnl.ts`.
 *
 * The bug these guard was invisible in three separate ways at once: TypeScript was satisfied,
 * the numbers looked plausible, and a wrong answer rendered as data rather than as an error.
 * So the assertions are about the *shape mismatch* and the *absent-vs-zero distinction*,
 * not about arithmetic.
 *
 * Run by `npm run test:lib`.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { formatPnlTile, pnlTiles } from './pnl.js'
import type { CumulativePnl, PnlEnvelope } from './pnl.js'

/** Exactly what `GET /analytics/pnl?period=1d` returns. One field. */
const DAILY_ONLY = {
  pnl: { daily: 1234.5 },
  period: '1d',
  broker: 'fyers',
}

/** Exactly what `GET /analytics/pnl?period=1w` returns. */
const CUMULATIVE = {
  pnl: {
    realised_pnl: 50000,
    unrealised_pnl: -3200.5,
    daily_pnl: 1234.5,
    weekly_pnl: 8000,
    monthly_pnl: 41000,
    overall_pnl: 46800,
    drawdown_pct: 4.2,
  },
  period: '1w',
  broker: 'fyers',
}

test('the daily figure comes from the 1d response', () => {
  const tiles = pnlTiles(DAILY_ONLY, CUMULATIVE)
  assert.equal(tiles[0].value, 1234.5)
  assert.equal(tiles[0].tone, 'up')
})

test('realised and unrealised come from the cumulative response', () => {
  const tiles = pnlTiles(DAILY_ONLY, CUMULATIVE)
  assert.equal(tiles[1].value, 50000)
  assert.equal(tiles[2].value, -3200.5)
  assert.equal(tiles[2].tone, 'down')
})

test('a 1d response cannot populate the cumulative tiles — the original bug', () => {
  // This is the exact call the page used to make: one response, three numbers read from it.
  // `realised_pnl` and `unrealised_pnl` do not exist on a `period=1d` body at all, so the
  // honest answer is `null`. The previous inline version produced 0 for both.
  //
  // The cast is required, and that is the point: `tsc` rejects this call outright, because
  // `{ daily: number }` has no properties in common with `CumulativePnl`. Passing one
  // response where the other is expected has become a compile error rather than a silent
  // zero. This assertion documents the runtime behaviour for anyone who reaches past the
  // compiler with a cast — and the compiler refusing is why the cast is a visible act.
  const wrongShape = DAILY_ONLY as unknown as PnlEnvelope<CumulativePnl>
  const tiles = pnlTiles(DAILY_ONLY, wrongShape)
  assert.equal(tiles[1].value, null, 'realised must be null, never a fabricated 0')
  assert.equal(tiles[2].value, null, 'unrealised must be null, never a fabricated 0')
  assert.equal(tiles[1].tone, 'unknown')
  assert.equal(tiles[2].tone, 'unknown')
})

test('a missing response is null, not zero', () => {
  const tiles = pnlTiles(null, undefined)
  assert.deepEqual(tiles.map((t) => t.value), [null, null, null])
  assert.deepEqual(tiles.map((t) => t.tone), ['unknown', 'unknown', 'unknown'])
})

test('an empty pnl object is null, not zero', () => {
  const tiles = pnlTiles({ pnl: {}, period: '1d', broker: null }, { pnl: null, period: '1w', broker: null })
  assert.deepEqual(tiles.map((t) => t.value), [null, null, null])
})

test('a genuine zero is a zero and still reads as up', () => {
  // The distinction that matters: 0 is a real answer, null is "unavailable".
  const tiles = pnlTiles(
    { pnl: { daily: 0 }, period: '1d', broker: 'fyers' },
    { pnl: { realised_pnl: 0, unrealised_pnl: 0 }, period: '1w', broker: 'fyers' },
  )
  assert.deepEqual(tiles.map((t) => t.value), [0, 0, 0])
  assert.deepEqual(tiles.map((t) => t.tone), ['up', 'up', 'up'])
  assert.equal(formatPnlTile(0), '+0')
})

test('an unavailable value renders as a dash, never as 0', () => {
  assert.equal(formatPnlTile(null), '—')
  assert.notEqual(formatPnlTile(null), formatPnlTile(0))
})

test('formatting keeps the sign for a loss and omits it for a gain', () => {
  assert.equal(formatPnlTile(1500), '+1500')
  assert.equal(formatPnlTile(-3200.5), '-3201')
})

test('a string number from the broker is coerced rather than becoming NaN', () => {
  const tiles = pnlTiles(
    { pnl: { daily: '1234.5' as unknown as number }, period: '1d', broker: 'fyers' },
    null,
  )
  assert.equal(tiles[0].value, 1234.5)
})

test('NaN and Infinity are unavailable, not numbers', () => {
  const tiles = pnlTiles(
    { pnl: { daily: NaN }, period: '1d', broker: 'fyers' },
    { pnl: { realised_pnl: Infinity }, period: '1w', broker: 'fyers' },
  )
  assert.equal(tiles[0].value, null)
  assert.equal(tiles[1].value, null)
})

test('the tile labels say which figure they are', () => {
  const tiles = pnlTiles(DAILY_ONLY, CUMULATIVE)
  assert.deepEqual(tiles.map((t) => t.label), ['Today (realized)', 'Realized', 'Unrealized'])
  // `Today (realized)` vs `Realized` reads as today-versus-cumulative. Before the fix both
  // tiles came from one response, so a dash under either was unexplained; the hint carries
  // the period so the distinction is visible on the tile itself.
  assert.equal(tiles[0].hint, '1d')
  assert.equal(tiles[1].hint, 'all time')
  assert.equal(tiles[2].hint, 'open positions')
})
