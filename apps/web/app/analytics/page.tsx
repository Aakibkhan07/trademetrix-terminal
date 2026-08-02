'use client'

import { useState, useMemo } from 'react'
import { useApi } from '@/lib/use-api'
import { SkeletonGrid } from '@/components/skeleton'
import { ErrorMessage } from '@/components/error-message'

function EquityMiniChart({ values, height = 80, width = 200 }: { values: number[]; height?: number; width?: number }) {
  if (values.length < 2) return null
  const min = Math.min(...values); const max = Math.max(...values); const range = max - min || 1
  const isUp = values[values.length - 1] >= values[0]
  const color = isUp ? 'var(--green)' : 'var(--red)'
  const x = (i: number) => (i / (values.length - 1)) * width
  const y = (v: number) => height - ((v - min) / range) * (height - 4) - 2
  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <path d={values.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(v)}`).join('')}
        fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  )
}

function BarChart({ data, height = 100 }: { data: { label: string; value: number; color?: string }[]; height?: number }) {
  if (data.length === 0) return null
  const maxVal = Math.max(...data.map(d => Math.abs(d.value)), 1)
  return (
    <svg viewBox={`0 0 ${data.length * 28} ${height}`} style={{ width: '100%', height: 'auto' }}>
      {data.map((d) => {
        const i = data.indexOf(d)
        const barH = (Math.abs(d.value) / maxVal) * (height - 28)
        const yPos = d.value >= 0 ? height - 24 - barH : height - 24
        return (
          <g key={d.label}>
            <rect x={i * 28 + 4} y={yPos} width={20} height={Math.max(2, barH)} rx={2} fill={d.color || (d.value >= 0 ? 'var(--green)' : 'var(--red)')} opacity={0.7} />
            <text x={i * 28 + 14} y={height - 8} textAnchor="middle" fill="var(--text-faint)" fontSize={8} fontFamily="var(--font-sans)">
              {d.label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

export default function AnalyticsPage() {
  const { data: posData, loading: posLoading, error: posError } = useApi<{ positions: any[] }>('/engine/positions')
  const { data: ordData, loading: ordLoading, error: ordError } = useApi<{ orders: any[] }>('/engine/orders')
  const { data: fundData, loading: fundLoading, error: fundError } = useApi('/engine/funds')
  const { data: runData, loading: runLoading, error: runError } = useApi<{ runs: any[] }>('/engine/runs')
  const { data: pnlDailyData, loading: pnlDailyLoading, error: pnlDailyError } = useApi<{ pnl: { daily?: number } | any; broker: string | null }>('/analytics/pnl?period=1d')
  const { data: pnlStateData, loading: pnlStateLoading, error: pnlStateError } = useApi<{ pnl: any; broker: string | null }>('/analytics/pnl?period=1w')
  const { data: mtmData, loading: mtmLoading, error: mtmError } = useApi<{ mtm: number }>('/analytics/mtm')

  const loading = posLoading || ordLoading || fundLoading || runLoading || pnlDailyLoading || pnlStateLoading || mtmLoading
  const error = posError || ordError || fundError || runError || pnlDailyError || pnlStateError || mtmError

  const positions = posData?.positions || []
  const orders = ordData?.orders || []
  const funds = fundData as { total_margin?: number; available_margin?: number; used_margin?: number } | null
  const runs = runData?.runs || []
  const dailyPnl = pnlDailyData?.pnl?.daily ?? null
  const pnlState = pnlStateData?.pnl ?? null
  const mtm = mtmData?.mtm ?? null

  const analytics = useMemo(() => {
    const totalPnl = positions.reduce((s: number, p: any) => s + (p.unrealised_pnl || 0), 0)

    const filled = orders.filter((o: any) => o.status === 'FILLED')
    const wins = filled.filter((o: any) => (o.pnl || 0) > 0)
    const losses = filled.filter((o: any) => (o.pnl || 0) < 0)
    const winRate = filled.length > 0 ? (wins.length / filled.length) * 100 : 0
    const avgWin = wins.length > 0 ? wins.reduce((s: number, o: any) => s + (o.pnl || 0), 0) / wins.length : 0
    const avgLoss = losses.length > 0 ? Math.abs(losses.reduce((s: number, o: any) => s + (o.pnl || 0), 0) / losses.length) : 0
    const profitFactor = avgLoss > 0 ? avgWin / avgLoss : avgWin > 0 ? 99 : 0
    const expectancy = filled.length > 0 ? filled.reduce((s: number, o: any) => s + (o.pnl || 0), 0) / filled.length : 0

    const equityCurve = positions.map((p: any, i: number) => {
      const pnl = p.unrealised_pnl || 0
      return positions.slice(0, i + 1).reduce((s: number, pp: any) => s + (pp.unrealised_pnl || 0), 0)
    })

    const dayOfWeek: Record<string, number> = {}
    const hourOfDay: Record<string, number> = {}
    for (const o of orders) {
      if (o.created_at) {
        const d = new Date(o.created_at)
        const day = d.toLocaleDateString('en', { weekday: 'short' })
        const hour = `${d.getHours()}h`
        dayOfWeek[day] = (dayOfWeek[day] || 0) + 1
        hourOfDay[hour] = (hourOfDay[hour] || 0) + 1
      }
    }
    const dayOrder = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    const activeRuns = runs.filter((r: any) => r.status === 'active').length

    return { totalPnl, winRate, avgWin, avgLoss, profitFactor, expectancy, equityCurve, dayOfWeek, hourOfDay, dayOrder, activeRuns, filled, wins, losses }
  }, [positions, orders, runs])

  if (loading) return <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}><SkeletonGrid count={6} /></div>
  if (error) return <ErrorMessage message="Failed to load analytics" onRetry={() => window.location.reload()} />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <h1 style={{ fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 18, margin: 0, color: 'var(--text)' }}>Analytics</h1>
        <p style={{ color: 'var(--text-sub)', fontSize: 12, margin: '2px 0 0' }}>Performance metrics and trade analysis</p>
      </div>

      {/* KPI Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8 }}>
        {[
          { label: 'Today\'s P&L', value: dailyPnl === null ? '—' : `${dailyPnl >= 0 ? '+' : ''}${dailyPnl.toFixed(0)}`, sub: pnlDailyData?.broker ? `${pnlDailyData.broker} (realized)` : 'no broker', color: (dailyPnl ?? 0) >= 0 ? 'var(--text-green)' : 'var(--text-red)' },
          { label: 'Total P&L', value: `${analytics.totalPnl >= 0 ? '+' : ''}${analytics.totalPnl.toFixed(0)}`, sub: `${positions.length} positions`, color: analytics.totalPnl >= 0 ? 'var(--text-green)' : 'var(--text-red)' },
          { label: 'Win Rate', value: `${analytics.winRate.toFixed(1)}%`, sub: `${analytics.wins.length}W / ${analytics.losses.length}L`, color: analytics.winRate >= 50 ? 'var(--text-green)' : 'var(--text-red)' },
          { label: 'Avg Win / Loss', value: `+${analytics.avgWin.toFixed(0)} / -${analytics.avgLoss.toFixed(0)}`, sub: `PF: ${analytics.profitFactor.toFixed(2)}` },
          { label: 'Expectancy', value: analytics.expectancy >= 0 ? `+${analytics.expectancy.toFixed(0)}` : analytics.expectancy.toFixed(0), sub: 'per trade', color: analytics.expectancy >= 0 ? 'var(--text-green)' : 'var(--text-red)' },
          { label: 'Active Runs', value: `${analytics.activeRuns}`, sub: `${runs.length} total runs` },
        ].map(kpi => (
          <div key={kpi.label} className="t-panel" style={{ padding: 12 }}>
            <div style={{ fontSize: 9, color: 'var(--text-faint)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>{kpi.label}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: kpi.color || 'var(--text)', marginBottom: 1 }}>{kpi.value}</div>
            <div style={{ fontSize: 10, color: 'var(--text-faint)' }}>{kpi.sub}</div>
          </div>
        ))}
      </div>

      {/* Charts Row */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 10 }}>
        {/* Equity Curve */}
        <div className="t-panel" style={{ padding: 12 }}>
          <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 6 }}>Equity Curve</div>
          {analytics.equityCurve.length > 1 ? (
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 100 }}>
              {analytics.equityCurve.map((v: number, i: number) => {
                const min = Math.min(...analytics.equityCurve)
                const max = Math.max(...analytics.equityCurve)
                const range = max - min || 1
                const h = ((v - min) / range) * 96
                const isUp = v >= 0
                return (
                  <div key={i} style={{
                    flex: 1, height: `${Math.max(2, h)}px`, alignSelf: 'flex-end',
                    background: isUp ? 'var(--green)' : 'var(--red)',
                    opacity: 0.5, borderRadius: '1px 1px 0 0',
                  }} title={`${v.toFixed(0)}`} />
                )
              })}
            </div>
          ) : (
            <p style={{ color: 'var(--text-faint)', fontSize: 11, margin: '32px 0', textAlign: 'center' }}>No position data</p>
          )}
        </div>

        {/* Orders by Day */}
        <div className="t-panel" style={{ padding: 12 }}>
          <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 6 }}>Orders by Day</div>
          <BarChart data={analytics.dayOrder.map(d => ({ label: d, value: analytics.dayOfWeek[d] || 0 }))} height={100} />
          {Object.keys(analytics.dayOfWeek).length === 0 && (
            <p style={{ color: 'var(--text-faint)', fontSize: 11, margin: '32px 0', textAlign: 'center' }}>No data</p>
          )}
        </div>

        {/* Positions Breakdown */}
        <div className="t-panel" style={{ padding: 12 }}>
          <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 6 }}>Positions</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {positions.length > 0 ? (
              positions.map((p: any, i: number) => {
                const pnl = p.unrealised_pnl || 0
                return (
                  <div key={i}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 2 }}>
                      <span style={{ fontWeight: 600, color: 'var(--text)' }}>{p.symbol?.split(':').pop()}</span>
                      <span style={{ fontFamily: 'var(--font-mono)', color: pnl >= 0 ? 'var(--text-green)' : 'var(--text-red)', fontWeight: 700 }}>
                        {pnl >= 0 ? '+' : ''}{pnl.toFixed(0)}
                      </span>
                    </div>
                    <EquityMiniChart values={[pnl * 0.5, pnl * 0.7, pnl * 0.9, pnl]} height={24} width={180} />
                  </div>
                )
              })
            ) : (
              <p style={{ color: 'var(--text-faint)', fontSize: 11, margin: '28px 0', textAlign: 'center' }}>No positions</p>
            )}
          </div>
        </div>
      </div>

      {/* P&L Snapshot (live portfolio P&L) */}
      {(pnlState || mtm !== null) && (
        <div className="t-panel" style={{ padding: 12 }}>
          <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 8 }}>
            P&L Snapshot {pnlStateData?.broker ? `· ${pnlStateData.broker}` : ''}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 8 }}>
            {[
              { label: 'Realized', value: pnlState?.realised_pnl ?? null, fmt: (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(0)}` },
              { label: 'Unrealized', value: pnlState?.unrealised_pnl ?? null, fmt: (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(0)}` },
              { label: 'Weekly', value: pnlState?.weekly_pnl ?? null, fmt: (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(0)}` },
              { label: 'Monthly', value: pnlState?.monthly_pnl ?? null, fmt: (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(0)}` },
              { label: 'Overall', value: pnlState?.overall_pnl ?? null, fmt: (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(0)}` },
              { label: 'Current Equity', value: pnlState?.current_equity ?? null, fmt: (v: number) => `₹${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}` },
              { label: 'Drawdown', value: pnlState?.drawdown_pct ?? null, fmt: (v: number) => `${v.toFixed(2)}%` },
              { label: 'MTM Exposure', value: mtm, fmt: (v: number) => `₹${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}` },
            ].map(m => (
              <div key={m.label} style={{ padding: '8px 10px', borderRadius: 6, background: 'color-mix(in srgb, var(--violet) 4%, transparent)' }}>
                <div style={{ fontSize: 9, color: 'var(--text-faint)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>{m.label}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: m.value === null ? 'var(--text-faint)' : (m.label === 'Drawdown' || m.label === 'MTM Exposure' || m.label === 'Current Equity' ? 'var(--text)' : ((m.value as number) >= 0 ? 'var(--text-green)' : 'var(--text-red)')) }}>
                  {m.value === null ? '—' : m.fmt(m.value as number)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Holdings + Recent Runs */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        {/* Holdings Table */}
        <div className="t-panel" style={{ padding: 0 }}>
          <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>Holdings ({positions.length})</span>
          </div>
          {positions.length > 0 ? (
            <div style={{ overflowX: 'auto' }}>
              <table className="t-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th className="num">Qty</th>
                    <th className="num">Avg</th>
                    <th className="num">LTP</th>
                    <th className="num">P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p: any, i: number) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 600, fontSize: 12 }}>{p.symbol?.split(':').pop()}</td>
                      <td className="t-num">{p.quantity || 0}</td>
                      <td className="t-num">{(p.average_buy_price || 0).toFixed(1)}</td>
                      <td className="t-num">{(p.last_price || 0).toFixed(1)}</td>
                      <td className={`t-num ${(p.unrealised_pnl || 0) >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 700 }}>
                        {(p.unrealised_pnl || 0) >= 0 ? '+' : ''}{(p.unrealised_pnl || 0).toFixed(0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p style={{ color: 'var(--text-faint)', fontSize: 11, textAlign: 'center', padding: 20, margin: 0 }}>No open positions</p>
          )}
        </div>

        {/* Recent Runs */}
        <div className="t-panel" style={{ padding: 0 }}>
          <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>Recent Engine Runs</span>
            <span className="t-faint" style={{ fontSize: 10 }}>{runs.length} total</span>
          </div>
          {runs.length > 0 ? (
            <div style={{ maxHeight: 200, overflowY: 'auto' }}>
              {runs.slice(0, 10).map((r: any, i: number) => (
                <div key={r.id || i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '6px 12px', borderBottom: '1px solid color-mix(in srgb, var(--text-inverse) 3%, transparent)',
                  fontSize: 11,
                }}>
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--text)' }}>{r.strategy_name || r.strategy_id || 'Run'}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-faint)' }}>{r.symbol || ''} {r.created_at ? new Date(r.created_at).toLocaleDateString() : ''}</div>
                  </div>
                  <span className={`t-badge ${r.status === 'active' ? 't-badge-green' : r.status === 'error' ? 't-badge-red' : 't-badge-sub'}`} style={{ fontSize: 8 }}>
                    {r.status || 'unknown'}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ color: 'var(--text-faint)', fontSize: 11, textAlign: 'center', padding: 20, margin: 0 }}>No engine runs yet</p>
          )}
        </div>
      </div>

      {/* Account Summary */}
      {funds && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
          {[
            { label: 'Total Margin', value: `₹${(funds.total_margin || 0).toLocaleString()}`, pct: 100, color: 'var(--cyan)' },
            { label: 'Used Margin', value: `₹${(funds.used_margin || 0).toLocaleString()}`, pct: funds.total_margin ? ((funds.used_margin || 0) / funds.total_margin) * 100 : 0, color: 'var(--amber)' },
            { label: 'Available Margin', value: `₹${(funds.available_margin || 0).toLocaleString()}`, pct: funds.total_margin ? ((funds.available_margin || 0) / funds.total_margin) * 100 : 0, color: 'var(--green)' },
          ].map(m => (
            <div key={m.label} className="t-panel" style={{ padding: 12 }}>
              <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 4 }}>{m.label}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>{m.value}</div>
              <div className="t-progress">
                <div className="t-progress-fill" style={{ width: `${Math.min(m.pct, 100)}%`, background: m.color }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
