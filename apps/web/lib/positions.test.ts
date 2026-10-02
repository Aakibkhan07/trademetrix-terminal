/**
 * Node-run assertions for `lib/positions.ts`.
 *
 * There is no test runner in this web package, so these run under `node --test` with the
 * TypeScript compiled first — a bare `node` cannot import `.ts`. The command is in
 * `package.json` as `test:lib`.
 *
 * They exist because the two bugs this file fixes were both *silent*: the old formula
 * returned a confident number for every input, including the ones it was wrong about. A
 * test that only checks a long position passes against code that breaks every short, which
 * is exactly what the previous version did — the short case was simply not written.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { displayPrice, isLong, positionPnl, positionSide, usablePrice } from './positions.js'

// A long: bought 100, now 110. +10 per unit.
const LONG = { quantity: 10, average_buy_price: 100, average_sell_price: 0, unrealised_pnl: 0 }

// A short, as the broker reports it: netQty is negative, sold at 100, now 90.
// +10 per unit — the price fell, which is what a short wants.
const SHORT = {
  quantity: -10,
  average_buy_price: 0,
  average_sell_price: 100,
  unrealised_pnl: 0,
}

test('a long gains when the price rises', () => {
  assert.equal(positionPnl(LONG, 110), 100)
})

test('a long loses when the price falls', () => {
  assert.equal(positionPnl(LONG, 95), -50)
})

test('a short gains when the price falls — this is the case that was inverted', () => {
  // The old formula gave -10 * (90 - 0) = -900: a large loss on a profitable short.
  assert.equal(positionPnl(SHORT, 90), 100)
})

test('a short loses when the price rises', () => {
  assert.equal(positionPnl(SHORT, 110), -100)
})

test('a short prices off average_sell_price, not average_buy_price', () => {
  // A position only ever short has no meaningful average buy price. If the basis is
  // taken from there, the number is arbitrary.
  const shortWithStaleBuy = {
    quantity: -10,
    average_buy_price: 999, // nonsense left over from a previous round trip
    average_sell_price: 100,
    unrealised_pnl: 0,
  }
  assert.equal(positionPnl(shortWithStaleBuy, 90), 100)
})

test('a zero price is never treated as a price', () => {
  // quantity * (0 - 100) would be -1000 of fabricated loss on a live row.
  assert.equal(positionPnl(LONG, 0), LONG.unrealised_pnl)
  assert.equal(positionPnl(LONG, null), LONG.unrealised_pnl)
  assert.equal(positionPnl(LONG, undefined), LONG.unrealised_pnl)
})

test('a zero price falls back to the broker figure rather than inventing one', () => {
  const p = { ...LONG, unrealised_pnl: 42 }
  assert.equal(positionPnl(p, 0), 42)
})

test('usablePrice rejects zero, negatives, NaN and non-numbers', () => {
  assert.equal(usablePrice(0), null)
  assert.equal(usablePrice(-1), null)
  assert.equal(usablePrice(NaN), null)
  assert.equal(usablePrice(null), null)
  assert.equal(usablePrice(undefined), null)
  assert.equal(usablePrice(0.5), 0.5)
})

test('displayPrice falls back to the position last_price, and then to nothing', () => {
  assert.equal(displayPrice({ last_price: 88 }, 0), 88)
  assert.equal(displayPrice({ last_price: 88 }, 90), 90)
  assert.equal(displayPrice({ last_price: 0 }, 0), null)
})

test('a string price from a broker response is coerced, not NaN', () => {
  assert.equal(positionPnl({ quantity: 10, average_buy_price: '100' }, '110'), 100)
})

// ─────────────────────────────────────────────────────────────────────────────
// Position direction.
//
// The bug these guard: `/paper` compared a position's `side` against `'BUY'`, the value an
// *order* carries. A position's `side` is `LONG` / `SHORT` / `FLAT`, so the comparison was
// never true and every row rendered in the loss colour — including profitable longs.
//
// A test that only checked a short would have passed against the old code, because
// `SHORT !== 'BUY'` too. The long case is the one that distinguishes "correct" from "always
// red", so it is the one that has to be written.
// ─────────────────────────────────────────────────────────────────────────────

test('a long position is long, not "not BUY"', () => {
  // Exactly what `EnginePosition(side=LONG, quantity=10).model_dump()` produces.
  const p = { side: 'LONG', quantity: 10 }
  assert.equal(positionSide(p), 'LONG')
  assert.equal(isLong(p), true)
  // The comparison the page used to make, kept so the regression is visible in the output.
  assert.equal(p.side === 'BUY', false, "if this ever becomes true, the vocabulary merged")
})

test('a short position is a short', () => {
  assert.equal(positionSide({ side: 'SHORT', quantity: -8 }), 'SHORT')
  assert.equal(isLong({ side: 'SHORT', quantity: -8 }), false)
})

test('a flat position is flat', () => {
  assert.equal(positionSide({ side: 'FLAT', quantity: 0 }), 'FLAT')
  assert.equal(isLong({ side: 'FLAT', quantity: 0 }), false)
})

test('direction falls back to the sign of quantity when side is missing', () => {
  // `positions.py` derives `side` from the sign of the net quantity, so the sign is the
  // source of truth and is always available even if the field is absent.
  assert.equal(positionSide({ quantity: 5 }), 'LONG')
  assert.equal(positionSide({ quantity: -5 }), 'SHORT')
  assert.equal(positionSide({ quantity: 0 }), 'FLAT')
  assert.equal(positionSide({}), 'FLAT')
})

test('an unrecognised side value is not trusted — the sign wins', () => {
  // A colour derived from a value that means nothing is worse than one derived from the sign.
  assert.equal(positionSide({ side: 'BUY', quantity: 10 }), 'LONG')
  assert.equal(positionSide({ side: 'sell', quantity: -3 }), 'SHORT')
  assert.equal(positionSide({ side: 42, quantity: 7 }), 'LONG')
})

test('a string quantity still classifies, since brokers send strings', () => {
  assert.equal(positionSide({ side: 'LONG', quantity: '10' }), 'LONG')
  assert.equal(positionSide({ quantity: '-10' }), 'SHORT')
})

test('the three sides are mutually exclusive', () => {
  const positions = [
    { side: 'LONG', quantity: 1 },
    { side: 'SHORT', quantity: -1 },
    { side: 'FLAT', quantity: 0 },
  ]
  const longs = positions.filter(isLong).length
  assert.equal(longs, 1, 'exactly one of the three is long')
})
