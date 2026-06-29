'use client'

import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import { useMarketData } from '@/lib/use-market-data'
import { usePolling } from '@/lib/use-polling'
import { useAuth } from '@/lib/auth-context'

export default function PositionsPage() {
  const { token } = useAuth()
  const { ticks, connected, subscribe, startFeed } = useMarketData()
  const [positions, setPositions] = useState<any[]>([])
  const [orders, setOrders] = useState<any[]>([])
  const [funds, setFunds] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState('')
  const [paper, setPaper] = useState(true)

  useEffect(() => {
    const symbols = ['NSE:NIFTY50-INDEX', 'NSE:NIFTYBANK-INDEX', 'NSE:FINNIFTY-INDEX',
      'BSE:SENSEX-INDEX', 'NSE:INDIAVIX-INDEX']
    subscribe(symbols)
    startFeed()
  }, [subscribe, startFeed])

  const loadData = useCallback(async () => {
    try {
      const [p, o, f] = await Promise.all([
        api.engine.positions(paper).catch(() => ({ positions: [] })),
        api.engine.orders().catch(() => ({ orders: [] })),
        api.engine.funds(paper).catch(() => ({ funds: null })),
      ])
      setPositions((p as any).positions || [])
      setOrders((o as any).orders || [])
      setFunds((f as any).funds || null)
      setLastRefresh(new Date().toLocaleTimeString())
    } catch {} finally { setLoading(false) }
  }, [paper])

  usePolling(loadData, 3000, !!token)

  useEffect(() => { loadData() }, [loadData])

  const totalPnl = positions.reduce((sum: number, p: any) => {
    const live = ticks[p.symbol]
    const ltp = live?.last_price || p.last_price || 0
    const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : p.unrealised_pnl
    return sum + (pnl || 0)
  }, 0)

  const sqOff = async (symbol: string, qty: number) => {
    const side = qty > 0 ? 'SELL' : 'BUY'
    await api.engine.trade({
      symbol, side, quantity: Math.abs(qty), price: 0,
      exchange: 'NFO', order_type: 'MARKET', product: 'INTRADAY',
      instrument_type: positions.find(p => p.symbol === symbol)?.instrument_type || 'EQ',
    }, paper)
    setTimeout(loadData, 1000)
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Positions</h1>
          <p className="page-subtitle">
            <span className={`live-dot ${connected ? 'active' : 'inactive'}`} />
            {connected ? 'Live' : 'Connecting...'}
            {lastRefresh && <span className="last-updated" style={{ marginLeft: 12 }}>Updated {lastRefresh}</span>}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{paper ? 'PAPER' : 'LIVE'}</span>
          <label className="switch" style={{ position: 'relative', display: 'inline-block', width: 36, height: 20 }}>
            <input type="checkbox" checked={!paper} onChange={() => setPaper(!paper)}
              style={{ opacity: 0, width: 0, height: 0 }} />
            <span style={{
              position: 'absolute', cursor: 'pointer', top: 0, left: 0, right: 0, bottom: 0,
              background: paper ? '#555570' : '#8b5cf6', borderRadius: 20, transition: '.3s',
            }}>
              <span style={{
                position: 'absolute', height: 16, width: 16, borderRadius: '50%', background: '#fff',
                top: 2, transition: '.3s', left: paper ? 2 : 18,
              }} />
            </span>
          </label>
          <button className="btn btn-ghost btn-sm" onClick={loadData}>Refresh</button>
        </div>
      </div>

      {funds && (
        <div className="grid-3" style={{ gap: 12, marginBottom: 20 }}>
          <div className="stat-card" style={{ padding: 12 }}>
            <span className="stat-label">Available</span>
            <span className="stat-value" style={{ fontSize: 18 }}>{(funds.available_margin || 0).toLocaleString()}</span>
          </div>
          <div className="stat-card" style={{ padding: 12 }}>
            <span className="stat-label">Used</span>
            <span className="stat-value" style={{ fontSize: 18, color: '#22d3ee' }}>{(funds.used_margin || 0).toLocaleString()}</span>
          </div>
          <div className="stat-card" style={{ padding: 12 }}>
            <span className="stat-label">Total P&L</span>
            <span className={`stat-value ${totalPnl >= 0 ? 'positive' : 'negative'}`} style={{ fontSize: 18 }}>
              {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(0)}
            </span>
          </div>
        </div>
      )}

      <div className="panel" style={{ padding: 0, marginBottom: 20 }}>
        <div className="panel-header" style={{ padding: '10px 14px', margin: 0 }}>
          <h3 className="panel-title" style={{ fontSize: 13 }}>Open Positions ({positions.length})</h3>
        </div>
        {positions.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ fontSize: 11 }}>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th>Expiry</th>
                  <th className="numeric">Strike</th>
                  <th className="numeric">Qty</th>
                  <th className="numeric">Buy Avg</th>
                  <th className="numeric">LTP</th>
                  <th className="numeric">P&L</th>
                  <th className="numeric">P&L%</th>
                  <th className="numeric">Product</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p: any, i: number) => {
                  const live = ticks[p.symbol]
                  const ltp = live?.last_price || p.last_price || 0
                  const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : p.unrealised_pnl
                  const pnlPct = p.average_buy_price ? (pnl / (Math.abs(p.quantity) * p.average_buy_price) * 100) : 0
                  return (
                    <tr key={i}>
                      <td style={{ fontWeight: 600 }}>{p.symbol?.split(':').pop()}</td>
                      <td>
                        <span className={`badge ${p.instrument_type === 'OPT' ? 'badge-violet' : p.instrument_type === 'FUT' ? 'badge-cyan' : 'badge-green'}`} style={{ fontSize: 9 }}>
                          {p.instrument_type || 'EQ'}
                        </span>
                      </td>
                      <td style={{ fontSize: 11 }}>{p.expiry_date || '-'}</td>
                      <td className="numeric">{p.strike_price || '-'}</td>
                      <td className="numeric">{p.quantity}</td>
                      <td className="numeric">{p.average_buy_price?.toFixed(1) || '-'}</td>
                      <td className="numeric">{ltp?.toFixed(1) || '-'}</td>
                      <td className={`numeric ${pnl >= 0 ? 'positive' : 'negative'}`} style={{ fontWeight: 600 }}>
                        {pnl >= 0 ? '+' : ''}{pnl?.toFixed(0) || '0'}
                      </td>
                      <td className={`numeric ${pnlPct >= 0 ? 'positive' : 'negative'}`}>
                        {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                      </td>
                      <td className="numeric">
                        <span className={`badge ${p.product === 'INTRADAY' ? 'badge-cyan' : 'badge-violet'}`} style={{ fontSize: 9 }}>
                          {p.product}
                        </span>
                      </td>
                      <td>
                        <button className="btn btn-sm btn-danger" style={{ fontSize: 9, padding: '2px 8px' }}
                          onClick={() => sqOff(p.symbol, p.quantity)}>
                          {p.quantity > 0 ? 'SELL' : 'BUY'}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, margin: 0, textAlign: 'center' }}>
            {loading ? 'Loading...' : 'No open positions'}
          </p>
        )}
      </div>

      <div className="panel" style={{ padding: 0 }}>
        <div className="panel-header" style={{ padding: '10px 14px', margin: 0 }}>
          <h3 className="panel-title" style={{ fontSize: 13 }}>Orders ({orders.length})</h3>
        </div>
        {orders.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ fontSize: 11 }}>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th>Expiry</th>
                  <th className="numeric">Strike</th>
                  <th>Side</th>
                  <th className="numeric">Qty</th>
                  <th className="numeric">Price</th>
                  <th className="numeric">Filled</th>
                  <th className="numeric">Avg</th>
                  <th>Status</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o: any, i: number) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600 }}>{o.symbol?.split(':').pop()}</td>
                    <td>
                      <span className={`badge ${o.instrument_type === 'OPT' ? 'badge-violet' : o.instrument_type === 'FUT' ? 'badge-cyan' : 'badge-green'}`} style={{ fontSize: 9 }}>
                        {o.instrument_type || 'EQ'}
                      </span>
                    </td>
                    <td style={{ fontSize: 11 }}>{o.expiry_date || '-'}</td>
                    <td className="numeric">{o.strike_price || '-'}</td>
                    <td style={{ color: o.side === 'BUY' ? '#22c55e' : '#ef4444' }}>{o.side}</td>
                    <td className="numeric">{o.quantity}</td>
                    <td className="numeric">{o.price?.toFixed(1) || '-'}</td>
                    <td className="numeric">{o.filled_quantity || 0}</td>
                    <td className="numeric">{o.average_price?.toFixed(1) || '-'}</td>
                    <td>
                      <span className={`badge ${o.status === 'FILLED' ? 'badge-green' : o.status === 'OPEN' ? 'badge-cyan' : o.status === 'REJECTED' ? 'badge-red' : 'badge-violet'}`}
                        style={{ fontSize: 9 }}>
                        {o.status}
                      </span>
                    </td>
                    <td style={{ fontSize: 10, color: '#555570' }}>
                      {o.created_at ? new Date(o.created_at).toLocaleTimeString() : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, margin: 0, textAlign: 'center' }}>
            {loading ? 'Loading...' : 'No orders yet'}
          </p>
        )}
      </div>
    </div>
  )
}
