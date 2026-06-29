'use client'

import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import { useMarketData } from '@/lib/use-market-data'
import { usePolling } from '@/lib/use-polling'
import { useAuth } from '@/lib/auth-context'

const INDICES = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX']
const LOT_SIZES: Record<string, number> = { NIFTY: 65, SENSEX: 20, BANKNIFTY: 30, FINNIFTY: 60 }

interface OrderData {
  symbol: string; side: string; quantity: number; price: number
  exchange: string; order_type: string; product: string; trigger_price: number | null
  instrument_type: string; strike_price: number | null; expiry_date: string | null; option_type: string | null
}

export default function TradePage() {
  const { token } = useAuth()
  const { ticks, connected, subscribe, startFeed } = useMarketData()
  const [orders, setOrders] = useState<any[]>([])
  const [positions, setPositions] = useState<any[]>([])
  const [funds, setFunds] = useState<Record<string, number> | null>(null)
  const [placing, setPlacing] = useState(false)
  const [resultMsg, setResultMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [lastRefresh, setLastRefresh] = useState('')
  const [paper, setPaper] = useState(true)
  const [expiries, setExpiries] = useState<string[]>([])
  const [optionChain, setOptionChain] = useState<any[]>([])
  const [chainLoading, setChainLoading] = useState(false)
  const [chainErr, setChainErr] = useState('')

  const [form, setForm] = useState<OrderData>({
    symbol: 'NIFTY', side: 'BUY', quantity: LOT_SIZES.NIFTY, price: 0,
    exchange: 'NFO', order_type: 'MARKET', product: 'INTRADAY', trigger_price: null,
    instrument_type: 'OPT', strike_price: 0, expiry_date: '', option_type: 'CE',
  })

  const loadChain = useCallback(async (sym: string, expiry?: string) => {
    setChainLoading(true); setChainErr('')
    try {
      const data = await api.marketdata.optionChain(sym) as any
      const exps = Array.isArray(data.expiries) ? data.expiries : []
      const chain = Array.isArray(data.optionChain) ? data.optionChain : []
      setExpiries(exps)
      if (exps.length) {
        const currentExpiry = form.expiry_date
        if (!currentExpiry || (expiry && expiry !== currentExpiry)) {
          setForm((prev) => ({ ...prev, expiry_date: exps[0] }))
        }
      }
      setOptionChain(chain)
      if (chain.length) {
        const mid = chain[Math.floor(chain.length / 2)]
        if (mid) setForm((prev) => ({ ...prev, strike_price: mid.strike }))
      }
    } catch (e) { setChainErr(String(e)); setExpiries([]); setOptionChain([]) }
    finally { setChainLoading(false) }
  }, [])

  useEffect(() => { if (token) loadChain(form.symbol) }, [form.symbol, token])

  const loadData = useCallback(async () => {
    try {
      const [o, p, f] = await Promise.all([
        api.engine.orders().catch(() => ({ orders: [] })),
        api.engine.positions().catch(() => ({ positions: [] })),
        api.engine.funds().catch(() => ({ funds: null })),
      ])
      setOrders((o as any).orders || [])
      setPositions((p as any).positions || [])
      setFunds((f as any).funds || null)
      setLastRefresh(new Date().toLocaleTimeString())
    } catch {}
  }, [])

  useEffect(() => {
    const symbols = INDICES.map((s) => `NSE:${s === 'BANKNIFTY' ? 'NIFTYBANK' : s === 'FINNIFTY' ? 'FINNIFTY' : s === 'SENSEX' ? 'SENSEX' : 'NIFTY50'}-INDEX`)
    subscribe(symbols)
    startFeed()
  }, [subscribe, startFeed])

  const fyersSymbol = `NSE:${form.symbol === 'BANKNIFTY' ? 'NIFTYBANK' : form.symbol === 'FINNIFTY' ? 'FINNIFTY' : form.symbol === 'SENSEX' ? 'SENSEX' : 'NIFTY50'}-INDEX`
  const livePrice = ticks[fyersSymbol]

  usePolling(loadData, 3000, !!token)

  const optionSymbol = form.instrument_type === 'OPT' && form.expiry_date && form.strike_price && form.option_type
    ? `${form.symbol}${form.expiry_date}${form.strike_price}${form.option_type}`
    : form.instrument_type === 'FUT' && form.expiry_date
      ? `${form.symbol}${form.expiry_date}`
      : form.symbol

  const handlePlace = async () => {
    setPlacing(true); setResultMsg(null)
    try {
      const res = await api.engine.trade({
        symbol: optionSymbol, side: form.side, quantity: form.quantity,
        price: form.price || undefined, exchange: form.exchange,
        order_type: form.order_type, product: form.product,
        trigger_price: form.trigger_price || undefined,
        instrument_type: form.instrument_type,
        strike_price: form.strike_price || undefined,
        expiry_date: form.expiry_date || undefined,
        option_type: form.option_type || undefined,
      }, paper) as any
      setResultMsg({ ok: res.result.success, text: res.result.message || 'Order placed' })
      if (res.result.success) setTimeout(loadData, 1000)
    } catch (e) { setResultMsg({ ok: false, text: String(e) }) }
    finally { setPlacing(false) }
  }

  const handleCancel = async (orderId: string) => {
    try { await api.engine.cancelOrder(orderId); loadData() } catch {}
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Trade</h1>
          <p className="page-subtitle">
            <span className={`live-dot ${connected ? 'active' : 'inactive'}`} />
            {connected ? 'Live' : 'Connecting...'}
            {lastRefresh && <span className="last-updated" style={{ marginLeft: 12 }}>Updated {lastRefresh}</span>}
          </p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={loadData}>Refresh</button>
      </div>

      {livePrice && (
        <div className="glass-card" style={{ padding: '12px 16px', marginBottom: 16 }}>
          <div style={{ display: 'flex', gap: 24, alignItems: 'center', flexWrap: 'wrap' }}>
            <div>
              <span className="card-label">{form.symbol}</span>
              <span className="last-updated" style={{ marginLeft: 8 }}>{form.exchange}</span>
            </div>
            <div>
              <span className="card-value" style={{ fontSize: 22 }}>{livePrice.last_price?.toFixed(1)}</span>
              <span className={`card-change ${livePrice.change >= 0 ? 'up' : 'down'}`} style={{ marginLeft: 8, fontSize: 13 }}>
                {livePrice.change >= 0 ? '+' : ''}{livePrice.change?.toFixed(1)} ({(livePrice.change_pct ?? 0) >= 0 ? '+' : ''}{(livePrice.change_pct ?? 0).toFixed(2)}%)
              </span>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              Bid: <span style={{ color: '#22c55e' }}>{livePrice.bid || '-'}</span>
              {' \u00B7 '}
              Ask: <span style={{ color: '#ef4444' }}>{livePrice.ask || '-'}</span>
            </div>
            <div style={{ flex: 1, textAlign: 'right' }}>
              <span className={`live-badge ${connected ? 'on' : 'off'}`}>
                <span className={`live-dot ${connected ? 'active' : 'inactive'}`} />
                {connected ? 'Live Feed' : 'Disconnected'}
              </span>
            </div>
          </div>
        </div>
      )}

      {resultMsg && (
        <div className={`alert ${resultMsg.ok ? 'alert-success' : 'alert-error'}`} style={{ marginBottom: 16 }}>
          {resultMsg.ok ? '\u2713 ' : '\u2717 '}{resultMsg.text}
        </div>
      )}

      <div className="grid-2" style={{ gap: 20, marginBottom: 24 }}>
          <div className="panel" style={{ padding: 0 }}>
          <div className="panel-header" style={{ padding: '14px 16px', margin: 0 }}>
            <h3 className="panel-title" style={{ fontSize: 14 }}>Place Order</h3>
            <div className="tab-bar" style={{ gap: 3 }}>
              <button className={`tab ${paper ? 'active' : ''}`} onClick={() => setPaper(true)}
                style={{ fontSize: 10, padding: '3px 10px', color: paper ? '#22c55e' : undefined }}>
                Paper
              </button>
              <button className={`tab ${!paper ? 'active' : ''}`} onClick={() => setPaper(false)}
                style={{ fontSize: 10, padding: '3px 10px', color: !paper ? '#ef4444' : undefined }}>
                Live
              </button>
            </div>
          </div>
          <div style={{ padding: 16 }}>
            <div className="tab-bar" style={{ marginBottom: 14 }}>
              {(['EQ', 'FUT', 'OPT'] as const).map((t) => (
                <button key={t} className={`tab ${form.instrument_type === t ? 'active' : ''}`}
                  onClick={() => setForm({ ...form, instrument_type: t, exchange: t === 'EQ' ? 'NSE' : 'NFO' })}>
                  {t === 'OPT' ? 'Options' : t === 'FUT' ? 'Futures' : 'Equity'}
                </button>
              ))}
            </div>

            <div className="trade-form-row" style={{ marginBottom: 8 }}>
              <div>
                <label className="stat-label">Symbol</label>
                <select className="select" value={form.symbol}
                  onChange={(e) => setForm({ ...form, symbol: e.target.value, quantity: LOT_SIZES[e.target.value] || 50 })}>
                  {INDICES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label className="stat-label">Side</label>
                <div style={{ display: 'flex', gap: 3 }}>
                  <button className={`btn btn-sm ${form.side === 'BUY' ? 'btn-success' : 'btn-secondary'}`} style={{ flex: 1, fontSize: 11 }}
                    onClick={() => setForm({ ...form, side: 'BUY' })}>BUY</button>
                  <button className={`btn btn-sm ${form.side === 'SELL' ? 'btn-danger' : 'btn-secondary'}`} style={{ flex: 1, fontSize: 11 }}
                    onClick={() => setForm({ ...form, side: 'SELL' })}>SELL</button>
                </div>
              </div>
            </div>

            <div className="trade-form-row" style={{ marginBottom: 8 }}>
              <div>
                <label className="stat-label">Type</label>
                <select className="select" value={form.order_type}
                  onChange={(e) => setForm({ ...form, order_type: e.target.value })}>
                  <option value="MARKET">Market</option>
                  <option value="LIMIT">Limit</option>
                  <option value="SL">Stop Loss</option>
                  <option value="SLM">SL Market</option>
                </select>
              </div>
              <div>
                <label className="stat-label">Product</label>
                <select className="select" value={form.product}
                  onChange={(e) => setForm({ ...form, product: e.target.value })}>
                  <option value="INTRADAY">MIS</option>
                  <option value="NRML">NRML</option>
                </select>
              </div>
            </div>

            {form.instrument_type === 'OPT' && (
              <div className="trade-form-row" style={{ marginBottom: 8 }}>
                <div>
                  <label className="stat-label">Expiry</label>
                  <select className="select" value={form.expiry_date || ''}
                    onChange={(e) => setForm({ ...form, expiry_date: e.target.value })}>
                    {expiries.map((e) => <option key={e} value={e}>{e}</option>)}
                  </select>
                </div>
                <div>
                  <label className="stat-label">Strike</label>
                  <select className="select" value={form.strike_price || 0}
                    onChange={(e) => setForm({ ...form, strike_price: Number(e.target.value) })}>
                    {optionChain.length > 0
                      ? optionChain.map((r: any) => <option key={r.strike} value={r.strike}>{r.strike}</option>)
                      : <option value={0}>{chainLoading ? 'Loading...' : 'No data'}</option>}
                  </select>
                </div>
                <div>
                  <label className="stat-label">Type</label>
                  <div className="tab-bar">
                    <button className={`tab ${form.option_type === 'CE' ? 'active' : ''}`}
                      onClick={() => setForm({ ...form, option_type: 'CE' })}>CE</button>
                    <button className={`tab ${form.option_type === 'PE' ? 'active' : ''}`}
                      onClick={() => setForm({ ...form, option_type: 'PE' })}>PE</button>
                  </div>
                </div>
              </div>
            )}

            {form.instrument_type === 'FUT' && (
              <div style={{ marginBottom: 8 }}>
                <label className="stat-label">Expiry</label>
                <select className="select" value={form.expiry_date || ''}
                  onChange={(e) => setForm({ ...form, expiry_date: e.target.value })}>
                  {expiries.map((e) => <option key={e} value={e}>{e}</option>)}
                </select>
              </div>
            )}

            <div className="trade-form-row">
              <div>
                <label className="stat-label">Qty</label>
                <input className="input" type="number" value={form.quantity}
                  onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })} />
              </div>
              <div>
                <label className="stat-label">{form.order_type === 'MARKET' ? 'Price' : 'Price'}</label>
                <input className="input" type="number" value={form.price}
                  onChange={(e) => setForm({ ...form, price: Number(e.target.value) })} />
              </div>
            </div>

            {form.order_type === 'SL' && (
              <div style={{ marginTop: 8 }}>
                <label className="stat-label">Trigger</label>
                <input className="input" type="number" value={form.trigger_price || ''}
                  onChange={(e) => setForm({ ...form, trigger_price: Number(e.target.value) })} />
              </div>
            )}

            <div className="trade-summary">
              <span style={{ color: 'var(--text-muted)' }}>Order: </span>
              <span style={{ color: form.side === 'BUY' ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
                {form.side} {form.quantity}x
              </span>
              <span style={{ color: '#22d3ee', marginLeft: 4 }}>{optionSymbol}</span>
              <span className="last-updated" style={{ marginLeft: 4 }}>@{form.exchange} {form.order_type}</span>
              {livePrice && <span className="last-updated" style={{ marginLeft: 8 }}>LTP: {livePrice.last_price}</span>}
            </div>

            <button className="btn btn-primary" style={{ width: '100%', marginTop: 12 }}
              onClick={handlePlace} disabled={placing || !form.quantity || form.quantity <= 0}>
              {placing ? 'Placing...' : `${form.side} ${form.option_type || form.instrument_type}`}
            </button>
          </div>
        </div>

        <div>
          <div className="glass-card" style={{ padding: 14, marginBottom: 12 }}>
            <div className="page-header" style={{ marginBottom: 8 }}>
              <span className="stat-label">Funds</span>
              <span className="last-updated">{lastRefresh}</span>
            </div>
            <div className="grid-3" style={{ gap: 8 }}>
              <div className="stat-card" style={{ padding: 10 }}>
                <p className="stat-label">Available</p>
                <p className="stat-value" style={{ fontSize: 16 }}>{(funds?.available_margin || 0).toLocaleString()}</p>
              </div>
              <div className="stat-card" style={{ padding: 10 }}>
                <p className="stat-label">Used</p>
                <p className="stat-value" style={{ fontSize: 16, color: '#22d3ee' }}>{(funds?.used_margin || 0).toLocaleString()}</p>
              </div>
              <div className="stat-card" style={{ padding: 10 }}>
                <p className="stat-label">Total</p>
                <p className="stat-value" style={{ fontSize: 16 }}>{(funds?.total_margin || 0).toLocaleString()}</p>
              </div>
            </div>
          </div>

          <div className="panel" style={{ padding: 0 }}>
            <div className="panel-header" style={{ padding: '10px 14px', margin: 0 }}>
              <h3 className="panel-title" style={{ fontSize: 13 }}>Positions ({positions.length})</h3>
              <button className="btn btn-ghost btn-sm" onClick={loadData} style={{ fontSize: 9 }}>Refresh</button>
            </div>
            {positions.length > 0 ? (
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table" style={{ fontSize: 11 }}>
                  <thead>
                    <tr>
                      <th style={{ padding: '6px 8px' }}>Symbol</th>
                      <th className="numeric">Qty</th>
                      <th className="numeric">Avg</th>
                      <th className="numeric">LTP</th>
                      <th className="numeric">P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((p: any, i: number) => {
                      const live = ticks[p.symbol]
                      const ltp = live?.last_price || p.last_price || 0
                      const pnl = live ? (p.quantity * (ltp - p.average_buy_price)) : p.unrealised_pnl
                      return (
                        <tr key={i}>
                          <td style={{ fontWeight: 600, padding: '6px 8px' }}>{p.symbol?.split(':').pop()}</td>
                          <td className="numeric">{p.quantity}</td>
                          <td className="numeric">{p.average_buy_price?.toFixed(1) || '-'}</td>
                          <td className="numeric">{ltp?.toFixed(1) || '-'}</td>
                          <td className={`numeric ${pnl >= 0 ? 'positive' : 'negative'}`} style={{ fontWeight: 600 }}>
                            {pnl >= 0 ? '+' : ''}{pnl?.toFixed(0) || '0'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p style={{ color: 'var(--text-muted)', fontSize: 12, padding: 14, margin: 0, textAlign: 'center' }}>No positions</p>
            )}
          </div>
        </div>
      </div>

      {form.instrument_type === 'OPT' && (
        <>
        {chainErr && <div className="alert alert-error" style={{ marginBottom: 12, fontSize: 11 }}>{chainErr}</div>}
        {chainErr && <div style={{ marginBottom: 12, padding: 12, background: 'rgba(239,68,68,0.08)', borderRadius: 8, fontSize: 11, color: '#ef4444' }}>
          {chainErr}
        </div>}
        </>)}
      {form.instrument_type === 'OPT' && optionChain.length > 0 && (
        <div className="panel" style={{ padding: 0, marginBottom: 20 }}>
          <div className="panel-header" style={{ padding: '10px 14px', margin: 0 }}>
            <h3 className="panel-title" style={{ fontSize: 13 }}>
              {form.symbol} Option Chain
              <span className="last-updated" style={{ marginLeft: 8, fontSize: 10 }}>
                {form.expiry_date}
              </span>
            </h3>
            <button className="btn btn-ghost btn-sm" onClick={() => loadChain(form.symbol)} disabled={chainLoading} style={{ fontSize: 9 }}>
              {chainLoading ? 'Loading...' : 'Refresh'}
            </button>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ fontSize: 10, minWidth: 600 }}>
              <thead>
                <tr>
                  <th colSpan={5} style={{ textAlign: 'center', color: '#22c55e' }}>CALL</th>
                  <th className="numeric" style={{ color: '#8b5cf6' }}>Strike</th>
                  <th colSpan={5} style={{ textAlign: 'center', color: '#ef4444' }}>PUT</th>
                </tr>
                <tr>
                  <th className="numeric">LTP</th><th className="numeric">Chg%</th><th className="numeric">Bid</th>
                  <th className="numeric">Ask</th><th className="numeric">OI</th><th></th>
                  <th className="numeric">LTP</th><th className="numeric">Chg%</th><th className="numeric">Bid</th>
                  <th className="numeric">Ask</th><th className="numeric">OI</th>
                </tr>
              </thead>
              <tbody>
                {optionChain.map((row: any, i: number) => {
                  const c = row.call || {}
                  const p = row.put || {}
                  return (
                    <tr key={i} style={{ cursor: 'pointer', background: row.strike === form.strike_price ? 'rgba(139,92,246,0.08)' : undefined }}
                      onClick={() => setForm((prev) => ({ ...prev, strike_price: row.strike }))}>
                      <td className="numeric">{c.ltp || '-'}</td>
                      <td className={`numeric ${(c.change_pct || 0) >= 0 ? 'positive' : 'negative'}`}>
                        {(c.change_pct || 0) ? `${(c.change_pct || 0) >= 0 ? '+' : ''}${(c.change_pct || 0).toFixed(1)}%` : '-'}
                      </td>
                      <td className="numeric" style={{ color: '#22c55e' }}>{c.bid || '-'}</td>
                      <td className="numeric" style={{ color: '#ef4444' }}>{c.ask || '-'}</td>
                      <td className="numeric">{(c.oi || 0).toLocaleString()}</td>
                      <td className="numeric" style={{ fontWeight: 700, color: '#8b5cf6' }}>{row.strike}</td>
                      <td className="numeric">{p.ltp || '-'}</td>
                      <td className={`numeric ${(p.change_pct || 0) >= 0 ? 'positive' : 'negative'}`}>
                        {(p.change_pct || 0) ? `${(p.change_pct || 0) >= 0 ? '+' : ''}${(p.change_pct || 0).toFixed(1)}%` : '-'}
                      </td>
                      <td className="numeric" style={{ color: '#22c55e' }}>{p.bid || '-'}</td>
                      <td className="numeric" style={{ color: '#ef4444' }}>{p.ask || '-'}</td>
                      <td className="numeric">{(p.oi || 0).toLocaleString()}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="panel" style={{ padding: 0 }}>
        <div className="panel-header" style={{ padding: '10px 14px', margin: 0 }}>
          <h3 className="panel-title" style={{ fontSize: 13 }}>Orders ({orders.length})</h3>
        </div>
        {orders.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ fontSize: 11 }}>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th>Expiry</th>
                  <th className="numeric">Strike</th>
                  <th>Side</th>
                  <th className="numeric">Qty</th>
                  <th className="numeric">Price</th>
                  <th className="numeric">Filled</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o: any, i: number) => {
                  const cancelable = ['OPEN', 'PENDING', 'TRIGGER_PENDING'].includes(o.status)
                  return (
                    <tr key={o.id || i}>
                      <td style={{ color: 'var(--text-muted)' }}>{o.created_at ? new Date(o.created_at).toLocaleTimeString() : '-'}</td>
                      <td style={{ fontWeight: 600 }}>{o.symbol?.split(':').pop()}</td>
                      <td>
                        <span className={`badge ${o.instrument_type === 'OPT' ? 'badge-violet' : o.instrument_type === 'FUT' ? 'badge-cyan' : 'badge-green'}`} style={{ fontSize: 8 }}>
                          {o.instrument_type || 'EQ'}
                        </span>
                      </td>
                      <td style={{ fontSize: 11 }}>{o.expiry_date || '-'}</td>
                      <td className="numeric">{o.strike_price || '-'}</td>
                      <td style={{ color: o.side === 'BUY' ? '#22c55e' : '#ef4444', fontWeight: 600 }}>{o.side}</td>
                      <td className="numeric">{o.quantity}</td>
                      <td className="numeric">{o.price?.toFixed(1) || '-'}</td>
                      <td className="numeric">{o.filled_quantity || 0}</td>
                      <td>
                        <span className={`badge ${['FILLED', 'COMPLETE'].includes(o.status) ? 'badge-green' : ['REJECTED', 'CANCELLED'].includes(o.status) ? 'badge-red' : 'badge-violet'}`} style={{ fontSize: 8 }}>
                          {o.status}
                        </span>
                      </td>
                      <td>
                        {cancelable && <button className="btn btn-sm btn-danger" style={{ fontSize: 8, padding: '2px 6px' }} onClick={() => handleCancel(o.id)}>Cancel</button>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ color: 'var(--text-muted)', fontSize: 12, padding: 14, margin: 0, textAlign: 'center' }}>No orders yet</p>
        )}
      </div>
    </div>
  )
}
