'use client'

import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import { useMarketData } from '@/lib/use-market-data'
import { usePolling } from '@/lib/use-polling'
import { useAuth } from '@/lib/auth-context'

const WATCH_SYMBOLS = [
  { name: 'NIFTY', key: 'NSE:NIFTY50-INDEX' },
  { name: 'BANKNIFTY', key: 'NSE:NIFTYBANK-INDEX' },
  { name: 'FINNIFTY', key: 'NSE:FINNIFTY-INDEX' },
  { name: 'SENSEX', key: 'BSE:SENSEX-INDEX' },
]

export default function DashboardPage() {
  const { token } = useAuth()
  const { ticks, connected, subscribe, startFeed } = useMarketData()
  const [positions, setPositions] = useState<any[]>([])
  const [funds, setFunds] = useState<Record<string, number> | null>(null)
  const [orders, setOrders] = useState<any[]>([])
  const [lastRefresh, setLastRefresh] = useState('')

  const loadData = useCallback(async () => {
    try {
      const [p, f, o] = await Promise.all([
        api.engine.positions().catch(() => ({ positions: [] })),
        api.engine.funds().catch(() => ({ funds: null })),
        api.engine.orders().catch(() => ({ orders: [] })),
      ])
      setPositions((p as any).positions || [])
      setFunds((f as any).funds || null)
      setOrders((o as any).orders || [])
      setLastRefresh(new Date().toLocaleTimeString())
    } catch {}
  }, [])

  useEffect(() => {
    subscribe(WATCH_SYMBOLS.map((s) => s.key))
    startFeed()
  }, [subscribe, startFeed])

  usePolling(loadData, 4000, !!token)

  const totalPnl = positions.reduce((sum: number, p: any) => {
    const live = ticks[p.symbol]
    const ltp = live?.last_price || p.last_price || 0
    return sum + (live ? (p.quantity * (ltp - p.average_buy_price)) : (p.unrealised_pnl || 0))
  }, 0)

  const niftyTick = ticks['NSE:NIFTY50-INDEX']
  const bankNiftyTick = ticks['NSE:NIFTYBANK-INDEX']
  const ratio = niftyTick && bankNiftyTick ? (niftyTick.last_price / bankNiftyTick.last_price * 100) : null

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">
            <span className={`live-dot ${connected ? 'active' : 'inactive'}`} />
            {connected ? 'Live' : 'Connecting...'}
            <span className="last-updated" style={{ marginLeft: 12 }}>Updated {lastRefresh}</span>
          </p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={loadData}>Refresh</button>
      </div>

      <div className="grid-4">
        {WATCH_SYMBOLS.map((s) => {
          const t = ticks[s.key]
          const pct = t?.change_pct ?? 0
          return (
            <div key={s.key} className="glass-card">
              <p className="card-label">{s.name}</p>
              {t ? (
                <>
                  <p className="card-value">{t.last_price.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</p>
                  <p className={`card-change ${pct >= 0 ? 'up' : 'down'}`}>
                    {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
                    <span className="card-sec"> {t.change >= 0 ? '+' : ''}{t.change.toFixed(1)}</span>
                  </p>
                </>
              ) : (
                <p className="card-placeholder">Waiting...</p>
              )}
            </div>
          )
        })}
      </div>

      <div className="grid-2" style={{ gap: 20, marginBottom: 24 }}>
        <div className="panel">
          <div className="panel-header">
            <h3 className="panel-title">Portfolio Summary</h3>
            <span className="last-updated">{lastRefresh}</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="stat-card">
              <p className="stat-label">Total P&L</p>
              <p className={`stat-value ${totalPnl >= 0 ? 'positive' : 'negative'}`}>
                {totalPnl >= 0 ? '+' : ''}{totalPnl?.toFixed(0) || '0'}
              </p>
              <p className="stat-sub">{positions.length} positions</p>
            </div>
            <div className="stat-card">
              <p className="stat-label">Available</p>
              <p className="stat-value">{(funds?.available_margin || 0).toLocaleString()}</p>
              <p className="stat-sub">of {(funds?.total_margin || 0).toLocaleString()} total</p>
            </div>
            <div className="stat-card">
              <p className="stat-label">Positions</p>
              <p className="stat-value">{positions.length}</p>
              <p className="stat-sub">{positions.filter((p: any) => p.quantity > 0).length} long / {positions.filter((p: any) => p.quantity < 0).length} short</p>
            </div>
            <div className="stat-card">
              <p className="stat-label">Orders Today</p>
              <p className="stat-value">{orders.length}</p>
              <p className="stat-sub">{orders.filter((o: any) => o.status === 'FILLED').length} filled</p>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h3 className="panel-title">Market at a Glance</h3>
            <span className={`badge ${connected ? 'badge-green' : 'badge-red'}`}>
              <span className={`live-dot ${connected ? 'active' : 'inactive'}`} />
              {connected ? 'Live Feed' : 'Offline'}
            </span>
          </div>
          <div style={{ padding: '8px 0' }}>
            {ratio && (
              <div style={{ marginBottom: 16 }}>
                <p className="stat-label" style={{ margin: '0 0 6px' }}>NIFTY / BANKNIFTY RATIO</p>
                <p className="stat-value" style={{ fontSize: 28, fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan)' }}>
                  {ratio.toFixed(3)}
                </p>
              </div>
            )}
            <div className="market-grid">
              <div>
                <p className="stat-label">NIFTY</p>
                <p style={{ fontSize: 18, fontWeight: 600, color: (niftyTick?.change_pct ?? 0) >= 0 ? 'var(--status-up)' : 'var(--status-down)', margin: 0 }}>
                  {niftyTick?.last_price?.toFixed(1) || '--'}
                </p>
              </div>
              <div>
                <p className="stat-label">BANKNIFTY</p>
                <p style={{ fontSize: 18, fontWeight: 600, color: (bankNiftyTick?.change_pct ?? 0) >= 0 ? 'var(--status-up)' : 'var(--status-down)', margin: 0 }}>
                  {bankNiftyTick?.last_price?.toFixed(1) || '--'}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="panel" style={{ padding: 0 }}>
        <div className="panel-header" style={{ padding: '12px 16px', margin: 0 }}>
          <h3 className="panel-title" style={{ fontSize: 14 }}>Open Positions ({positions.length})</h3>
        </div>
        {positions.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th className="numeric">Qty</th>
                  <th className="numeric">Avg</th>
                  <th className="numeric">LTP</th>
                  <th className="numeric">P&L</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p: any, i: number) => {
                  const live = ticks[p.symbol]
                  const ltp = live?.last_price || p.last_price || 0
                  const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : p.unrealised_pnl
                  return (
                    <tr key={i}>
                      <td style={{ fontWeight: 600 }}>{p.symbol?.split(':').pop()}</td>
                      <td className="numeric">{p.quantity}</td>
                      <td className="numeric">{p.average_buy_price?.toFixed(1) || '-'}</td>
                      <td className="numeric">{ltp?.toFixed(1) || '-'}</td>
                      <td className={`numeric ${pnl >= 0 ? 'positive' : 'negative'}`} style={{ fontWeight: 600 }}>
                        {pnl >= 0 ? '+' : ''}{pnl?.toFixed(0) || '0'}
                      </td>
                      <td>
                        <span className={`badge ${p.instrument_type === 'OPT' ? 'badge-violet' : 'badge-cyan'}`} style={{ fontSize: 8 }}>
                          {p.instrument_type || 'EQ'}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ color: 'var(--text-muted)', fontSize: 13, padding: 24, margin: 0, textAlign: 'center' }}>No open positions</p>
        )}
      </div>
    </div>
  )
}
