/**
 * The two shapes of `/analytics/pnl`, and the tiles built from them.
 *
 * `GET /analytics/pnl` returns a different body depending on `period`, and this is the
 * whole reason `lib/pnl.ts` exists:
 *
 *   period=1d  ->  { pnl: { daily: <number> }, period, broker }
 *   period=1w  ->  { pnl: PortfolioPnL, period, broker }
 *
 * where `PortfolioPnL` carries `realised_pnl`, `unrealised_pnl`, `daily_pnl`,
 * `weekly_pnl`, `monthly_pnl`, `overall_pnl` and `drawdown_pct`. A `period=1d` response has
 * exactly one field. It never carries the other seven, and no amount of asking will make it.
 *
 * `/funds` used to declare one interface spanning both shapes and read all three of its
 * numbers out of a single `period=1d` call. TypeScript was satisfied; two of the three
 * P&L tiles were permanently zero. Worse, `?? 0` rendered that absence as `₹0` rather than a
 * dash, so a tenant with real open profits was shown as flat — the most expensive kind of
 * wrong, because it looks like data.
 *
 * The tiles are built here rather than inline in the page so the mapping can be asserted.
 * A null value means "this response does not carry that figure" and must survive as null all
 * the way to the screen; it is never a zero.
 */

/** What a `period=1d` response carries. One field, and that is all. */
export interface DailyPnl {
  daily?: number | null
}

/** `PortfolioPnL` — what every non-`1d` period returns. */
export interface CumulativePnl {
  realised_pnl?: number | null
  unrealised_pnl?: number | null
  daily_pnl?: number | null
  weekly_pnl?: number | null
  monthly_pnl?: number | null
  overall_pnl?: number | null
  drawdown_pct?: number | null
}

export interface PnlEnvelope<T> {
  pnl: T | null
  period: string
  broker: string | null
}

export interface PnlTile {
  label: string
  /** `null` means unavailable. Distinct from `0`, which means available and flat. */
  value: number | null
  /** Where the figure comes from, shown under the number so a dash is self-explaining. */
  hint: string
  /** 'up' | 'down' | 'unknown' — a dash is grey, never green or red. */
  tone: 'up' | 'down' | 'unknown'
}

/** Coerce a broker-supplied number, rejecting anything that is not finite. */
function num(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

function tone(v: number | null): PnlTile['tone'] {
  if (v === null) return 'unknown'
  return v >= 0 ? 'up' : 'down'
}

/**
 * The three P&L tiles `/funds` shows, from the two responses it fetches.
 *
 * `daily` comes from the `1d` response and the other two from the cumulative one. If you
 * pass the same response as both arguments, the two cumulative tiles come back `null` —
 * which is the correct, visible answer for that mistake, rather than the silent zero the
 * inline version produced.
 */
export function pnlTiles(
  dailyResponse: PnlEnvelope<DailyPnl> | null | undefined,
  cumulativeResponse: PnlEnvelope<CumulativePnl> | null | undefined,
): PnlTile[] {
  const daily = num(dailyResponse?.pnl?.daily)
  const realised = num(cumulativeResponse?.pnl?.realised_pnl)
  const unrealised = num(cumulativeResponse?.pnl?.unrealised_pnl)

  return [
    { label: 'Today (realized)', value: daily, hint: dailyResponse?.period ?? '1d', tone: tone(daily) },
    { label: 'Realized', value: realised, hint: 'all time', tone: tone(realised) },
    { label: 'Unrealized', value: unrealised, hint: 'open positions', tone: tone(unrealised) },
  ]
}

/**
 * Format a tile's value for display.
 *
 * `null` is a dash. Zero is `+0`. Collapsing those two is the bug: a user cannot tell "you
 * made nothing" from "I could not read this", and on a money page the second is a claim the
 * system should never make.
 */
export function formatPnlTile(value: number | null): string {
  if (value === null) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(0)}`
}
