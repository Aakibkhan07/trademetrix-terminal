'use client'

import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import { useToast } from '@/lib/use-toast'

interface Pair {
  symbol: string; price: number
}

interface Position {
  symbol: string; asset_class: string; quantity: number
  entry_price: number; current_price: number
  unrealized_pnl: number; realized_pnl: number
}

interface Order {
  order_id: string; symbol: string; side: string; order_type: string
  quantity: number; fill_price: number; cost: number
  balance_after: number; timestamp: string
}

interface Account {
  balance: number; equity: number; initial_balance: number
  total_pnl: number; trade_count: number; open_positions: number
}

const FOREX_PAIRS_LIST = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD']

export default function ForexPage() {
  const { toast } = useToast()
  const [pairs, setPairs] = useState<Pair[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [account, setAccount] = useState<Account | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [selectedSymbol, setSelectedSymbol] = useState('EURUSD')
  const [side, setSide] = useState<'buy' | 'sell'>('buy')
  const [qty, setQty] = useState(1000)
  const [orderType, setOrderType] = useState<'market' | 'limit'>('market')
  const [limitPrice, setLimitPrice] = useState(0)
  const [placing, setPlacing] = useState(false)
  const [orderError, setOrderError] = useState('')
  const [dataSource, setDataSource] = useState('Connecting...')

  const loadAll = useCallback(async () => {
    try {
      const [p, a, pos, o] = await Promise.all([
        api.forex.pairs(),
        api.forex.account(),
        api.forex.positions(),
        api.forex.orders(),
      ])
      setPairs((p as any).pairs || [])
      setAccount((a as any).account || null)
      setPositions((pos as any).positions || [])
      setOrders((o as any).orders || [])
      setDataSource('Daily rates, polled every 60s')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadAll(); const id = setInterval(loadAll, 5000); return () => clearInterval(id) }, [])

  const livePair = pairs.find(p => p.symbol === selectedSymbol)
  const pairPrice = livePair?.price

  const handlePlaceOrder = async () => {
    if (!qty || qty <= 0) { setOrderError('Quantity required'); return }
    setPlacing(true); setOrderError('')
    try {
      const res = await api.forex.order({
        symbol: selectedSymbol,
        side,
        quantity: qty,
        order_type: orderType,
        price: orderType === 'limit' ? limitPrice : undefined,
      }) as any
      if (res.success) {
        toast('success', `${side.toUpperCase()} ${qty} ${selectedSymbol} @ ${res.fill_price}`)
        loadAll()
      } else {
        setOrderError(res.message || 'Order failed')
      }
    } catch (e) { setOrderError(String(e)) }
    finally { setPlacing(false) }
  }

  if (loading) return <div className="t-loading" style={{ padding: 24, color: 'var(--text-faint)', fontSize: 12 }}>Loading...</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%', padding: 12 }}>
      {/* PAPER TRADING badge — persistent safety signal */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <h1 style={{ fontFamily: "'DM Sans', 'Inter', sans-serif", fontWeight: 700, fontSize: 18, margin: 0, color: 'var(--text)' }}>Forex</h1>
          <span style={{
            background: 'linear-gradient(135deg, #8b5cf6, #22d3ee)',
            color: '#fff', fontSize: 9, fontWeight: 800, letterSpacing: '0.08em',
            padding: '2px 8px', borderRadius: 10, textTransform: 'uppercase',
          }}>Paper Trading</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 9, color: 'var(--text-faint)' }}>{dataSource}</span>
          <button className="t-btn t-btn-xs" onClick={loadAll}>Refresh</button>
        </div>
      </div>

      {error && <div className="t-alert t-alert-error" style={{ fontSize: 12 }}>{error}</div>}

      {/* Price Ticker Bar */}
      <div style={{
        display: 'flex', gap: 8, overflow: 'auto', padding: '6px 0',
      }}>
        {FOREX_PAIRS_LIST.map(sym => {
          const p = pairs.find(pp => pp.symbol === sym)
          return (
            <button key={sym} onClick={() => setSelectedSymbol(sym)} style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
              padding: '6px 12px', borderRadius: 'var(--radius-sm)',
              background: selectedSymbol === sym ? 'var(--bg-active)' : 'var(--bg-tertiary)',
              border: selectedSymbol === sym ? '1px solid rgba(139,92,246,0.3)' : '1px solid var(--border)',
              cursor: 'pointer', flexShrink: 0, minWidth: 90,
              fontFamily: "'DM Sans', 'Inter', sans-serif",
              transition: 'all 120ms ease',
            }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text)' }}>{sym}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, color: 'var(--text)' }}>
                {p?.price ? p.price.toFixed(5) : '—'}
              </span>
            </button>
          )
        })}
      </div>

      <div style={{ display: 'flex', gap: 12, flex: 1, minHeight: 0 }}>
        {/* Order Panel */}
        <div style={{ width: 300, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div className="t-panel" style={{
            padding: 0, borderTop: `3px solid ${side === 'buy' ? 'var(--green)' : 'var(--red)'}`,
          }}>
            <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>Paper Order</span>
              <span style={{ fontSize: 8, color: 'var(--text-faint)', background: 'rgba(139,92,246,0.1)', padding: '1px 6px', borderRadius: 8 }}>PAPER</span>
            </div>
            <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div>
                <label style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-faint)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Pair</label>
                <select className="t-select" value={selectedSymbol} onChange={e => setSelectedSymbol(e.target.value)}>
                  {FOREX_PAIRS_LIST.map(sym => <option key={sym} value={sym}>{sym}</option>)}
                </select>
              </div>

              <div style={{ display: 'flex', gap: 4 }}>
                <button onClick={() => setSide('buy')} style={{
                  flex: 1, padding: '7px 0', borderRadius: 'var(--radius-sm)',
                  border: `1px solid ${side === 'buy' ? 'var(--green)' : 'var(--border)'}`,
                  background: side === 'buy' ? 'rgba(34,197,94,0.1)' : 'transparent',
                  color: side === 'buy' ? 'var(--text-green)' : 'var(--text-sub)',
                  fontSize: 12, fontWeight: 700, fontFamily: "'DM Sans', sans-serif",
                  cursor: 'pointer',
                }}>BUY</button>
                <button onClick={() => setSide('sell')} style={{
                  flex: 1, padding: '7px 0', borderRadius: 'var(--radius-sm)',
                  border: `1px solid ${side === 'sell' ? 'var(--red)' : 'var(--border)'}`,
                  background: side === 'sell' ? 'rgba(239,68,68,0.1)' : 'transparent',
                  color: side === 'sell' ? 'var(--text-red)' : 'var(--text-sub)',
                  fontSize: 12, fontWeight: 700, fontFamily: "'DM Sans', sans-serif",
                  cursor: 'pointer',
                }}>SELL</button>
              </div>

              <div>
                <label style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-faint)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Quantity (units)</label>
                <input className="t-input" type="number" min={0} step={100} value={qty} onChange={e => setQty(Number(e.target.value))} />
              </div>

              <div>
                <label style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-faint)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Type</label>
                <select className="t-select" value={orderType} onChange={e => setOrderType(e.target.value as 'market' | 'limit')}>
                  <option value="market">Market</option>
                  <option value="limit">Limit</option>
                </select>
              </div>

              {orderType === 'limit' && (
                <div>
                  <label style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-faint)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Limit Price</label>
                  <input className="t-input" type="number" min={0} step={0.00001} value={limitPrice} onChange={e => setLimitPrice(Number(e.target.value))} />
                </div>
              )}

              {pairPrice && (
                <div style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '6px 8px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)', fontSize: 11,
                }}>
                  <span style={{ fontWeight: 700, color: 'var(--text)' }}>{selectedSymbol}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--text)', fontSize: 14 }}>
                    {pairPrice.toFixed(5)}
                  </span>
                </div>
              )}

              {orderError && (
                <div style={{
                  background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.15)',
                  borderRadius: 'var(--radius-sm)', padding: '6px 8px', fontSize: 11, color: 'var(--text-red)',
                }}>{orderError}</div>
              )}

              <button onClick={handlePlaceOrder} disabled={placing || !qty} style={{
                padding: '8px 0', borderRadius: 'var(--radius-sm)', border: 'none',
                background: side === 'buy' ? 'var(--green)' : 'var(--red)',
                color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer',
                fontFamily: "'DM Sans', sans-serif",
              }}>
                {placing ? 'Placing...' : `${side.toUpperCase()} ${qty} ${selectedSymbol}`}
              </button>
            </div>
          </div>

          {/* Virtual Account */}
          {account && (
            <div className="t-panel" style={{ padding: 10 }}>
              <div style={{ fontSize: 9, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Virtual Account
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 4 }}>
                <span style={{ color: 'var(--text-sub)' }}>Balance</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--text-green)' }}>
                  ${(account.balance || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 4 }}>
                <span style={{ color: 'var(--text-sub)' }}>Equity</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: account.equity >= account.initial_balance ? 'var(--text-green)' : 'var(--text-red)' }}>
                  ${(account.equity || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 4 }}>
                <span style={{ color: 'var(--text-sub)' }}>Total P&L</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: (account.total_pnl || 0) >= 0 ? 'var(--text-green)' : 'var(--text-red)' }}>
                  {(account.total_pnl || 0) >= 0 ? '+' : ''}${(account.total_pnl || 0).toFixed(2)}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
                <span style={{ color: 'var(--text-sub)' }}>Trades</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--text)' }}>{account.trade_count || 0}</span>
              </div>
            </div>
          )}
        </div>

        {/* Positions + Orders */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0, overflow: 'hidden' }}>
          {/* Positions */}
          <div className="t-panel" style={{ padding: 0, flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>Positions ({positions.length})</span>
            </div>
            {positions.length > 0 ? (
              <div style={{ overflow: 'auto', flex: 1 }}>
                <table className="t-table">
                  <thead>
                    <tr>
                      <th>Pair</th>
                      <th className="num">Qty</th>
                      <th className="num">Entry</th>
                      <th className="num">LTP</th>
                      <th className="num">P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((p, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 600, fontSize: 12 }}>{p.symbol}</td>
                        <td className="t-num">{p.quantity.toFixed(0)}</td>
                        <td className="t-num">{p.entry_price?.toFixed(5) || '—'}</td>
                        <td className="t-num">{p.current_price?.toFixed(5) || '—'}</td>
                        <td className={`t-num ${(p.unrealized_pnl || 0) >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 700 }}>
                          {(p.unrealized_pnl || 0) >= 0 ? '+' : ''}${(p.unrealized_pnl || 0).toFixed(2)}
                        </td>
                      </tr>
                    ))}
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
            <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>Order History ({orders.length})</span>
            </div>
            {orders.length > 0 ? (
              <div style={{ overflow: 'auto', flex: 1 }}>
                <table className="t-table">
                  <thead>
                    <tr>
                      <th>Pair</th>
                      <th>Side</th>
                      <th className="num">Qty</th>
                      <th className="num">Fill</th>
                      <th className="num">Cost</th>
                      <th>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.slice(0, 50).map((o, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 600, fontSize: 12 }}>{o.symbol}</td>
                        <td style={{ color: o.side === 'buy' ? 'var(--text-green)' : 'var(--text-red)', fontWeight: 600 }}>{o.side.toUpperCase()}</td>
                        <td className="t-num">{o.quantity.toFixed(0)}</td>
                        <td className="t-num">{o.fill_price?.toFixed(5) || '—'}</td>
                        <td className="t-num">${o.cost?.toFixed(2) || '—'}</td>
                        <td className="t-faint" style={{ fontSize: 9 }}>
                          {o.timestamp ? new Date(o.timestamp).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'}
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
