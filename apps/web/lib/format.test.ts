/**
 * Node-run assertions for `lib/format.ts`.
 *
 * The bug class these guard is a crash, so the assertions are mostly about *not throwing* and
 * about the distinction the old guards got wrong: `undefined !== null` is true, so a field the
 * response omitted passed the check and then failed on `.toFixed`.
 *
 * Each of the two real crashes gets its own case, reproducing the exact expression that threw.
 *
 * Run by `npm run test:lib`.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  NO_VALUE,
  field,
  fmtMoney,
  fmtNum,
  fmtPct,
  fmtRate,
  fmtSigned,
  fmtSignedMoney,
  fmtWithUnit,
  isNum,
  numOrNull,
} from './format.js'

// ── isNum / numOrNull ────────────────────────────────────────────────────────

test('isNum accepts finite numbers only', () => {
  assert.equal(isNum(0), true)
  assert.equal(isNum(-12.5), true)
  assert.equal(isNum(NaN), false)
  assert.equal(isNum(Infinity), false)
  assert.equal(isNum('3'), false)
  assert.equal(isNum(null), false)
  assert.equal(isNum(undefined), false)
})

test('numOrNull coerces the numeric strings brokers actually send', () => {
  assert.equal(numOrNull('3.5'), 3.5)
  assert.equal(numOrNull('-0.25'), -0.25)
  assert.equal(numOrNull(''), null)
  assert.equal(numOrNull('abc'), null)
  assert.equal(numOrNull(NaN), null)
})

test('the original guard let undefined through — this is the whole bug', () => {
  // `undefined !== null` is true, so the old conditional took the "has a value" branch and
  // then called `.toFixed` on nothing.
  const o: { latency_ms?: number } = {}
  assert.equal(o.latency_ms !== null, true, 'precondition: the old guard passes')
  assert.throws(() => (o.latency_ms as number).toFixed(1))
  // The replacement is total.
  assert.equal(fmtNum(o.latency_ms, 1), NO_VALUE)
})

test('an explicit null is unavailable too', () => {
  assert.equal(fmtNum(null, 1), NO_VALUE)
  assert.equal(fmtMoney(null), NO_VALUE)
  assert.equal(fmtPct(null), NO_VALUE)
})

// ── fmtNum / fmtSigned / fmtWithUnit ─────────────────────────────────────────

test('fmtNum renders fixed decimals', () => {
  assert.equal(fmtNum(1.005, 1), '1.0')
  assert.equal(fmtNum(1234.5678, 2), '1234.57')
  assert.equal(fmtNum(0, 2), '0.00')
})

test('fmtSigned marks positives and leaves negatives alone', () => {
  assert.equal(fmtSigned(5), '+5.00')
  assert.equal(fmtSigned(0), '+0.00')
  assert.equal(fmtSigned(-5), '-5.00')
  assert.equal(fmtSigned(null), NO_VALUE)
})

test('fmtWithUnit is what /transparency needs, and cannot throw', () => {
  // The two lines that crashed the page.
  assert.equal(fmtWithUnit(12.34, 1, 'ms'), '12.3ms')
  assert.equal(fmtWithUnit(0, 2, ''), '0.00')
  assert.equal(fmtWithUnit(undefined, 1, 'ms'), NO_VALUE)
  assert.equal(fmtWithUnit(null, 2, ''), NO_VALUE)
})

// ── money and percentages ───────────────────────────────────────────────────

test('fmtMoney uses Indian digit grouping', () => {
  assert.equal(fmtMoney(1234567), '12,34,567')
  assert.equal(fmtMoney(500000), '5,00,000')
  assert.equal(fmtMoney(999), '999')
  assert.equal(fmtMoney(-45000), '-45,000')
  assert.equal(fmtMoney(undefined), NO_VALUE)
})

test('fmtSignedMoney carries the rupee sign', () => {
  assert.equal(fmtSignedMoney(45000), '+₹45,000')
  assert.equal(fmtSignedMoney(-45000), '-₹45,000')
  assert.equal(fmtSignedMoney(null), NO_VALUE)
})

test('fmtPct marks positives and appends the unit', () => {
  assert.equal(fmtPct(1.5), '+1.50%')
  assert.equal(fmtPct(-1.5), '-1.50%')
  assert.equal(fmtPct(null), NO_VALUE)
})

test('fmtRate is unsigned — a win rate is a rate, not a delta', () => {
  assert.equal(fmtRate(62.5), '62.5%')
  assert.equal(fmtRate(0), '0.0%')
  assert.equal(fmtRate(undefined), NO_VALUE)
})

// ── field: absent versus zero ────────────────────────────────────────────────

test('field separates an absent field from a real zero', () => {
  // Slippage of exactly 0 is a meaningful value; a missing slippage column is not.
  assert.equal(field(0), 0)
  assert.equal(field(null), null)
  assert.equal(field(undefined), null)
  assert.equal(field('0'), 0)
})

test('every formatter returns the same dash for missing input', () => {
  const missing = [undefined, null, NaN, 'abc', {}, []]
  for (const v of missing) {
    assert.equal(fmtNum(v), NO_VALUE)
    assert.equal(fmtMoney(v), NO_VALUE)
    assert.equal(fmtSignedMoney(v), NO_VALUE)
    assert.equal(fmtPct(v), NO_VALUE)
    assert.equal(fmtRate(v), NO_VALUE)
    assert.equal(fmtSigned(v), NO_VALUE)
  }
})

test('NO_VALUE is a dash, not a zero or an empty string', () => {
  assert.equal(NO_VALUE, '—')
  assert.notEqual(NO_VALUE, '0')
  assert.notEqual(NO_VALUE, '')
})
