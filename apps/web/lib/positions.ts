/**
 * Position arithmetic, in one place, because getting it wrong is silent.
 *
 * Two independent bugs lived in this file's callers before it existed, and both showed a
 * confident number rather than an error:
 *
 * **1. Shorts were computed with the long formula.** Both `/portal` and `/terminal` did
 *
 *     pnl = quantity * (ltp - average_buy_price)
 *
 * which is correct only for a long. `quantity` is signed — a Fyers v3 `netQty` short is
 * negative, and a prod probe in AGENTS.md v1.5.7 recorded one at `-192` — so for a short
 * this used the wrong basis price *and* inverted the sign. A short opened at 100 and
 * trading at 90 is +1920 of profit; the old formula reported a large loss, and the row was
 * coloured as one. AGENTS.md v1.5.9 spells the rule out for the backtest engine — "LONG
 * entry = average_buy_price, SHORT entry = average_sell_price" — so the backend already
 * knew it and these two pages did not.
 *
 * **2. A zero-price quote was treated as a real price.** Symbols the fallback provider
 * cannot resolve come back as `{last_price: 0}` — documented in AGENTS.md v1.5.6 — and
 * the established guard is `last_price > 0`, used in `/trade` and `/terminal` for exactly
 * this reason. `/portal` had no such guard, so a zero tick produced
 * `quantity * (0 - average_buy_price)`: a large fabricated loss on a live row.
 *
 * Both callers now read their P&L from here. The fallback in every case is the broker's
 * own `unrealised_pnl`, which is the only figure here that does not depend on a price we
 * failed to read.
 */

/**
 * Which way a position points.
 *
 * **Not `"BUY"` / `"SELL"`, and that is the whole point of naming them here.**
 * `execution_engine/positions.py` defines `LONG = "LONG"` / `SHORT = "SHORT"` / `FLAT =
 * "FLAT"` and assigns `side` from the sign of the net quantity. Orders and fills use a
 * genuinely different vocabulary — `OrderSide.BUY` / `SELL` in `core/models.py` — and the two
 * never mix within one response.
 *
 * `/paper` compared a *position's* `side` against `'BUY'`, which is never true, so every row
 * on that table rendered in the loss colour: a profitable long showed the text `LONG` in red,
 * and a short showed `SHORT` in red for the right reason by coincidence. The comparison
 * could not distinguish the two cases, so the colour carried no information at all.
 *
 * Ten sites in the web app compare `.side` against `'BUY'`; only the one reading a position
 * was wrong. That is the hazard — the vocabulary is per-response, and TypeScript cannot see
 * it, so the wrong comparison type-checks. Naming it once here is cheaper than auditing ten
 * sites every time a comparison moves.
 */
export type PositionSide = 'LONG' | 'SHORT' | 'FLAT'

/** The three values the engine actually stores. */
const POSITION_SIDES: ReadonlySet<string> = new Set<PositionSide>(['LONG', 'SHORT', 'FLAT'])

/**
 * A position's direction, preferring the value the API sent.
 *
 * Falls back to the sign of `quantity`, which is what `positions.py` uses to derive `side` in
 * the first place — so a payload that omits or misspells the field still classifies correctly
 * rather than silently reading as flat. An unrecognised `side` is treated as absent rather
 * than trusted, because a colour that means nothing is worse than one derived from the sign.
 */
export function positionSide(p: { side?: unknown; quantity?: number | string }): PositionSide {
  if (typeof p.side === 'string') {
    const upper = p.side.toUpperCase()
    if (POSITION_SIDES.has(upper)) return upper as PositionSide
  }
  const qty = num(p.quantity)
  return qty > 0 ? 'LONG' : qty < 0 ? 'SHORT' : 'FLAT'
}

/** True when the position is long. The only question the Side column is actually asking. */
export function isLong(p: { side?: unknown; quantity?: number | string }): boolean {
  return positionSide(p) === 'LONG'
}

/**
 * The shape these helpers need. Every field optional, because it is a broker response.
 *
 * `number | string` is not hedging — it is what the brokers actually send. Dhan's margin
 * payload returns `availablecash: "0.00"`, and a `number`-only type would make every
 * helper quietly coerce, or worse, produce `NaN`, on a value that was always a legitimate
 * string. Typing it as `number` would have hidden the coercion this file performs.
 */
export interface PositionLike {
  quantity?: number | string
  average_buy_price?: number | string
  average_sell_price?: number | string
  unrealised_pnl?: number | string
  realised_pnl?: number | string
  last_price?: number | string
}

/**
 * A price is authoritative only when it is positive.
 *
 * Not a truthiness check: `{last_price: 0}` is how the fallback provider reports a symbol
 * it cannot resolve, and treating that as a price is the bug this guard exists for.
 */
export function usablePrice(price: number | string | null | undefined): number | null {
  // Coerced rather than type-checked. Some brokers send prices as strings — Dhan's
  // margin payload returns `availablecash: "0.00"` — and rejecting a string price would
  // silently fall back to the broker's own P&L for a symbol that *does* have a live
  // price. Only a value that does not coerce to a positive number is unusable.
  const n = num(price)
  return n > 0 ? n : null
}

/**
 * Unrealised P&L for one position.
 *
 * `price` is the live price if there is a trustworthy one, otherwise the position's own
 * `last_price`, otherwise nothing. When no price can be trusted, the broker's
 * `unrealised_pnl` is returned — correct by definition, since it is the figure the broker
 * computed from a price it *could* read.
 */
export function positionPnl(p: PositionLike, price?: number | string | null): number {
  const live = usablePrice(price)
  if (live === null) return num(p.unrealised_pnl)

  const qty = num(p.quantity)
  if (qty >= 0) {
    // Long: bought at the average buy price, now worth `live`.
    return qty * (live - num(p.average_buy_price))
  }

  // Short: `qty` is negative, so the size is its negation. Sold at the average sell
  // price and now worth `live`, so the position gains when the price falls.
  //
  // `average_sell_price` is the basis. A position that has only ever been short has no
  // meaningful average buy price, so using it would price the short off a number the
  // broker never filled it at.
  const basis = num(p.average_sell_price) || num(p.average_buy_price)
  return -qty * (basis - live)
}

/** The price a row should display as "last traded", or null when none is trustworthy. */
export function displayPrice(p: PositionLike, price?: number | string | null): number | null {
  return usablePrice(price) ?? usablePrice(p.last_price)
}

/** Coerce to a finite number or 0, so a string price never renders as NaN. */
function num(v: unknown): number {
  const n = typeof v === 'number' ? v : typeof v === 'string' ? Number(v) : NaN
  return Number.isFinite(n) ? n : 0
}
