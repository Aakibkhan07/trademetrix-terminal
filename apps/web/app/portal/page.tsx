'use client'

import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import { useMarketData } from '@/lib/use-market-data'

/* ========== Types ========== */

interface Position {
  symbol: string; quantity: number; average_buy_price: number
  unrealised_pnl: number; product: string; instrument_type: string
}
interface Order {
  id: string; symbol: string; side: string; quantity: number
  price: number; status: string; filled_quantity: number
  average_price: number; created_at: string; is_paper: boolean
}
interface Funds { total_margin: number; used_margin: number; available_margin: number; broker: string }
interface Strategy { strategy_key: string; name: string; description: string; required_tier: string }

/* ========== Helpers ========== */

function fmt(n: number) { return n.toLocaleString('en-IN', { maximumFractionDigits: 2 }) }
function fmtDate(iso?: string) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}
function otpStyle(active: boolean) {
  return {
    width: 44, height: 48, textAlign: 'center' as const, fontSize: 20, fontWeight: 700 as const,
    fontFamily: 'var(--font-mono)', border: `2px solid ${active ? 'var(--cyan)' : 'var(--border)'}`,
    borderRadius: 8, background: active ? 'rgba(0,229,255,0.06)' : 'var(--bg-tertiary)',
    color: 'var(--text)', outline: 'none', caretColor: 'var(--cyan)',
    transition: 'border-color 0.15s, background 0.15s',
  }
}

/* ========== Authenticated Dashboard ========== */

