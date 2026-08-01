'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useMarketData, type TickData } from '@/lib/use-market-data'
import { api } from '@/lib/api'
import { aiSummary } from './indicator'

interface ChainRow { strikePrice: number; call?: { ltp: number; oi: number; iv: number }; put?: { ltp: number; oi: number; iv: number } }

interface MarketPanelProps {
  activeSymbol: string
  activeName: string
  ticks: Record<string, TickData>
  onAnalyze: (symbol: string, name: string) => void
}

export default function MarketPanel({ activeSymbol, activeName, ticks, onAnalyze }: MarketPanelProps) {
  const { subscribe } = useMarketData()
  const [chain, setChain] = useState<{ rows: ChainRow[]; atm: number | null }>({ rows: [], atm: null })
  const [sr, setSr] = useState<{ s1: number; s2: number; r1: number; r2: number } | null>(null)
  const [chainAt, setChainAt] = useState<string>('')
  const busyRef = useRef(false)

  useEffect(() => { subscribe(['NSE:INDIAVIX-INDEX']) }, [subscribe])

  useEffect(() => {
    if (!activeSymbol || chainAt === activeSymbol || busyRef.current) return
    busyRef.current = true
    const sym = activeSymbol.replace(/^NSE:/, '')
    Promise.all([
      api.marketdata.optionChain(sym).catch(() => null),
      api.marketdata.historical(sym, '15m', 7).catch(() => null),
    ]).then(([chainData, histData]) => {
      const rows = ((chainData as { optionChain?: ChainRow[] })?.optionChain || []) as ChainRow[]
      if (rows.length) {
        const atm = rows.reduce((best, r) =>
          Math.abs(r.strikePrice - 24500) < Math.abs(best - 24500) ? r.strikePrice : best, rows[0].strikePrice)
        setChain({ rows, atm })
      }
      const candles = ((histData as { candles?: { high: number; low: number; close: number }[] })?.candles || []).slice(-300)
      if (candles.length >= 20) {
        const highs = candles.map(c => c.high)
        const lows = candles.map(c => c.low)
        const closes = candles.map(c => c.close)
        const s1 = [...lows].sort((a, b) => a - b).slice(0, 2)
        const r1 = [...highs].sort((a, b) => b - a).slice(0, 2)
        const avg = closes.reduce((a, b) => a + b, 0) / closes.length
        setSr({ s1: s1[0] || avg, s2: s1[1] || s1[0] || avg, r1: r1[0] || avg, r2: r1[1] || r1[0] || avg })
      }
      setChainAt(activeSymbol)
      busyRef.current = false
    }).catch(() => { busyRef.current = false })
  }, [activeSymbol, chainAt])

  const vix = ticks['NSE:INDIAVIX-INDEX']
  const activeTick = ticks[activeSymbol]

  const { gainers, losers } = useMemo(() => {
    const stocks = Object.values(ticks).filter(t => t.change_pct !== undefined)
    const sorted = [...stocks].sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0))
    return { gainers: sorted.slice(0, 5), losers: sorted.slice(-5).reverse() }
  }, [ticks])

  const pcr = useMemo(() => {
    const rows = chain.rows
    if (rows.length < 4) return null
    const callOi = rows.reduce((a, r) => a + (r.call?.oi || 0), 0)
    const putOi = rows.reduce((a, r) => a + (r.put?.oi || 0), 0)
    if (callOi <= 0) return null
    const atm = rows.find(r => r.strikePrice === chain.atm)
    return {
      ratio: putOi / callOi,
      atmCall: atm?.call?.oi || 0,
      atmPut: atm?.put?.oi || 0,
      atmIvC: atm?.call?.iv ?? 0,
      atmIvP: atm?.put?.iv ?? 0,
    }
  }, [chain])

  const oiDelta = useMemo(() => {
    if (!chain.rows.length || !chain.atm) return null
    const atm = chain.atm
    const near = chain.rows.filter(r =>
      Math.abs(r.strikePrice - atm) <= 2 * (chain.rows[1]?.strikePrice - chain.rows[0]?.strikePrice || 50))
    const ceOi = near.reduce((a, r) => a + (r.call?.oi || 0), 0)
    const peOi = near.reduce((a, r) => a + (r.put?.oi || 0), 0)
    const total = ceOi + peOi
    if (!total) return null
    return Math.round(((ceOi - peOi) / total) * 100)
  }, [chain])

  const ai = useMemo(() => {
    const summary = aiSummary({
      trend: activeTick ? (activeTick.change_pct ?? 0) >= 0 ? 'trending up' : 'trending down' : 'no live tick',
      structure: '—',
      rsi: null,
      aboveVwap: null,
      macdHist: null,
      adx: null,
      pcr: pcr?.ratio ?? null,
      support: sr?.s1 ?? null,
      resistance: sr?.r1 ?? null,
    })
    const verdict = summary.startsWith('BULLISH') ? 'BULLISH' : summary.startsWith('BEARISH') ? 'BEARISH' : 'NEUTRAL'
    return { summary, verdict, tags: [] }
  }, [pcr, sr, activeTick?.last_price, activeTick?.change_pct])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, height: '100%', minHeight: 0, overflowY: 'auto', paddingRight: 2 }}>
      <div className="t-panel">
        <div className="t-panel-header" style={{ fontSize: 11, fontWeight: 800 }}>MARKET SUMMARY</div>
        <div className="t-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div className="t-stat-row" style={{ gap: 12, justifyContent: 'space-between', padding: 0 }}>
            <div>
              <div className="t-stat-label" style={{ fontSize: 9 }}>VIX</div>
              <div className="t-num" style={{ fontSize: 15, fontWeight: 800 }}>{vix?.last_price?.toFixed(2) ?? '—'}</div>
            </div>
            <div>
              <div className="t-stat-label" style={{ fontSize: 9 }}>VIX CHG</div>
              <div className={`t-num ${(vix?.change_pct ?? 0) >= 0 ? 't-up' : 't-down'}`} style={{ fontSize: 15, fontWeight: 800 }}>
                {vix?.change_pct !== undefined ? `${vix.change_pct >= 0 ? '+' : ''}${vix.change_pct.toFixed(2)}%` : '—'}
              </div>
            </div>
            <div>
              <div className="t-stat-label" style={{ fontSize: 9 }}>PCR</div>
              <div className={`t-num ${(pcr?.ratio ?? 0) >= 1 ? 't-up' : 't-down'}`} style={{ fontSize: 15, fontWeight: 800 }}>
                {pcr?.ratio ? pcr.ratio.toFixed(2) : '—'}
              </div>
            </div>
            <div>
              <div className="t-stat-label" style={{ fontSize: 9 }}>OI BIAS</div>
              <div className={`t-num ${(oiDelta ?? 0) >= 0 ? 't-up' : 't-down'}`} style={{ fontSize: 15, fontWeight: 800 }}>
                {oiDelta === null ? '—' : `${oiDelta >= 0 ? '+' : ''}${oiDelta}%`}
              </div>
            </div>
          </div>
          {sr && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <span className="t-badge t-badge-red" style={{ fontSize: 9 }}>S2 {sr.s2.toFixed(0)}</span>
              <span className="t-badge t-badge-red" style={{ fontSize: 9 }}>S1 {sr.s1.toFixed(0)}</span>
              <span className="t-badge t-badge-green" style={{ fontSize: 9 }}>R1 {sr.r1.toFixed(0)}</span>
              <span className="t-badge t-badge-green" style={{ fontSize: 9 }}>R2 {sr.r2.toFixed(0)}</span>
            </div>
          )}
          {chain.atm && pcr && (
            <div className="t-faint" style={{ fontSize: 9 }}>
              ATM {chain.atm} · CE OI {pcr.atmCall.toLocaleString()} · PE OI {pcr.atmPut.toLocaleString()}
              {pcr.atmIvC > 0 && ` · IV ${(pcr.atmIvC * 100).toFixed(0)}/${(pcr.atmIvP * 100).toFixed(0)}`}
            </div>
          )}
        </div>
      </div>

      <div className="t-panel">
        <div className="t-panel-header" style={{ fontSize: 11, fontWeight: 800 }}>GAINERS</div>
        <div className="t-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {gainers.length === 0 && <span className="t-faint" style={{ fontSize: 10 }}>No live data</span>}
          {gainers.map(t => (
            <div key={t.symbol} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <span style={{ fontWeight: 600 }}>{t.symbol.split(':').pop()}</span>
              <span className="t-num t-up">{t.change_pct!.toFixed(2)}%</span>
            </div>
          ))}
        </div>
      </div>

      <div className="t-panel">
        <div className="t-panel-header" style={{ fontSize: 11, fontWeight: 800 }}>LOSERS</div>
        <div className="t-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {losers.length === 0 && <span className="t-faint" style={{ fontSize: 10 }}>No live data</span>}
          {losers.map(t => (
            <div key={t.symbol} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <span style={{ fontWeight: 600 }}>{t.symbol.split(':').pop()}</span>
              <span className="t-num t-down">{t.change_pct!.toFixed(2)}%</span>
            </div>
          ))}
        </div>
      </div>

      <div className="t-panel" style={{ borderLeft: `3px solid ${ai.verdict === 'BULLISH' ? 'var(--green)' : ai.verdict === 'BEARISH' ? 'var(--red)' : 'var(--amber)'}` }}>
        <div className="t-panel-header" style={{ fontSize: 11, fontWeight: 800 }}>
          AI SUMMARY {activeName && <span className="t-faint" style={{ fontWeight: 500 }}>· {activeName}</span>}
        </div>
        <div className="t-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className={`t-badge ${ai.verdict === 'BULLISH' ? 't-badge-green' : ai.verdict === 'BEARISH' ? 't-badge-red' : 't-badge-amber'}`} style={{ alignSelf: 'flex-start', fontSize: 10, fontWeight: 800 }}>
            {ai.verdict}
          </span>
          <div className="t-faint" style={{ fontSize: 10, lineHeight: 1.5 }}>{ai.summary}</div>
          {ai.tags.map(tag => <span key={tag} className="t-chip" style={{ fontSize: 9, alignSelf: 'flex-start' }}>{tag}</span>)}
        </div>
      </div>

      <button className="t-btn t-btn-sm" onClick={() => onAnalyze(activeSymbol, activeName)}
        style={{ border: '1px solid var(--border-hi)' }}>
        🔬 Full Analyzer →
      </button>
    </div>
  )
}
