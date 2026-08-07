'use client'

/**
 * Index-options domain helpers for the trader workspace.
 *
 * Everything the trader picks (INDEX → EXPIRY → MONEYNESS → CE/PE → LOTS) is
 * converted here into exchange-level values (strike, lot size, quantity, margin
 * request, engine symbol). No user ever types a symbol, strike or quantity.
 *
 * Data sources (existing APIs only):
 *  - spot: marketdata WS ticks / `api.marketdata.quote`
 *  - chain + expiries: `api.marketdata.optionChain`
 *  - lot size: `/marketdata/instruments` (NSE_FO master), fallback map below
 *  - margin: `api.marginEstimate` (SPAN + exposure + total)
 */

export type IndexKey = 'NIFTY' | 'BANKNIFTY' | 'FINNIFTY' | 'MIDCPNIFTY' | 'SENSEX'

export interface IndexMeta {
  key: IndexKey
  name: string
  spotSymbol: string
  /** Fallback lot size — always overridden from the instrument master when reachable. */
  fallbackLot: number
  /** Typical strike interval for ATM-offset math. */
  strikeInterval: number
}

export const INDEXES: IndexMeta[] = [
  { key: 'NIFTY', name: 'NIFTY', spotSymbol: 'NSE:NIFTY50-INDEX', fallbackLot: 50, strikeInterval: 50 },
  { key: 'BANKNIFTY', name: 'BANKNIFTY', spotSymbol: 'NSE:NIFTYBANK-INDEX', fallbackLot: 15, strikeInterval: 100 },
  { key: 'FINNIFTY', name: 'FINNIFTY', spotSymbol: 'NSE:FINNIFTY-INDEX', fallbackLot: 40, strikeInterval: 50 },
  { key: 'MIDCPNIFTY', name: 'MIDCPNIFTY', spotSymbol: 'NSE:MIDCPNIFTY-INDEX', fallbackLot: 75, strikeInterval: 25 },
  { key: 'SENSEX', name: 'SENSEX', spotSymbol: 'BSE:SENSEX-INDEX', fallbackLot: 10, strikeInterval: 100 },
]

export function indexMeta(key: IndexKey): IndexMeta {
  return INDEXES.find(i => i.key === key) || INDEXES[0]
}

/** Moneyness selection in trader terms. Offset = strike-interval steps from ATM. */
export type Moneyness = 'ATM' | 'ATM_P1' | 'ATM_P2' | 'ATM_M1' | 'ATM_M2' | 'CUSTOM'

export const MONEYNESS_OPTIONS: { key: Moneyness; label: string; offsetSteps: number }[] = [
  { key: 'ATM', label: 'ATM', offsetSteps: 0 },
  { key: 'ATM_P1', label: 'ATM +1', offsetSteps: 1 },
  { key: 'ATM_P2', label: 'ATM +2', offsetSteps: 2 },
  { key: 'ATM_M1', label: 'ATM −1', offsetSteps: -1 },
  { key: 'ATM_M2', label: 'ATM −2', offsetSteps: -2 },
]

/** Nearest chain strike to a target (spot or target price). */
export function nearestStrike(chainStrikes: number[], target: number): number | null {
  if (!chainStrikes.length) return null
  let best = chainStrikes[0]
  let bestDiff = Math.abs(best - target)
  for (const s of chainStrikes) {
    const d = Math.abs(s - target)
    if (d < bestDiff) { best = s; bestDiff = d }
  }
  return best
}

/** Moneyness → target strike: ATM round of spot, ± interval steps (not chain-clamped here). */
export function moneynessTargetStrike(meta: IndexMeta, spot: number, moneyness: Moneyness, customStrike: number | null): number | null {
  if (moneyness === 'CUSTOM') return customStrike
  if (!isFinite(spot)) return null
  const atm = Math.round(spot / meta.strikeInterval) * meta.strikeInterval
  const step = MONEYNESS_OPTIONS.find(o => o.key === moneyness)?.offsetSteps || 0
  return atm + step * meta.strikeInterval
}

