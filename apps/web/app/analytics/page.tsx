'use client'

import { useState, useMemo } from 'react'
import { useApi } from '@/lib/use-api'
import { EmptyState } from '@/components/empty-state'
import { ErrorMessage } from '@/components/error-message'
import { SkeletonGrid, SkeletonTable } from '@/components/skeleton'

export default function AnalyticsPage() {
  const { data: posData, loading: posLoading, error: posError } = useApi<{ positions: any[] }>('/engine/positions')
  const { data: ordData, loading: ordLoading, error: ordError } = useApi<{ orders: any[] }>('/engine/orders')
  const { data: fundData, loading: fundLoading, error: fundError } = useApi('/engine/funds')
  const { data: runData, loading: runLoading, error: runError } = useApi<{ runs: any[] }>('/engine/runs')
  const { data: stratData, loading: stratLoading } = useApi<{ strategies: any[] }>('/strategies/list')
  const { data: brokerData, loading: brokerLoading } = useApi('/brokers/credentials')
  const { data: userData, loading: userLoading } = useApi('/auth/me')
  const { data: statsData, loading: statsLoading } = useApi<{ total_users?: number; active_assignments?: number; total_strategies?: number }>('/admin/stats')

  const loading = posLoading || ordLoading || fundLoading || runLoading || stratLoading || brokerLoading || userLoading || statsLoading
  const error = posError || ordError || fundError || runError

  const positions = posData?.positions || []
  const orders = ordData?.orders || []
  const funds = fundData as { total_margin?: number; available_margin?: number; used_margin?: number } | null
  const runs = runData?.runs || []
  const strategies = stratData?.strategies || []
  const brokers = (brokerData as { credentials?: any[] })?.credentials || []
  const stats = statsData

  const totalPnl = useMemo(() => positions.reduce((s: number, p: any) => s + (p.unrealised_pnl || 0), 0), [positions])
  const winRate = useMemo(() => {
    const filled = orders.filter((o: any) => o.status === 'FILLED')
    if (!filled.length) return 0
    return filled.filter((o: any) => (o.pnl || 0) > 0).length / filled.length * 100
  }, [orders])
  const totalTrades = orders.length
  const activeStrategies = strategies.filter((s: any) => s.is_active).length

  if (loading) return <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}><SkeletonGrid count={4} /><SkeletonTable rows={5} /></div>
  if (error) return <ErrorMessage message="Failed to load analytics data" onRetry={() => window.location.reload()} />

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-page-title">Analytics</h1>
        <p className="t-sub" style={{ fontSize: 13 }}>Platform performance and trading metrics</p>
      </div>

      <div className="t-grid-4" style={{ gap: 10, marginBottom: 20 }}>
        <div className="t-panel" style={{ padding: '14px 16px', borderLeft: '3px solid var(--cyan)' }}>
          <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>TOTAL P&L</div>
          <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-mono)', color: totalPnl >= 0 ? '#22c55e' : '#ef4444' }}>
            {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(2)}
          </div>
        </div>
        <div className="t-panel" style={{ padding: '14px 16px', borderLeft: '3px solid var(--violet)' }}>
          <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>WIN RATE</div>
          <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{winRate.toFixed(1)}%</div>
        </div>
        <div className="t-panel" style={{ padding: '14px 16px', borderLeft: '3px solid var(--green)' }}>
          <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>TOTAL TRADES</div>
          <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{totalTrades}</div>
        </div>
        <div className="t-panel" style={{ padding: '14px 16px', borderLeft: '3px solid var(--amber)' }}>
          <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>ACTIVE STRATEGIES</div>
          <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{activeStrategies}</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
        <div className="t-panel" style={{ padding: 16 }}>
          <h3 style={{ margin: '0 0 12px', fontSize: 13, fontWeight: 600 }}>Account Overview</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-sub)' }}>Total Margin</span>
              <span style={{ fontWeight: 600 }}>{funds?.total_margin?.toFixed(2) || '—'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-sub)' }}>Available</span>
              <span style={{ fontWeight: 600 }}>{funds?.available_margin?.toFixed(2) || '—'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-sub)' }}>Used</span>
              <span style={{ fontWeight: 600 }}>{funds?.used_margin?.toFixed(2) || '—'}</span>
            </div>
          </div>
        </div>
        <div className="t-panel" style={{ padding: 16 }}>
          <h3 style={{ margin: '0 0 12px', fontSize: 13, fontWeight: 600 }}>Platform Stats</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-sub)' }}>Brokers Connected</span>
              <span style={{ fontWeight: 600 }}>{brokers.length}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-sub)' }}>Strategies</span>
              <span style={{ fontWeight: 600 }}>{strategies.length}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-sub)' }}>Users</span>
              <span style={{ fontWeight: 600 }}>{stats?.total_users || '—'}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="t-panel" style={{ padding: 16, marginBottom: 20 }}>
        <h3 style={{ margin: '0 0 12px', fontSize: 13, fontWeight: 600 }}>Recent Runs</h3>
        {runs.length === 0 ? (
          <p style={{ fontSize: 12, color: 'var(--text-faint)' }}>No backtest runs yet.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {runs.slice(0, 5).map((r: any, i: number) => (
              <div key={r.id || i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
                <span>{r.strategy_name || r.strategy || 'Unknown'}</span>
                <span style={{ color: 'var(--text-sub)' }}>{r.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
