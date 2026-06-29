'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { DEMO_ORDERS, DEMO_POSITIONS, DEMO_FUNDS } from '@/lib/demo-data'

const INDICES = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX']
const EXPIRIES = ['24JUN', '27JUN', '04JUL', '11JUL', '25JUL']
const STRIKES = [26400, 26500, 26600, 26700, 26800]

interface OrderData {
  symbol: string
  side: string
  quantity: number
  price: number
  exchange: string
  order_type: string
  product: string
  trigger_price: number | null
  instrument_type: string
  strike_price: number | null
  expiry_date: string | null
  option_type: string | null
}

export default function TradePage() {
  const [orders, setOrders] = useState<unknown[]>([])
  const [positions, setPositions] = useState<unknown[]>([])
  const [funds, setFunds] = useState<Record<string, number> | null>(null)
  const [loading, setLoading] = useState(true)
  const [placing, setPlacing] = useState(false)
  const [resultMsg, setResultMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const [form, setForm] = useState<OrderData>({
    symbol: 'NIFTY',
    side: 'BUY',
    quantity: 75,
    price: 0,
    exchange: 'NFO',
    order_type: 'MARKET',
    product: 'INTRADAY',
    trigger_price: null,
    instrument_type: 'OPT',
    strike_price: 26600,
    expiry_date: '27JUN',
    option_type: 'CE',
  })

  const loadData = async () => {
    try {
      const [o, p, f] = await Promise.all([
        api.engine.orders().catch(() => ({ orders: DEMO_ORDERS })),
        api.engine.positions().catch(() => ({ positions: DEMO_POSITIONS })),
        api.engine.funds().catch(() => ({ funds: DEMO_FUNDS })),
      ])
      const od = o as { orders: unknown[] }
      const pd = p as { positions: unknown[] }
      const fd = f as { funds: Record<string, number> }
      setOrders(od.orders || DEMO_ORDERS)
      setPositions(pd.positions || DEMO_POSITIONS)
      setFunds(fd.funds || DEMO_FUNDS)
    } catch {
      setOrders(DEMO_ORDERS)
      setPositions(DEMO_POSITIONS)
      setFunds(DEMO_FUNDS)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  const handlePlace = async () => {
    setPlacing(true)
    setResultMsg(null)
    try {
      const res = await api.engine.trade({
        symbol: form.instrument_type === 'OPT' && form.expiry_date && form.strike_price && form.option_type
          ? `${form.symbol}${form.expiry_date}${form.strike_price}${form.option_type}`
          : form.instrument_type === 'FUT' && form.expiry_date
            ? `${form.symbol}${form.expiry_date}`
            : form.symbol,
        side: form.side,
        quantity: form.quantity,
        price: form.price || undefined,
        exchange: form.exchange,
        order_type: form.order_type,
        product: form.product,
        trigger_price: form.trigger_price || undefined,
        instrument_type: form.instrument_type,
        strike_price: form.strike_price || undefined,
        expiry_date: form.expiry_date || undefined,
        option_type: form.option_type || undefined,
      }) as { result: { success: boolean; message: string } }
      setResultMsg({ ok: res.result.success, text: res.result.message || 'Order placed' })
      if (res.result.success) setTimeout(loadData, 1000)
    } catch (e) {
      setResultMsg({ ok: false, text: String(e) })
    } finally {
      setPlacing(false)
    }
  }

  const handleCancel = async (orderId: string) => {
    try {
      await api.engine.cancelOrder(orderId)
      loadData()
    } catch { /* ignore */ }
  }

  const optionSymbol = form.instrument_type === 'OPT' && form.expiry_date && form.strike_price && form.option_type
    ? `${form.symbol}${form.expiry_date}${form.strike_price}${form.option_type}`
    : form.instrument_type === 'FUT' && form.expiry_date
      ? `${form.symbol}${form.expiry_date}`
      : form.symbol

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontFamily: 'Outfit', fontSize: 24, margin: 0 }}>Trade</h1>
        <p style={{ color: '#8888a0', fontSize: 14, margin: '4px 0 0' }}>
          Place orders and monitor positions
        </p>
      </div>

      {resultMsg && (
        <div style={{
          background: resultMsg.ok ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
          border: `1px solid ${resultMsg.ok ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`,
          borderRadius: 8, padding: '10px 14px', marginBottom: 16,
        }}>
          <p style={{ color: resultMsg.ok ? '#22c55e' : '#ef4444', fontSize: 13, margin: 0 }}>
            {resultMsg.ok ? '✓ ' : '✗ '}{resultMsg.text}
          </p>
        </div>
      )}

      <div className="grid-2" style={{ gap: 20, marginBottom: 24 }}>
        <div className="panel" style={{ padding: 0 }}>
          <div className="panel-header" style={{ padding: '16px 18px', borderBottom: '1px solid rgba(139,92,246,0.06)' }}>
            <h3 className="panel-title" style={{ fontSize: 15, margin: 0 }}>Place Order</h3>
          </div>
          <div style={{ padding: '18px' }}>
            <div className="tab-bar" style={{ marginBottom: 16 }}>
              {['EQ', 'FUT', 'OPT'].map((t) => (
                <button
                  key={t}
                  className={`tab ${form.instrument_type === t ? 'active' : ''}`}
                  onClick={() => setForm({ ...form, instrument_type: t, exchange: t === 'EQ' ? 'NSE' : 'NFO' })}
                >
                  {t === 'OPT' ? 'Options' : t === 'FUT' ? 'Futures' : 'Equity'}
                </button>
              ))}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ color: '#8888a0', fontSize: 11, display: 'block', marginBottom: 4 }}>Symbol</label>
                <select className="select" value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })}>
                  {INDICES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label style={{ color: '#8888a0', fontSize: 11, display: 'block', marginBottom: 4 }}>Side</label>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button
                    className={`btn btn-sm ${form.side === 'BUY' ? 'btn-success' : 'btn-secondary'}`}
                    style={{ flex: 1 }}
                    onClick={() => setForm({ ...form, side: 'BUY' })}
                  >BUY</button>
                  <button
                    className={`btn btn-sm ${form.side === 'SELL' ? 'btn-danger' : 'btn-secondary'}`}
                    style={{ flex: 1 }}
                    onClick={() => setForm({ ...form, side: 'SELL' })}
                  >SELL</button>
                </div>
              </div>
              <div>
                <label style={{ color: '#8888a0', fontSize: 11, display: 'block', marginBottom: 4 }}>Order Type</label>
                <select className="select" value={form.order_type} onChange={(e) => setForm({ ...form, order_type: e.target.value })}>
                  <option value="MARKET">Market</option>
                  <option value="LIMIT">Limit</option>
                  <option value="SL">Stop Loss</option>
                  <option value="SLM">Stop Loss Market</option>
                </select>
              </div>
              <div>
                <label style={{ color: '#8888a0', fontSize: 11, display: 'block', marginBottom: 4 }}>Product</label>
                <select className="select" value={form.product} onChange={(e) => setForm({ ...form, product: e.target.value })}>
                  <option value="INTRADAY">Intraday (MIS)</option>
                  <option value="NRML">Delivery (NRML)</option>
                </select>
              </div>
            </div>

            {form.instrument_type === 'OPT' && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginTop: 12 }}>
                <div>
                  <label style={{ color: '#8888a0', fontSize: 11, display: 'block', marginBottom: 4 }}>Expiry</label>
                  <select className="select" value={form.expiry_date || ''} onChange={(e) => setForm({ ...form, expiry_date: e.target.value })}>
                    {EXPIRIES.map((e) => <option key={e} value={e}>{e}</option>)}
                  </select>
                </div>
                <div>
                  <label style={{ color: '#8888a0', fontSize: 11, display: 'block', marginBottom: 4 }}>Strike</label>
                  <select className="select" value={form.strike_price || 0} onChange={(e) => setForm({ ...form, strike_price: Number(e.target.value) })}>
                    {STRIKES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label style={{ color: '#8888a0', fontSize: 11, display: 'block', marginBottom: 4 }}>Type</label>
                  <div className="tab-bar">
                    <button
                      className={`tab ${form.option_type === 'CE' ? 'active' : ''}`}
                      onClick={() => setForm({ ...form, option_type: 'CE' })}
                      style={{ fontSize: 11, padding: '4px 12px' }}
                    >CE</button>
                    <button
                      className={`tab ${form.option_type === 'PE' ? 'active' : ''}`}
                      onClick={() => setForm({ ...form, option_type: 'PE' })}
                      style={{ fontSize: 11, padding: '4px 12px' }}
                    >PE</button>
                  </div>
                </div>
              </div>
            )}

            {form.instrument_type === 'FUT' && (
              <div style={{ marginTop: 12 }}>
                <label style={{ color: '#8888a0', fontSize: 11, display: 'block', marginBottom: 4 }}>Expiry</label>
                <select className="select" value={form.expiry_date || ''} onChange={(e) => setForm({ ...form, expiry_date: e.target.value })}>
                  {EXPIRIES.map((e) => <option key={e} value={e}>{e}</option>)}
                </select>
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
              <div>
                <label style={{ color: '#8888a0', fontSize: 11, display: 'block', marginBottom: 4 }}>Quantity</label>
                <input className="input" type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })} />
              </div>
              <div>
                <label style={{ color: '#8888a0', fontSize: 11, display: 'block', marginBottom: 4 }}>
                  {form.order_type === 'MARKET' ? 'Price (0 for market)' : 'Price'}
                </label>
                <input className="input" type="number" value={form.price} onChange={(e) => setForm({ ...form, price: Number(e.target.value) })} />
              </div>
            </div>

            {form.order_type === 'SL' && (
              <div style={{ marginTop: 12 }}>
                <label style={{ color: '#8888a0', fontSize: 11, display: 'block', marginBottom: 4 }}>Trigger Price</label>
                <input className="input" type="number" value={form.trigger_price || ''} onChange={(e) => setForm({ ...form, trigger_price: Number(e.target.value) })} />
              </div>
            )}

            <div style={{ background: 'rgba(139,92,246,0.04)', borderRadius: 8, padding: 10, marginTop: 14, fontSize: 12 }}>
              <span style={{ color: '#555570' }}>Order preview: </span>
              <span style={{ color: '#f0f0f5' }}>{form.side} {form.quantity}x </span>
              <span style={{ color: '#22d3ee' }}>{optionSymbol}</span>
              <span style={{ color: '#555570' }}> @ {form.exchange} {form.order_type}</span>
            </div>

            <button
              className="btn btn-primary"
              style={{ width: '100%', marginTop: 14 }}
              onClick={handlePlace}
              disabled={placing || !form.quantity || form.quantity <= 0}
            >
              {placing ? 'Placing...' : `Place ${form.side} Order`}
            </button>
          </div>
        </div>

        <div>
          <div className="glass-card" style={{ padding: '16px', marginBottom: 16 }}>
            <p style={{ color: '#555570', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 10px', fontWeight: 600 }}>Funds</p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
              <div>
                <p style={{ margin: 0, fontSize: 18, fontWeight: 700, color: '#f0f0f5' }}>
                  {(funds?.available_margin || 0).toLocaleString()}
                </p>
                <p style={{ margin: 0, fontSize: 10, color: '#555570' }}>Available</p>
              </div>
              <div>
                <p style={{ margin: 0, fontSize: 18, fontWeight: 700, color: '#22d3ee' }}>
                  {(funds?.used_margin || 0).toLocaleString()}
                </p>
                <p style={{ margin: 0, fontSize: 10, color: '#555570' }}>Used</p>
              </div>
              <div>
                <p style={{ margin: 0, fontSize: 18, fontWeight: 700, color: '#f0f0f5' }}>
                  {(funds?.total_margin || 0).toLocaleString()}
                </p>
                <p style={{ margin: 0, fontSize: 10, color: '#555570' }}>Total</p>
              </div>
            </div>
          </div>

          <div className="panel" style={{ padding: 0 }}>
            <div className="panel-header" style={{ padding: '12px 16px', borderBottom: '1px solid rgba(139,92,246,0.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 className="panel-title" style={{ fontSize: 14, margin: 0 }}>Open Positions</h3>
              <button className="btn btn-sm btn-ghost" onClick={loadData} style={{ fontSize: 10 }}>Refresh</button>
            </div>
            <div style={{ overflowX: 'auto' }}>
              {!loading && positions.length > 0 ? (
                <table className="data-table" style={{ fontSize: 11 }}>
                  <thead>
                    <tr>
                      <th style={{ padding: '8px 10px' }}>Symbol</th>
                      <th style={{ padding: '8px 10px' }}>Type</th>
                      <th style={{ padding: '8px 10px' }}>Qty</th>
                      <th style={{ padding: '8px 10px' }}>Avg</th>
                      <th style={{ padding: '8px 10px' }}>P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(positions as Array<{
                      symbol: string; quantity: number; average_buy_price: number;
                      unrealised_pnl: number; instrument_type: string; exchange: string;
                    }>).map((p, i) => {
                      const isOption = p.instrument_type === 'OPT'
                      return (
                        <tr key={i}>
                          <td style={{ fontWeight: 600, padding: '8px 10px' }}>{p.symbol}</td>
                          <td style={{ padding: '8px 10px' }}>
                            <span className={`badge ${isOption ? 'badge-violet' : p.instrument_type === 'FUT' ? 'badge-cyan' : 'badge-green'}`} style={{ fontSize: 8 }}>
                              {p.instrument_type}
                            </span>
                          </td>
                          <td style={{ padding: '8px 10px' }} className="numeric">{p.quantity}</td>
                          <td style={{ padding: '8px 10px' }} className="numeric">{p.average_buy_price?.toFixed(1) || '-'}</td>
                          <td className="numeric" style={{ padding: '8px 10px', color: p.unrealised_pnl >= 0 ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
                            {p.unrealised_pnl >= 0 ? '+' : ''}{p.unrealised_pnl?.toFixed(0) || '0'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              ) : (
                <p style={{ color: '#555570', fontSize: 12, padding: 16, margin: 0, textAlign: 'center' }}>
                  {loading ? 'Loading...' : 'No open positions'}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="panel" style={{ padding: 0 }}>
        <div className="panel-header" style={{ padding: '12px 16px', borderBottom: '1px solid rgba(139,92,246,0.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 className="panel-title" style={{ fontSize: 14, margin: 0 }}>Orders ({orders.length})</h3>
        </div>
        <div style={{ overflowX: 'auto' }}>
          {!loading && orders.length > 0 ? (
            <table className="data-table" style={{ fontSize: 11 }}>
              <thead>
                <tr>
                  <th style={{ padding: '8px 10px' }}>Time</th>
                  <th style={{ padding: '8px 10px' }}>Symbol</th>
                  <th style={{ padding: '8px 10px' }}>Side</th>
                  <th style={{ padding: '8px 10px' }}>Qty</th>
                  <th style={{ padding: '8px 10px' }}>Price</th>
                  <th style={{ padding: '8px 10px' }}>Filled</th>
                  <th style={{ padding: '8px 10px' }}>Avg</th>
                  <th style={{ padding: '8px 10px' }}>Status</th>
                  <th style={{ padding: '8px 10px' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {(orders as Array<{
                  id: string; symbol: string; side: string; quantity: number;
                  price: number; status: string; filled_quantity: number;
                  average_price: number; created_at: string; instrument_type: string;
                }>).map((o, i) => {
                  const cancelable = o.status === 'OPEN' || o.status === 'PENDING' || o.status === 'TRIGGER_PENDING'
                  const isOption = o.instrument_type === 'OPT' || o.symbol.includes('CE') || o.symbol.includes('PE')
                  return (
                    <tr key={o.id || i}>
                      <td style={{ color: '#555570', padding: '8px 10px' }}>{o.created_at ? new Date(o.created_at).toLocaleTimeString() : '-'}</td>
                      <td style={{ fontWeight: 600, padding: '8px 10px' }}>
                        {o.symbol}
                        {isOption && <span className="badge badge-violet" style={{ marginLeft: 4, fontSize: 8 }}>OPT</span>}
                      </td>
                      <td style={{ color: o.side === 'BUY' ? '#22c55e' : '#ef4444', fontWeight: 600, padding: '8px 10px' }}>{o.side}</td>
                      <td className="numeric" style={{ padding: '8px 10px' }}>{o.quantity}</td>
                      <td className="numeric" style={{ padding: '8px 10px' }}>{o.price?.toFixed(1) || '-'}</td>
                      <td className="numeric" style={{ padding: '8px 10px' }}>{o.filled_quantity || 0}</td>
                      <td className="numeric" style={{ padding: '8px 10px' }}>{o.average_price?.toFixed(1) || '-'}</td>
                      <td style={{ padding: '8px 10px' }}>
                        <span className={`badge ${o.status === 'FILLED' || o.status === 'COMPLETE' ? 'badge-green' : o.status === 'REJECTED' || o.status === 'CANCELLED' ? 'badge-red' : 'badge-violet'}`} style={{ fontSize: 8 }}>
                          {o.status}
                        </span>
                      </td>
                      <td style={{ padding: '8px 10px' }}>
                        {cancelable && (
                          <button className="btn btn-sm btn-danger" style={{ fontSize: 9, padding: '2px 8px' }} onClick={() => handleCancel(o.id)}>
                            Cancel
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          ) : (
            <p style={{ color: '#555570', fontSize: 12, padding: 16, margin: 0, textAlign: 'center' }}>
              {loading ? 'Loading...' : 'No orders yet'}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
