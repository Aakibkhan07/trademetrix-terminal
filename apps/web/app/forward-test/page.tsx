'use client'

import { useEffect, useState, useCallback } from 'react'
import { api, friendlyApiError, type ForwardTestItem, type ForwardTestStatus } from '@/lib/api'
import { SkeletonCard } from '@/components/skeleton'
import { ErrorMessage } from '@/components/error-message'

export default function ForwardTestPage() {
  return <ForwardTests />
}

function ForwardTests() {
  const [items, setItems] = useState<ForwardTestItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.forwardTests.list().then(setItems).catch(() => {}).finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ padding: 20 }}><SkeletonCard /></div>

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '40px 20px', fontFamily: 'var(--font-body)' }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: '0 0 6px', color: 'var(--text)' }}>Forward Testing</h1>
        <p style={{ fontSize: 13, color: 'var(--text-dim)', margin: 0, lineHeight: 1.5 }}>
          Run a backtested strategy against live market data — virtual capital, real ticks, no real risk.
          Validates your backtest expectations before going live.
        </p>
      </div>

      {items.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-dim)' }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>→</div>
          <p style={{ fontSize: 14, margin: 0 }}>No forward tests yet.</p>
          <p style={{ fontSize: 13, marginTop: 8, color: 'var(--text-faint)' }}>
            Run a backtest first, then create a forward test from the backtest results page.
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {items.map(ft => <ForwardTestCard key={ft.id} item={ft} />)}
        </div>
      )}

      <div style={{ marginTop: 40, padding: 20, background: 'var(--panel-bg)', borderRadius: 14, border: '1px solid var(--panel-brd)' }}>
        <h2 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 12px', color: 'var(--text)' }}>How forward testing works</h2>
        <ul style={{ fontSize: 13, color: 'var(--text-dim)', lineHeight: 1.8, paddingLeft: 18, margin: 0 }}>
          <li>Pick a completed backtest run with positive results</li>
          <li>The strategy runs against LIVE market ticks (paper mode)</li>
          <li>Virtual capital — zero real money risk</li>
          <li>Monitored in real-time: equity, drawdown, deviation from backtest expectations</li>
          <li>Auto-stops if performance deviates beyond your threshold or max duration is reached</li>
          <li>Compare live results vs backtest to validate strategy robustness</li>
        </ul>
      </div>
    </div>
  )
}

