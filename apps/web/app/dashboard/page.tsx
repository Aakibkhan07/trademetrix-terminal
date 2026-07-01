'use client'

import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import { useMarketData } from '@/lib/use-market-data'
import { usePolling } from '@/lib/use-polling'
import { useAuth } from '@/lib/auth-context'
import EquityCurve from '@/components/equity-curve'

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
      <div className="t-page-header">
        <h1 className="t-page-title">Dashboard</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-red'}`} />
          <span className={connected ? 't-up' : 't-down'} style={{ fontSize: 12 }}>{connected ? 'Live' : 'Connecting...'}</span>
          <span className="t-faint" style={{ fontSize: 11 }}>Updated {lastRefresh}</span>
          <button className="t-btn t-btn-sm t-btn-ghost" onClick={loadData}>Refresh</button>
        </div>
      </div>

      <div className="t-grid-4">
        {WATCH_SYMBOLS.map((s) => {
          const t = ticks[s.key]
          const pct = t?.change_pct ?? 0
          return (
            <div key={s.key} className="t-panel">
              <div className="t-panel-body">
                <p className="t-stat-label">{s.name}</p>
                {t ? (
                  <>
                    <p className="t-stat-value" style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 22, margin: '4px 0' }}>
                      {t.last_price.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
                    </p>
                    <p className={pct >= 0 ? 't-up' : 't-down'} style={{ fontSize: 12, margin: 0 }}>
                      {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
                      <span className="t-faint" style={{ marginLeft: 6 }}>
                        {t.change >= 0 ? '+' : ''}{t.change.toFixed(1)}
                      </span>
                    </p>
                  </>
                ) : (
                  <p className="t-faint" style={{ margin: 0 }}>Waiting...</p>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <div className="t-row" style={{ marginBottom: 20 }}>
        <div className="t-col">
          <div className="t-panel">
            <div className="t-panel-header">
              <h3 className="t-panel-title">Portfolio Summary</h3>
              <span className={`t-num ${totalPnl >= 0 ? 't-up' : 't-down'}`} style={{ fontSize: 14 }}>
                {totalPnl >= 0 ? '+' : ''}{totalPnl?.toFixed(0) || '0'}
              </span>
            </div>
            <div className="t-panel-body">
              {positions.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <EquityCurve points={(() => {
                    let cum = 0
                    return positions.map((p: any) => {
                      const live = ticks[p.symbol]
                      const ltp = live?.last_price || p.last_price || 0
                      const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : (p.unrealised_pnl || 0)
                      cum += pnl || 0
                      return cum
                    })
                  })()} height={140} />
                </div>
              )}

              {positions.length > 1 && (
                <div>
                  <p className="t-stat-label" style={{ marginBottom: 8 }}>P&L by Symbol</p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                    {positions.map((p: any) => {
                      const live = ticks[p.symbol]
                      const ltp = live?.last_price || p.last_price || 0
                      const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : (p.unrealised_pnl || 0)
                      const maxPnl = Math.max(...positions.map((x: any) => {
                        const l = ticks[x.symbol]
                        const lp = l?.last_price || x.last_price || 0
                        return Math.abs(l ? (x.quantity * (lp - x.average_buy_price)) : (x.unrealised_pnl || 0))
                      })) || 1
                      const pct = Math.abs(pnl) / maxPnl * 100
                      return (
                        <div key={p.symbol} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span className="t-faint" style={{ fontSize: 11, minWidth: 80 }}>{p.symbol?.split(':').pop()}</span>
                          <div className="t-progress" style={{ flex: 1, height: 6 }}>
                            <div className={`t-progress-fill ${pnl >= 0 ? 'green' : 'red'}`} style={{ width: `${pct}%` }} />
                          </div>
                          <span className={`t-num ${pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontSize: 11, minWidth: 60, textAlign: 'right' }}>
                            {pnl >= 0 ? '+' : ''}{pnl?.toFixed(0) || '0'}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="t-col">
          <div className="t-panel">
            <div className="t-panel-header">
              <h3 className="t-panel-title">Account Overview</h3>
              <span className={`t-badge ${connected ? 't-badge-green' : 't-badge-red'}`}>
                <span className={`t-dot ${connected ? 't-dot-green' : 't-dot-red'}`} />
                {connected ? 'Live Feed' : 'Offline'}
              </span>
            </div>
            <div className="t-panel-body">
              {ratio && (
                <div style={{ marginBottom: 20 }}>
                  <p className="t-stat-label" style={{ marginBottom: 4 }}>NIFTY / BANKNIFTY</p>
                  <p className="t-num" style={{ fontSize: 26, color: 'var(--accent-cyan)' }}>
                    {ratio.toFixed(3)}
                  </p>
                </div>
              )}

              <div className="t-stat-row">
                <div className="t-stat">
                  <span className="t-stat-label">Total P&L</span>
                  <span className={`t-stat-value ${totalPnl >= 0 ? 't-up' : 't-down'}`}>
                    {totalPnl >= 0 ? '+' : ''}{totalPnl?.toFixed(0) || '0'}
                  </span>
                  <span className="t-stat-sub">{positions.length} positions</span>
                </div>
                <div className="t-stat">
                  <span className="t-stat-label">Available Margin</span>
                  <span className="t-stat-value">{(funds?.available_margin || 0).toLocaleString()}</span>
                  <span className="t-stat-sub">of {(funds?.total_margin || 0).toLocaleString()} total</span>
                </div>
                <div className="t-stat">
                  <span className="t-stat-label">Positions</span>
                  <span className="t-stat-value">{positions.length}</span>
                  <span className="t-stat-sub">
                    {positions.filter((p: any) => p.quantity > 0).length} long / {positions.filter((p: any) => p.quantity < 0).length} short
                  </span>
                </div>
                <div className="t-stat">
                  <span className="t-stat-label">Orders Today</span>
                  <span className="t-stat-value">{orders.length}</span>
                  <span className="t-stat-sub">{orders.filter((o: any) => o.status === 'FILLED').length} filled</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="t-panel">
        <div className="t-panel-header">
          <h3 className="t-panel-title">Open Positions ({positions.length})</h3>
        </div>
        {positions.length > 0 ? (
          <div className="t-table-wrap">
            <table className="t-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th className="num">Qty</th>
                  <th className="num">Avg</th>
                  <th className="num">LTP</th>
                  <th className="num">P&amp;L</th>
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
                      <td className="num">{p.quantity}</td>
                      <td className="num">{p.average_buy_price?.toFixed(1) || '-'}</td>
                      <td className="num">{ltp?.toFixed(1) || '-'}</td>
                      <td className={`num ${pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 600 }}>
                        {pnl >= 0 ? '+' : ''}{pnl?.toFixed(0) || '0'}
                      </td>
                      <td>
                        <span className={`t-badge ${p.instrument_type === 'OPT' ? 't-badge-violet' : 't-badge-cyan'}`} style={{ fontSize: 10 }}>
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
          <p className="t-faint" style={{ textAlign: 'center', padding: 24, margin: 0 }}>No open positions</p>
        )}
      </div>
    </div>
  )
}
