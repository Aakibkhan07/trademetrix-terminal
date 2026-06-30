'use client'

import { useApi } from '@/lib/use-api'

/* -------- Types -------- */

interface Position {
  symbol: string
  exchange: string
  quantity: number
  average_buy_price: number
  average_sell_price: number
  unrealised_pnl: number
  realised_pnl: number
  m2m: number
  product: string
  instrument_type: string
  multiplier: number
}

interface Order {
  id: string
  symbol: string
  side: string
  order_type: string
  quantity: number
  price: number
  status: string
  filled_quantity: number
  average_price: number
  total_value: number
  message: string
  is_paper: boolean
  created_at: string
}

interface Funds {
  total_margin: number
  used_margin: number
  available_margin: number
  payin: number
  payout: number
  broker: string
}

interface AssignedStrategy {
  strategy_key: string
  name: string
  description: string
  required_tier: string
}

interface WatchlistItem {
  symbol: string
  name: string
  type: string
}

/* -------- Helpers -------- */

const STATUS_COLOR: Record<string, string> = {
  FILLED: '#22c55e',
  REJECTED: '#ef4444',
  CANCELLED: '#f59e0b',
  PENDING: '#3b82f6',
  OPEN: '#3b82f6',
  PARTIALLY_FILLED: '#f59e0b',
  EXPIRED: '#8888a0',
}

function statusColor(s: string) { return STATUS_COLOR[s.toUpperCase()] || '#8888a0' }

