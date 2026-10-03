'use client'

import { useEffect, useState, useCallback } from 'react'
import { api, friendlyApiError, type ForwardTestItem, type ForwardTestStatus } from '@/lib/api'
import { SkeletonCard } from '@/components/skeleton'
import { ErrorMessage } from '@/components/error-message'

/**
 * How often a running forward test is re-read.
 *
 * A forward test's status only changes when its runner advances, so this is a display refresh
 * rather than a liveness requirement — long enough to stay well inside any sane rate limit.
 */
const STATUS_POLL_MS = 5000

export default function ForwardTestPage() {
  return <ForwardTests />
}

function ForwardTests() {
  const [items, setItems] = useState<ForwardTestItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // `GET /forward-tests/` answers `{ items: [...] }`, not a bare array. That envelope used
    // to be typed as an array and handed straight to `setItems`, which left `items` an object:
    // `items.length === 0` was then false, the render fell through to `items.map`, and the
    // page died with `items.map is not a function`.
    //
    // Both halves of that are now fixed — the type in `lib/api.ts` and the unwrap here. The
    // unwrap stays defensive on purpose: the failure mode is a whole page in an error
    // boundary, so a shape change should cost an empty state rather than a crash.
    api.forwardTests
      .list()
      .then((res) => setItems(Array.isArray(res?.items) ? res.items : []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ padding: 20 }}><SkeletonCard /></div>

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '40px 20px', fontFamily: 'var(--font-sans)' }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 26, fontWeight: 600, margin: '0 0 6px', color: 'var(--text)' }}>Forward Testing</h1>
        <p style={{ fontSize: 16, color: 'var(--text-sub)', margin: 0, lineHeight: 1.5 }}>
          Run a backtested strategy against live market data — virtual capital, real ticks, no real risk.
          Validates your backtest expectations before going live.
        </p>
      </div>

      {items.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-sub)' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>→</div>
          <p style={{ fontSize: 17, margin: 0 }}>No forward tests yet.</p>
          <p style={{ fontSize: 16, marginTop: 8, color: 'var(--text-faint)' }}>
            Run a backtest first, then create a forward test from the backtest results page.
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {items.map(ft => <ForwardTestCard key={ft.id} item={ft} />)}
        </div>
      )}

      <div style={{ marginTop: 40, padding: 20, background: 'var(--panel)', borderRadius: 14, border: '1px solid var(--border-2)' }}>
        <h2 style={{ fontSize: 18, fontWeight: 600, margin: '0 0 12px', color: 'var(--text)' }}>How forward testing works</h2>
        <ul style={{ fontSize: 16, color: 'var(--text-sub)', lineHeight: 1.8, paddingLeft: 18, margin: 0 }}>
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

    // Poll only while the test is actually running, and never at a zero interval.
    //
    // The previous expression was `setInterval(fetchStatus, item.status === 'running' ? 5000 : 0)`,
    // so **every state other than `running` set a 0 ms interval** — `pending`, `completed`,
    // `failed`, `stopped` all became an unbounded request loop firing as fast as the event loop
    // allowed. It only appeared once a forward test existed, which is why no crawl caught it.
    //
    // The blast radius is wider than the page. It exhausted the caller's rate-limit budget, so
    // unrelated pages' own polling started getting 429: a crawl after creating a forward test showed
    // `/funds` and `/go-live` rendering 402 chars of layout with none of their data, and the API log
    // carried 16 rate-limit events. One page's polling bug silently emptied others.
    if (item.status !== 'running') return

    const iv = setInterval(fetchStatus, STATUS_POLL_MS)
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
    tracking: 'var(--green)',
    deviating: 'var(--red)',
    recovered: 'var(--green)',
    stopped: 'var(--text-sub)',
    completed: 'var(--cyan)',
    error: 'var(--red)',
  }[status?.estimated_trend ?? item.estimated_trend] ?? 'var(--text-sub)'

  return (
    <div style={{ background: 'var(--panel)', borderRadius: 14, border: '1px solid var(--border-2)', padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 17, fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>
            {item.symbol} · {item.interval} · {item.mode}
          </div>
          <div style={{ fontSize: 14, color: 'var(--text-faint)' }}>
            Run: {item.backtest_run_id} · Strategy: {item.strategy_id}
          </div>
        </div>
        <span style={{ fontSize: 13, padding: '3px 10px', borderRadius: 'var(--radius-pill)', background: 'var(--panel)', color: trendColor, border: '1px solid var(--border-2)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          {status?.estimated_trend ?? item.estimated_trend}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
        <Stat label="Equity" value={`₹${Math.round((status?.current_equity ?? item.current_equity)).toLocaleString('en-IN')}`} color={status?.current_equity !== undefined ? (status.current_equity >= item.initial_capital ? 'var(--green)' : 'var(--red)') : 'var(--text)'} />
        <Stat label="Peak" value={`₹${Math.round((status?.peak_equity ?? item.peak_equity)).toLocaleString('en-IN')}`} />
        <Stat label="Drawdown" value={`${(status?.drawdown_pct ?? item.drawdown_pct).toFixed(1)}%`} color={(status?.drawdown_pct ?? item.drawdown_pct) > 10 ? 'var(--red)' : 'var(--text)'} />
        <Stat label="Trades" value={(status?.trades_count ?? item.trades_count).toString()} />
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        {item.status === 'pending' && (
          <button onClick={handleStart} style={{ padding: '7px 18px', borderRadius: 'var(--radius-md)', border: 'none', background: 'var(--gradient-primary)', color: 'var(--text-inverse)', fontSize: 16, fontWeight: 500, cursor: 'pointer' }}>
            Start Forward Test
          </button>
        )}
        {item.status === 'running' && (
          <button onClick={handleStop} style={{ padding: '7px 18px', borderRadius: 'var(--radius-md)', border: '1px solid var(--red)', background: 'transparent', color: 'var(--red)', fontSize: 16, fontWeight: 500, cursor: 'pointer' }}>
            Stop
          </button>
        )}
        {(item.status === 'running' || item.status === 'stopped' || item.status === 'completed') && (
          <button onClick={handleCompare} disabled={comparing} style={{ padding: '7px 18px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-2)', background: 'var(--panel)', color: 'var(--text)', fontSize: 16, cursor: comparing ? 'wait' : 'pointer' }}>
            {comparing ? 'Comparing...' : 'Compare vs Backtest'}
          </button>
        )}
      </div>

      {error && <ErrorMessage message={error} />}

      {comparison && (
        <div style={{ marginTop: 12, padding: 14, background: 'var(--panel-2)', borderRadius: 10, border: '1px solid var(--border-2)' }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 10, color: 'var(--text)' }}>Backtest vs Forward Comparison</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-faint)', marginBottom: 2 }}>Backtest PnL</div>
              <div style={{ fontSize: 17, fontWeight: 600, color: 'var(--text)' }}>
                ₹{(comparison.backtest.total_pnl as number).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                {' '}({(comparison.backtest.pnl_pct as number).toFixed(1)}%)
              </div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-faint)', marginBottom: 2 }}>Forward PnL</div>
              <div style={{ fontSize: 17, fontWeight: 600, color: (comparison.forward.pnl_pct as number) >= 0 ? 'var(--green)' : 'var(--red)' }}>
                ₹{((comparison.forward.current_equity as number) - (comparison.initial_capital as number)).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                {' '}({(comparison.forward.pnl_pct as number).toFixed(1)}%)
              </div>
            </div>
            <div style={{ textAlign: 'center', padding: '8px', borderRadius: 8, background: (comparison.deviation_alert as boolean) ? 'var(--red-dim)' : 'var(--cyan-dim)', border: `1px solid ${(comparison.deviation_alert as boolean) ? 'var(--red-dim)' : 'var(--cyan-dim)'}` }}>
              <div style={{ fontSize: 12, color: 'var(--text-faint)', marginBottom: 2 }}>Deviation Alert</div>
              <div style={{ fontSize: 16, fontWeight: 600, color: (comparison.deviation_alert as boolean) ? 'var(--red)' : 'var(--green)' }}>
                {(comparison.deviation_alert as boolean) ? '⚠ Exceeded' : '✓ Within range'}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 16, marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--border-2)' }}>
            <div style={{ fontSize: 13, color: 'var(--text-sub)' }}>
              <span style={{ color: 'var(--text-faint)' }}>Win Rate: </span>
              <span style={{ fontWeight: 600, color: 'var(--text)' }}>{(comparison.backtest.win_rate as number).toFixed(1)}%</span>
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-sub)' }}>
              <span style={{ color: 'var(--text-faint)' }}>Profit Factor: </span>
              <span style={{ fontWeight: 600, color: 'var(--text)' }}>{(comparison.backtest.profit_factor as number).toFixed(2)}</span>
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-sub)' }}>
              <span style={{ color: 'var(--text-faint)' }}>Backtest Trades: </span>
              <span style={{ fontWeight: 600, color: 'var(--text)' }}>{(comparison.backtest.trades as number).toLocaleString()}</span>
            </div>
          </div>
        </div>
      )}

      {status && (
        <div style={{ fontSize: 13, color: 'var(--text-faint)', marginTop: 8, display: 'flex', gap: 16 }}>
          <span>Status: <b style={{ color: 'var(--text-sub)' }}>{status.status}</b></span>
          {/* From the list row, not the detail response — the detail endpoint never returned
              these two fields, so reading them from `status` left both lines permanently hidden. */}
          {item.started_at && <span>Started: {new Date(item.started_at).toLocaleString('en-IN')}</span>}
          {item.stopped_at && <span>Stopped: {new Date(item.stopped_at).toLocaleString('en-IN')}</span>}
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ padding: 10, background: 'var(--panel-2)', borderRadius: 10, border: '1px solid var(--border-2)' }}>
      <div style={{ fontSize: 12, color: 'var(--text-faint)', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: color ?? 'var(--text)', fontFamily: 'var(--font-mono)' }}>{value}</div>
    </div>
  )
}
