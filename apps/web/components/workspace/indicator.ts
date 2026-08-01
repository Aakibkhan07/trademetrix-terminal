export interface Candle {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export function ema(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null)
  if (values.length < period) return out
  const k = 2 / (period + 1)
  let prev = values.slice(0, period).reduce((a, b) => a + b, 0) / period
  out[period - 1] = prev
  for (let i = period; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k)
    out[i] = prev
  }
  return out
}

export function rsi(closes: number[], period = 14): (number | null)[] {
  const out: (number | null)[] = new Array(closes.length).fill(null)
  if (closes.length <= period) return out
  let gain = 0
  let loss = 0
  for (let i = 1; i <= period; i++) {
    const d = closes[i] - closes[i - 1]
    if (d >= 0) gain += d; else loss -= d
  }
  let avgGain = gain / period
  let avgLoss = loss / period
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)
  for (let i = period + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1]
    avgGain = (avgGain * (period - 1) + Math.max(d, 0)) / period
    avgLoss = (avgLoss * (period - 1) + Math.max(-d, 0)) / period
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)
  }
  return out
}

export function macd(closes: number[]): { macd: (number | null)[]; signal: (number | null)[]; hist: (number | null)[] } {
  const e12 = ema(closes, 12)
  const e26 = ema(closes, 26)
  const macdLine = closes.map((_, i) => (e12[i] !== null && e26[i] !== null ? (e12[i] as number) - (e26[i] as number) : null))
  const macdVals = macdLine.filter((v): v is number => v !== null)
  const signalLine: (number | null)[] = new Array(closes.length).fill(null)
  const sig = ema(macdVals, 9)
  let j = 0
  for (let i = 0; i < closes.length; i++) {
    if (macdLine[i] !== null) { signalLine[i] = sig[j]; j++ }
  }
  const hist = macdLine.map((v, i) => (v !== null && signalLine[i] !== null ? v - (signalLine[i] as number) : null))
  return { macd: macdLine, signal: signalLine, hist }
}

export function adx(highs: number[], lows: number[], closes: number[], period = 14): (number | null)[] {
  const out: (number | null)[] = new Array(highs.length).fill(null)
  if (highs.length <= period * 2) return out
  const plusDM: number[] = []
  const minusDM: number[] = []
  const tr: number[] = []
  for (let i = 1; i < highs.length; i++) {
    const up = highs[i] - highs[i - 1]
    const down = lows[i - 1] - lows[i]
    plusDM.push(up > down && up > 0 ? up : 0)
    minusDM.push(down > up && down > 0 ? down : 0)
    tr.push(Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1])))
  }
  let atr = tr.slice(0, period).reduce((a, b) => a + b, 0) / period
  let pdi = (plusDM.slice(0, period).reduce((a, b) => a + b, 0) / atr) * 100
  let mdi = (minusDM.slice(0, period).reduce((a, b) => a + b, 0) / atr) * 100
  let dx = (Math.abs(pdi - mdi) / Math.max(pdi + mdi, 1e-9)) * 100
  let adxVal = dx
  for (let i = period; i < tr.length; i++) {
    atr = (atr * (period - 1) + tr[i]) / period
    pdi = ((pdi * (period - 1) + plusDM[i]) / atr) * 100
    mdi = ((mdi * (period - 1) + minusDM[i]) / atr) * 100
    dx = (Math.abs(pdi - mdi) / Math.max(pdi + mdi, 1e-9)) * 100
    adxVal = (adxVal * (period - 1) + dx) / period
    out[i + 1] = adxVal
  }
  return out
}

export function vwap(candles: Candle[]): (number | null)[] {
  const out: (number | null)[] = new Array(candles.length).fill(null)
  let cumPV = 0
  let cumV = 0
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i]
    const typ = (c.high + c.low + c.close) / 3
    const v = c.volume || 0
    cumPV += typ * v
    cumV += v
    out[i] = cumV > 0 ? cumPV / cumV : null
  }
  return out
}

export interface SwingLevel { price: number; kind: 'support' | 'resistance'; index: number }