export interface GeneratedContract {
  index: IndexKey
  spot: number | null
  atmStrike: number | null
  strike: number | null
  strikeLabel: string
  optionType: 'CE' | 'PE'
  expiry: string
  expiryGroup: 'weekly' | 'monthly'
  lots: number
  lotSize: number
  quantity: number
  /** Compact engine symbol, e.g. NIFTY26AUG24450CE. */
  symbol: string
}

/** Group raw expiry codes (e.g. "26AUG") into nearest (weekly-ish) and farthest (monthly-ish). */
export function groupExpiries(expiries: string[]): { weekly: string | null; monthly: string | null; all: string[] } {
  if (!expiries.length) return { weekly: null, monthly: null, all: [] }
  return { weekly: expiries[0], monthly: expiries[expiries.length - 1], all: expiries }
}

/** Build the full trader selection → exchange contract. Never requires typing. */
export function buildContract(opts: {
  index: IndexKey
  spot: number | null
  chainStrikes: number[]
  moneyness: Moneyness
  customStrike: number | null
  optionType: 'CE' | 'PE'
  expiry: string
  expiryGroup: 'weekly' | 'monthly'
  lots: number
  lotSize: number
}): GeneratedContract {
  const meta = indexMeta(opts.index)
  const target = moneynessTargetStrike(meta, opts.spot || NaN, opts.moneyness, opts.customStrike)
  const strike = target !== null ? nearestStrike(opts.chainStrikes, target) : null
  const atmStrike = opts.spot ? nearestStrike(opts.chainStrikes, opts.spot) : null
  const qty = opts.lots * opts.lotSize
  return {
    index: opts.index,
    spot: opts.spot,
    atmStrike,
    strike,
    strikeLabel: strike !== null ? String(strike) : '—',
    optionType: opts.optionType,
    expiry: opts.expiry,
    expiryGroup: opts.expiryGroup,
    lots: opts.lots,
    lotSize: opts.lotSize,
    quantity: qty,
    symbol: strike !== null ? `${opts.index}${opts.expiry}${strike}${opts.optionType}` : '',
  }
}

/** Client-side charges estimate (informational; brokerage ₹20 flat + STT intraday + exchange). */
export function estimateCharges(quantity: number, premium: number, side: 'BUY' | 'SELL'): { brokerage: number; stt: number; exchange: number; total: number } {
  const brokerage = quantity > 0 ? 20 : 0
  const notional = quantity * premium
  const stt = side === 'SELL' ? notional * 0.001 : 0
  const exchange = notional * 0.0003
  return { brokerage, stt, exchange, total: brokerage + stt + exchange }
}

/** Map trader selection → /margin-estimate leg (the API already speaks this language). */
export function marginLeg(opts: {
  position: 'buy' | 'sell'
  optionType: 'CE' | 'PE'
  lots: number
  strikeCriteria: 'atm_offset'
  strikeValue: number
}) {
  return {
    segment: 'options',
    position: opts.position,
    lots: opts.lots,
    option_type: opts.optionType,
    expiry: 'weekly',
    strike_criteria: opts.strikeCriteria,
    strike_value: opts.strikeValue,
  }
}

/** Resolve the current lot size for an index from the instrument master (NSE_FO), with fallback. */
export async function fetchLotSize(index: IndexKey, api: {
  get: <T>(path: string, signal?: AbortSignal) => Promise<T>
}): Promise<number> {
  const fallback = indexMeta(index).fallbackLot
  try {
    const d = await api.get<{ instruments?: { symbol?: string; lot_size?: number; instrument_type?: string }[] }>(
      `/marketdata/instruments?query=${encodeURIComponent(index)}&instrument_type=OPT&limit=20`,
    )
    const list = d.instruments || []
    const found = list.find(i => (i.lot_size || 0) > 1) || list.find(i => (i.symbol || '').toUpperCase().startsWith(index))
    return found?.lot_size && found.lot_size > 1 ? found.lot_size : fallback
  } catch {
    return fallback
  }
}
