'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { api } from '@/lib/api'
import { useMarketData } from '@/lib/use-market-data'
import { usePolling } from '@/lib/use-polling'
import { useAuth } from '@/lib/auth-context'
import { useToast } from '@/lib/use-toast'

function downloadCSV(rows: string[][], filename: string) {
  const csv = rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

export default function PositionsPage() {
  const { token } = useAuth()
  const { ticks, connected, subscribe } = useMarketData()
  const { toast } = useToast()
  const [positions, setPositions] = useState<any[]>([])
  const [orders, setOrders] = useState<any[]>([])
  const [funds, setFunds] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState('')

  useEffect(() => {
    const symbols = ['NSE:NIFTY50-INDEX', 'NSE:NIFTYBANK-INDEX', 'NSE:FINNIFTY-INDEX',
      'BSE:SENSEX-INDEX', 'NSE:INDIAVIX-INDEX']
    subscribe(symbols)
  }, [subscribe])

  const loadData = useCallback(async () => {
    try {
      const [p, o, f] = await Promise.all([
        api.engine.positions().catch(() => ({ positions: [] })),
        api.engine.orders().catch(() => ({ orders: [] })),
        api.engine.funds().catch(() => ({ funds: null })),
      ])
      setPositions((p as any).positions || [])
      setOrders((o as any).orders || [])
      setFunds((f as any).funds || null)
      setLastRefresh(new Date().toLocaleTimeString())
    } catch {} finally { setLoading(false) }
  }, [])

  usePolling(loadData, 3000, !!token)

  useEffect(() => { loadData() }, [loadData])

  const totalPnl = positions.reduce((sum: number, p: any) => {
    const live = ticks[p.symbol]
    const ltp = live?.last_price || p.last_price || 0
    const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : p.unrealised_pnl
    return sum + (pnl || 0)
  }, 0)

  const cancelOrder = async (orderId: string) => {
    try {
      await api.engine.cancelOrder(orderId)
      toast('success', 'Order cancelled')
      setTimeout(loadData, 500)
    } catch {
      toast('error', 'Failed to cancel order')
    }
  }

  const sqOff = async (symbol: string, qty: number) => {
    const side = qty > 0 ? 'SELL' : 'BUY'
    await api.engine.trade({
      symbol, side, quantity: Math.abs(qty), price: 0,
      exchange: 'NFO', order_type: 'MARKET', product: 'INTRADAY',
      instrument_type: positions.find(p => p.symbol === symbol)?.instrument_type || 'EQ',
    })
    setTimeout(loadData, 1000)
  }

  return (
    <div>
      <div className="t-page-header">
        <div>
          <h1 className="t-page-title">Positions</h1>
          <p className="t-page-subtitle" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-sub'}`} />
            {connected ? 'Live' : 'Connecting...'}
            {lastRefresh && <span className="t-faint" style={{ marginLeft: 8 }}>Updated <span className="t-num">{lastRefresh}</span></span>}
          </p>
        </div>
        <button className="t-btn t-btn-ghost t-btn-sm" onClick={loadData}>Refresh</button>
      </div>

      {funds && (
        <div className="t-row" style={{ gap: 12, marginBottom: 16 }}>
          <div className="t-panel" style={{ flex: 1 }}>
            <div className="t-stat">
              <div className="t-stat-label">Available</div>
              <div className="t-stat-value">{(funds.available_margin || 0).toLocaleString()}</div>
            </div>
          </div>
          <div className="t-panel" style={{ flex: 1 }}>
            <div className="t-stat">
              <div className="t-stat-label">Used</div>
              <div className="t-stat-value" style={{ color: 'var(--cyan)' }}>{(funds.used_margin || 0).toLocaleString()}</div>
            </div>
          </div>
          <div className="t-panel" style={{ flex: 1 }}>
            <div className="t-stat">
              <div className="t-stat-label">Total P&amp;L</div>
              <div className={`t-stat-value ${totalPnl >= 0 ? 't-up' : 't-down'}`}>
                {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(0)}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Open Positions ({positions.length})</h3>
          {positions.length > 0 && (
            <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => {
              const header = ['Symbol', 'Type', 'Expiry', 'Strike', 'Qty', 'Buy Avg', 'LTP', 'P&L', 'P&L%', 'Product']
              const data = positions.map((p: any) => {
                const live = ticks[p.symbol]
                const ltp = live?.last_price || p.last_price || 0
                const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : p.unrealised_pnl
                const pnlPct = p.average_buy_price ? (pnl / (Math.abs(p.quantity) * p.average_buy_price) * 100) : 0
                return [p.symbol, p.instrument_type, p.expiry_date || '', String(p.strike_price || ''), String(p.quantity), p.average_buy_price?.toFixed(1) || '', ltp.toFixed(1), pnl.toFixed(0), pnlPct.toFixed(2), p.product]
              })
              downloadCSV([header, ...data], `positions-${new Date().toISOString().slice(0, 10)}.csv`)
            }}>
              Export CSV
            </button>
          )}
        </div>
        {positions.length > 0 ? (
          <div className="t-table-wrap">
            <table className="t-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th>Expiry</th>
                  <th className="t-num">Strike</th>
                  <th className="t-num">Qty</th>
                  <th className="t-num">Buy Avg</th>
                  <th className="t-num">LTP</th>
                  <th className="t-num">P&amp;L</th>
                  <th className="t-num">P&amp;L%</th>
                  <th className="t-num">Product</th>
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
                        <span className={`t-badge ${p.instrument_type === 'OPT' ? 't-badge-violet' : p.instrument_type === 'FUT' ? 't-badge-cyan' : 't-badge-green'}`}>
                          {p.instrument_type || 'EQ'}
                        </span>
                      </td>
                      <td className="t-faint" style={{ fontSize: 11 }}>{p.expiry_date || '-'}</td>
                      <td className="t-num">{p.strike_price || '-'}</td>
                      <td className="t-num">{p.quantity}</td>
                      <td className="t-num">{p.average_buy_price?.toFixed(1) || '-'}</td>
                      <td className="t-num">{ltp?.toFixed(1) || '-'}</td>
                      <td className={`t-num ${pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 600 }}>
                        {pnl >= 0 ? '+' : ''}{pnl?.toFixed(0) || '0'}
                      </td>
                      <td className={`t-num ${pnlPct >= 0 ? 't-up' : 't-down'}`}>
                        {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                      </td>
                      <td className="t-num">
                        <span className={`t-badge ${p.product === 'INTRADAY' ? 't-badge-cyan' : 't-badge-violet'}`}>
                          {p.product}
                        </span>
                      </td>
                      <td>
                        <button className="t-btn t-btn-sm t-btn-danger"
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
          <div className="t-panel-body" style={{ textAlign: 'center', padding: 20 }}>
            <span className="t-faint">{loading ? 'Loading...' : 'No open positions'}</span>
          </div>
        )}
      </div>

      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Orders ({orders.length})</h3>
          {orders.length > 0 && (
            <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => {
              const header = ['Symbol', 'Type', 'Expiry', 'Strike', 'Side', 'Qty', 'Price', 'Filled', 'Avg', 'Status', 'Time']
              const data = orders.map((o: any) => [o.symbol, o.instrument_type, o.expiry_date || '', String(o.strike_price || ''), o.side, String(o.quantity), o.price?.toFixed(1) || '', String(o.filled_quantity || 0), o.average_price?.toFixed(1) || '', o.status, o.created_at ? new Date(o.created_at).toISOString() : ''])
              downloadCSV([header, ...data], `orders-${new Date().toISOString().slice(0, 10)}.csv`)
            }}>
              Export CSV
            </button>
          )}
        </div>
        {orders.length > 0 ? (
          <div className="t-table-wrap">
            <table className="t-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th>Expiry</th>
                  <th className="t-num">Strike</th>
                  <th>Side</th>
                  <th className="t-num">Qty</th>
                  <th className="t-num">Price</th>
                  <th className="t-num">Filled</th>
                  <th className="t-num">Avg</th>
                  <th>Status</th>
                  <th>Time</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o: any, i: number) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600 }}>{o.symbol?.split(':').pop()}</td>
                    <td>
                      <span className={`t-badge ${o.instrument_type === 'OPT' ? 't-badge-violet' : o.instrument_type === 'FUT' ? 't-badge-cyan' : 't-badge-green'}`}>
                        {o.instrument_type || 'EQ'}
                      </span>
                    </td>
                    <td className="t-faint" style={{ fontSize: 11 }}>{o.expiry_date || '-'}</td>
                    <td className="t-num">{o.strike_price || '-'}</td>
                    <td className={o.side === 'BUY' ? 't-up' : 't-down'} style={{ fontWeight: 600 }}>{o.side}</td>
                    <td className="t-num">{o.quantity}</td>
                    <td className="t-num">{o.price?.toFixed(1) || '-'}</td>
                    <td className="t-num">{o.filled_quantity || 0}</td>
                    <td className="t-num">{o.average_price?.toFixed(1) || '-'}</td>
                    <td>
                      <span className={`t-badge ${o.status === 'FILLED' ? 't-badge-green' : o.status === 'OPEN' ? 't-badge-cyan' : o.status === 'REJECTED' ? 't-badge-red' : 't-badge-violet'}`}>
                        {o.status}
                      </span>
                    </td>
                    <td className="t-faint t-num" style={{ fontSize: 10 }}>
                      {o.created_at ? new Date(o.created_at).toLocaleTimeString() : '-'}
                    </td>
                    <td>
                      {['OPEN', 'PENDING', 'PARTIALLY_FILLED'].includes(o.status) && (
                        <button className="t-btn t-btn-sm t-btn-danger"
                          onClick={() => cancelOrder(o.id)}>
                          Cancel
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="t-panel-body" style={{ textAlign: 'center', padding: 20 }}>
            <span className="t-faint">{loading ? 'Loading...' : 'No orders yet'}</span>
          </div>
        )}
      </div>
    </div>
  )
}
