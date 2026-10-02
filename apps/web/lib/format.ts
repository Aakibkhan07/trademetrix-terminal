/**
 * Number formatting that cannot throw.
 *
 * Every function here exists because of one recurring crash. The pattern that produced it:
 *
 *     {row.latency_ms !== null ? row.latency_ms.toFixed(1) : '-'}
 *     {data ? `${data.max_drawdown.toFixed(1)}%` : '—'}
 *
 * Both guards read as safe and are not. `undefined !== null` is **true**, so a field the
 * response simply did not include passes the guard and then throws on `.toFixed`. The second
 * checks that the *envelope* exists, not the *field*, so it protects nothing.
 *
 * That is not hypothetical. `/transparency` crashed on every render with
 * "Cannot read properties of undefined (reading 'toFixed')", and `/reports/daily` crashed on
 * `max_drawdown` the same way. Both reached the app's error boundary, so each page was a
 * "Something went wrong" panel rather than a page.
 *
 * The fix is not to find every `!== null` — there are dozens and more will be written. It is to
 * make the safe form the short one, so the next page reaches for `fmtNum` instead of
 * re-deriving a guard. `isNum` is the single place that decides what counts as a number.
 */

/** True only for a real, finite number. `NaN` and `Infinity` are not numbers worth printing. */
export function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

/** Coerce anything into a finite number, or `null`. Brokers do send numeric strings. */
export function numOrNull(v: unknown): number | null {
  if (isNum(v)) return v
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

/** What every formatter below prints when there is genuinely nothing to show. */
export const NO_VALUE = '—'

/** Fixed decimals, or a dash. `fmtNum(1.005, 1)` is `'1.0'` — `toFixed` semantics, unchanged. */
export function fmtNum(v: unknown, decimals = 2): string {
  const n = numOrNull(v)
  return n === null ? NO_VALUE : n.toFixed(decimals)
}

/** Fixed decimals with an explicit `+` on positives, or a dash. */
export function fmtSigned(v: unknown, decimals = 2): string {
  const n = numOrNull(v)
  if (n === null) return NO_VALUE
  return `${n >= 0 ? '+' : ''}${n.toFixed(decimals)}`
}

/**
 * Indian digit grouping — `12,34,567` — or a dash.
 *
 * `toLocaleString('en-IN')` with `maximumFractionDigits: 0`, matching the convention used
 * across the money pages.
 */
export function fmtMoney(v: unknown, decimals = 0): string {
  const n = numOrNull(v)
  if (n === null) return NO_VALUE
  return n.toLocaleString('en-IN', { maximumFractionDigits: decimals })
}

/**
 * Money with an explicit sign, or a dash.
 *
 * The sign goes **before** the symbol: `-₹45,000`, not `₹-45,000`. That is the Indian
 * convention and what the rest of the app already renders, but it is not what falls out of
 * `toLocaleString` — that places the minus directly before the digits, so naively prefixing
 * `₹` yields `₹-45,000`. The magnitude is formatted separately from the sign for that reason.
 * Caught by the assertion in `format.test.ts` on the first run.
 */
export function fmtSignedMoney(v: unknown, decimals = 0): string {
  const n = numOrNull(v)
  if (n === null) return NO_VALUE
  const body = Math.abs(n).toLocaleString('en-IN', { maximumFractionDigits: decimals })
  return `${n < 0 ? '-' : '+'}₹${body}`
}

/** A percentage with an explicit `+` on positives, or a dash. */
export function fmtPct(v: unknown, decimals = 2): string {
  const n = numOrNull(v)
  if (n === null) return NO_VALUE
  return `${n >= 0 ? '+' : ''}${n.toFixed(decimals)}%`
}

/** A whole percentage without a sign — for rates like win rate, which are not deltas. */
export function fmtRate(v: unknown, decimals = 1): string {
  const n = numOrNull(v)
  return n === null ? NO_VALUE : `${n.toFixed(decimals)}%`
}

/**
 * A number with a unit suffix, or a dash.
 *
 * For columns like "Latency" and "Slippage" where the unit is part of the cell. Built on
 * `fmtNum` so it cannot reintroduce the unguarded `toFixed`.
 */
export function fmtWithUnit(v: unknown, decimals: number, unit: string): string {
  const n = numOrNull(v)
  return n === null ? NO_VALUE : `${n.toFixed(decimals)}${unit}`
}

/**
 * A field for which "absent" and "zero" must not be confused.
 *
 * Returns `null` when the key is missing or nullish, and the number otherwise. This is the
 * shape to reach for when a *zero* is a meaningful value and absence should render differently
 * — a slippage of exactly `0` is good news, whereas a missing `slippage` is no information.
 */
export function field(v: unknown): number | null {
  return v === null || v === undefined ? null : numOrNull(v)
}
