'use client'

import { useEffect, useState, useCallback } from 'react'
import { useMarketData } from '@/lib/use-market-data'
import { api } from '@/lib/api'

type WatchItem = { symbol: string; name: string; type: string }

export default function MarketDataPage() {
  const { ticks, connected, feedMode, subscribe, startFeed, stopFeed } = useMarketData()
  const [feedOn, setFeedOn] = useState(false)
  const [indices, setIndices] = useState<WatchItem[]>([])
  const [stocks, setStocks] = useState<WatchItem[]>([])
  const [search, setSearch] = useState('')
  const [activeTab, setActiveTab] = useState<'all' | 'indices' | 'stocks'>('all')

  const loadWatchlist = useCallback(async () => {
    try {
      const data = await api.marketdata.watchlist() as { indices: WatchItem[]; stocks: WatchItem[] }
      setIndices(data.indices || [])
      setStocks(data.stocks || [])
      const allSymbols = [...(data.indices || []), ...(data.stocks || [])].map(i => i.symbol)
      subscribe(allSymbols)
    } catch {}
  }, [subscribe])

  useEffect(() => { loadWatchlist() }, [loadWatchlist])

  const toggleFeed = async () => {
    if (feedOn) { await stopFeed(); setFeedOn(false) }
    else { await startFeed(); setFeedOn(true) }
  }

  const items = activeTab === 'indices' ? indices : activeTab === 'stocks' ? stocks : [...indices, ...stocks]
  const filtered = search
    ? items.filter(i => i.name.toLowerCase().includes(search.toLowerCase()) || i.symbol.toLowerCase().includes(search.toLowerCase()))
    : items

  const sortedTicks = Object.values(ticks).sort((a, b) => Math.abs(b.change_pct ?? 0) - Math.abs(a.change_pct ?? 0))

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Market Data</h1>
          <p className="page-subtitle">
            <span className={`live-dot ${connected ? 'active' : 'inactive'}`} />
            {connected ? 'Connected' : 'Disconnected'} &middot; {Object.keys(ticks).length} symbols
            {feedMode === 'simulator' && (
              <span className="badge badge-amber" style={{ marginLeft: 8 }}>SIMULATED DATA</span>
            )}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className={`btn btn-sm ${feedOn ? 'btn-danger' : 'btn-primary'}`} onClick={toggleFeed}>
            {feedOn ? 'Stop Feed' : 'Start Feed'}
          </button>
        </div>
      </div>

      {sortedTicks.length > 0 && (
        <div className="grid-4" style={{ marginBottom: 20, gap: 12 }}>
          {sortedTicks.slice(0, 8).map((t) => {
            const pct = t.change_pct ?? 0
            const item = [...indices, ...stocks].find(i => i.symbol === t.symbol)
            return (
              <div key={t.symbol} className="glass-card" style={{ padding: '10px 14px' }}>
                <p className="card-label">{item?.name || t.symbol?.split(':').pop()}</p>
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

      <input className="input" placeholder="Search symbols..." value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ width: '100%', marginBottom: 12, boxSizing: 'border-box' }} />

      <div className="tab-bar" style={{ marginBottom: 12 }}>
        <button className={`tab ${activeTab === 'all' ? 'active' : ''}`} onClick={() => setActiveTab('all')}>
          All ({indices.length + stocks.length})
        </button>
        <button className={`tab ${activeTab === 'indices' ? 'active' : ''}`} onClick={() => setActiveTab('indices')}>
          Indices ({indices.length})
        </button>
        <button className={`tab ${activeTab === 'stocks' ? 'active' : ''}`} onClick={() => setActiveTab('stocks')}>
          Stocks ({stocks.length})
        </button>
      </div>

      <div className="panel" style={{ padding: 0 }}>
        <div className="panel-header" style={{ padding: '10px 14px', margin: 0 }}>
          <h3 className="panel-title" style={{ fontSize: 13 }}>
            Live Ticks
            <span className={`live-badge ${connected ? 'on' : 'off'}`} style={{ marginLeft: 8 }}>
              <span className={`live-dot ${connected ? 'active' : 'inactive'}`} />
              {connected ? 'Live' : 'Offline'}
            </span>
          </h3>
        </div>
        {filtered.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ fontSize: 11 }}>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Name</th>
                  <th>Type</th>
                  <th className="numeric">LTP</th>
                  <th className="numeric">Change</th>
                  <th className="numeric">Change%</th>
                  <th className="numeric">Bid</th>
                  <th className="numeric">Ask</th>
                  <th className="numeric">Volume</th>
                  <th className="numeric">OI</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => {
                  const t = ticks[item.symbol]
                  const chg = t?.change ?? 0
                  const pct = t?.change_pct ?? 0
                  const spread = t?.ask && t?.bid ? (t.ask - t.bid) : 0
                  return (
                    <tr key={item.symbol}>
                      <td style={{ fontWeight: 600, fontSize: 10 }}>{item.symbol}</td>
                      <td>{item.name}</td>
                      <td><span className={`badge ${item.type === 'index' ? 'badge-violet' : 'badge-cyan'}`} style={{ fontSize: 9 }}>{item.type}</span></td>
                      <td className="numeric">{t?.last_price?.toFixed(1) || '-'}</td>
                      <td className={`numeric ${chg >= 0 ? 'positive' : 'negative'}`}>
                        {t ? `${chg >= 0 ? '+' : ''}${chg?.toFixed(1)}` : '-'}
                      </td>
                      <td className={`numeric ${pct >= 0 ? 'positive' : 'negative'}`}>
                        {t ? `${pct >= 0 ? '+' : ''}${pct?.toFixed(2)}%` : '-'}
                      </td>
                      <td className="numeric" style={{ color: t?.bid ? '#22c55e' : 'var(--text-muted)' }}>{t?.bid || '-'}</td>
                      <td className="numeric" style={{ color: t?.ask ? '#ef4444' : 'var(--text-muted)' }}>{t?.ask || '-'}</td>
                      <td className="numeric">{t?.volume ? t.volume.toLocaleString() : '-'}</td>
                      <td className="numeric">{t?.oi ? t.oi.toLocaleString() : '-'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, margin: 0, textAlign: 'center' }}>
            {search ? 'No matches found' : 'Loading symbols...'}
          </p>
        )}
      </div>
    </div>
  )
}
