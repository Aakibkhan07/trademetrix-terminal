'use client'

import { useEffect, useState } from 'react'
import { useMarketData } from '@/lib/use-market-data'

const WATCHLIST = ['NSE:NIFTY50-INDEX', 'NSE:NIFTYBANK-INDEX', 'NSE:FINNIFTY-INDEX',
  'BSE:SENSEX-INDEX', 'NSE:MIDCPNIFTY-INDEX']

export default function MarketDataPage() {
  const { ticks, connected, subscribe, startFeed, stopFeed } = useMarketData()
  const [feedOn, setFeedOn] = useState(false)

  useEffect(() => {
    subscribe(WATCHLIST)
  }, [subscribe])

  const sorted = Object.values(ticks).sort((a, b) => Math.abs(b.change_pct ?? 0) - Math.abs(a.change_pct ?? 0))

  const toggleFeed = async () => {
    if (feedOn) { await stopFeed(); setFeedOn(false) }
    else { await startFeed(); setFeedOn(true) }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Market Data</h1>
          <p className="page-subtitle">
            <span className={`live-dot ${connected ? 'active' : 'inactive'}`} />
            {connected ? 'Connected' : 'Disconnected'} &middot; {Object.keys(ticks).length} symbols
          </p>
        </div>
        <button className={`btn btn-sm ${feedOn ? 'btn-danger' : 'btn-primary'}`} onClick={toggleFeed}>
          {feedOn ? 'Stop Feed' : 'Start Feed'}
        </button>
      </div>

      {sorted.length > 0 && (
        <div className="grid-4" style={{ marginBottom: 20, gap: 12 }}>
          {sorted.slice(0, 4).map((t) => {
            const pct = t.change_pct ?? 0
            return (
              <div key={t.symbol} className="glass-card" style={{ padding: '10px 14px' }}>
                <p className="card-label">{t.symbol?.split(':').pop()}</p>
                <p className="card-value" style={{ fontSize: 18 }}>
                  {t.last_price?.toFixed(1)}
                  <span className={`card-change ${pct >= 0 ? 'up' : 'down'}`} style={{ marginLeft: 6, fontSize: 11 }}>
                    {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
                  </span>
                </p>
              </div>
            )
          })}
        </div>
      )}

      <div className="panel" style={{ padding: 0 }}>
        <div className="panel-header" style={{ padding: '10px 14px', margin: 0 }}>
          <h3 className="panel-title" style={{ fontSize: 13 }}>
            Live Ticks ({sorted.length})
            <span className={`live-badge ${connected ? 'on' : 'off'}`} style={{ marginLeft: 8 }}>
              <span className={`live-dot ${connected ? 'active' : 'inactive'}`} />
              {connected ? 'Live' : 'Offline'}
            </span>
          </h3>
        </div>
        {sorted.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ fontSize: 11 }}>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th className="numeric">LTP</th>
                  <th className="numeric">Change</th>
                  <th className="numeric">Change%</th>
                  <th className="numeric">Bid</th>
                  <th className="numeric">Ask</th>
                  <th className="numeric">Volume</th>
                  <th className="numeric">OI</th>
                  <th className="numeric">Spread</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((t, i) => {
                  const spread = t.ask && t.bid ? (t.ask - t.bid) : 0
                  const pct = t.change_pct ?? 0
                  const chg = t.change ?? 0
                  return (
                    <tr key={t.symbol + i}>
                      <td style={{ fontWeight: 600 }}>{t.symbol?.split(':').pop()}</td>
                      <td className="numeric">{t.last_price?.toFixed(1)}</td>
                      <td className={`numeric ${chg >= 0 ? 'positive' : 'negative'}`}>
                        {chg >= 0 ? '+' : ''}{chg?.toFixed(1)}
                      </td>
                      <td className={`numeric ${pct >= 0 ? 'positive' : 'negative'}`}>
                        {pct >= 0 ? '+' : ''}{pct?.toFixed(2)}%
                      </td>
                      <td className="numeric positive">{t.bid || '-'}</td>
                      <td className="numeric negative">{t.ask || '-'}</td>
                      <td className="numeric">{(t.volume || 0).toLocaleString()}</td>
                      <td className="numeric">{(t.oi || 0).toLocaleString()}</td>
                      <td className={`numeric ${spread > 0 ? '' : 'neutral'}`} style={{ color: spread > 0 ? '#f59e0b' : 'var(--text-muted)' }}>
                        {spread > 0 ? spread.toFixed(1) : '-'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, margin: 0, textAlign: 'center' }}>
            No data yet. Start the feed and wait for ticks.
          </p>
        )}
      </div>
    </div>
  )
}
