/**
 * A P&L percentage needs a cost basis, and must not invent one when there is none.
 *
 * ## The bug
 *
 * `/positions` computed the P&L% column inline, in three places, as
 *
 *     p.average_buy_price ? (pnl / (Math.abs(p.quantity) * p.average_buy_price) * 100) : 0
 *
 * A **closed** position has `quantity = 0` and keeps its average price:
 *
 *     { symbol: 'NSE:TCS-EQ', quantity: 0, average_buy_price: 2075.21, unrealised_pnl: 0 }
 *
 * so `Math.abs(0) * 2075.21` is `0`, and `0 / 0` is `NaN`, which `.toFixed(2)` renders as the
 * string `"NaN"` — a literal `NaN` in the P&L% cell, and in the CSV export, for every closed
 * position. The browser crawler caught it the first time a position could actually be closed,
 * which is to say the first time an order could be recorded at all.
 *
 * The guard tested `average_buy_price` and never the denominator. `0` is falsy and the average
 * price is truthy, so the ternary took the division branch.
 *
 * ## The second failure, quieter
 *
 * A **short** has `average_buy_price = 0` — it was never bought — so the same expression fell to
 * the `else 0` and every short position reported `0.00%`. Not `NaN`, which at least looks wrong;
 * a confident zero for a percentage that is definitely not zero.
 *
 * ## Why the answer is `null`
 *
 * No cost basis means the percentage is uncomputable, not zero. Returning `0` would print a
 * real-looking number in the cell and in the CSV, which is the failure mode this file exists to
 * prevent.
 *
 * ## The gap in the previous suite
 *
 * `lib/positions.test.ts` covers `positionPnl` well — longs, shorts, zero quotes — but every
 * fixture there is an **open** position, because that is all that could exist while orders could
 * not be recorded. A suite written only against reachable states passes against code that breaks
 * the moment a new state becomes reachable, which is what happened here.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { positionPnl, positionPnlPct, type PositionLike } from './positions.js'

// 5 lots bought at 22424.19, now down 1629.50.
const LONG_OPEN: PositionLike = {
  quantity: 5, average_buy_price: 22424.19, average_sell_price: 0, unrealised_pnl: -1629.5,
}

// Closed: quantity zeroed, average price retained, P&L settled. This is the NaN.
const LONG_CLOSED: PositionLike = {
  quantity: 0, average_buy_price: 2075.21, average_sell_price: 0, unrealised_pnl: 0,
}

// 20 lots short, sold at 23512.85, down 2257. `average_buy_price` is 0 — never bought.
const SHORT_OPEN: PositionLike = {
  quantity: -20, average_buy_price: 0, average_sell_price: 23512.85, unrealised_pnl: -2257,
}

// ── the NaN ──────────────────────────────────────────────────────────────────────

test('a closed position has no P&L percentage, rather than NaN', () => {
  // The exact arithmetic that reached the DOM: 0 / (0 * 2075.21) * 100.
  assert.equal(Number.isNaN(0 / (Math.abs(0) * 2075.21) * 100), true)
  assert.equal(positionPnlPct(LONG_CLOSED), null)
})

test('every position shape the API can send yields a number or null, never NaN', () => {
  const rows: Array<[string, PositionLike]> = [
    ['open long', LONG_OPEN],
    ['closed long', LONG_CLOSED],
    ['open short', SHORT_OPEN],
    ['no prices at all', { quantity: 5 }],
    ['zero average, non-zero qty', { quantity: 5, average_buy_price: 0 }],
    ['quantity missing entirely', { average_buy_price: 100 }],
    ['strings', { quantity: '5', average_buy_price: '100' }],
    ['short as strings', { quantity: '-5', average_sell_price: '100' }],
    ['zero short', { quantity: -20, average_buy_price: 0, average_sell_price: 0 }],
  ]
  for (const [label, row] of rows) {
    const v = positionPnlPct(row)
    assert.ok(
      v === null || (Number.isFinite(v) && !Number.isNaN(v)),
      `${label} produced ${v}`,
    )
  }
})

// ── percentages it can compute ───────────────────────────────────────────────────

test('an open long is a percentage of its cost basis', () => {
  const expected = (-1629.5 / (5 * 22424.19)) * 100
  assert.ok(Math.abs(positionPnlPct(LONG_OPEN, -1629.5)! - expected) < 1e-9)
})

test('zero is returned only when the P&L really is zero', () => {
  assert.equal(positionPnlPct({ ...LONG_OPEN, unrealised_pnl: 0 }, 0), 0)
})

test('a short is priced off its average sell price, not its zero average buy price', () => {
  // With `average_buy_price` as the only basis this row is falsy and the old expression fell to
  // `else 0` — a confident 0.00% for a short that is losing money.
  const pct = positionPnlPct(SHORT_OPEN, -2257)
  assert.ok(pct !== null)
  assert.ok(Math.abs(pct! - (-2257 / (20 * 23512.85)) * 100) < 1e-9)
  assert.ok(pct! < 0)
  assert.notEqual(pct, 0)
})

test('with no pnl argument it falls back to positionPnl', () => {
  assert.equal(positionPnlPct(LONG_OPEN), positionPnlPct(LONG_OPEN, LONG_OPEN.unrealised_pnl))
})

test('it agrees with positionPnl when a live price is used', () => {
  const live = 23000
  const expected = (positionPnl(LONG_OPEN, live) / (5 * 22424.19)) * 100
  assert.ok(Math.abs(positionPnlPct(LONG_OPEN, positionPnl(LONG_OPEN, live))! - expected) < 1e-9)
})

// ── refusing to guess ────────────────────────────────────────────────────────────

test('a zero quantity yields null whatever the P&L claims', () => {
  assert.equal(positionPnlPct({ ...LONG_CLOSED, unrealised_pnl: 500 }, 500), null)
})

test('a long with no usable average buy price yields null, not zero', () => {
  assert.equal(positionPnlPct({ quantity: 5, average_buy_price: 0 }, 100), null)
  assert.equal(positionPnlPct({ quantity: 5 }, 100), null)
})

test('a zero average price is not treated as a real basis', () => {
  // `{last_price: 0}` is how a fallback provider reports "unresolvable"; a zero average price is
  // the same signal — never a fill at zero.
  assert.equal(positionPnlPct({ quantity: 5, average_buy_price: 0, average_sell_price: 0 }, 50), null)
})

test('a short with only a buy price uses it rather than refusing', () => {
  assert.ok(Math.abs(positionPnlPct({ quantity: -5, average_buy_price: 100 }, 50)! - 10) < 1e-9)
})