function fmt(n: number) {
  return n.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

/* -------- Skeletons -------- */

function SkeletonLine({ w, h = 12 }: { w: string; h?: number }) {
  return <div style={{ width: w, height: h, background: 'rgba(139,92,246,0.08)', borderRadius: 4 }} />
}

function SkeletonCard({ h = 80 }: { h?: number }) {
  return (
    <div className="glass-card" style={{ padding: 14, height: h, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <SkeletonLine w="40%" />
      <SkeletonLine w="60%" />
    </div>
  )
}

function SkeletonRow() {
  return (
    <div style={{ padding: '8px 14px', display: 'flex', gap: 12, borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
      <SkeletonLine w="80px" />
      <SkeletonLine w="50px" />
      <SkeletonLine w="40px" />
      <SkeletonLine w="60px" />
      <SkeletonLine w="50px" />
    </div>
  )
}

/* -------- Page -------- */

export default function TerminalPage() {
  const refreshKey = 0

  const { data: posData, loading: posLoading, error: posError } =
    useApi<{ positions: Position[] }>(`/engine/positions?_=${refreshKey}`)
  const { data: ordData, loading: ordLoading, error: ordError } =
    useApi<{ orders: Order[] }>(`/engine/orders?_=${refreshKey}`)
  const { data: fundData, loading: fundLoading, error: fundError } =
    useApi<{ funds: Funds }>(`/engine/funds?_=${refreshKey}`)
  const { data: stratData, loading: stratLoading, error: stratError } =
    useApi<{ strategies: AssignedStrategy[] }>(`/strategies/assigned?_=${refreshKey}`)
  const { data: wlData } =
    useApi<{ indices: WatchlistItem[]; stocks: WatchlistItem[] }>(`/marketdata/watchlist?_=${refreshKey}`)

  const positions = posData?.positions || []
  const orders = ordData?.orders || []
  const funds = fundData?.funds || null
  const assignedStrats = stratData?.strategies || []
  const indices = wlData?.indices || []

  const hasLive: boolean = funds !== null && (funds.total_margin > 0 || funds.available_margin > 0)
  const posCount = positions.length
  const activeStrats = assignedStrats.length

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Terminal</h1>
          <p className="page-subtitle">Real-time trading dashboard</p>
        </div>
      </div>

      {/* Global errors */}
      {(posError || ordError || fundError || stratError) && (
        <div className="alert alert-error" style={{ marginBottom: 16 }}>
          {posError?.message || ordError?.message || fundError?.message || stratError?.message}
        </div>
      )}

      {/* KPI row */}
      <div className="grid-4" style={{ marginBottom: 20 }}>
        {fundLoading ? (
          <>
            <SkeletonCard h={70} />
            <SkeletonCard h={70} />
            <SkeletonCard h={70} />
            <SkeletonCard h={70} />
          </>
        ) : (
          <>
            <div className="stat-card">
              <p className="stat-label">Total Margin</p>
              <p className={`stat-value ${hasLive ? 'neon-cyan' : ''}`}>
                {funds ? `\u20B9${fmt(funds.total_margin)}` : '\u2014'}
              </p>
              {funds && <p className="stat-sub">{funds.broker || 'N/A'}</p>}
            </div>
            <div className="stat-card">
              <p className="stat-label">Available Margin</p>
              <p className={`stat-value ${hasLive ? 'neon-cyan' : ''}`}>
                {funds ? `\u20B9${fmt(funds.available_margin)}` : '\u2014'}
              </p>
            </div>
            <div className="stat-card">
              <p className="stat-label">Open Positions</p>
              <p className="stat-value">{posLoading ? '\u2014' : posCount}</p>
            </div>
            <div className="stat-card">
              <p className="stat-label">Active Strategies</p>
              <p className="stat-value">{stratLoading ? '\u2014' : activeStrats}</p>
              {!stratLoading && activeStrats > 0 && (
                <p className="stat-sub">{assignedStrats.map(s => s.name).join(', ')}</p>
              )}
            </div>
          </>
        )}
      </div>

      <div style={{ display: 'flex', gap: 20, marginBottom: 20 }}>
        {/* Open Positions */}
        <div className="panel" style={{ flex: 1, padding: 0, overflow: 'hidden' }}>
          <div className="panel-header" style={{ padding: '14px 16px 10px', margin: 0 }}>
            <h3 className="panel-title" style={{ fontSize: 14 }}>Open Positions</h3>
            <span style={{ fontSize: 11, color: '#555570' }}>{posCount} open</span>
          </div>
          {posLoading && (
            <div style={{ padding: '8px 16px 16px' }}>
              <SkeletonRow /><SkeletonRow /><SkeletonRow />
            </div>
          )}
          {posError && (
            <p style={{ padding: '12px 16px', margin: 0, fontSize: 12, color: '#ef4444' }}>
              {posError.message}
            </p>
          )}
          {!posLoading && !posError && positions.length === 0 && (
            <p style={{ padding: '16px', margin: 0, fontSize: 12, color: '#555570' }}>
              No open positions.
            </p>
          )}
          {!posLoading && positions.length > 0 && (
            <table className="data-table" style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Qty</th>
                  <th>Avg</th>
                  <th>P&amp;L</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600 }}>{p.symbol}</td>
                    <td>{p.quantity}</td>
                    <td>{(p.average_buy_price || p.average_sell_price) ? `\u20B9${fmt(p.average_buy_price || p.average_sell_price)}` : '\u2014'}</td>
                    <td className={`numeric ${(p.unrealised_pnl || p.m2m) >= 0 ? 'positive' : 'negative'}`}>
                      {(p.unrealised_pnl || p.m2m) !== 0 ? `${(p.unrealised_pnl || p.m2m) >= 0 ? '+' : ''}\u20B9${fmt(p.unrealised_pnl || p.m2m)}` : '\u20B90'}
                    </td>
                    <td style={{ color: '#555570', fontSize: 10 }}>{p.instrument_type} {p.product}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Your Strategies */}
        <div className="panel" style={{ flex: '0 0 280px', padding: 0, overflow: 'hidden' }}>
          <div className="panel-header" style={{ padding: '14px 16px 10px', margin: 0 }}>
            <h3 className="panel-title" style={{ fontSize: 14 }}>Your Strategies</h3>
            <span style={{ fontSize: 11, color: '#555570' }}>{activeStrats} active</span>
          </div>
          {stratLoading && (
            <div style={{ padding: '8px 16px 16px' }}>
              <SkeletonCard h={50} />
              <SkeletonCard h={50} />
            </div>
          )}
          {stratError && (
            <p style={{ padding: '12px 16px', margin: 0, fontSize: 12, color: '#ef4444' }}>
              {stratError.message}
            </p>
          )}
          {!stratLoading && !stratError && assignedStrats.length === 0 && (
            <p style={{ padding: '16px', margin: 0, fontSize: 12, color: '#555570' }}>
              No strategies assigned.
            </p>
          )}
          {!stratLoading && assignedStrats.length > 0 && (
            <div style={{ padding: '0 16px 16px' }}>
              {assignedStrats.map(s => (
                <div key={s.strategy_key} className="glass-card" style={{
                  padding: '10px 12px', marginTop: 8,
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: '#f0f0f5' }}>{s.name}</span>
                    <span style={{
                      fontSize: 9, padding: '1px 6px', borderRadius: 4,
                      background: 'rgba(139,92,246,0.15)', color: '#8b5cf6',
                      border: '1px solid rgba(139,92,246,0.2)',
                      textTransform: 'capitalize',
                    }}>{s.required_tier}</span>
                  </div>
                  <p style={{ margin: 0, fontSize: 10, color: '#555570', lineHeight: 1.4 }}>
                    {s.description}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 20 }}>
        {/* Recent Orders */}
        <div className="panel" style={{ flex: 1, padding: 0, overflow: 'hidden' }}>
          <div className="panel-header" style={{ padding: '14px 16px 10px', margin: 0 }}>
            <h3 className="panel-title" style={{ fontSize: 14 }}>Recent Orders</h3>
            <span style={{ fontSize: 11, color: '#555570' }}>{ordLoading ? '\u2014' : `${orders.length} total`}</span>
          </div>
          {ordLoading && (
            <div style={{ padding: '8px 16px 16px' }}>
              <SkeletonRow /><SkeletonRow /><SkeletonRow />
            </div>
          )}
          {ordError && (
            <p style={{ padding: '12px 16px', margin: 0, fontSize: 12, color: '#ef4444' }}>
              {ordError.message}
            </p>
          )}
          {!ordLoading && !ordError && orders.length === 0 && (
            <p style={{ padding: '16px', margin: 0, fontSize: 12, color: '#555570' }}>
              No orders yet.
            </p>
          )}
          {!ordLoading && orders.length > 0 && (
            <table className="data-table" style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Qty</th>
                  <th>Price</th>
                  <th>Status</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {orders.slice(0, 20).map(o => (
                  <tr key={o.id}>
                    <td style={{ fontWeight: 600 }}>{o.symbol}</td>
                    <td className={o.side === 'BUY' ? 'positive' : 'negative'} style={{ fontWeight: 500 }}>
                      {o.side}
                    </td>
                    <td>{o.filled_quantity || o.quantity}</td>
                    <td>{o.average_price ? `\u20B9${fmt(o.average_price)}` : o.price ? `\u20B9${fmt(o.price)}` : '\u2014'}</td>
                    <td>
                      <span style={{
                        display: 'inline-block', padding: '1px 6px', borderRadius: 3,
                        fontSize: 10, fontWeight: 600,
                        background: `${statusColor(o.status)}22`,
                        color: statusColor(o.status),
                        border: `1px solid ${statusColor(o.status)}44`,
                      }}>
                        {o.status}
                      </span>
                    </td>
                    <td style={{ color: '#555570', fontSize: 10 }}>
                      {o.created_at ? new Date(o.created_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '\u2014'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Indices / Watchlist */}
        <div className="panel" style={{ flex: '0 0 200px', padding: 0, overflow: 'hidden' }}>
          <div className="panel-header" style={{ padding: '14px 16px 10px', margin: 0 }}>
            <h3 className="panel-title" style={{ fontSize: 14 }}>Indices</h3>
            <span style={{ fontSize: 11, color: '#555570' }}>{indices.length}</span>
          </div>
          <div style={{ padding: '0 16px 16px' }}>
            {indices.length === 0 && (
              <p style={{ margin: '12px 0 0', fontSize: 12, color: '#555570' }}>
                Market data unavailable.
              </p>
            )}
            {indices.map(idx => (
              <div key={idx.symbol} className="glass-card" style={{
                padding: '8px 10px', marginTop: 8, display: 'flex',
                justifyContent: 'space-between', alignItems: 'center',
              }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: '#f0f0f5' }}>{idx.name}</span>
                <span style={{ fontSize: 9, color: '#555570' }}>
                  {idx.symbol.includes('VIX') ? '\u2014' : '\u2014'}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
