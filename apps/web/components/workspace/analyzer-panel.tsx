'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useMarketData } from '@/lib/use-market-data'
import { useUIStore } from '@/lib/stores/ui-store'
import { useToast } from '@/lib/use-toast'
import { api } from '@/lib/api'
import {
  type Candle, rsi, macd, adx, vwap, swings, trendLabel, aiSummary,
} from './indicator'

interface AnalyzerPanelProps {
  symbol: string
  name: string
  onClose: () => void
}

function fmt(v: number | null | undefined, d = 2): string {
  return v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(d)
}

function cell(label: string, value: string, tone?: 'up' | 'down' | '') {
  return (
    <div style={{ background: 'var(--bg-secondary)', borderRadius: 8, padding: '8px 10px', minWidth: 0 }}>
      <div className="t-stat-label" style={{ fontSize: 9 }}>{label}</div>
      <div className={`t-num ${tone}`} style={{ fontSize: 13, fontWeight: 700, marginTop: 2 }}>{value}</div>
    </div>
  )
}

export default function AnalyzerPanel({ symbol, name, onClose }: AnalyzerPanelProps) {
  const openQuickOrder = useUIStore(s => s.openQuickOrder)
  const { toast } = useToast()
  const { ticks, subscribe } = useMarketData()
  const [candles, setCandles] = useState<Candle[]>([])
  const [loading, setLoading] = useState(true)
  const [chainAt, setChainAt] = useState('')
  const [chain, setChain] = useState<{ rows: { strikePrice: number; call?: { oi: number }; put?: { oi: number } }[]; atm: number | null } | null>(null)
  const tick = ticks[symbol]

  useEffect(() => {
    if (symbol) subscribe([symbol])
  }, [subscribe, symbol])

  useEffect(() => {
    if (!symbol || chainAt === symbol) return
    setLoading(true)
    setChainAt(symbol)
    const sym = symbol.replace(/^NSE:/, '')
    Promise.all([
      api.marketdata.historical(sym, '1d', 90).catch(() => null),
      api.marketdata.historical(sym, '15m', 7).catch(() => null),
      api.marketdata.optionChain(sym).catch(() => null),
    ]).then(([daily, intraday, chainData]) => {
      const base = ((daily as { candles?: Candle[] })?.candles || []) as Candle[]
      const intra = ((intraday as { candles?: Candle[] })?.candles || []) as Candle[]
      setCandles(base.length >= 15 ? base : intra.length >= 15 ? intra : base)
      const rows = ((chainData as { optionChain?: { strikePrice: number; call?: { oi: number }; put?: { oi: number } }[] })?.optionChain || []) as { strikePrice: number; call?: { oi: number }; put?: { oi: number } }[]
      if (rows.length) {
        const last = base.length ? base[base.length - 1].close : intra.length ? intra[intra.length - 1].close : rows[0].strikePrice
        const atm = rows.reduce((best, r) => Math.abs(r.strikePrice - last) < Math.abs(best - last) ? r.strikePrice : best, rows[0].strikePrice)
        setChain({ rows, atm })
      } else {
        setChain(null)
      }
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [symbol, chainAt])

  const ind = useMemo(() => {
    if (candles.length < 15) return null
    const closes = candles.map(c => c.close)
    const highs = candles.map(c => c.high)
    const lows = candles.map(c => c.low)
    const r = rsi(closes)
    const m = macd(closes)
    const a = adx(highs, lows, closes)
    const v = vwap(candles)
    const sw = swings(candles)
    const last = candles.length - 1
    const ema9 = closes.slice(-9).reduce((x, y) => x + y, 0) / 9
    const ema21 = closes.slice(-21).reduce((x, y) => x + y, 0) / 21
    const support = sw.levels.filter(l => l.kind === 'support').map(l => l.price).sort((x, y) => y - x)[0] ?? null
    const resistance = sw.levels.filter(l => l.kind === 'resistance').map(l => l.price).sort((x, y) => x - y)[0] ?? null
    return {
      price: closes[last],
      rsi: r[last] as number | null,
      macd: m.macd[last] as number | null,
      signal: m.signal[last] as number | null,
      hist: m.hist[last] as number | null,
      adx: a[last] as number | null,
      vwap: v[last] as number | null,
      ema9, ema21,
      structure: sw.structure,
      support, resistance,
      swings: sw.levels,
    }
  }, [candles])

  const pcr = useMemo(() => {
    if (!chain || chain.rows.length < 4) return null
    const callOi = chain.rows.reduce((a, r) => a + (r.call?.oi || 0), 0)
    const putOi = chain.rows.reduce((a, r) => a + (r.put?.oi || 0), 0)
    return callOi > 0 ? putOi / callOi : null
  }, [chain])

  const summary = useMemo(() => {
    if (!ind) return 'Insufficient data — need ≥15 candles.'
    return aiSummary({
      trend: trendLabel(tick?.change_pct ?? undefined, ind.rsi, ind.vwap !== null && ind.price >= ind.vwap, ind.adx),
      structure: ind.structure,
      rsi: ind.rsi,
      aboveVwap: ind.vwap !== null && ind.price >= ind.vwap,
      macdHist: ind.hist,
      adx: ind.adx,
      pcr,
      support: ind.support,
      resistance: ind.resistance,
    })
  }, [ind, pcr, tick?.change_pct])

  const tradeSummary = useMemo(() => {
    if (!ind) return null
    const votes = [
      ind.rsi !== null ? (ind.rsi >= 55 ? 1 : ind.rsi <= 45 ? -1 : 0) : 0,
      ind.vwap !== null ? (ind.price >= ind.vwap ? 1 : -1) : 0,
      ind.hist !== null ? (ind.hist > 0 ? 1 : -1) : 0,
      pcr !== null ? (pcr > 1.1 ? 1 : pcr < 0.9 ? -1 : 0) : 0,
      ind.structure === 'HH' || ind.structure === 'HL' ? 1 : ind.structure === 'LH' || ind.structure === 'LL' ? -1 : 0,
    ]
    const score = votes.reduce((a, b) => a + b, 0)
    const bias = score >= 2 ? 'Bullish' : score <= -2 ? 'Bearish' : 'Neutral'
    const adx = ind.adx ?? 0
    const momentum = adx >= 25 ? 'Strong' : adx >= 15 ? 'Building' : 'Weak'
    const long = bias !== 'Bearish'
    const stop = long ? ind.support : ind.resistance
    const tgt = long ? ind.resistance : ind.support
    const risk = (() => {
      if (!stop || ind.price <= 0) return 'Medium'
      const d = Math.abs(ind.price - stop) / ind.price
      return d < 0.02 ? 'Low' : d < 0.05 ? 'Medium' : 'High'
    })()
    const voted = votes.filter(v => v !== 0).length || 1
    const confidence = Math.min(95, Math.round(50 + (Math.abs(score) / voted) * 42 + (adx >= 25 ? 5 : 0)))
    return {
      bias, momentum, rsi: ind.rsi, vwap: ind.vwap !== null && ind.price >= ind.vwap ? 'Above' : ind.vwap !== null ? 'Below' : '—',
      structure: ind.structure, risk, confidence,
      stop, tgt,
      stopDist: stop && ind.price > 0 ? (Math.abs(ind.price - stop) / ind.price) * 100 : null,
    }
  }, [ind, pcr])

  const risk = useMemo(() => {
    if (!ind || ind.support === null || ind.resistance === null) return null
    const dist = (ind.price - ind.support) / ind.price
    const rr = (ind.resistance - ind.price) / Math.max(ind.price - ind.support, 1e-9)
    return { dist, rr }
  }, [ind])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{
        padding: '10px 12px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 800 }}>🔬 Analyzer</div>
          <div className="t-faint" style={{ fontSize: 10 }}>{name} · {symbol}</div>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className="t-btn t-btn-sm" style={{ color: 'var(--green)' }} onClick={() => openQuickOrder(symbol, name, 'BUY')}>Buy</button>
          <button className="t-btn t-btn-sm" style={{ color: 'var(--red)' }} onClick={() => openQuickOrder(symbol, name, 'SELL')}>Sell</button>
          <button className="t-btn t-btn-sm t-btn-ghost" onClick={onClose}>✕</button>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {loading && <span className="t-faint" style={{ fontSize: 11 }}>Loading indicators…</span>}
        {!loading && ind && (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(86px, 1fr))', gap: 6 }}>
              {cell('PRICE', fmt(ind.price, 1))}
              {cell('VWAP', fmt(ind.vwap))}
              {cell('EMA 9/21', `${fmt(ind.ema9, 0)}/${fmt(ind.ema21, 0)}`)}
              {cell('RSI 14', fmt(ind.rsi), ind.rsi !== null ? (ind.rsi >= 55 ? 'up' : ind.rsi <= 45 ? 'down' : '') : '')}
              {cell('MACD', fmt(ind.macd, 2), ind.hist !== null ? (ind.hist >= 0 ? 'up' : 'down') : '')}
              {cell('SIGNAL', fmt(ind.signal, 2))}
              {cell('HIST', fmt(ind.hist, 2), ind.hist !== null ? (ind.hist >= 0 ? 'up' : 'down') : '')}
              {cell('ADX', fmt(ind.adx, 1), ind.adx !== null ? (ind.adx >= 25 ? 'up' : '') : '')}
              {cell('PCR', fmt(pcr, 2), pcr !== null ? (pcr >= 1.1 ? 'up' : 'down') : '')}
              {cell('STRUCTURE', ind.structure, ind.structure === 'HH' || ind.structure === 'HL' ? 'up' : ind.structure === 'LL' || ind.structure === 'LH' ? 'down' : '')}
            </div>

            <div className="t-panel">
              <div className="t-panel-header" style={{ fontSize: 10, fontWeight: 800 }}>SMC / SWING LEVELS</div>
              <div className="t-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {ind.swings.length === 0 && <span className="t-faint" style={{ fontSize: 10 }}>No swing levels</span>}
                {ind.swings.map((s, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                    <span style={{ fontWeight: 600 }}>{s.kind === 'resistance' ? 'Resistance' : 'Support'}</span>
                    <span className="t-num" style={{ color: s.kind === 'resistance' ? 'var(--green)' : 'var(--red)' }}>{fmt(s.price, 1)}</span>
                  </div>
                ))}
              </div>
            </div>

            {risk && (
              <div style={{ display: 'flex', gap: 6 }}>
                <span className="t-chip" style={{ fontSize: 9 }}>Risk {Math.abs(risk.dist * 100).toFixed(1)}% to S</span>
                <span className="t-chip" style={{ fontSize: 9 }}>RR {risk.rr.toFixed(2)}:1</span>
              </div>
            )}

            <div className="t-panel" style={{ borderLeft: `3px solid ${tradeSummary?.bias === 'Bullish' ? 'var(--green)' : tradeSummary?.bias === 'Bearish' ? 'var(--red)' : 'var(--amber)'}` }}>
              <div className="t-panel-header" style={{ fontSize: 10, fontWeight: 800 }}>TRADE SUMMARY</div>
              <div className="t-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {tradeSummary ? (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span className={`t-badge ${tradeSummary.bias === 'Bullish' ? 't-badge-green' : tradeSummary.bias === 'Bearish' ? 't-badge-red' : 't-badge-amber'}`} style={{ fontSize: 10, fontWeight: 800 }}>
                        {tradeSummary.bias}
                      </span>
                      <span className="t-faint" style={{ fontSize: 10 }}>Momentum {tradeSummary.momentum} · Risk {tradeSummary.risk}</span>
                      <span className="t-num" style={{ fontSize: 10, marginLeft: 'auto' }}>Confidence {tradeSummary.confidence}%</span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, fontSize: 10 }}>
                      <span className="t-faint">RSI</span><span className="t-num">{fmt(tradeSummary.rsi)}</span>
                      <span className="t-faint">VWAP</span><span className="t-num">{tradeSummary.vwap}</span>
                      <span className="t-faint">Structure</span><span className="t-num">{tradeSummary.structure}</span>
                      <span className="t-faint">Suggested risk</span>
                      <span className="t-num">{tradeSummary.stopDist !== null ? `${tradeSummary.stopDist.toFixed(1)}% to stop` : '—'}</span>
                      <span className="t-faint">Suggested stop</span>
                      <span className="t-num t-down">{tradeSummary.stop ? fmt(tradeSummary.stop) : '—'}</span>
                      <span className="t-faint">Suggested target</span>
                      <span className="t-num t-up">{tradeSummary.tgt ? fmt(tradeSummary.tgt) : '—'}</span>
                    </div>
                    <div className="t-faint" style={{ fontSize: 8.5, lineHeight: 1.4 }}>
                      Rule-based summary of the indicator grid above — analytics only, not a trading signal.
                    </div>
                  </>
                ) : (
                  <span className="t-faint" style={{ fontSize: 10 }}>Needs ≥15 candles.</span>
                )}
              </div>
            </div>

            <div className="t-panel" style={{ borderLeft: '3px solid var(--cyan)' }}>
              <div className="t-panel-header" style={{ fontSize: 10, fontWeight: 800 }}>AI SUMMARY</div>
              <div className="t-panel-body t-faint" style={{ fontSize: 11, lineHeight: 1.55 }}>{summary}</div>
            </div>

            <div style={{ display: 'flex', gap: 6, marginTop: 2 }}>
              <button className="t-btn t-btn-sm" style={{ flex: 1 }} onClick={() => openQuickOrder(symbol, name)}>Trade</button>
              <button className="t-btn t-btn-sm" style={{ flex: 1 }} onClick={() => toast('info', 'Backtest opens with strategy builder')}>Backtest</button>
              <button className="t-btn t-btn-sm" style={{ flex: 1 }} onClick={() => window.location.assign('/strategies')}>Strategy</button>
            </div>
          </>
        )}
        {!loading && !ind && <span className="t-faint" style={{ fontSize: 11 }}>Insufficient data.</span>}
      </div>
    </div>
  )
}