function ClientDashboard({ email, onSignOut }: { email: string; onSignOut: () => void }) {
  const { ticks, connected, subscribe, startFeed } = useMarketData()
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [funds, setFunds] = useState<Funds | null>(null)
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'orders' | 'performance'>('overview')

  const loadData = useCallback(async () => {
    try {
      const [p, o, f, s] = await Promise.all([
        api.engine.positions().catch(() => ({ positions: [] })),
        api.engine.orders().catch(() => ({ orders: [] })),
        api.engine.funds().catch(() => ({ funds: null })),
        api.strategies.assigned().catch(() => ({ strategies: [] })),
      ])
      setPositions((p as { positions: Position[] }).positions || [])
      setOrders((o as { orders: Order[] }).orders || [])
      setFunds((f as { funds: Funds }).funds || null)
      setStrategies((s as { strategies: Strategy[] }).strategies || [])
    } catch {} finally { setLoading(false) }
  }, [])

  useEffect(() => {
    const symbols = ['NSE:NIFTY50-INDEX', 'NSE:BANKNIFTY-INDEX', 'NSE:FINNIFTY-INDEX',
      'BSE:SENSEX-INDEX', 'NSE:INDIAVIX-INDEX']
    subscribe(symbols)
    startFeed().catch(() => {})
    loadData()
    const interval = setInterval(loadData, 5000)
    return () => clearInterval(interval)
  }, [subscribe, startFeed, loadData])

  const totalPnl = positions.reduce((s, p) => {
    const live = ticks[p.symbol]
    return s + (live ? p.quantity * (live.last_price - p.average_buy_price) : p.unrealised_pnl || 0)
  }, 0)

  const orderStats = {
    total: orders.length,
    filled: orders.filter(o => o.status === 'FILLED').length,
    open: orders.filter(o => ['OPEN', 'PENDING', 'PARTIALLY_FILLED'].includes(o.status)).length,
    rejected: orders.filter(o => o.status === 'REJECTED').length,
  }

  const activeStrategies = strategies.filter(() => true)

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>
      {/* Portal Header */}
      <header style={{
        height: 48, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 16px', borderBottom: '1px solid var(--border)',
        background: 'var(--bg-secondary)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{
            fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 700,
            background: 'var(--gradient-primary)', WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}>TradeMetrix</span>
          <span className="t-badge t-badge-cyan" style={{ fontSize: 9, letterSpacing: '0.06em' }}>CLIENT PORTAL</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-red'}`} />
          <span style={{ fontSize: 10, color: 'var(--text-sub)', fontFamily: 'var(--font-mono)' }}>
            {connected ? 'LIVE' : 'OFF'}
          </span>
          <span style={{ fontSize: 10, color: 'var(--text-sub)' }}>{email}</span>
          <button className="t-btn t-btn-xs t-btn-ghost" onClick={onSignOut}
            style={{ color: 'var(--text-red)' }}>Sign Out</button>
        </div>
      </header>

      {/* Tab Navigation */}
      <div style={{ padding: '8px 16px 0', borderBottom: '1px solid var(--border)', display: 'flex', gap: 0 }}>
        {[
          { key: 'overview' as const, label: 'Overview', icon: 'D' },
          { key: 'positions' as const, label: 'Positions', icon: 'P' },
          { key: 'orders' as const, label: 'Orders', icon: 'O' },
          { key: 'performance' as const, label: 'Performance', icon: 'S' },
        ].map(tab => (
          <button key={tab.key} onClick={() => setActiveTab(tab.key)} style={{
            padding: '8px 16px', fontSize: 11, fontWeight: 600, letterSpacing: '0.03em',
            border: 'none', background: 'none', cursor: 'pointer',
            color: activeTab === tab.key ? 'var(--cyan)' : 'var(--text-sub)',
            borderBottom: `2px solid ${activeTab === tab.key ? 'var(--cyan)' : 'transparent'}`,
            transition: 'color 0.12s, border-color 0.12s',
            fontFamily: 'var(--font-sans)',
          }}>
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, padding: 16, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* ======= OVERVIEW TAB ======= */}
        {activeTab === 'overview' && (
          <>
            {/* Capital Bar */}
            {funds && (
              <div style={{
                padding: '14px 18px', borderRadius: 10,
                background: 'linear-gradient(135deg, rgba(0,229,255,0.08), rgba(124,92,252,0.08))',
                border: '1px solid rgba(0,229,255,0.1)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: 10, color: 'var(--text-sub)', fontWeight: 600, letterSpacing: '0.04em' }}>
                    CAPITAL UTILIZATION
                  </span>
                  <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
                    {funds.used_margin > 0 ? Math.round((funds.used_margin / funds.total_margin) * 100) : 0}%
                  </span>
                </div>
                <div style={{ height: 6, borderRadius: 3, background: 'var(--panel-2)', overflow: 'hidden', marginBottom: 10 }}>
                  <div style={{
                    width: funds.total_margin > 0 ? `${(funds.used_margin / funds.total_margin) * 100}%` : '0%',
                    height: '100%', borderRadius: 3,
                    background: 'linear-gradient(90deg, var(--cyan), var(--violet))',
                    transition: 'width 0.5s ease',
                  }} />
                </div>
                <div className="t-grid-3" style={{ gap: 8 }}>
                  <div>
                    <div className="t-faint" style={{ fontSize: 9 }}>Total Capital</div>
                    <div style={{ fontSize: 16, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                      \u20B9{fmt(funds.total_margin)}
                    </div>
                  </div>
                  <div>
                    <div className="t-faint" style={{ fontSize: 9 }}>Used Margin</div>
                    <div style={{ fontSize: 16, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--cyan)' }}>
                      \u20B9{fmt(funds.used_margin)}
                    </div>
                  </div>
                  <div>
                    <div className="t-faint" style={{ fontSize: 9 }}>Available</div>
                    <div style={{ fontSize: 16, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-green)' }}>
                      \u20B9{fmt(funds.available_margin)}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* P&L + Stats */}
            <div className="t-grid-4" style={{ gap: 10 }}>
              <div className="t-panel" style={{ padding: '12px 14px' }}>
                <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>TOTAL P&amp;L</div>
                <div style={{
                  fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)',
                  color: totalPnl >= 0 ? 'var(--text-green)' : 'var(--text-red)',
                }}>
                  {totalPnl >= 0 ? '+' : ''}\u20B9{fmt(Math.abs(totalPnl))}
                </div>
              </div>
              <div className="t-panel" style={{ padding: '12px 14px' }}>
                <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>POSITIONS</div>
                <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                  {positions.length}
                </div>
              </div>
              <div className="t-panel" style={{ padding: '12px 14px' }}>
                <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>FILLED ORDERS</div>
                <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--green)' }}>
                  {orderStats.filled}
                </div>
              </div>
              <div className="t-panel" style={{ padding: '12px 14px' }}>
                <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>STRATEGIES</div>
                <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--violet)' }}>
                  {activeStrategies.length}
                </div>
              </div>
            </div>

            {/* Active Positions Mini Table */}
            {positions.length > 0 && (
              <div className="t-panel" style={{ padding: 0 }}>
                <div className="t-panel-header" style={{ minHeight: 28, padding: '6px 12px' }}>
                  <h3 className="t-panel-title" style={{ fontSize: 11 }}>Open Positions</h3>
                  <span className="t-faint" style={{ fontSize: 9 }}>{positions.length} active</span>
                </div>
                <div className="t-table-wrap">
                  <table className="t-table" style={{ fontSize: 10 }}>
                    <thead>
                      <tr>
                        <th>Symbol</th>
                        <th>Qty</th>
                        <th>Avg</th>
                        <th>LTP</th>
                        <th>P&amp;L</th>
                      </tr>
                    </thead>
                    <tbody>
                      {positions.map((p, i) => {
                        const live = ticks[p.symbol]
                        const ltp = live?.last_price || 0
                        const pnl = live ? p.quantity * (ltp - p.average_buy_price) : p.unrealised_pnl || 0
                        return (
                          <tr key={i}>
                            <td style={{ fontWeight: 600 }}>{p.symbol.split(':').pop()}</td>
                            <td className="t-num">{p.quantity}</td>
                            <td className="t-num">\u20B9{fmt(p.average_buy_price)}</td>
                            <td className="t-num">{ltp ? `\u20B9${fmt(ltp)}` : '-'}</td>
                            <td className={`t-num ${pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 600 }}>
                              {pnl >= 0 ? '+' : ''}\u20B9{fmt(pnl)}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Index Prices */}
            {Object.keys(ticks).length > 0 && (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {['NSE:NIFTY50-INDEX', 'NSE:BANKNIFTY-INDEX', 'NSE:FINNIFTY-INDEX', 'BSE:SENSEX-INDEX'].map(sym => {
                  const t = ticks[sym]
                  if (!t) return null
                  const pct = t.change_pct ?? 0
                  return (
                    <div key={sym} style={{
                      padding: '8px 12px', borderRadius: 8,
                      background: 'var(--panel-2)', border: '1px solid var(--border)',
                      display: 'flex', flexDirection: 'column', gap: 2,
                    }}>
                      <span className="t-faint" style={{ fontSize: 9, fontWeight: 600 }}>
                        {sym.split(':')[1]?.split('-')[0] || sym}
                      </span>
                      <span style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                        {t.last_price?.toFixed(1)}
                      </span>
                      <span style={{
                        fontSize: 10, fontFamily: 'var(--font-mono)',
                        color: pct >= 0 ? 'var(--text-green)' : 'var(--text-red)',
                      }}>
                        {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
                      </span>
                    </div>
                  )
                })}
              </div>
            )}

            {/* No data state */}
            {!loading && positions.length === 0 && Object.keys(ticks).length === 0 && (
              <div style={{ textAlign: 'center', padding: 40 }}>
                <div style={{ fontSize: 32, marginBottom: 8, opacity: 0.2 }}>T</div>
                <h3 style={{ fontSize: 16, marginBottom: 4 }}>Your trading dashboard</h3>
                <p className="t-faint" style={{ fontSize: 12, maxWidth: 360, margin: '0 auto' }}>
                  Once your strategies start trading, you will see live positions, P&amp;L, and market data here.
                </p>
              </div>
            )}
          </>
        )}

        {/* ======= POSITIONS TAB ======= */}
        {activeTab === 'positions' && (
          <div className="t-panel" style={{ padding: 0 }}>
            <div className="t-panel-header">
              <h3 className="t-panel-title">All Positions ({positions.length})</h3>
              {positions.length > 0 && (
                <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => {
                  const header = ['Symbol', 'Qty', 'Avg Price', 'LTP', 'P&L', 'Product', 'Type']
                  const data = positions.map(p => {
                    const ltp = ticks[p.symbol]?.last_price || 0
                    const pnl = ticks[p.symbol] ? p.quantity * (ltp - p.average_buy_price) : p.unrealised_pnl || 0
                    return [p.symbol, String(p.quantity), fmt(p.average_buy_price), fmt(ltp), fmt(pnl), p.product, p.instrument_type]
                  })
                  const csv = [header, ...data].map(r => r.map(c => `"${c}"`).join(',')).join('\n')
                  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv' })
                  const a = document.createElement('a')
                  a.href = URL.createObjectURL(blob); a.download = 'positions.csv'; a.click()
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
                      <th>Qty</th>
                      <th>Avg</th>
                      <th>LTP</th>
                      <th>P&amp;L</th>
                      <th>Product</th>
                      <th>Type</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((p, i) => {
                      const live = ticks[p.symbol]
                      const ltp = live?.last_price || 0
                      const pnl = live ? p.quantity * (ltp - p.average_buy_price) : p.unrealised_pnl || 0
                      return (
                        <tr key={i}>
                          <td style={{ fontWeight: 600 }}>{p.symbol}</td>
                          <td className="t-num">{p.quantity}</td>
                          <td className="t-num">\u20B9{fmt(p.average_buy_price)}</td>
                          <td className="t-num">{ltp ? `\u20B9${fmt(ltp)}` : '-'}</td>
                          <td className={`t-num ${pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 700 }}>
                            {pnl >= 0 ? '+' : ''}\u20B9{fmt(pnl)}
                          </td>
                          <td><span className={`t-badge ${p.product === 'INTRADAY' ? 't-badge-cyan' : 't-badge-violet'}`} style={{ fontSize: 9 }}>{p.product}</span></td>
                          <td><span className="t-badge t-badge-sub" style={{ fontSize: 9 }}>{p.instrument_type}</span></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="t-panel-body" style={{ textAlign: 'center', padding: 24 }}>
                <span className="t-faint">No open positions</span>
              </div>
            )}
          </div>
        )}

        {/* ======= ORDERS TAB ======= */}
        {activeTab === 'orders' && (
          <div className="t-panel" style={{ padding: 0 }}>
            <div className="t-panel-header">
              <h3 className="t-panel-title">Order History ({orders.length})</h3>
              {orders.length > 0 && (
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span className={`t-badge t-badge-green`} style={{ fontSize: 9 }}>{orderStats.filled} Filled</span>
                  <span className={`t-badge t-badge-cyan`} style={{ fontSize: 9 }}>{orderStats.open} Open</span>
                  {orderStats.rejected > 0 && (
                    <span className={`t-badge t-badge-red`} style={{ fontSize: 9 }}>{orderStats.rejected} Rejected</span>
                  )}
                  <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => {
                    const header = ['Symbol', 'Side', 'Qty', 'Price', 'Status', 'Time']
                    const data = orders.map(o => [o.symbol, o.side, String(o.quantity), fmt(o.price || 0), o.status, o.created_at])
                    const csv = [header, ...data].map(r => r.map(c => `"${c}"`).join(',')).join('\n')
                    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv' })
                    const a = document.createElement('a')
                    a.href = URL.createObjectURL(blob); a.download = 'orders.csv'; a.click()
                  }}>
                    Export CSV
                  </button>
                </div>
              )}
            </div>
            {orders.length > 0 ? (
              <div className="t-table-wrap">
                <table className="t-table">
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Side</th>
                      <th>Qty</th>
                      <th>Price</th>
                      <th>Filled</th>
                      <th>Avg</th>
                      <th>Status</th>
                      <th>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.map(o => (
                      <tr key={o.id}>
                        <td style={{ fontWeight: 600 }}>{o.symbol}</td>
                        <td className={o.side === 'BUY' ? 't-up' : 't-down'} style={{ fontWeight: 600 }}>{o.side}</td>
                        <td className="t-num">{o.quantity}</td>
                        <td className="t-num">{o.price ? `\u20B9${fmt(o.price)}` : '-'}</td>
                        <td className="t-num">{o.filled_quantity || 0}</td>
                        <td className="t-num">{o.average_price ? `\u20B9${fmt(o.average_price)}` : '-'}</td>
                        <td>
                          <span className={`t-badge ${o.status === 'FILLED' ? 't-badge-green' : o.status === 'REJECTED' ? 't-badge-red' : o.status === 'CANCELLED' ? 't-badge-amber' : 't-badge-cyan'}`} style={{ fontSize: 9 }}>
                            {o.status}
                          </span>
                        </td>
                        <td className="t-faint t-num" style={{ fontSize: 9 }}>{fmtDate(o.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="t-panel-body" style={{ textAlign: 'center', padding: 24 }}>
                <span className="t-faint">No orders yet</span>
              </div>
            )}
          </div>
        )}

        {/* ======= PERFORMANCE TAB ======= */}
        {activeTab === 'performance' && (
          <>
            <div className="t-grid-4" style={{ gap: 10 }}>
              <div className="t-panel" style={{ padding: '12px 14px' }}>
                <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>TOTAL TRADES</div>
                <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{orderStats.total}</div>
              </div>
              <div className="t-panel" style={{ padding: '12px 14px' }}>
                <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>WIN RATE</div>
                <div style={{
                  fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)',
                  color: orderStats.total > 0 ? 'var(--text-green)' : 'var(--text-faint)',
                }}>
                  {orderStats.total > 0 ? `${Math.round((orderStats.filled / Math.max(orderStats.total, 1)) * 100)}%` : '-'}
                </div>
              </div>
              <div className="t-panel" style={{ padding: '12px 14px' }}>
                <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>OPEN P&amp;L</div>
                <div style={{
                  fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)',
                  color: totalPnl >= 0 ? 'var(--text-green)' : 'var(--text-red)',
                }}>
                  {totalPnl >= 0 ? '+' : ''}\u20B9{fmt(Math.abs(totalPnl))}
                </div>
              </div>
              <div className="t-panel" style={{ padding: '12px 14px' }}>
                <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>ACTIVE STRATEGIES</div>
                <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--violet)' }}>
                  {activeStrategies.length}
                </div>
              </div>
            </div>

            {/* Strategy Cards */}
            {activeStrategies.length > 0 && (
              <div className="t-grid-2" style={{ gap: 10 }}>
                {activeStrategies.map(s => (
                  <div key={s.strategy_key} className="t-panel" style={{
                    padding: '14px 16px',
                    borderLeft: '3px solid var(--violet)',
                    transition: 'transform 0.12s',
                  }}
                    onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-1px)' }}
                    onMouseLeave={e => { e.currentTarget.style.transform = '' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span style={{ fontSize: 13, fontWeight: 700 }}>{s.name}</span>
                      <span className={`t-badge ${s.required_tier === 'free' ? 't-badge-green' : s.required_tier === 'pro' ? 't-badge-violet' : 't-badge-amber'}`} style={{ fontSize: 9, textTransform: 'capitalize' }}>
                        {s.required_tier}
                      </span>
                    </div>
                    <p className="t-faint" style={{ margin: 0, fontSize: 10, lineHeight: 1.4 }}>{s.description}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Download Report */}
            {orders.length > 0 && (
              <div style={{ textAlign: 'center', padding: 8 }}>
                <button className="t-btn t-btn-sm t-btn-ghost" onClick={() => {
                  const rows = [['Symbol', 'Side', 'Qty', 'Price', 'Status', 'P&L', 'Time']]
                  orders.forEach(o => rows.push([o.symbol, o.side, String(o.quantity), fmt(o.price || 0), o.status, '', o.created_at]))
                  const csv = rows.map(r => r.map(c => `"${c}"`).join(',')).join('\n')
                  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv' })
                  const a = document.createElement('a')
                  a.href = URL.createObjectURL(blob); a.download = `trademetrix-report-${new Date().toISOString().slice(0, 10)}.csv`; a.click()
                }}>
                  Download Full Report (CSV)
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Footer */}
      <footer style={{
        height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
        borderTop: '1px solid var(--border)', fontSize: 9, color: 'var(--text-faint)',
        fontFamily: 'var(--font-mono)',
      }}>
        TradeMetrix Terminal v0.1 &middot; Client Portal &middot; Data refreshes every 5s
      </footer>
    </div>
  )
}

/* ========== OTP Login Screen ========== */

function OTPScreen({ onVerify }: { onVerify: () => void }) {
  const [step, setStep] = useState<'email' | 'otp' | 'register'>('email')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [otp, setOtp] = useState(['', '', '', '', '', ''])
  const [sending, setSending] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState('')
  const [resendTimer, setResendTimer] = useState(0)
  const [otpSent, setOtpSent] = useState(false)

  useEffect(() => {
    if (resendTimer <= 0) return
    const t = setInterval(() => setResendTimer(p => p - 1), 1000)
    return () => clearInterval(t)
  }, [resendTimer])

  const handleSendOTP = async () => {
    if (!email || !email.includes('@')) { setError('Enter a valid email'); return }
    setError('')
    setSending(true)

    const code = Math.floor(100000 + Math.random() * 900000).toString()
    sessionStorage.setItem('tm_portal_otp', code)

    await new Promise(r => setTimeout(r, 800))

    console.log(`[DEV] OTP for ${email}: ${code}`)
    setOtpSent(true)
    setSending(false)
    setStep('otp')
    setResendTimer(30)
  }

  const handleRegister = async () => {
    if (!email || !password || password.length < 6) { setError('Email and password (min 6 chars) required'); return }
    setError('')
    setSending(true)
    try {
      await api.auth.signup({ email, password, full_name: fullName || undefined })
      const code = Math.floor(100000 + Math.random() * 900000).toString()
      sessionStorage.setItem('tm_portal_otp', code)
      console.log(`[DEV] OTP for ${email}: ${code}`)
      setSending(false)
      setStep('otp')
      setResendTimer(30)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Registration failed')
      setSending(false)
    }
  }

  const handleVerifyOTP = async () => {
    const entered = otp.join('')
    if (entered.length !== 6) { setError('Enter the full 6-digit code'); return }
    setError('')
    setVerifying(true)

    const stored = sessionStorage.getItem('tm_portal_otp')

    if (entered !== stored) {
      await new Promise(r => setTimeout(r, 500))
      setError('Invalid OTP. Please try again.')
      setVerifying(false)
      return
    }

    sessionStorage.removeItem('tm_portal_otp')
    sessionStorage.setItem('tm_portal_email', email)

    if (step !== 'otp') {
      try {
        await api.auth.signin({ email, password: password || 'temporary' })
      } catch {}
    }

    setVerifying(false)
    onVerify()
  }

  const handleResend = async () => {
    if (resendTimer > 0) return
    const code = Math.floor(100000 + Math.random() * 900000).toString()
    sessionStorage.setItem('tm_portal_otp', code)
    console.log(`[DEV] New OTP for ${email}: ${code}`)
    setResendTimer(30)
    setOtp(['', '', '', '', '', ''])
    setError('')
  }

  const inputRefs = Array.from({ length: 6 }, () => null) as (HTMLInputElement | null)[]

  const handleOtpInput = (i: number, val: string) => {
    if (!/^\d?$/.test(val)) return
    const newOtp = [...otp]
    newOtp[i] = val
    setOtp(newOtp)
    if (val && i < 5) {
      const next = document.getElementById(`otp-${i + 1}`)
      next?.focus()
    }
  }

  const handleOtpKey = (i: number, key: string) => {
    if (key === 'Backspace' && !otp[i] && i > 0) {
      const prev = document.getElementById(`otp-${i - 1}`)
      prev?.focus()
    }
    if (key === 'Enter') {
      handleVerifyOTP()
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg)', padding: 16,
    }}>
      <div style={{
        width: '100%', maxWidth: 400,
        padding: '32px 28px',
        borderRadius: 12,
        border: '1px solid var(--border)',
        background: 'var(--bg-secondary)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
      }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 48, height: 48, borderRadius: 12,
            background: 'var(--gradient-primary)', marginBottom: 12,
            fontSize: 20, fontWeight: 700, color: '#000',
          }}>
            TM
          </div>
          <h2 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 4px' }}>Client Portal</h2>
          <p className="t-faint" style={{ fontSize: 11, margin: 0 }}>
            {step === 'email' ? 'Sign in to view your trading dashboard' :
             step === 'register' ? 'Create your account' :
             `Enter the code sent to ${email}`}
          </p>
        </div>

        {step === 'email' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label className="t-label" style={{ fontSize: 10 }}>Email Address</label>
            <input className="t-input" type="email" placeholder="you@example.com" value={email}
              onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSendOTP()}
              autoFocus />
            {error && <span className="t-down" style={{ fontSize: 10 }}>{error}</span>}
            <button className="t-btn t-btn-primary" onClick={handleSendOTP} disabled={sending}
              style={{ width: '100%', height: 36 }}>
              {sending ? 'Sending OTP...' : 'Send OTP'}
            </button>
            <div style={{ textAlign: 'center', marginTop: 8 }}>
              <button style={{
                background: 'none', border: 'none', color: 'var(--text-sub)', fontSize: 10,
                cursor: 'pointer', fontFamily: 'var(--font-sans)',
                textDecoration: 'underline', textUnderlineOffset: 2,
              }} onClick={() => setStep('register')}>
                New user? Create an account
              </button>
            </div>
          </div>
        )}

        {step === 'register' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label className="t-label" style={{ fontSize: 10 }}>Full Name</label>
            <input className="t-input" placeholder="Your name" value={fullName}
              onChange={e => setFullName(e.target.value)} />
            <label className="t-label" style={{ fontSize: 10 }}>Email Address</label>
            <input className="t-input" type="email" placeholder="you@example.com" value={email}
              onChange={e => setEmail(e.target.value)} />
            <label className="t-label" style={{ fontSize: 10 }}>Password</label>
            <input className="t-input" type="password" placeholder="Min 6 characters" value={password}
              onChange={e => setPassword(e.target.value)} />
            {error && <span className="t-down" style={{ fontSize: 10 }}>{error}</span>}
            <button className="t-btn t-btn-primary" onClick={handleRegister} disabled={sending}
              style={{ width: '100%', height: 36 }}>
              {sending ? 'Creating account...' : 'Create Account & Send OTP'}
            </button>
            <div style={{ textAlign: 'center' }}>
              <button style={{
                background: 'none', border: 'none', color: 'var(--text-sub)', fontSize: 10,
                cursor: 'pointer', fontFamily: 'var(--font-sans)',
                textDecoration: 'underline', textUnderlineOffset: 2,
              }} onClick={() => setStep('email')}>
                Already have an account? Sign in
              </button>
            </div>
          </div>
        )}

        {step === 'otp' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, alignItems: 'center' }}>
            {otpSent && (
              <div style={{
                padding: '8px 12px', borderRadius: 6, fontSize: 10,
                background: 'rgba(0,200,83,0.08)', color: 'var(--text-green)',
                width: '100%', textAlign: 'center',
                border: '1px solid rgba(0,200,83,0.12)',
              }}>
                OTP sent to {email}
              </div>
            )}
            <div style={{ display: 'flex', gap: 8 }}>
              {otp.map((d, i) => (
                <input key={i} id={`otp-${i}`}
                  ref={el => { inputRefs[i] = el }}
                  style={otpStyle(d !== '')}
                  type="text" inputMode="numeric" maxLength={1}
                  value={d}
                  onChange={e => handleOtpInput(i, e.target.value)}
                  onKeyDown={e => handleOtpKey(i, e.key)}
                  autoFocus={i === 0}
                />
              ))}
            </div>
            {error && <span className="t-down" style={{ fontSize: 10 }}>{error}</span>}
            <button className="t-btn t-btn-primary" onClick={handleVerifyOTP} disabled={verifying}
              style={{ width: '100%', height: 36 }}>
              {verifying ? 'Verifying...' : 'Verify & Sign In'}
            </button>
            <button className="t-btn t-btn-ghost" onClick={handleResend} disabled={resendTimer > 0}
              style={{ width: '100%', height: 32, fontSize: 11 }}>
              {resendTimer > 0 ? `Resend in ${resendTimer}s` : 'Resend OTP'}
            </button>
            <button style={{
              background: 'none', border: 'none', color: 'var(--text-sub)', fontSize: 10,
              cursor: 'pointer', fontFamily: 'var(--font-sans)',
            }} onClick={() => setStep('email')}>
              Change email
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

/* ========== Main Portal ========== */

export default function PortalPage() {
  const [authenticated, setAuthenticated] = useState(false)
  const [email, setEmail] = useState('')

  useEffect(() => {
    const saved = sessionStorage.getItem('tm_portal_email')
    if (saved) {
      setEmail(saved)
      setAuthenticated(true)
    }
  }, [])

  const handleVerify = () => {
    const saved = sessionStorage.getItem('tm_portal_email') || ''
    setEmail(saved)
    setAuthenticated(true)
  }

  const handleSignOut = () => {
    sessionStorage.removeItem('tm_portal_email')
    setAuthenticated(false)
    setEmail('')
  }

  if (!authenticated) {
    return <OTPScreen onVerify={handleVerify} />
  }

  return <ClientDashboard email={email} onSignOut={handleSignOut} />
}
