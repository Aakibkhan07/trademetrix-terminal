'use client'

import { useState, useEffect } from 'react'

interface Broker {
  broker: string
  active: boolean
}

interface UserWithBroker {
  id: string
  email: string
  full_name: string
  subscription_tier: string
  brokers: Broker[]
  has_broker: boolean
}

interface TradeResult {
  success: boolean
  broker_order_id?: string
  message?: string
  status?: string
}

export function TradeRouterTab() {
  const [users, setUsers] = useState<UserWithBroker[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedUser, setSelectedUser] = useState('')
  const [symbol, setSymbol] = useState('NIFTY')
  const [exchange, setExchange] = useState('NSE')
  const [side, setSide] = useState('BUY')
  const [orderType, setOrderType] = useState('MARKET')
  const [product, setProduct] = useState('INTRADAY')
  const [quantity, setQuantity] = useState('65')
  const [price, setPrice] = useState('0')
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<TradeResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/v1/admin/users/with-brokers')
      .then(r => r.json())
      .then(d => { setUsers(d.users || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const placeTrade = async () => {
    setSending(true)
    setError(null)
    setResult(null)
    try {
      const res = await fetch('/api/v1/admin/execute-trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: selectedUser,
          symbol: symbol.toUpperCase(),
          exchange: exchange.toUpperCase(),
          side: side.toUpperCase(),
          order_type: orderType.toUpperCase(),
          product: product.toUpperCase(),
          quantity: parseInt(quantity) || 0,
          price: parseFloat(price) || 0,
        }),
      })
      const data = await res.json()
      if (!res.ok) setError(data.detail || `HTTP ${res.status}`)
      else setResult(data)
    } catch (e) {
      setError(String(e))
    }
    setSending(false)
  }

  const selectedUserData = users.find(u => u.id === selectedUser)

  return (
    <div>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 360px', minWidth: 300 }}>
          <div className="t-panel" style={{ padding: 14 }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 13, fontWeight: 600 }}>Select User</h3>
            {loading && <p style={{ fontSize: 11, color: 'var(--text-faint)' }}>Loading users...</p>}
            {!loading && (
              <select className="t-input" value={selectedUser} onChange={e => setSelectedUser(e.target.value)}
                style={{ width: '100%', fontSize: 11 }}>
                <option value="">— Choose a user —</option>
                {users.filter(u => u.has_broker).map(u => (
                  <option key={u.id} value={u.id}>
                    {u.full_name || u.email} ({u.brokers.map(b => b.broker).join(', ')})
                  </option>
                ))}
              </select>
            )}
            {selectedUserData && (
              <div style={{ marginTop: 10, fontSize: 10, color: 'var(--text-sub)' }}>
                <p style={{ margin: 0 }}>
                  Brokers: {selectedUserData.brokers.map(b =>
                    <span key={b.broker} style={{ color: b.active ? 'var(--green)' : 'var(--text-faint)', marginRight: 6 }}>
                      {b.broker}{b.active ? ' (active)' : ''}
                    </span>
                  )}
                </p>
                <p style={{ margin: '4px 0 0' }}>Tier: {selectedUserData.subscription_tier}</p>
              </div>
            )}
          </div>

          <div className="t-panel" style={{ padding: 14, marginTop: 12 }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 13, fontWeight: 600 }}>Trade Form</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <div>
                <label style={{ fontSize: 9, color: 'var(--text-sub)', display: 'block', marginBottom: 2 }}>Symbol</label>
                <input className="t-input" value={symbol} onChange={e => setSymbol(e.target.value)} style={{ fontSize: 11, width: '100%' }} />
              </div>
              <div>
                <label style={{ fontSize: 9, color: 'var(--text-sub)', display: 'block', marginBottom: 2 }}>Exchange</label>
                <select className="t-input" value={exchange} onChange={e => setExchange(e.target.value)} style={{ fontSize: 11, width: '100%' }}>
                  <option value="NSE">NSE</option>
                  <option value="NFO">NFO</option>
                  <option value="BSE">BSE</option>
                  <option value="CDS">CDS</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: 9, color: 'var(--text-sub)', display: 'block', marginBottom: 2 }}>Side</label>
                <select className="t-input" value={side} onChange={e => setSide(e.target.value)} style={{ fontSize: 11, width: '100%' }}>
                  <option value="BUY">BUY</option>
                  <option value="SELL">SELL</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: 9, color: 'var(--text-sub)', display: 'block', marginBottom: 2 }}>Order Type</label>
                <select className="t-input" value={orderType} onChange={e => setOrderType(e.target.value)} style={{ fontSize: 11, width: '100%' }}>
                  <option value="MARKET">MARKET</option>
                  <option value="LIMIT">LIMIT</option>
                  <option value="SL">SL</option>
                  <option value="SL-M">SL-M</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: 9, color: 'var(--text-sub)', display: 'block', marginBottom: 2 }}>Product</label>
                <select className="t-input" value={product} onChange={e => setProduct(e.target.value)} style={{ fontSize: 11, width: '100%' }}>
                  <option value="INTRADAY">INTRADAY</option>
                  <option value="DELIVERY">DELIVERY</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: 9, color: 'var(--text-sub)', display: 'block', marginBottom: 2 }}>Quantity</label>
                <input className="t-input" type="number" value={quantity} onChange={e => setQuantity(e.target.value)} style={{ fontSize: 11, width: '100%' }} />
              </div>
              <div>
                <label style={{ fontSize: 9, color: 'var(--text-sub)', display: 'block', marginBottom: 2 }}>Price (0=market)</label>
                <input className="t-input" type="number" step="0.05" value={price} onChange={e => setPrice(e.target.value)} style={{ fontSize: 11, width: '100%' }} />
              </div>
            </div>
            <button onClick={placeTrade} disabled={sending || !selectedUser}
              style={{
                marginTop: 12, width: '100%', padding: '8px 16px', fontSize: 11, fontWeight: 600,
                background: selectedUser && !sending ? 'var(--violet)' : 'var(--bg)',
                color: selectedUser && !sending ? '#fff' : 'var(--text-faint)',
                border: selectedUser && !sending ? 'none' : '1px solid var(--border)',
                borderRadius: 5, cursor: sending || !selectedUser ? 'not-allowed' : 'pointer',
              }}>
              {sending ? 'Placing Trade...' : selectedUser ? `Place Trade for ${selectedUserData?.full_name || selectedUserData?.email || ''}` : 'Select a user first'}
            </button>
          </div>
        </div>

        <div style={{ flex: '1 1 360px', minWidth: 300 }}>
          <div className="t-panel" style={{ padding: 14 }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 13, fontWeight: 600 }}>Result</h3>
            {error && (
              <div style={{
                padding: 12, fontSize: 11, fontFamily: 'monospace', borderRadius: 5,
                background: 'color-mix(in srgb, var(--red) 10%, var(--bg))',
                border: '1px solid color-mix(in srgb, var(--red) 20%, transparent)',
                color: 'var(--red)', whiteSpace: 'pre-wrap',
              }}>
                {error}
              </div>
            )}
            {result && !error && (
              <div>
                <div style={{
                  padding: '8px 12px', borderRadius: 5, marginBottom: 10,
                  background: result.success ? 'color-mix(in srgb, var(--green) 10%, var(--bg))' : 'color-mix(in srgb, var(--red) 10%, var(--bg))',
                  border: `1px solid color-mix(in srgb, ${result.success ? 'var(--green)' : 'var(--red)'} 20%, transparent)`,
                }}>
                  <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: result.success ? 'var(--green)' : 'var(--red)' }}>
                    {result.success ? 'Trade Placed ✓' : 'Trade Failed ✗'}
                  </p>
                </div>
                <table className="t-table" style={{ fontSize: 10, width: '100%' }}>
                  <tbody>
                    {Object.entries(result).map(([k, v]) => (
                      <tr key={k} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                        <td style={{ padding: '4px 8px', color: 'var(--text-sub)', fontWeight: 600, textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}</td>
                        <td style={{ padding: '4px 8px', fontFamily: 'monospace' }}>{String(v)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {!result && !error && (
              <div style={{ padding: 20, textAlign: 'center', fontSize: 11, color: 'var(--text-faint)' }}>
                Place a trade to see the result
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
