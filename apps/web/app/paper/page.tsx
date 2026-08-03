'use client'

import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import { useEvents } from '@/lib/use-events'
import Link from 'next/link'
import { SkeletonCard } from '@/components/skeleton'
import { ErrorMessage } from '@/components/error-message'

interface PaperAccount {
  broker: string
  initial_capital: number
  realised_pnl: number
  unrealised_pnl: number
  daily_pnl: number
  current_equity: number
  day_start_equity: number
  peak_equity: number
  drawdown_pct: number
  day_date: string
  updated_at: string
}

interface PaperPosition {
  symbol: string
  side: string
  quantity: number
  open_quantity: number
  average_price: number
  last_price: number
  realised_pnl: number
  unrealised_pnl: number
  m2m: number
  product: string
  strategy_id: string
}

interface PaperTrade {
  client_order_id: string
  symbol: string
  side: string
  quantity: number
  price: number
  average_price: number
  realised_pnl: number
  state: string
  broker: string
  executed_at: string
}

interface RuntimeEntry {
  strategy_id: string
  status: string
  started_at: string
  symbol: string
  interval: string
  mode?: string
  candles?: number
  signals?: number
  orders_placed?: number
  orders_filled?: number
  orders_rejected?: number
  errors?: number
  last_error?: string
  last_activity?: string
  avg_latency_ms?: number
  pnl?: number
  health?: string
  user_id?: string
}

interface BuilderStrategy {
  id: string
  name: string
  status: string
}

