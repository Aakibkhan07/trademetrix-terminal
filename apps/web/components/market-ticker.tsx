'use client'

import { useEffect } from 'react'
import { useMarketData } from '@/lib/use-market-data'

const TICKER_SYMBOLS = [
  { key: 'NSE:NIFTY50-INDEX', label: 'NIFTY' },
  { key: 'NSE:NIFTYBANK-INDEX', label: 'BANKNIFTY' },
  { key: 'NSE:FINNIFTY-INDEX', label: 'FINNIFTY' },
  { key: 'BSE:SENSEX-INDEX', label: 'SENSEX' },
  { key: 'NSE:INDIAVIX-INDEX', label: 'INDIAVIX' },
  { key: 'NSE:NIFTYIT-INDEX', label: 'NIFTYIT' },
  { key: 'NSE:NIFTYPHARMA-INDEX', label: 'PHARMA' },
  { key: 'NSE:NIFTYAUTO-INDEX', label: 'AUTO' },
]

export default function MarketTicker() {
  const { ticks, feedMode, subscribe } = useMarketData()

  useEffect(() => {
    subscribe(TICKER_SYMBOLS.map((s) => s.key))
  }, [subscribe])

  return (
    <div className="t-ticker">
      {feedMode === 'simulator' && (
        <span className="t-badge t-badge-amber" style={{ flexShrink: 0, fontSize: 8 }}>
          SIM
        </span>
      )}
      {TICKER_SYMBOLS.map((s, i) => {
        const t = ticks[s.key]
        const pct = t?.change_pct ?? 0
        return (
          <span key={s.key} className="t-ticker-item">
            <span className="t-ticker-sym">{s.label}</span>
            <span className="t-ticker-price">{t ? t.last_price.toLocaleString() : '--'}</span>
            {t && (
              <span className={`t-ticker-chg ${pct >= 0 ? 'up' : 'down'}`}>
                {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
              </span>
            )}
            {i < TICKER_SYMBOLS.length - 1 && <span className="t-ticker-sep">|</span>}
          </span>
        )
      })}
    </div>
  )
}
