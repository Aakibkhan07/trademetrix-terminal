'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

interface OrderItem {
  id: string
  symbol: string
  side: string
  quantity: number
  price: number
  status: string
  signal_at: string | null
  risk_checked_at: string | null
  sent_at: string | null
  filled_at: string | null
  latency_ms: number | null
  slippage: number | null
  is_paper: boolean
  created_at: string
}

export default function TransparencyPage() {
  const [orders, setOrders] = useState<OrderItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const data = await api.engine.runs() as { runs?: OrderItem[] }
        setOrders(data.runs || [])
      } catch {
        setOrders([])
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontFamily: 'Outfit', fontSize: 24, margin: 0 }}>Transparency Dashboard</h1>
        <p className="t-sub" style={{ margin: '4px 0 0' }}>
          Full order lifecycle — every signal, every check, every fill
        </p>
      </div>

      {loading ? (
        <p style={{ color: '#8888a0' }}>Loading order data...</p>
      ) : orders.length === 0 ? (
        <div className="t-panel" style={{ textAlign: 'center', padding: 48 }}>
          <p style={{ color: '#555570', margin: 0 }}>No orders yet. Start a strategy to see your order lifecycle here.</p>
        </div>
      ) : (
        <div className="t-panel" style={{ overflowX: 'auto' }}>
          <table className="t-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Status</th>
                <th>Signal</th>
                <th>Risk Check</th>
                <th>Sent</th>
                <th>Filled</th>
                <th>Latency</th>
                <th>Slippage</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id}>
                  <td className="t-num neon-cyan">{o.symbol}</td>
                  <td>
                    <span className={o.side === 'BUY' ? 't-up' : 't-down'}>
                      {o.side}
                    </span>
                  </td>
                  <td className="t-num">{o.quantity}</td>
                  <td>
                    <span className={`t-badge ${
                      o.status === 'FILLED' ? 't-badge-green' :
                      o.status === 'REJECTED' ? 't-badge-red' :
                      o.status === 'PENDING' ? 't-badge-violet' : 't-badge-cyan'
                    }`}>
                      {o.status}
                    </span>
                  </td>
                  <td className="t-num">{o.signal_at ? new Date(o.signal_at).toLocaleTimeString() : '-'}</td>
                  <td className="t-num">{o.risk_checked_at ? new Date(o.risk_checked_at).toLocaleTimeString() : '-'}</td>
                  <td className="t-num">{o.sent_at ? new Date(o.sent_at).toLocaleTimeString() : '-'}</td>
                  <td className="t-num">{o.filled_at ? new Date(o.filled_at).toLocaleTimeString() : '-'}</td>
                  <td className="t-num">
                    {o.latency_ms !== null ? (
                      <span style={{ color: (o.latency_ms || 0) < 100 ? '#22c55e' : '#f59e0b' }}>
                        {o.latency_ms.toFixed(1)}ms
                      </span>
                    ) : '-'}
                  </td>
                  <td className="t-num">
                    {o.slippage !== null ? (
                      <span style={{ color: (o.slippage || 0) === 0 ? '#22c55e' : '#ef4444' }}>
                        {o.slippage.toFixed(2)}
                      </span>
                    ) : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ marginTop: 24 }}>
        <div className="t-panel">
          <div className="t-panel-header">
            <h3 className="t-panel-title">Lifecycle Legend</h3>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
            <div>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Signal</p>
              <p style={{ fontSize: 13, margin: 0 }}>When the strategy generated the signal</p>
            </div>
            <div>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Risk Check</p>
              <p style={{ fontSize: 13, margin: 0 }}>When RiskGuard validated the signal</p>
            </div>
            <div>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Sent</p>
              <p style={{ fontSize: 13, margin: 0 }}>When the order was sent to the broker</p>
            </div>
            <div>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Filled</p>
              <p style={{ fontSize: 13, margin: 0 }}>When the broker confirmed the fill</p>
            </div>
            <div>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Latency</p>
              <p style={{ fontSize: 13, margin: 0 }}>Round-trip time: signal → fill (lower is better)</p>
            </div>
            <div>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Slippage</p>
              <p style={{ fontSize: 13, margin: 0 }}>Difference between expected and actual fill price</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