function Money({ value, suffix = '₹' }: { value?: number; suffix?: string }) {
  const v = value ?? 0
  return (
    <span style={{ fontSize: 13, fontWeight: 700, color: v >= 0 ? 'var(--green)' : 'var(--red)' }}>
      {v >= 0 ? '+' : ''}{suffix}{v.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
    </span>
  )
}

function Card({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="t-panel" style={{ padding: '14px 16px' }}>
      <p style={{ margin: '0 0 6px', fontSize: 10, color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</p>
      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>{children}</div>
      {hint && <p style={{ margin: '4px 0 0', fontSize: 10, color: 'var(--text-faint)' }}>{hint}</p>}
    </div>
  )
}

export default function PaperTradingPage() {
  const [account, setAccount] = useState<PaperAccount | null>(null)
  const [positions, setPositions] = useState<PaperPosition[]>([])
  const [trades, setTrades] = useState<PaperTrade[]>([])
  const [portfolio, setPortfolio] = useState<{ open_positions: number; total_positions: number } | null>(null)
  const [status, setStatus] = useState<{ engine: { wired: boolean; engine_bridge: boolean } } | null>(null)
  const [running, setRunning] = useState<RuntimeEntry[]>([])
  const [strategies, setStrategies] = useState<BuilderStrategy[]>([])
  const [selected, setSelected] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [acting, setActing] = useState('')
  const [notice, setNotice] = useState('')
  const { connected, subscribe } = useEvents()

  const refresh = useCallback(async () => {
    try {
      const [acc, pos, tr, port, st, dash] = await Promise.all([
        api.paper.account(), api.paper.positions(), api.paper.trades(50),
        api.paper.portfolio(), api.paper.status(), api.builder.dashboard(),
      ])
      setAccount(acc)
      setPositions(pos.positions)
      setTrades(tr.trades)
      setPortfolio(port)
      setStatus(st)
      setRunning((dash as { running: RuntimeEntry[] }).running || [])
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load paper trading data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    const t = setInterval(refresh, 3000)
    return () => clearInterval(t)
  }, [refresh])

  useEffect(() => {
    const unsub = subscribe('*', () => refresh())
    return unsub
  }, [subscribe, refresh])

  const loadStrategies = async () => {
    try {
      const d = await api.builder.list()
      const list = (d as { strategies: BuilderStrategy[] }).strategies || []
      setStrategies(list)
      if (!selected && list.length > 0) setSelected(list[0].id)
    } catch { setStrategies([]) }
  }

  useEffect(() => { loadStrategies() }, [])

  const run = async (action: string, id?: string) => {
    setActing(action + (id || ''))
    setNotice('')
    try {
      if (action === 'start') {
        await api.builder.start(selected, 'NIFTY', '15m', 'paper')
        setNotice('Paper strategy started. Watching live fills...')
      } else if (action === 'stop') {
        await api.builder.stop(id!)
        setNotice('Strategy stopped. Positions remain visible until closed.')
      } else if (action === 'restart') {
        await api.builder.stop(id!)
        await new Promise(r => setTimeout(r, 400))
        await api.builder.start(id!, 'NIFTY', '15m', 'paper')
        setNotice('Strategy restarted.')
      }
      await refresh()
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Action failed')
    } finally {
      setActing('')
    }
  }

  const engineOk = !!status?.engine?.wired && !!status?.engine?.engine_bridge

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24, flexWrap: 'wrap', gap: 8 }}>
        <div>
          <h1 className="t-page-title">Paper Trading</h1>
          <p className="t-sub" style={{ fontSize: 13 }}>
            Deploy strategies to the live paper account and watch fills, positions, and P&L in real time
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className={`t-badge ${connected ? 't-badge-green' : 't-badge-red'}`} style={{ fontSize: 9 }}>
            {connected ? '● LIVE' : '○ CONNECTING'}
          </span>
          <span className={`t-badge ${engineOk ? 't-badge-green' : 't-badge-violet'}`} style={{ fontSize: 9 }}>
            {engineOk ? 'ENGINE OK' : 'ENGINE IDLE'}
          </span>
          <Link href="/strategies" className="t-btn t-btn-sm" style={{ fontSize: 10 }}>Strategies</Link>
        </div>
      </div>

      {notice && (
        <div style={{ background: 'color-mix(in srgb, var(--cyan) 6%, transparent)', border: '1px solid color-mix(in srgb, var(--cyan) 12%, transparent)', borderRadius: 10, padding: '10px 14px', marginBottom: 20, fontSize: 12, color: 'var(--cyan)' }}>
          {notice}
        </div>
      )}

      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : error ? (
        <ErrorMessage message={error} onRetry={refresh} />
      ) : (
        <>
          <div className="t-grid-auto" style={{ marginBottom: 24 }}>
            <Card label="Equity" hint={`Day start ${account?.day_start_equity ? '₹' + account.day_start_equity.toLocaleString('en-IN') : '—'}`}>
              {account ? '₹' + account.current_equity.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—'}
            </Card>
            <Card label="Realised P&L"><Money value={account?.realised_pnl} /></Card>
            <Card label="Unrealised P&L"><Money value={account?.unrealised_pnl} /></Card>
            <Card label="Daily P&L"><Money value={account?.daily_pnl} /></Card>
            <Card label="Peak Equity">{account ? '₹' + account.peak_equity.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—'}</Card>
            <Card label="Drawdown" hint={portfolio ? `${portfolio.open_positions} open / ${portfolio.total_positions} total positions` : undefined}>
              <span style={{ color: 'var(--text)' }}>{account?.drawdown_pct?.toFixed(2)}%</span>
            </Card>
          </div>

          <div className="t-panel" style={{ padding: '18px 20px', marginBottom: 24 }}>
            <div className="t-panel-header" style={{ marginBottom: 14 }}>
              <h3 className="t-panel-title" style={{ fontSize: 15 }}>Paper Account</h3>
              <span className="t-badge t-badge-violet" style={{ fontSize: 9 }}>strategy mode: paper</span>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <select className="t-select" value={selected} onChange={(e) => setSelected(e.target.value)} style={{ minWidth: 220 }}>
                {strategies.length === 0 && <option value="">No builder strategies</option>}
                {strategies.map(s => (
                  <option key={s.id} value={s.id}>{s.name} ({s.status})</option>
                ))}
              </select>
              <button className="t-btn-primary" disabled={!selected || !!acting || running.length >= 5} onClick={() => run('start')} style={{ fontSize: 12 }}>
                {acting === 'start' ? 'Starting...' : 'Start Paper Trading'}
              </button>
              {!engineOk && (
                <span className="t-faint" style={{ fontSize: 10 }}>
                  Engine idle — start a strategy to begin (live event feed powers this page)
                </span>
              )}
            </div>
          </div>

          <div className="t-panel" style={{ padding: '18px 20px', marginBottom: 24 }}>
            <div className="t-panel-header" style={{ marginBottom: 14 }}>
              <h3 className="t-panel-title" style={{ fontSize: 15 }}>Running Strategies</h3>
              <span className="t-badge t-badge-green" style={{ fontSize: 9 }}>{running.length} running</span>
            </div>
            {running.length === 0 ? (
              <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>
                Nothing running. Pick a strategy above and hit Start Paper Trading.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {running.map((r) => (
                  <div key={r.strategy_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)', flexWrap: 'wrap' }}>
                    <span className={`t-badge ${r.health === 'ok' ? 't-badge-green' : 't-badge-red'}`} style={{ fontSize: 9, flexShrink: 0 }}>
                      {r.health === 'ok' ? '● Healthy' : '● Degraded'}
                    </span>
                    <span style={{ fontSize: 12, fontWeight: 700 }}>{r.symbol || '—'}</span>
                    <span className="t-faint" style={{ fontSize: 10 }}>{r.interval || '—'} · {r.mode || 'paper'}</span>
                    <span className="t-faint" style={{ fontSize: 10 }}>
                      {r.orders_filled ?? 0}/{r.orders_placed ?? 0} filled{typeof r.errors === 'number' && r.errors > 0 ? ` · ${r.errors} err` : ''}
                    </span>
                    <span style={{ flex: 1 }} />
                    <Money value={r.pnl} />
                    <Link href={`/strategies/builder?id=${r.strategy_id}`} className="t-btn t-btn-sm" style={{ fontSize: 10 }}>Open</Link>
                    <button className="t-btn t-btn-sm" disabled={!!acting} onClick={() => run('restart', r.strategy_id)} style={{ fontSize: 10 }}>Restart</button>
                    <button className="t-btn t-btn-sm t-btn-danger" disabled={!!acting} onClick={() => run('stop', r.strategy_id)} style={{ fontSize: 10 }}>Stop</button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="t-grid-2" style={{ marginBottom: 24, gridTemplateColumns: '1.2fr 1fr' }}>
            <div className="t-panel" style={{ padding: '18px 20px' }}>
              <div className="t-panel-header" style={{ marginBottom: 14 }}>
                <h3 className="t-panel-title" style={{ fontSize: 15 }}>Open Positions</h3>
                <span className="t-badge t-badge-violet" style={{ fontSize: 9 }}>{positions.length} open</span>
              </div>
              {positions.length === 0 ? (
                <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No open positions. Net-flat or nothing traded yet.</p>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table className="t-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                    <thead>
                      <tr style={{ textAlign: 'left', fontSize: 10, color: 'var(--text-faint)' }}>
                        <th style={{ padding: '6px 8px' }}>Symbol</th>
                        <th style={{ padding: '6px 8px' }}>Side</th>
                        <th style={{ padding: '6px 8px' }}>Qty</th>
                        <th style={{ padding: '6px 8px' }}>Avg</th>
                        <th style={{ padding: '6px 8px' }}>LTP</th>
                        <th style={{ padding: '6px 8px' }}>Unrealised</th>
                        <th style={{ padding: '6px 8px' }}>Realised</th>
                      </tr>
                    </thead>
                    <tbody>
                      {positions.map((p) => (
                        <tr key={p.symbol} style={{ borderTop: '1px solid var(--border)' }}>
                          <td style={{ padding: '8px', fontWeight: 600 }}>{p.symbol}</td>
                          <td style={{ padding: '8px', color: p.side === 'BUY' ? 'var(--green)' : 'var(--red)' }}>{p.side}</td>
                          <td style={{ padding: '8px' }}>{p.open_quantity || p.quantity}</td>
                          <td style={{ padding: '8px' }}>{p.average_price}</td>
                          <td style={{ padding: '8px' }}>{p.last_price || '—'}</td>
                          <td style={{ padding: '8px' }}><Money value={p.unrealised_pnl} /></td>
                          <td style={{ padding: '8px' }}><Money value={p.realised_pnl} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="t-panel" style={{ padding: '18px 20px' }}>
              <div className="t-panel-header" style={{ marginBottom: 14 }}>
                <h3 className="t-panel-title" style={{ fontSize: 15 }}>Recent Fills</h3>
                <span className="t-faint" style={{ fontSize: 9 }}>latest 50</span>
              </div>
              {trades.length === 0 ? (
                <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No closed trades yet.</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 320, overflowY: 'auto' }}>
                  {trades.map((t) => (
                    <div key={t.client_order_id || (t.symbol + t.executed_at)} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 6, background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
                      <span style={{ fontSize: 11, fontWeight: 700 }}>{t.symbol}</span>
                      <span style={{ fontSize: 10, color: t.side === 'BUY' ? 'var(--green)' : 'var(--red)' }}>{t.side} {t.quantity}</span>
                      <span className="t-faint" style={{ fontSize: 10 }}>@ {t.average_price || t.price || '—'}</span>
                      <span style={{ flex: 1 }} />
                      <Money value={t.realised_pnl} />
                      <span className="t-faint" style={{ fontSize: 9 }}>
                        {t.executed_at ? new Date(t.executed_at).toLocaleTimeString() : ''}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <p className="t-faint" style={{ fontSize: 10, marginTop: 4 }}>
            Open positions, P&amp;L, and running strategies are checkpointed automatically and restored after a server restart.
          </p>
        </>
      )}
    </div>
  )
}
