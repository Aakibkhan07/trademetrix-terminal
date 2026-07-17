'use client'

import { useState, useMemo } from 'react'
import { useApi } from '@/lib/use-api'
import { AdminUser } from '@/lib/api'

interface PnLSummary {
  total_realised: number
  total_unrealised: number
  total_m2m: number
  trading_pnl: number
  open_positions: number
  filled_orders: number
}

interface DailyPnL {
  date: string
  pnl: number
  trades: number
  paper_trades: number
}

interface PnLData {
  summary: PnLSummary
  daily_pnl: DailyPnL[]
  users: { id: string; email: string; full_name: string }[]
}

function BarChart({ data, height = 160 }: { data: { date: string; pnl: number }[]; height?: number }) {
  if (!data.length) return <div style={{ fontSize: 11, color: 'var(--text-faint)', padding: 16, textAlign: 'center' }}>No data</div>
  const max = Math.max(...data.map(d => Math.abs(d.pnl)), 1)
  const w = Math.max(8, Math.min(40, 600 / data.length))

  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height, padding: '4px 0' }}>
      {data.map(d => {
        const pct = (d.pnl / max) * 100
        const barH = Math.max(2, Math.abs(pct) * (height / 100))
        const isNeg = d.pnl < 0
        return (
          <div key={d.date} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: w }}>
            <div style={{
              width: w - 2, height: barH,
              background: isNeg ? 'color-mix(in srgb, var(--red) 60%, transparent)' : 'color-mix(in srgb, var(--green) 60%, transparent)',
              borderRadius: '2px 2px 0 0',
              transition: 'height 0.3s',
              position: 'relative',
            }} title={`${d.date}: ₹${d.pnl.toLocaleString()}`} />
            {data.length < 20 && (
              <span style={{ fontSize: 7, color: 'var(--text-faint)', marginTop: 2, writingMode: 'vertical-lr' as any, transform: 'rotate(180deg)' }}>
                {d.date.slice(5)}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

function StatCard({ label, value, color, prefix = '₹' }: { label: string; value: number | string; color: string; prefix?: string }) {
  const val = typeof value === 'number' ? `${prefix}${Math.abs(value).toLocaleString()}` : String(value)
  return (
    <div className="t-panel" style={{ padding: '14px 16px', borderLeft: `3px solid ${color}` }}>
      <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, fontFamily: 'var(--font-mono)', color: typeof value === 'number' && value < 0 ? 'var(--red)' : 'var(--text)' }}>
        {typeof value === 'number' && value < 0 ? '-' : ''}{val}
      </div>
    </div>
  )
}

export function PnLDashboardTab() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [userFilter, setUserFilter] = useState('')
  const [period, setPeriod] = useState<'daily' | 'weekly' | 'monthly'>('daily')

  const params: Record<string, string> = { period }
  if (userFilter) params.user_id = userFilter

  const { data, loading } = useApi<PnLData>(`/admin/pnl?${new URLSearchParams(params)}&_=${refreshKey}`)
  const { data: usersData } = useApi<{ users: AdminUser[] }>('/admin/users')

  const users = usersData?.users || []
  const summary = data?.summary
  const dailyPnl = data?.daily_pnl || []

  const weeklyPnl = useMemo(() => {
    const groups: Record<string, number> = {}
    dailyPnl.forEach(d => {
      const d2 = new Date(d.date)
      const weekStart = new Date(d2)
      weekStart.setDate(d2.getDate() - d2.getDay())
      const key = weekStart.toISOString().slice(0, 10)
      groups[key] = (groups[key] || 0) + d.pnl
    })
    return Object.entries(groups).map(([date, pnl]) => ({ date, pnl })).sort((a, b) => a.date.localeCompare(b.date))
  }, [dailyPnl])

  const monthlyPnl = useMemo(() => {
    const groups: Record<string, number> = {}
    dailyPnl.forEach(d => {
      const key = d.date.slice(0, 7)
      groups[key] = (groups[key] || 0) + d.pnl
    })
    return Object.entries(groups).map(([date, pnl]) => ({ date, pnl })).sort((a, b) => a.date.localeCompare(b.date))
  }, [dailyPnl])

  const chartData = period === 'weekly' ? weeklyPnl : period === 'monthly' ? monthlyPnl : dailyPnl

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <select className="t-input" value={userFilter} onChange={e => setUserFilter(e.target.value)}
          style={{ fontSize: 11, maxWidth: 220 }}>
          <option value="">— All users —</option>
          {users.map(u => (
            <option key={u.id} value={u.id}>{u.full_name || u.email} ({u.email})</option>
          ))}
        </select>
        <div style={{ display: 'flex', gap: 2, borderRadius: 4, overflow: 'hidden', border: '1px solid color-mix(in srgb, var(--violet) 15%, transparent)' }}>
          {(['daily', 'weekly', 'monthly'] as const).map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              style={{
                padding: '4px 10px', fontSize: 9, fontWeight: 600, border: 'none', cursor: 'pointer',
                background: period === p ? 'var(--violet)' : 'transparent',
                color: period === p ? '#fff' : 'var(--text-sub)',
              }}>{p.charAt(0).toUpperCase() + p.slice(1)}</button>
          ))}
        </div>
        <button className="t-btn t-btn-sm" onClick={() => setRefreshKey(k => k + 1)} style={{ fontSize: 10 }}>Refresh</button>
      </div>

      {loading && (
        <div className="t-grid-4" style={{ gap: 10 }}>
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="t-panel" style={{ padding: '14px 16px' }}>
              <div style={{ width: '50%', height: 10, background: 'color-mix(in srgb, var(--violet) 8%, transparent)', borderRadius: 4 }} />
              <div style={{ height: 8 }} />
              <div style={{ width: '40%', height: 20, background: 'color-mix(in srgb, var(--violet) 8%, transparent)', borderRadius: 4 }} />
            </div>
          ))}
        </div>
      )}

      {!loading && summary && (
        <div className="t-grid-4" style={{ gap: 10, marginBottom: 16 }}>
          <StatCard label="TRADING P&L" value={summary.trading_pnl} color="var(--green)" />
          <StatCard label="REALISED P&L" value={summary.total_realised} color="var(--cyan)" />
          <StatCard label="UNREALISED P&L" value={summary.total_unrealised} color="var(--amber)" />
          <StatCard label="OPEN POSITIONS" value={summary.open_positions} color="var(--violet)" prefix="" />
        </div>
      )}

      {!loading && summary && (
        <div className="t-panel" style={{ padding: '14px 16px', marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <h3 style={{ margin: 0, fontSize: 11, fontWeight: 600, letterSpacing: '0.03em' }}>
              {period === 'daily' ? 'DAILY' : period === 'weekly' ? 'WEEKLY' : 'MONTHLY'} P&L
            </h3>
            <span style={{ fontSize: 9, color: 'var(--text-faint)' }}>
              {chartData.length} {period === 'daily' ? 'days' : period === 'weekly' ? 'weeks' : 'months'}
            </span>
          </div>
          {chartData.length > 0 && (
            <div>
              <div style={{
                fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-mono)',
                color: chartData.reduce((s, d) => s + d.pnl, 0) >= 0 ? 'var(--green)' : 'var(--red)',
                marginBottom: 8,
              }}>
                ₹{Math.abs(chartData.reduce((s, d) => s + d.pnl, 0)).toLocaleString()}
                <span style={{ fontSize: 10, fontWeight: 400, color: 'var(--text-sub)', marginLeft: 6 }}>
                  total ({chartData.reduce((s, d) => s + d.pnl, 0) >= 0 ? 'profit' : 'loss'})
                </span>
              </div>
              <BarChart data={chartData} />
            </div>
          )}
        </div>
      )}

      {!loading && summary && dailyPnl.length > 0 && (
        <div className="t-panel" style={{ padding: '14px 16px' }}>
          <h3 style={{ margin: '0 0 8px', fontSize: 11, fontWeight: 600, letterSpacing: '0.03em' }}>RECENT TRADES</h3>
          <div style={{ overflowX: 'auto' }}>
            <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                  <th style={{ padding: '4px 6px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>DATE</th>
                  <th style={{ padding: '4px 6px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>P&L</th>
                  <th style={{ padding: '4px 6px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>TRADES</th>
                  <th style={{ padding: '4px 6px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>PAPER</th>
                </tr>
              </thead>
              <tbody>
                {dailyPnl.slice(0, 30).map(d => (
                  <tr key={d.date} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 4%, transparent)' }}>
                    <td style={{ padding: '4px 6px', color: 'var(--text-faint)' }}>{d.date}</td>
                    <td style={{ padding: '4px 6px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: d.pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
                      ₹{d.pnl.toLocaleString()}
                    </td>
                    <td style={{ padding: '4px 6px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{d.trades}</td>
                    <td style={{ padding: '4px 6px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: d.paper_trades > 0 ? 'var(--amber)' : 'var(--text-faint)' }}>
                      {d.paper_trades || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!loading && !summary && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No P&L data available.</p>
        </div>
      )}
    </div>
  )
}
