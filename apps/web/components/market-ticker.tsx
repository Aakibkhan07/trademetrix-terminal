'use client'

import { useEffect } from 'react'
import { useMarketData } from '@/lib/use-market-data'

const TICKER_SYMBOLS = [
  { key: 'NSE:NIFTY50-INDEX', label: 'NIFTY 50' },
  { key: 'NSE:NIFTYBANK-INDEX', label: 'BANK NIFTY' },
  { key: 'NSE:FINNIFTY-INDEX', label: 'FIN NIFTY' },
  { key: 'BSE:SENSEX-INDEX', label: 'SENSEX' },
  { key: 'NSE:INDIAVIX-INDEX', label: 'INDIA VIX' },
  { key: 'NSE:NIFTYIT-INDEX', label: 'NIFTY IT' },
  { key: 'NSE:NIFTYPHARMA-INDEX', label: 'NIFTY PHARMA' },
  { key: 'NSE:NIFTYAUTO-INDEX', label: 'NIFTY AUTO' },
]

export default function MarketTicker() {
  const { ticks, feedMode, subscribe, startFeed } = useMarketData()

  useEffect(() => {
    subscribe(TICKER_SYMBOLS.map((s) => s.key))
    startFeed()
  }, [subscribe, startFeed])

  return (
    <div className="ticker">
      {feedMode === 'simulator' && (
        <span className="badge badge-amber" style={{ marginRight: 12, fontSize: 10, flexShrink: 0 }}>
          SIMULATED DATA
        </span>
      )}
      {TICKER_SYMBOLS.map((s, i) => {
        const t = ticks[s.key]
        const pct = t?.change_pct ?? 0
        return (
          <span key={s.key} className="ticker-item">
            <span className="ticker-symbol">{s.label}</span>
            <span className="ticker-price">{t ? t.last_price.toLocaleString() : '--'}</span>
            {t && (
              <span className={`ticker-change ${pct >= 0 ? 'up' : 'down'}`}>
                {pct >= 0 ? '+' : ''}{pct.toFixed(1)}%
              </span>
            )}
            {i < TICKER_SYMBOLS.length - 1 && <span className="ticker-sep">|</span>}
          </span>
        )
      })}
    </div>
  )
}
