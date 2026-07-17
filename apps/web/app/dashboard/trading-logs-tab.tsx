'use client'

import { useState, useCallback } from 'react'
import { useApi } from '@/lib/use-api'
import { api, AdminUser, AdminOrder } from '@/lib/api'

function SkeletonCard() {
  return <div className="t-panel" style={{ padding: 12, height: 40, marginBottom: 6 }} />
}

export function TradingLogsTab() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [userFilter, setUserFilter] = useState('')
  const [symbolFilter, setSymbolFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [offset, setOffset] = useState(0)
  const limit = 100

  const params: Record<string, string> = { limit: String(limit), offset: String(offset) }
  if (userFilter) params.user_id = userFilter
  if (symbolFilter) params.symbol = symbolFilter
  if (statusFilter) params.status = statusFilter
  if (fromDate) params.from_date = fromDate
  if (toDate) params.to_date = toDate

  const { data, loading } = useApi<{ orders: AdminOrder[]; count: number }>(
    `/admin/orders?${new URLSearchParams(params)}&_=${refreshKey}`
  )
  const { data: usersData } = useApi<{ users: AdminUser[] }>('/admin/users')

  const orders = data?.orders || []
  const users = usersData?.users || []

  const exportCsv = useCallback(() => {
    const headers = ['Time', 'User', 'Email', 'Symbol', 'Exchange', 'Side', 'Qty', 'Price', 'Status', 'Broker', 'Type', 'Product', 'Filled Qty', 'Avg Price']
    const rows = orders.map(o => [
      o.created_at ? new Date(o.created_at).toISOString() : '',
      o.full_name || '',
      o.email || '',
      o.symbol || '',
      o.exchange || '',
      o.side || '',
      String(o.quantity || 0),
      String(o.price || 0),
      o.status || '',
      o.broker || '',
      o.instrument_type || 'EQ',
      o.product || '',
      String(o.filled_quantity || 0),
      String(o.average_price || 0),
    ])
    const csv = [headers.join(','), ...rows.map(r => r.map(c => `"${c.replace(/"/g, '""')}"`).join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `trading-logs-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }, [orders])

  const segColor = (t?: string) => {
    const map: Record<string, string> = { OPT: 'var(--violet)', FUT: 'var(--cyan)', EQ: 'var(--green)' }
    return map[t || 'EQ'] || 'var(--text-sub)'
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <select className="t-input" value={userFilter} onChange={e => { setUserFilter(e.target.value); setOffset(0) }}
          style={{ fontSize: 11, maxWidth: 220 }}>
          <option value="">— All users —</option>
          {users.map(u => (
            <option key={u.id} value={u.id}>{u.full_name || u.email} ({u.email})</option>
          ))}
        </select>
        <input className="t-input" placeholder="Symbol (e.g. NIFTY)" value={symbolFilter}
          onChange={e => { setSymbolFilter(e.target.value); setOffset(0) }} style={{ width: 140, fontSize: 11 }} />
        <select className="t-input" value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setOffset(0) }}
          style={{ fontSize: 11, maxWidth: 110 }}>
          <option value="">All statuses</option>
          <option value="OPEN">OPEN</option>
          <option value="FILLED">FILLED</option>
          <option value="REJECTED">REJECTED</option>
          <option value="CANCELLED">CANCELLED</option>
          <option value="PENDING">PENDING</option>
        </select>
        <input className="t-input" type="date" value={fromDate}
          onChange={e => { setFromDate(e.target.value); setOffset(0) }} style={{ width: 130, fontSize: 11 }} />
        <input className="t-input" type="date" value={toDate}
          onChange={e => { setToDate(e.target.value); setOffset(0) }} style={{ width: 130, fontSize: 11 }} />
        <span style={{ fontSize: 10, color: 'var(--text-sub)' }}>{data?.count || orders.length} orders</span>
        <button className="t-btn t-btn-sm" onClick={() => setRefreshKey(k => k + 1)} style={{ fontSize: 10 }}>Refresh</button>
        <button className="t-btn t-btn-sm" onClick={exportCsv} disabled={orders.length === 0}
          style={{ fontSize: 10, background: 'color-mix(in srgb, var(--green) 12%, transparent)', borderColor: 'color-mix(in srgb, var(--green) 20%, transparent)', color: 'var(--green)' }}>
          Export CSV
        </button>
      </div>

      {loading && <SkeletonCard />}
      {!loading && orders.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No orders found. Adjust filters.</p>
        </div>
      )}

      {!loading && orders.length > 0 && (
        <>
          <div style={{ overflowX: 'auto' }}>
            <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                  <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>TIME</th>
                  <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>USER</th>
                  <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>SYMBOL</th>
                  <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>SEG</th>
                  <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>SIDE</th>
                  <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>QTY</th>
                  <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>PRICE</th>
                  <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>STATUS</th>
                  <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>BROKER</th>
                  <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>TYPE</th>
                  <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>PAPER</th>
                  <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>FILLED</th>
                </tr>
              </thead>
              <tbody>
                {orders.map(o => (
                  <tr key={o.id || o.broker_order_id} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                    <td style={{ padding: '6px 8px', fontSize: 8, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>
                      {o.created_at ? new Date(o.created_at).toLocaleString() : '—'}
                    </td>
                    <td style={{ padding: '6px 8px' }}>
                      <div style={{ fontWeight: 600, color: 'var(--text)', fontSize: 9 }}>{o.full_name || '—'}</div>
                      <div style={{ fontSize: 7, color: 'var(--text-faint)' }}>{o.email}</div>
                    </td>
                    <td style={{ padding: '6px 8px', fontWeight: 500, color: 'var(--text)' }}>{o.symbol?.split(':').pop()}</td>
                    <td style={{ padding: '6px 8px' }}>
                      <span style={{ color: segColor(o.instrument_type), fontWeight: 600, fontSize: 9 }}>{o.instrument_type || 'EQ'}</span>
                    </td>
                    <td style={{ padding: '6px 8px', color: o.side === 'BUY' ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>{o.side}</td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{o.quantity}</td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{o.price ? o.price.toFixed(2) : '—'}</td>
                    <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                      <span style={{
                        color: o.status === 'FILLED' || o.status === 'OPEN' ? 'var(--green)'
                          : o.status === 'REJECTED' || o.status === 'CANCELLED' ? 'var(--red)'
                          : 'var(--amber)',
                        fontSize: 9, fontWeight: 600,
                      }}>{o.status}</span>
                    </td>
                    <td style={{ padding: '6px 8px', textTransform: 'capitalize', fontSize: 9 }}>{o.broker}</td>
                    <td style={{ padding: '6px 8px', fontSize: 9, color: 'var(--text-sub)' }}>{o.order_type}</td>
                    <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                      {o.is_paper
                        ? <span style={{ color: 'var(--amber)', fontSize: 8 }}>Paper</span>
                        : <span style={{ color: 'var(--green)', fontSize: 8 }}>Live</span>
                      }
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: 9 }}>
                      {o.filled_quantity || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 12 }}>
            <button className="t-btn t-btn-sm" disabled={offset === 0} onClick={() => setOffset(o => Math.max(0, o - limit))}
              style={{ fontSize: 10 }}>Previous</button>
            <span style={{ fontSize: 10, color: 'var(--text-sub)', alignSelf: 'center' }}>{offset + 1}–{offset + orders.length}</span>
            <button className="t-btn t-btn-sm" disabled={orders.length < limit} onClick={() => setOffset(o => o + limit)}
              style={{ fontSize: 10 }}>Next</button>
          </div>
        </>
      )}
    </div>
  )
}
