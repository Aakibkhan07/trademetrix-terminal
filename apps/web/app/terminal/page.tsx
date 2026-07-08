'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useMarketData } from '@/lib/use-market-data'
import { useToast } from '@/lib/use-toast'

interface Position {
  symbol: string; exchange: string; quantity: number
  average_buy_price: number; unrealised_pnl: number; m2m: number
  product: string; instrument_type: string
}

interface Order {
  id: string; symbol: string; side: string; order_type: string
  quantity: number; price: number; status: string
  filled_quantity: number; average_price: number
  message: string; created_at: string
}

interface Funds { total_margin: number; used_margin: number; available_margin: number; broker: string }

const STATUS_BADGE: Record<string, string> = {
  FILLED: 't-badge-green', REJECTED: 't-badge-red', CANCELLED: 't-badge-amber',
  PENDING: 't-badge-cyan', OPEN: 't-badge-cyan', PARTIALLY_FILLED: 't-badge-amber', EXPIRED: 't-badge-sub',
}

export default function TerminalPage() {
  const { ticks, subscribe, startFeed } = useMarketData()
  const { toast } = useToast()
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [funds, setFunds] = useState<Funds | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [cancelling, setCancelling] = useState<string | null>(null)

  const [symbol, setSymbol] = useState('')
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY')
  const [qty, setQty] = useState(1)
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET')
  const [limitPrice, setLimitPrice] = useState(0)
  const [product, setProduct] = useState<'INTRADAY' | 'NRML'>('INTRADAY')
  const [placing, setPlacing] = useState(false)
  const [orderError, setOrderError] = useState('')

  const loadData = async () => {
    try {
      const [p, f, o] = await Promise.all([
        api.engine.positions(),
        api.engine.funds(),
        api.engine.orders(),
      ])
      setPositions((p as any).positions || [])
      setFunds((f as any).funds || null)
      setOrders((o as any).orders || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData(); startFeed() }, [])
  useEffect(() => { if (symbol) subscribe([symbol]) }, [symbol])

  const liveTick = symbol ? ticks[symbol] : null

  const handleCancel = async (orderId: string) => {
    setCancelling(orderId)
    try { await api.engine.cancelOrder(orderId); toast('success', 'Order cancelled') }
    catch { toast('error', 'Cancel failed') }
    finally { setCancelling(null); loadData() }
  }

  const handlePlaceOrder = async () => {
    if (!symbol) { setOrderError('Symbol required'); return }
    setPlacing(true); setOrderError('')
    try {
      const res = await api.engine.trade({
        symbol, side, quantity: qty,
        price: orderType === 'LIMIT' ? limitPrice : 0,
        order_type: orderType, product,
      }) as { result?: { success: boolean; message: string } }
      if (res.result?.success) {
        toast('success', `${side} ${qty} ${symbol}`)
        setSymbol('')
        loadData()
      } else {
        setOrderError(res.result?.message || 'Order failed')
      }
    } catch (e) { setOrderError(String(e)) }
    finally { setPlacing(false) }
  }

  const tickPct = liveTick?.change_pct ?? null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 className="t-page-title" style={{ margin: 0 }}>Terminal</h1>
          <p style={{ color: 'var(--text-sub)', fontSize: 12, margin: '2px 0 0' }}>
            Real-time order placement & execution
            {funds && <span style={{ marginLeft: 8, color: 'var(--text-faint)' }}>• {funds.broker || 'No broker'}</span>}
          </p>
        </div>
      </div>

      {error && (
        <div style={{
          background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.15)',
          borderRadius: 'var(--radius-md)', padding: '8px 12px', color: 'var(--text-red)', fontSize: 12,
        }}>{error}</div>
      )}

      <div style={{ display: 'flex', gap: 12, flex: 1, minHeight: 0 }}>
        {/* Left: Order Ticket */}
        <div style={{
          width: 300, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          <div className="t-panel" style={{
            padding: 0, borderTop: `3px solid ${side === 'BUY' ? 'var(--green)' : 'var(--red)'}`,
          }}>
            <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)' }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>Quick Order</span>
            </div>
            <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {/* Side toggle */}
              <div style={{ display: 'flex', gap: 4 }}>
                <button onClick={() => setSide('BUY')} style={{
                  flex: 1, padding: '7px 0', borderRadius: 'var(--radius-sm)',
                  border: `1px solid ${side === 'BUY' ? 'var(--green)' : 'var(--border)'}`,
                  background: side === 'BUY' ? 'rgba(34,197,94,0.1)' : 'transparent',
                  color: side === 'BUY' ? 'var(--text-green)' : 'var(--text-sub)',
                  fontSize: 12, fontWeight: 700,
                  cursor: 'pointer', transition: 'all 120ms ease',
                }}>BUY</button>
                <button onClick={() => setSide('SELL')} style={{
                  flex: 1, padding: '7px 0', borderRadius: 'var(--radius-sm)',
                  border: `1px solid ${side === 'SELL' ? 'var(--red)' : 'var(--border)'}`,
                  background: side === 'SELL' ? 'rgba(239,68,68,0.1)' : 'transparent',
                  color: side === 'SELL' ? 'var(--text-red)' : 'var(--text-sub)',
                  fontSize: 12, fontWeight: 700,
                  cursor: 'pointer', transition: 'all 120ms ease',
                }}>SELL</button>
              </div>

              {/* Symbol + Qty */}
              <div style={{ display: 'flex', gap: 6 }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-faint)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Symbol</label>
                  <input className="t-input" placeholder="NIFTY, RELIANCE..." value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} />
                </div>
                <div style={{ width: 80 }}>
                  <label style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-faint)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Qty</label>
                  <input className="t-input" type="number" min={1} value={qty} onChange={e => setQty(Number(e.target.value))} />
                </div>
              </div>

              {/* Order Type + Product */}
              <div style={{ display: 'flex', gap: 6 }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-faint)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Type</label>
                  <select className="t-select" value={orderType} onChange={e => setOrderType(e.target.value as 'MARKET' | 'LIMIT')}>
                    <option value="MARKET">Market</option>
                    <option value="LIMIT">Limit</option>
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-faint)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Product</label>
                  <select className="t-select" value={product} onChange={e => setProduct(e.target.value as 'INTRADAY' | 'NRML')}>
                    <option value="INTRADAY">Intraday</option>
                    <option value="NRML">Delivery</option>
                  </select>
                </div>
              </div>

              {orderType === 'LIMIT' && (
                <div>
                  <label style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-faint)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Limit Price</label>
                  <input className="t-input" type="number" min={0} step={0.05} value={limitPrice} onChange={e => setLimitPrice(Number(e.target.value))} />
                </div>
              )}

              {/* Live Quote */}
              {liveTick && (
                <div style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '6px 8px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)',
                  fontSize: 11,
                }}>
                  <span style={{ fontWeight: 700, color: 'var(--text)' }}>{symbol}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--text)', fontSize: 14 }}>
                    {liveTick.last_price?.toFixed(1)}
                  </span>
                  {tickPct !== null && (
                    <span style={{ fontWeight: 700, color: tickPct >= 0 ? 'var(--text-green)' : 'var(--text-red)' }}>
                      {tickPct >= 0 ? '+' : ''}{tickPct.toFixed(2)}%
                    </span>
                  )}
                </div>
              )}

              {orderError && (
                <div style={{
                  background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.15)',
                  borderRadius: 'var(--radius-sm)', padding: '6px 8px', fontSize: 11, color: 'var(--text-red)',
                }}>{orderError}</div>
              )}

                  <button
                    onClick={handlePlaceOrder} disabled={placing || !symbol}
                    className={`t-order-submit ${side === 'BUY' ? 'buy' : 'sell'}`}
                    style={{ marginTop: 4 }}
              >
                {placing ? 'Placing...' : `${side} ${qty} ${symbol || '...'}`}
              </button>
            </div>
          </div>

          {/* Margin Info */}
          {funds && (
            <div className="t-panel" style={{ padding: 10 }}>
              <div style={{ fontSize: 9, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Margin</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 4 }}>
                <span style={{ color: 'var(--text-sub)' }}>Available</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--text-green)' }}>
                  ₹{(funds.available_margin || 0).toLocaleString()}
                </span>
              </div>
              <div className="t-progress">
                <div className="t-progress-fill" style={{
                  width: funds.total_margin ? `${((funds.used_margin || 0) / funds.total_margin) * 100}%` : '0%',
                  background: 'var(--cyan)',
                }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, marginTop: 3, color: 'var(--text-faint)' }}>
                <span>Used: ₹{(funds.used_margin || 0).toLocaleString()}</span>
                <span>Total: ₹{(funds.total_margin || 0).toLocaleString()}</span>
              </div>
            </div>
          )}
        </div>

        {/* Right: Positions + Orders */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0, overflow: 'hidden' }}>
          {/* Positions */}
          <div className="t-panel" style={{ padding: 0, flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{
              padding: '8px 12px', borderBottom: '1px solid var(--border)',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>
                Positions ({positions.length})
              </span>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="t-btn t-btn-xs" onClick={loadData}>Refresh</button>
              </div>
            </div>
            {positions.length > 0 ? (
              <div style={{ overflow: 'auto', flex: 1 }}>
                <table className="t-table">
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th className="num">Qty</th>
                      <th className="num">Avg</th>
                      <th className="num">P&L</th>
                      <th>Type</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((p, i) => {
                      const live = ticks[p.symbol]
                      const ltp = live?.last_price || p.average_buy_price || 0
                      const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : p.unrealised_pnl
                      return (
                        <tr key={i}>
                          <td style={{ fontWeight: 600, fontSize: 12 }}>{p.symbol?.split(':').pop()}</td>
                          <td className="t-num">{p.quantity}</td>
                          <td className="t-num">{(p.average_buy_price || 0).toFixed(1)}</td>
                          <td className={`t-num ${(pnl || 0) >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 700 }}>
                            {(pnl || 0) >= 0 ? '+' : ''}{(pnl || 0).toFixed(0)}
                          </td>
                          <td>
                            <span className={`t-badge ${p.instrument_type === 'OPT' ? 't-badge-violet' : 't-badge-cyan'}`} style={{ fontSize: 8 }}>
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
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <p style={{ color: 'var(--text-faint)', fontSize: 11 }}>No open positions</p>
              </div>
            )}
          </div>

          {/* Orders */}
          <div className="t-panel" style={{ padding: 0, flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{
              padding: '8px 12px', borderBottom: '1px solid var(--border)',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>
                Orders ({orders.length})
              </span>
              <span className="t-faint" style={{ fontSize: 10 }}>Last 50</span>
            </div>
            {orders.length > 0 ? (
              <div style={{ overflow: 'auto', flex: 1 }}>
                <table className="t-table">
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Side</th>
                      <th className="num">Qty</th>
                      <th className="num">Price</th>
                      <th>Status</th>
                      <th>Time</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {orders.slice(0, 50).map(o => (
                      <tr key={o.id}>
                        <td style={{ fontWeight: 600, fontSize: 12 }}>{o.symbol?.split(':').pop()}</td>
                        <td style={{ color: o.side === 'BUY' ? 'var(--text-green)' : 'var(--text-red)', fontWeight: 600 }}>{o.side}</td>
                        <td className="t-num">{o.filled_quantity || o.quantity}</td>
                        <td className="t-num">{(o.average_price || o.price || 0).toFixed(1)}</td>
                        <td><span className={`t-badge ${STATUS_BADGE[o.status] || 't-badge-sub'}`} style={{ fontSize: 8 }}>{o.status}</span></td>
                        <td className="t-faint" style={{ fontSize: 9 }}>
                          {o.created_at ? new Date(o.created_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'}
                        </td>
                        <td>
                          {['OPEN', 'PENDING', 'PARTIALLY_FILLED'].includes(o.status) && (
                            <button className="t-btn t-btn-xs t-btn-danger" onClick={() => handleCancel(o.id)} disabled={cancelling === o.id}>
                              {cancelling === o.id ? '...' : 'X'}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <p style={{ color: 'var(--text-faint)', fontSize: 11 }}>No orders yet</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