function ForwardTestCard({ item }: { item: ForwardTestItem }) {
  const [status, setStatus] = useState<ForwardTestStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [comparing, setComparing] = useState(false)
  const [comparison, setComparison] = useState<{ backtest: { total_pnl: number; pnl_pct: number; win_rate: number; profit_factor: number; trades: number }; forward: { current_equity: number; pnl_pct: number; trades_count: number; signals_count: number; drawdown_pct: number; estimated_trend: string; deviation_threshold_pct: number }; initial_capital: number; deviation_alert: boolean } | null>(null)

  const fetchStatus = useCallback(async () => {
    if (!item.id) return
    setLoading(true)
    try {
      const s = await api.forwardTests.get(item.id)
      setStatus(s)
    } catch (e) {
      setError(friendlyApiError(e))
    } finally {
      setLoading(false)
    }
  }, [item.id])

  useEffect(() => {
    fetchStatus()
    const iv = setInterval(fetchStatus, item.status === 'running' ? 5000 : 0)
    return () => clearInterval(iv)
  }, [fetchStatus, item.status])

  const handleStart = async () => {
    setError(null)
    try {
      await api.forwardTests.start(item.id)
      fetchStatus()
    } catch (e) {
      setError(friendlyApiError(e))
    }
  }

  const handleStop = async () => {
    setError(null)
    try {
      await api.forwardTests.stop(item.id)
      fetchStatus()
    } catch (e) {
      setError(friendlyApiError(e))
    }
  }

  const handleCompare = async () => {
    setComparing(true)
    try {
      const c = await api.forwardTests.compare(item.id) as { backtest: { total_pnl: number; pnl_pct: number; win_rate: number; profit_factor: number; trades: number }; forward: { current_equity: number; pnl_pct: number; trades_count: number; signals_count: number; drawdown_pct: number; estimated_trend: string; deviation_threshold_pct: number }; initial_capital: number; deviation_alert: boolean }
      setComparison(c)
    } catch (e) {
      setError(friendlyApiError(e))
    } finally {
      setComparing(false)
    }
  }

  const trendColor = {
    pending: 'var(--text-faint)',
    tracking: 'var(--ok)',
    deviating: 'var(--err)',
    recovered: 'var(--ok)',
    stopped: 'var(--text-dim)',
    completed: 'var(--accent)',
    error: 'var(--err)',
  }[status?.estimated_trend ?? item.estimated_trend] ?? 'var(--text-dim)'

  return (
    <div style={{ background: 'var(--panel-bg)', borderRadius: 14, border: '1px solid var(--panel-brd)', padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>
            {item.symbol} · {item.interval} · {item.mode}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>
            Run: {item.backtest_run_id} · Strategy: {item.strategy_id}
          </div>
        </div>
        <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 20, background: 'var(--panel)', color: trendColor, border: '1px solid var(--panel-brd)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          {status?.estimated_trend ?? item.estimated_trend}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
        <Stat label="Equity" value={`₹${Math.round((status?.current_equity ?? item.current_equity)).toLocaleString('en-IN')}`} color={status?.current_equity !== undefined ? (status.current_equity >= item.initial_capital ? 'var(--ok)' : 'var(--err)') : 'var(--text)'} />
        <Stat label="Peak" value={`₹${Math.round((status?.peak_equity ?? item.peak_equity)).toLocaleString('en-IN')}`} />
        <Stat label="Drawdown" value={`${(status?.drawdown_pct ?? item.drawdown_pct).toFixed(1)}%`} color={(status?.drawdown_pct ?? item.drawdown_pct) > 10 ? 'var(--err)' : 'var(--text)'} />
        <Stat label="Trades" value={(status?.trades_count ?? item.trades_count).toString()} />
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        {item.status === 'pending' && (
          <button onClick={handleStart} style={{ padding: '7px 18px', borderRadius: 10, border: 'none', background: 'var(--accent)', color: '#fff', fontSize: 13, fontWeight: 500, cursor: 'pointer' }}>
            Start Forward Test
          </button>
        )}
        {item.status === 'running' && (
          <button onClick={handleStop} style={{ padding: '7px 18px', borderRadius: 10, border: '1px solid var(--err)', background: 'transparent', color: 'var(--err)', fontSize: 13, fontWeight: 500, cursor: 'pointer' }}>
            Stop
          </button>
        )}
        {(item.status === 'running' || item.status === 'stopped' || item.status === 'completed') && (
          <button onClick={handleCompare} disabled={comparing} style={{ padding: '7px 18px', borderRadius: 10, border: '1px solid var(--panel-brd)', background: 'var(--panel)', color: 'var(--text)', fontSize: 13, cursor: comparing ? 'wait' : 'pointer' }}>
            {comparing ? 'Comparing...' : 'Compare vs Backtest'}
          </button>
        )}
      </div>

      {error && <ErrorMessage message={error} />}

      {comparison && (
        <div style={{ marginTop: 12, padding: 14, background: 'var(--panel)', borderRadius: 10, border: '1px solid var(--panel-brd)' }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 10, color: 'var(--text)' }}>Backtest vs Forward Comparison</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
            <div>
              <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 2 }}>Backtest PnL</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>
                ₹{(comparison.backtest.total_pnl as number).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                {' '}({(comparison.backtest.pnl_pct as number).toFixed(1)}%)
              </div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 2 }}>Forward PnL</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: (comparison.forward.pnl_pct as number) >= 0 ? 'var(--ok)' : 'var(--err)' }}>
                ₹{((comparison.forward.current_equity as number) - (comparison.initial_capital as number)).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                {' '}({(comparison.forward.pnl_pct as number).toFixed(1)}%)
              </div>
            </div>
            <div style={{ textAlign: 'center', padding: '8px', borderRadius: 8, background: (comparison.deviation_alert as boolean) ? 'rgba(248,113,113,0.1)' : 'rgba(34,211,238,0.08)', border: `1px solid ${(comparison.deviation_alert as boolean) ? 'rgba(248,113,113,0.3)' : 'rgba(34,211,238,0.2)'}` }}>
              <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 2 }}>Deviation Alert</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: (comparison.deviation_alert as boolean) ? 'var(--err)' : 'var(--ok)' }}>
                {(comparison.deviation_alert as boolean) ? '⚠ Exceeded' : '✓ Within range'}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 16, marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--panel-brd)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
              <span style={{ color: 'var(--text-faint)' }}>Win Rate: </span>
              <span style={{ fontWeight: 600, color: 'var(--text)' }}>{(comparison.backtest.win_rate as number).toFixed(1)}%</span>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
              <span style={{ color: 'var(--text-faint)' }}>Profit Factor: </span>
              <span style={{ fontWeight: 600, color: 'var(--text)' }}>{(comparison.backtest.profit_factor as number).toFixed(2)}</span>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
              <span style={{ color: 'var(--text-faint)' }}>Backtest Trades: </span>
              <span style={{ fontWeight: 600, color: 'var(--text)' }}>{(comparison.backtest.trades as number).toLocaleString()}</span>
            </div>
          </div>
        </div>
      )}

      {status && (
        <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 8, display: 'flex', gap: 16 }}>
          <span>Status: <b style={{ color: 'var(--text-dim)' }}>{status.status}</b></span>
          {status.started_at && <span>Started: {new Date(status.started_at).toLocaleString('en-IN')}</span>}
          {status.stopped_at && <span>Stopped: {new Date(status.stopped_at).toLocaleString('en-IN')}</span>}
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ padding: 10, background: 'var(--panel)', borderRadius: 10, border: '1px solid var(--panel-brd)' }}>
      <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 15, fontWeight: 700, color: color ?? 'var(--text)', fontFamily: 'var(--font-mono)' }}>{value}</div>
    </div>
  )
}
