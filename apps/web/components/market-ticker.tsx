'use client'

import { useEffect, useState } from 'react'

interface TickerData {
  symbol: string
  price: number
  change: number
  changePercent: number
}

const DEFAULT_TICKERS: TickerData[] = [
  { symbol: 'NIFTY 50', price: 24582.30, change: 291.35, changePercent: 1.2 },
  { symbol: 'SENSEX', price: 81034.15, change: 882.50, changePercent: 1.1 },
  { symbol: 'BANK NIFTY', price: 52148.75, change: -156.45, changePercent: -0.3 },
  { symbol: 'FIN NIFTY', price: 23456.20, change: 116.45, changePercent: 0.8 },
  { symbol: 'INDIA VIX', price: 12.84, change: -0.27, changePercent: -2.1 },
  { symbol: 'NIFTY IT', price: 38429.60, change: 342.25, changePercent: 0.9 },
  { symbol: 'NIFTY PHARMA', price: 19812.35, change: -139.70, changePercent: -0.7 },
  { symbol: 'NIFTY AUTO', price: 22564.80, change: 333.45, changePercent: 1.5 },
]

export default function MarketTicker() {
  const [tickers] = useState<TickerData[]>(DEFAULT_TICKERS)

  return (
    <div className="ticker">
      {tickers.map((t, i) => (
        <span key={t.symbol} className="ticker-item">
          <span className="ticker-symbol">{t.symbol}</span>
          <span className="ticker-price">{t.price.toLocaleString()}</span>
          <span className={`ticker-change ${t.change >= 0 ? 'up' : 'down'}`}>
            {t.change >= 0 ? '+' : ''}{t.changePercent.toFixed(1)}%
          </span>
          {i < tickers.length - 1 && <span className="ticker-sep">|</span>}
        </span>
      ))}
    </div>
  )
}
