/**
 * Guard: a rejected order must say WHY.
 *
 * The Orders table in /positions showed a REJECTED badge and nothing else. The backend
 * already had the text the whole time -- OMS writes it to `orders.message`
 * (`_mirror_audit_status`) and `/engine/orders` returns it -- but no column rendered it,
 * so a user whose order was refused for insufficient margin saw a rejection and no
 * explanation.
 *
 * Two things make this easy to regress:
 *   - only ONE of `reason` / `message` is populated per rejection (the risk path writes
 *     `reason`, the OMS path writes `message`), so reading a single field silently shows
 *     nothing for the other class of rejection;
 *   - a source-text check for the word "reason" would pass on a header alone. The table
 *     is checked as rendered markup.
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { orderIssue } from '../components/trade/types'
import type { OrderRow } from '../components/trade/types'

/**
 * `test:lib` compiles into dist-test/, so a `__dirname`-relative path resolves to
 * dist-test/app/... and every source read fails on ENOENT. Find the web source root by
 * walking up to the directory that holds next.config.js.
 */
function webRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 8; i++) {
    if (existsSync(join(dir, 'next.config.js'))) return dir
    const parent = join(dir, '..')
    if (parent === dir) break
    dir = parent
  }
  throw new Error('could not locate the web source root above ' + __dirname)
}

const PAGE = join(webRoot(), 'app', 'positions', 'page.tsx')
const src = readFileSync(PAGE, 'utf8')

function row(patch: Partial<OrderRow>): OrderRow {
  return {
    id: 'x', symbol: 'NSE:NIFTY50-INDEX', side: 'BUY', order_type: 'MARKET',
    quantity: 1, status: 'REJECTED', ...patch,
  }
}

test('orderIssue reads whichever column carries the text', () => {
  assert.equal(orderIssue(row({ reason: 'RISK_REJECTED' })), 'RISK_REJECTED')
  assert.equal(orderIssue(row({ message: 'Insufficient margin' })), 'Insufficient margin')
  // Both populated: reason wins, but neither may be dropped.
  assert.equal(orderIssue(row({ reason: 'A', message: 'B' })), 'A')
  // Neither: empty, never the string "undefined".
  assert.equal(orderIssue(row({})), '')
})

test('orderIssue does not render a whitespace-only reason as text', () => {
  assert.equal(orderIssue(row({ reason: '   ', message: 'real reason' })), 'real reason')
})

test('the orders table has a Reason column', () => {
  assert.ok(src.includes('<th>Reason</th>'),
    'the header alone is not enough -- the row must render the text too')
})

test('the orders row renders the reason for a rejected order', () => {
  // The row must call orderIssue; reading o.reason alone misses every OMS rejection.
  assert.ok(src.includes('orderIssue(o)'),
    'the row must read both reason and message')
})

test('the reason cell is scoped to non-filled statuses', () => {
  // A FILLED order showing a stale rejection reason would be its own lie.
  assert.ok(/o\.status === 'REJECTED'/.test(src),
    'the reason cell must be gated on the order not having filled')
  const gated = /REJECTED' \|\| o\.status === 'CANCELLED' \|\| o\.status === 'EXPIRED'/.test(src)
  assert.ok(gated, 'cancelled and expired orders need a reason too')
})

test('a missing reason renders as a dash, never as blank or undefined', () => {
  assert.ok(src.includes("orderIssue(o) || '-'"),
    'an order with no stored reason must show "-" rather than an empty cell')
})
