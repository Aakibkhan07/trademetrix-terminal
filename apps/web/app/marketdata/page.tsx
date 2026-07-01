'use client'

import { useEffect, useState, useCallback } from 'react'
import { useMarketData } from '@/lib/use-market-data'
import { api } from '@/lib/api'
import Chart from '@/components/chart'

type WatchItem = { symbol: string; name: string; type: string }

export default function MarketDataPage() {
  const { ticks, connected, feedMode, subscribe, startFeed, stopFeed } = useMarketData()
  const [feedOn, setFeedOn] = useState(false)
  const [indices, setIndices] = useState<WatchItem[]>([])
  const [stocks, setStocks] = useState<WatchItem[]>([])
  const [search, setSearch] = useState('')
  const [activeTab, setActiveTab] = useState<'all' | 'indices' | 'stocks'>('all')
  const [chartSymbol, setChartSymbol] = useState('NSE:NIFTY50-INDEX')

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

  const timeframes = ['1D', '1W', '1M', '3M', '1Y']
  const [chartTF, setChartTF] = useState('1D')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Header */}
      <div className="t-row" style={{ alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0, letterSpacing: '-0.02em' }}>Market Data</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2, fontSize: 12 }}>
            <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-red'}`} />
            <span className={connected ? 't-up' : 't-down'}>{connected ? 'Connected' : 'Disconnected'}</span>
            <span className="t-faint">&middot;</span>
            <span className="t-sub">{Object.keys(ticks).length} symbols</span>
            {feedMode === 'simulator' && (
              <span className="t-badge t-badge-amber">SIMULATED</span>
            )}
          </div>
        </div>
        <button className={`t-btn t-btn-sm ${feedOn ? 't-btn-ghost' : 't-btn-primary'}`} onClick={toggleFeed}>
          {feedOn ? 'Stop Feed' : 'Start Feed'}
        </button>
      </div>

      {/* Top Movers */}
      {sortedTicks.length > 0 && (
        <div className="t-grid-2" style={{ gap: 8 }}>
          {sortedTicks.slice(0, 8).map((t) => {
            const pct = t.change_pct ?? 0
            const item = [...indices, ...stocks].find(i => i.symbol === t.symbol)
            return (
              <div key={t.symbol} className="t-panel" style={{ padding: '10px 14px' }}>
                <div className="t-panel-body" style={{ padding: 0 }}>
                  <div className="t-faint" style={{ fontSize: 11, marginBottom: 2 }}>{item?.name || t.symbol?.split(':').pop()}</div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                    <span className="t-num" style={{ fontSize: 18 }}>{t.last_price?.toFixed(1)}</span>
                    <span className={`t-num ${pct >= 0 ? 't-up' : 't-down'}`} style={{ fontSize: 12 }}>
                      {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
                    </span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Chart */}
      <div className="t-chart-box">
        <div className="t-chart-controls">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="t-panel-title" style={{ fontSize: 13, fontWeight: 600 }}>{chartSymbol}</span>
            <span className="t-dot t-dot-green t-dot-pulse" />
          </div>
          <div style={{ display: 'flex', gap: 2 }}>
            {timeframes.map(tf => (
              <button key={tf} className={`t-chart-btn ${chartTF === tf ? 'active' : ''}`} onClick={() => setChartTF(tf)}>
                {tf}
              </button>
            ))}
          </div>
        </div>
        <div className="t-chart-area">
          <Chart symbol={chartSymbol} height={320} />
        </div>
      </div>

      {/* Search */}
      <input className="t-input" placeholder="Search symbols..." value={search}
        onChange={(e) => setSearch(e.target.value)} />

      {/* Tabs */}
      <div className="t-tabs">
        <button className={`t-tab ${activeTab === 'all' ? 'active' : ''}`} onClick={() => setActiveTab('all')}>
          All <span className="t-badge t-badge-sub">{indices.length + stocks.length}</span>
        </button>
        <button className={`t-tab ${activeTab === 'indices' ? 'active' : ''}`} onClick={() => setActiveTab('indices')}>
          Indices <span className="t-badge t-badge-violet">{indices.length}</span>
        </button>
        <button className={`t-tab ${activeTab === 'stocks' ? 'active' : ''}`} onClick={() => setActiveTab('stocks')}>
          Stocks <span className="t-badge t-badge-cyan">{stocks.length}</span>
        </button>
      </div>

      {/* Live Ticks Table */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">
            Live Ticks
            <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-red'}`} style={{ marginLeft: 8 }} />
          </h3>
        </div>
        {filtered.length > 0 ? (
          <div className="t-table-wrap">
            <table className="t-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Name</th>
                  <th>Type</th>
                  <th>LTP</th>
                  <th>Change</th>
                  <th>Change%</th>
                  <th>Bid</th>
                  <th>Ask</th>
                  <th>Volume</th>
                  <th>OI</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => {
                  const t = ticks[item.symbol]
                  const chg = t?.change ?? 0
                  const pct = t?.change_pct ?? 0
                  return (
                    <tr key={item.symbol} style={{ cursor: 'pointer' }}
                      onClick={() => setChartSymbol(item.symbol)}>
                      <td style={{
                        fontWeight: 600,
                        fontSize: 10,
                        color: chartSymbol === item.symbol ? 'var(--cyan)' : undefined
                      }}>
                        {item.symbol}
                      </td>
                      <td>{item.name}</td>
                      <td>
                        <span className={`t-badge ${item.type === 'index' ? 't-badge-violet' : 't-badge-cyan'}`} style={{ fontSize: 9 }}>
                          {item.type}
                        </span>
                      </td>
                      <td><span className="t-num">{t?.last_price?.toFixed(1) || '-'}</span></td>
                      <td>
                        <span className={`t-num ${chg >= 0 ? 't-up' : 't-down'}`}>
                          {t ? `${chg >= 0 ? '+' : ''}${chg?.toFixed(1)}` : '-'}
                        </span>
                      </td>
                      <td>
                        <span className={`t-num ${pct >= 0 ? 't-up' : 't-down'}`}>
                          {t ? `${pct >= 0 ? '+' : ''}${pct?.toFixed(2)}%` : '-'}
                        </span>
                      </td>
                      <td><span className="t-num t-up">{t?.bid || '-'}</span></td>
                      <td><span className="t-num t-down">{t?.ask || '-'}</span></td>
                      <td><span className="t-num t-faint">{t?.volume ? t.volume.toLocaleString() : '-'}</span></td>
                      <td><span className="t-num t-faint">{t?.oi ? t.oi.toLocaleString() : '-'}</span></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="t-panel-body" style={{ textAlign: 'center' }}>
            <span className="t-faint">{search ? 'No matches found' : 'Loading symbols...'}</span>
          </div>
        )}
      </div>
    </div>
  )
}
