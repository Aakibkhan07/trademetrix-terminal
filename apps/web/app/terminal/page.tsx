'use client'

import { useEffect, useState } from 'react'
import { useApi } from '@/lib/use-api'
import { useMarketData } from '@/lib/use-market-data'
import { api } from '@/lib/api'
import { useToast } from '@/lib/use-toast'

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

const STATUS_BADGE: Record<string, string> = {
  FILLED: 't-badge-green',
  REJECTED: 't-badge-red',
  CANCELLED: 't-badge-amber',
  PENDING: 't-badge-cyan',
  OPEN: 't-badge-cyan',
  PARTIALLY_FILLED: 't-badge-amber',
  EXPIRED: 't-badge-sub',
}

function statusBadge(s: string) { return STATUS_BADGE[s.toUpperCase()] || 't-badge-sub' }

function fmt(n: number) {
  return n.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

/* -------- Skeletons -------- */

function SkeletonLine({ w, h = 12 }: { w: string; h?: number }) {
  return <div style={{ width: w, height: h, background: 'rgba(139,92,246,0.08)', borderRadius: 4 }} />
}

function SkeletonCard({ h = 80 }: { h?: number }) {
  return (
    <div className="t-stat" style={{ padding: 14, height: h, display: 'flex', flexDirection: 'column', gap: 8 }}>
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
  const { ticks, feedMode, subscribe } = useMarketData()
  const { toast } = useToast()
  const [cancelling, setCancelling] = useState<string | null>(null)

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

  const allSymbols = [
    ...(wlData?.indices || []).map(i => i.symbol),
    ...(wlData?.stocks || []).map(s => s.symbol),
  ]
  useEffect(() => {
    if (allSymbols.length) subscribe(allSymbols)
  }, [allSymbols, subscribe])

  const handleCancel = async (orderId: string) => {
    setCancelling(orderId)
    try {
      await api.engine.cancelOrder(orderId)
      toast('success', 'Order cancelled')
    } catch {
      toast('error', 'Failed to cancel order')
    }
    setCancelling(null)
  }

  const hasLive: boolean = funds !== null && (funds.total_margin > 0 || funds.available_margin > 0)
  const posCount = positions.length
  const activeStrats = assignedStrats.length

  /* -------- Order Ticket State -------- */
  const [showOrderTicket, setShowOrderTicket] = useState(false)
  const [orderSymbol, setOrderSymbol] = useState('')
  const [orderSide, setOrderSide] = useState<'BUY' | 'SELL'>('BUY')
  const [orderQty, setOrderQty] = useState(1)
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET')
  const [orderPrice, setOrderPrice] = useState(0)
  const [orderProduct, setOrderProduct] = useState<'INTRADAY' | 'NRML'>('INTRADAY')
  const [isLiveMode, setIsLiveMode] = useState(false)
  const [placing, setPlacing] = useState(false)
  const [orderError, setOrderError] = useState('')
  const [confirmingLive, setConfirmingLive] = useState(false)

  const handleToggleLive = async () => {
    if (isLiveMode) {
      setIsLiveMode(false)
      return
    }
    try {
      const status = await api.risk.liveStatus() as { is_live: boolean }
      if (status.is_live) {
        setIsLiveMode(true)
      } else {
        setConfirmingLive(true)
      }
    } catch {
      setConfirmingLive(true)
    }
  }

  const confirmLive = async () => {
    try {
      await api.risk.enableLive()
      setIsLiveMode(true)
      setConfirmingLive(false)
    } catch (e) {
      setOrderError(String(e))
      setConfirmingLive(false)
    }
  }

  const handlePlaceOrder = async () => {
    if (!orderSymbol) { setOrderError('Enter a symbol'); return }
    setPlacing(true)
    setOrderError('')
    try {
      const res = await api.engine.trade({
        symbol: orderSymbol,
        side: orderSide,
        quantity: orderQty,
        price: orderType === 'LIMIT' ? orderPrice : 0,
        order_type: orderType,
        product: orderProduct,
      }) as { result?: { success: boolean; broker_order_id: string; message: string; status: string } }
      if (res.result?.success) {
        toast('success', `${orderSide} ${orderQty} ${orderSymbol} placed`)
        setOrderSymbol('')
      } else {
        setOrderError(res.result?.message || 'Order failed')
      }
    } catch (e) {
      setOrderError(String(e))
    } finally {
      setPlacing(false)
    }
  }

  return (
    <div>
      <div className="t-page-header">
        <div>
          <h1 className="t-page-title">Terminal</h1>
          <p className="t-sub">
            Real-time trading dashboard
            {feedMode === 'simulator' && (
              <span className="t-badge t-badge-amber" style={{ marginLeft: 8 }}>SIMULATED DATA</span>
            )}
          </p>
        </div>
        <button className={`t-btn t-btn-sm ${showOrderTicket ? 't-btn-danger' : 't-btn-primary'}`}
          onClick={() => setShowOrderTicket(!showOrderTicket)}>
          {showOrderTicket ? 'Close Order' : '+ New Order'}
        </button>
      </div>

      {(posError || ordError || fundError || stratError) && (
        <div className="t-panel" style={{ marginBottom: 16, padding: 12, borderLeft: '3px solid #ef4444' }}>
          <span className="t-down">{posError?.message || ordError?.message || fundError?.message || stratError?.message}</span>
        </div>
      )}

      {/* KPI row */}
      <div className="t-grid-4" style={{ marginBottom: 20 }}>
        {fundLoading ? (
          <>
            <SkeletonCard h={70} />
            <SkeletonCard h={70} />
            <SkeletonCard h={70} />
            <SkeletonCard h={70} />
          </>
        ) : (
          <>
            <div className="t-stat">
              <div className="t-stat-row">
                <span className={`t-dot ${hasLive ? 't-dot-cyan t-dot-pulse' : 't-dot-sub'}`} />
                <span className="t-stat-label">Total Margin</span>
              </div>
              <p className="t-stat-value">
                {funds ? `\u20B9${fmt(funds.total_margin)}` : '\u2014'}
              </p>
              {funds && <p className="t-stat-sub">{funds.broker || 'N/A'}</p>}
            </div>
            <div className="t-stat">
              <div className="t-stat-row">
                <span className="t-dot t-dot-green" />
                <span className="t-stat-label">Available Margin</span>
              </div>
              <p className="t-stat-value">
                {funds ? `\u20B9${fmt(funds.available_margin)}` : '\u2014'}
              </p>
            </div>
            <div className="t-stat">
              <div className="t-stat-row">
                <span className="t-dot t-dot-sub" />
                <span className="t-stat-label">Open Positions</span>
              </div>
              <p className="t-stat-value">{posLoading ? '\u2014' : posCount}</p>
            </div>
            <div className="t-stat">
              <div className="t-stat-row">
                <span className="t-dot t-dot-violet" />
                <span className="t-stat-label">Active Strategies</span>
              </div>
              <p className="t-stat-value">{stratLoading ? '\u2014' : activeStrats}</p>
              {!stratLoading && activeStrats > 0 && (
                <p className="t-stat-sub">{assignedStrats.map(s => s.name).join(', ')}</p>
              )}
            </div>
          </>
        )}
      </div>

      <div className="t-row" style={{ gap: 20, marginBottom: 20 }}>
        {/* Open Positions */}
        <div className="t-panel" style={{ flex: 1, minWidth: 0, padding: 0, overflow: 'hidden' }}>
          <div className="t-panel-header">
            <h3 className="t-panel-title">Open Positions</h3>
            <span className="t-faint">{posCount} open</span>
          </div>
          {posLoading && (
            <div className="t-panel-body">
              <SkeletonRow /><SkeletonRow /><SkeletonRow />
            </div>
          )}
          {posError && (
            <div className="t-panel-body">
              <p className="t-down">{posError.message}</p>
            </div>
          )}
          {!posLoading && !posError && positions.length === 0 && (
            <div className="t-panel-body">
              <p className="t-faint">No open positions.</p>
            </div>
          )}
          {!posLoading && positions.length > 0 && (
            <div className="t-table-wrap">
              <table className="t-table">
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
                      <td className="t-num">{p.quantity}</td>
                      <td className="t-num">{(p.average_buy_price || p.average_sell_price) ? `\u20B9${fmt(p.average_buy_price || p.average_sell_price)}` : '\u2014'}</td>
                      <td className={`t-num ${(p.unrealised_pnl || p.m2m) >= 0 ? 't-up' : 't-down'}`}>
                        {(p.unrealised_pnl || p.m2m) !== 0 ? `${(p.unrealised_pnl || p.m2m) >= 0 ? '+' : ''}\u20B9${fmt(p.unrealised_pnl || p.m2m)}` : '\u20B90'}
                      </td>
                      <td className="t-faint">{p.instrument_type} {p.product}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Your Strategies */}
        <div className="t-panel" style={{ flex: '0 0 280px', padding: 0, overflow: 'hidden' }}>
          <div className="t-panel-header">
            <h3 className="t-panel-title">Your Strategies</h3>
            <span className="t-faint">{activeStrats} active</span>
          </div>
          {stratLoading && (
            <div className="t-panel-body">
              <SkeletonCard h={50} />
              <SkeletonCard h={50} />
            </div>
          )}
          {stratError && (
            <div className="t-panel-body">
              <p className="t-down">{stratError.message}</p>
            </div>
          )}
          {!stratLoading && !stratError && assignedStrats.length === 0 && (
            <div className="t-panel-body">
              <p className="t-faint">No strategies assigned.</p>
            </div>
          )}
          {!stratLoading && assignedStrats.length > 0 && (
            <div className="t-panel-body" style={{ paddingTop: 0 }}>
              {assignedStrats.map(s => (
                <div key={s.strategy_key} style={{
                  padding: '10px 12px', marginTop: 8,
                  background: 'rgba(255,255,255,0.02)',
                  borderRadius: 6, border: '1px solid rgba(255,255,255,0.04)',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: 12, fontWeight: 600 }}>{s.name}</span>
                    <span className="t-badge t-badge-violet" style={{ textTransform: 'capitalize' }}>{s.required_tier}</span>
                  </div>
                  <p className="t-faint" style={{ margin: 0, fontSize: 10, lineHeight: 1.4 }}>
                    {s.description}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="t-row" style={{ gap: 20 }}>
        {/* Recent Orders */}
        <div className="t-panel" style={{ flex: 1, minWidth: 0, padding: 0, overflow: 'hidden' }}>
          <div className="t-panel-header">
            <h3 className="t-panel-title">Recent Orders</h3>
            <span className="t-faint">{ordLoading ? '\u2014' : `${orders.length} total`}</span>
          </div>
          {ordLoading && (
            <div className="t-panel-body">
              <SkeletonRow /><SkeletonRow /><SkeletonRow />
            </div>
          )}
          {ordError && (
            <div className="t-panel-body">
              <p className="t-down">{ordError.message}</p>
            </div>
          )}
          {!ordLoading && !ordError && orders.length === 0 && (
            <div className="t-panel-body">
              <p className="t-faint">No orders yet.</p>
            </div>
          )}
          {!ordLoading && orders.length > 0 && (
            <div className="t-table-wrap">
              <table className="t-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>Status</th>
                    <th>Time</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {orders.slice(0, 20).map(o => (
                    <tr key={o.id}>
                      <td style={{ fontWeight: 600 }}>{o.symbol}</td>
                      <td className={o.side === 'BUY' ? 't-up' : 't-down'} style={{ fontWeight: 500 }}>
                        {o.side}
                      </td>
                      <td className="t-num">{o.filled_quantity || o.quantity}</td>
                      <td className="t-num">{o.average_price ? `\u20B9${fmt(o.average_price)}` : o.price ? `\u20B9${fmt(o.price)}` : '\u2014'}</td>
                      <td>
                        <span className={`t-badge ${statusBadge(o.status)}`}>
                          {o.status}
                        </span>
                      </td>
                      <td className="t-faint">
                        {o.created_at ? new Date(o.created_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '\u2014'}
                      </td>
                      <td>
                        {['OPEN', 'PENDING', 'PARTIALLY_FILLED'].includes(o.status) && (
                          <button className="t-btn t-btn-sm t-btn-danger"
                            onClick={() => handleCancel(o.id)} disabled={cancelling === o.id}>
                            {cancelling === o.id ? '...' : 'Cancel'}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Indices / Watchlist */}
        <div className="t-panel" style={{ flex: '0 0 200px', padding: 0, overflow: 'hidden' }}>
          <div className="t-panel-header">
            <h3 className="t-panel-title">Indices</h3>
            <span className="t-faint">{indices.length}</span>
            {feedMode === 'simulator' && (
              <span className="t-badge t-badge-amber" style={{ marginLeft: 8 }}>SIMULATED DATA</span>
            )}
          </div>
          <div className="t-panel-body">
            {indices.length === 0 && (
              <p className="t-faint" style={{ margin: '12px 0 0' }}>
                Market data unavailable.
              </p>
            )}
            {indices.map(idx => {
              const t = ticks[idx.symbol]
              const pct = t?.change_pct
              return (
                <div key={idx.symbol} style={{
                  padding: '8px 10px', marginTop: 8, display: 'flex',
                  justifyContent: 'space-between', alignItems: 'center',
                  background: 'rgba(255,255,255,0.02)',
                  borderRadius: 6, border: '1px solid rgba(255,255,255,0.04)',
                }}>
                  <span style={{ fontSize: 11, fontWeight: 600 }}>{idx.name}</span>
                  <span className={`t-num ${t ? (pct != null && pct >= 0 ? 't-up' : 't-down') : 't-faint'}`}>
                    {t?.last_price != null ? t.last_price.toFixed(1) : '\u2014'}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Inline Order Ticket */}
      {showOrderTicket && (
        <div className="t-panel" style={{
          marginTop: 20,
          borderTop: `3px solid ${orderSide === 'BUY' ? '#22c55e' : '#ef4444'}`,
          maxWidth: 520,
        }}>
          <div className="t-panel-header">
            <span className="t-panel-title">Quick Order</span>
            <button className="t-btn t-btn-sm t-btn-ghost" onClick={() => setShowOrderTicket(false)}>
              Close
            </button>
          </div>
          <div className="t-panel-body">
            <div className="t-row" style={{ gap: 8, marginBottom: 10 }}>
              <div className="t-col">
                <label className="t-label">Symbol</label>
                <input className="t-input" placeholder="e.g. NIFTY, RELIANCE..." value={orderSymbol}
                  onChange={e => setOrderSymbol(e.target.value.toUpperCase())} />
              </div>
              <div className="t-col" style={{ flex: '0 0 100px' }}>
                <label className="t-label">Qty</label>
                <input className="t-input" type="number" min={1} value={orderQty}
                  onChange={e => setOrderQty(Number(e.target.value))} />
              </div>
            </div>

            <div className="t-row" style={{ gap: 8, marginBottom: 10 }}>
              <div className="t-col">
                <label className="t-label">Side</label>
                <div className="t-row" style={{ gap: 4 }}>
                  <button className={`t-btn t-btn-sm ${orderSide === 'BUY' ? 't-btn-primary' : 't-btn-ghost'}`}
                    onClick={() => setOrderSide('BUY')} style={{ flex: 1 }}>
                    BUY
                  </button>
                  <button className={`t-btn t-btn-sm ${orderSide === 'SELL' ? 't-btn-danger' : 't-btn-ghost'}`}
                    onClick={() => setOrderSide('SELL')} style={{ flex: 1 }}>
                    SELL
                  </button>
                </div>
              </div>
              <div className="t-col">
                <label className="t-label">Type</label>
                <select className="t-select" value={orderType}
                  onChange={e => setOrderType(e.target.value as 'MARKET' | 'LIMIT')}>
                  <option value="MARKET">Market</option>
                  <option value="LIMIT">Limit</option>
                </select>
              </div>
              <div className="t-col">
                <label className="t-label">Product</label>
                <select className="t-select" value={orderProduct}
                  onChange={e => setOrderProduct(e.target.value as 'INTRADAY' | 'NRML')}>
                  <option value="INTRADAY">Intraday</option>
                  <option value="NRML">Delivery</option>
                </select>
              </div>
            </div>

            {orderType === 'LIMIT' && (
              <div style={{ marginBottom: 10 }}>
                <label className="t-label">Limit Price</label>
                <input className="t-input" type="number" min={0} step={0.05} value={orderPrice}
                  onChange={e => setOrderPrice(Number(e.target.value))} />
              </div>
            )}

            <div className="t-row" style={{ alignItems: 'center', gap: 6, marginBottom: 10 }}>
              <span className="t-faint" style={{ fontSize: 10, fontWeight: 600 }}>MODE</span>
              <button className={`t-chip ${!isLiveMode ? 'active' : ''}`}
                onClick={() => isLiveMode && setIsLiveMode(false)}>
                PAPER
              </button>
              <button className={`t-chip ${isLiveMode ? 'active' : ''}`}
                onClick={handleToggleLive} style={{ color: isLiveMode ? '#ef4444' : undefined }}>
                LIVE
              </button>
            </div>

            {confirmingLive && (
              <div style={{
                background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
                borderRadius: 8, padding: '10px 12px', marginBottom: 10,
              }}>
                <p style={{ margin: '0 0 8px', fontSize: 11, color: '#ef4444', fontWeight: 500 }}>
                  Enable live mode to place real orders?
                </p>
                <div className="t-row" style={{ gap: 6 }}>
                  <button className="t-btn t-btn-sm t-btn-danger" onClick={confirmLive}>
                    Enable Live
                  </button>
                  <button className="t-btn t-btn-sm t-btn-ghost" onClick={() => setConfirmingLive(false)}>
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {orderError && (
              <div style={{
                background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
                borderRadius: 8, padding: '8px 12px', marginBottom: 10,
              }}>
                <span className="t-down" style={{ fontSize: 11 }}>{orderError}</span>
              </div>
            )}

            <button className={`t-btn ${isLiveMode ? 't-btn-danger' : 't-btn-primary'}`}
              onClick={handlePlaceOrder} disabled={placing || !orderSymbol}
              style={{ width: '100%' }}>
              {placing ? 'Placing...' : `${isLiveMode ? 'LIVE ' : ''}${orderSide} ${orderQty} ${orderSymbol || '...'}`}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