export function swings(candles: Candle[], window = 5): { levels: SwingLevel[]; structure: 'HH' | 'HL' | 'LH' | 'LL' | '—' } {
  const levels: SwingLevel[] = []
  for (let i = window; i < candles.length - window; i++) {
    const c = candles[i]
    let isHigh = true
    let isLow = true
    for (let j = i - window; j <= i + window; j++) {
      if (j === i) continue
      if (candles[j].high >= c.high) isHigh = false
      if (candles[j].low <= c.low) isLow = false
    }
    if (isHigh) levels.push({ price: c.high, kind: 'resistance', index: i })
    if (isLow) levels.push({ price: c.low, kind: 'support', index: i })
  }
  const recent = levels.slice(-4)
  let structure: 'HH' | 'HL' | 'LH' | 'LL' | '—' = '—'
  if (recent.length >= 3) {
    const highs = recent.filter(l => l.kind === 'resistance').map(l => l.price)
    const lows = recent.filter(l => l.kind === 'support').map(l => l.price)
    const lastHigh = highs[highs.length - 1]
    const prevHigh = highs[highs.length - 2]
    const lastLow = lows[lows.length - 1]
    const prevLow = lows[lows.length - 2]
    if (lastHigh !== undefined && prevHigh !== undefined && lastLow !== undefined && prevLow !== undefined) {
      if (lastHigh > prevHigh && lastLow > prevLow) structure = 'HH'
      else if (lastHigh > prevHigh) structure = 'HL'
      else if (lastHigh < prevHigh && lastLow < prevLow) structure = 'LL'
      else if (lastHigh < prevHigh) structure = 'LH'
    }
  }
  return { levels: levels.slice(-6), structure }
}

export function trendLabel(changePct: number | undefined, rsiVal: number | null, aboveVwap: boolean | null, adxVal: number | null): string {
  const parts: string[] = []
  if (rsiVal !== null) parts.push(rsiVal >= 55 ? 'RSI bullish' : rsiVal <= 45 ? 'RSI bearish' : 'RSI neutral')
  if (aboveVwap !== null) parts.push(aboveVwap ? 'above VWAP' : 'below VWAP')
  if (adxVal !== null) parts.push(adxVal >= 25 ? `trend ${adxVal >= 40 ? 'strong' : 'firming'}` : 'range-bound')
  if (changePct !== undefined && Math.abs(changePct) >= 1) parts.push(`${changePct >= 0 ? 'up' : 'down'} ${Math.abs(changePct).toFixed(2)}%`)
  return parts.length ? parts.join(', ') : 'No data'
}

export function aiSummary(opts: {
  trend: string; structure: string; rsi: number | null; aboveVwap: boolean | null
  macdHist: number | null; adx: number | null; pcr: number | null; support: number | null; resistance: number | null
}): string {
  const score = [
    opts.rsi !== null && opts.rsi >= 55 ? 1 : opts.rsi !== null && opts.rsi <= 45 ? -1 : 0,
    opts.aboveVwap === true ? 1 : opts.aboveVwap === false ? -1 : 0,
    opts.macdHist !== null && opts.macdHist > 0 ? 1 : opts.macdHist !== null ? -1 : 0,
    opts.pcr !== null && opts.pcr > 1.1 ? 1 : opts.pcr !== null && opts.pcr < 0.9 ? -1 : 0,
  ].reduce((a, b) => a + b, 0)
  const bias = score > 0 ? 'bullish' : score < 0 ? 'bearish' : 'neutral'
  const parts: string[] = [`${bias.toUpperCase()} bias (${Math.abs(score)}/4 confirmations)`]
  if (opts.structure !== '—') parts.push(`structure ${opts.structure}`)
  if (opts.support !== null && opts.resistance !== null) {
    parts.push(`range ₹${opts.support.toFixed(2)}–₹${opts.resistance.toFixed(2)}`)
  }
  if (opts.adx !== null) parts.push(opts.adx >= 25 ? `trend strength ADX ${opts.adx.toFixed(1)}` : 'no strong trend')
  parts.push(opts.trend)
  return parts.join('. ')
}
