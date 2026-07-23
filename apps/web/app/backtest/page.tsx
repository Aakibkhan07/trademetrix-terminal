'use client'

import { Suspense, useState, useMemo, useCallback } from 'react'
import { useSearchParams } from 'next/navigation'
import { api } from '@/lib/api'

const STRATEGIES = [
  { id: 'trend_rider', name: 'Trend Rider' },
  { id: 'orb_pro', name: 'ORB Pro' },
  { id: 'smc_sniper', name: 'SMC Sniper' },
  { id: 'expiry_hunter', name: 'Expiry Hunter' },
  { id: 'rsi_mean_reversion', name: 'RSI Mean Reversion' },
  { id: 'bollinger_bandit', name: 'Bollinger Bandit' },
  { id: 'macd_cross', name: 'MACD Cross' },
  { id: 'vwap_band', name: 'VWAP Band' },
]

const INTERVALS = [
  { id: '5m', label: '5 min' },
  { id: '15m', label: '15 min' },
  { id: '1h', label: '1 hour' },
  { id: '1d', label: 'Daily' },
]

interface Trade {
  symbol: string; side: string; entry_price: number; exit_price: number
  quantity: number; pnl: number; entry_time: string; exit_time: string
}

interface BacktestResultsData {
  symbol: string; strategy: string; interval: string; days: number
  initial_capital: number; candles_analyzed: number
  slippage_pct?: number; brokerage_pct?: number; stt_pct?: number; exchange_pct?: number
  results: {
    total_trades: number; winning_trades: number; losing_trades: number
    win_rate: number; total_pnl: number; max_drawdown: number
    sharpe_ratio: number; avg_win: number; avg_loss: number
    largest_win: number; largest_loss: number
    trades: Trade[]
    equity_curve: { equity: number; timestamp: string }[]
  }
}

function runMonteCarlo(trades: Trade[], initialCapital: number, iterations = 500): number[][] {
  if (trades.length < 3) return []
  const pnlValues = trades.map(t => t.pnl)
  const paths: number[][] = []
  for (let i = 0; i < iterations; i++) {
    let eq = initialCapital
    const curve = [eq]
    for (let j = 0; j < trades.length; j++) {
      eq += pnlValues[Math.floor(Math.random() * pnlValues.length)]
      curve.push(eq)
    }
    paths.push(curve)
  }
  return paths
}

function computeMonthlyReturns(trades: Trade[]): { month: string; return_pct: number }[] {
  const byMonth: Record<string, number> = {}
  for (const t of trades) {
    const m = t.exit_time ? t.exit_time.slice(0, 7) : 'unknown'
    byMonth[m] = (byMonth[m] || 0) + t.pnl
  }
  const totalPnl = trades.reduce((s, t) => s + t.pnl, 0)
  return Object.entries(byMonth).map(([month, pnl]) => ({
    month,
    return_pct: totalPnl !== 0 ? (pnl / Math.abs(totalPnl)) * 100 : 0,
  }))
}

function computeDrawdowns(equityCurve: { equity: number }[]): { depth: number; from: number; to: number }[] {
  const dd: { depth: number; from: number; to: number }[] = []
  let peak = -Infinity
  let peakIdx = 0
  let inDrawdown = false
  let startIdx = 0
  for (let i = 0; i < equityCurve.length; i++) {
    const e = equityCurve[i].equity
    if (e > peak) {
      peak = e
      peakIdx = i
      if (inDrawdown) {
        inDrawdown = false
      }
    }
    if (e < peak) {
      if (!inDrawdown) {
        inDrawdown = true
        startIdx = peakIdx
      }
      const depth = ((peak - e) / peak) * 100
      dd.push({ depth, from: startIdx, to: i })
    }
  }
  return dd.sort((a, b) => b.depth - a.depth).slice(0, 5)
}

function EquityChart({ curves, height = 200, color = 'var(--green)', label }: { curves: number[][]; height?: number; color?: string; label?: string }) {
  if (curves.length === 0) return null
  const all = curves.flat()
  const min = Math.min(...all)
  const max = Math.max(...all)
  const range = max - min || 1
  const width = 600
  const pad = { top: 16, right: 16, bottom: 24, left: 60 }
  const cw = width - pad.left - pad.right
  const ch = height - pad.top - pad.bottom
  const x = (_i: number, len: number) => pad.left + (_i / (len - 1 || 1)) * cw
  const y = (v: number) => pad.top + ch - ((v - min) / range) * ch

  return (
    <div>
      {label && <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 4, fontWeight: 700 }}>{label}</div>}
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto' }}>
        <defs>
          <linearGradient id="mc-fade"><stop offset="0%" stopColor={color} stopOpacity="0.08" /><stop offset="100%" stopColor={color} stopOpacity="0.01" /></linearGradient>
        </defs>
        {Array.from({ length: 5 }).map((_, i) => {
          const yy = pad.top + (i / 5) * ch
          return (
            <g key={i}>
              <line x1={pad.left} y1={yy} x2={width - pad.right} y2={yy} stroke="color-mix(in srgb, var(--text-inverse) 3%, transparent)" strokeWidth={1} />
              <text x={pad.left - 6} y={yy + 3} textAnchor="end" fill="var(--text-faint)" fontSize={8} fontFamily="var(--font-mono)">
                {Math.round(min + (range / 5) * (5 - i)).toLocaleString()}
              </text>
            </g>
          )
        })}
        {curves.slice(0, 50).map((curve, ci) => (
          <path key={ci} d={curve.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i, curve.length)},${y(v)}`).join('')}
            fill="none" stroke={color} strokeWidth={0.3} strokeOpacity={0.15} />
        ))}
        {curves.length > 0 && (
          <path d={curves[0].map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i, curves[0].length)},${y(v)}`).join('')}
            fill="none" stroke={color} strokeWidth={2} />
        )}
      </svg>
    </div>
  )
}

function BarChart({ data, height = 120 }: { data: { label: string; value: number; color?: string }[]; height?: number }) {
  if (data.length === 0) return null
  const maxVal = Math.max(...data.map(d => Math.abs(d.value)), 1)
  const w = 600
  const barW = Math.max(8, (w - 60) / data.length - 4)
  return (
    <svg viewBox={`0 0 ${w} ${height}`} style={{ width: '100%', height: 'auto' }}>
      <line x1={40} y1={height - 20} x2={w - 10} y2={height - 20} stroke="color-mix(in srgb, var(--text-inverse) 6%, transparent)" />
      <line x1={40} y1={20} x2={40} y2={height - 20} stroke="color-mix(in srgb, var(--text-inverse) 6%, transparent)" />
      {data.map((d, i) => {
        const xPos = 44 + i * (barW + 4)
        const barH = (Math.abs(d.value) / maxVal) * (height - 40)
        const yPos = d.value >= 0 ? height - 20 - barH : height - 20
        return (
          <g key={i}>
            <rect x={xPos} y={yPos} width={barW} height={Math.max(1, barH)} rx={2} fill={d.color || (d.value >= 0 ? 'var(--green)' : 'var(--red)')} opacity={0.7} />
            {height > 80 && (
              <text x={xPos + barW / 2} y={height - 6} textAnchor="middle" fill="var(--text-faint)" fontSize={7} fontFamily="var(--font-sans)">
                {d.label.length > 5 ? d.label.slice(0, 5) : d.label}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}

export default function BacktestPage() {
  return (
    <Suspense fallback={null}>
      <BacktestContent />
    </Suspense>
  )
}

function BacktestContent() {
  const searchParams = useSearchParams()
  const initialStrategy = searchParams.get('strategy') || 'trend_rider'
  const [strategy, setStrategy] = useState(initialStrategy)
  const [symbol, setSymbol] = useState('NIFTY')
  const [interval, setInterval] = useState('15m')
  const [days, setDays] = useState(60)
  const [capital, setCapital] = useState(100000)
  const [slippage, setSlippage] = useState(0.05)
  const [brokerage, setBrokerage] = useState(0.03)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<BacktestResultsData | null>(null)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'overview' | 'montecarlo' | 'optimization' | 'trades'>('overview')
  const [optParam, setOptParam] = useState('fast_period')
  const [optValues, setOptValues] = useState('5,9,14,21')
  const [optResults, setOptResults] = useState<{ value: string; result: BacktestResultsData }[]>([])
  const [optRunning, setOptRunning] = useState(false)
  const [compareStrategies, setCompareStrategies] = useState<string[]>(['trend_rider'])
  const [compareResults, setCompareResults] = useState<BacktestResultsData[]>([])
  const [compareRunning, setCompareRunning] = useState(false)

  const handleRun = async () => {
    setRunning(true); setError(''); setResult(null)
    try {
      const data = await api.post('/backtests/run', {
        strategy_type: strategy, symbol, interval, days,
        initial_capital: capital, config: {},
        slippage_pct: slippage, brokerage_pct: brokerage,
      })
      setResult(data as BacktestResultsData)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Backtest failed')
    } finally { setRunning(false) }
  }

  const r = result?.results
  const mcPaths = useMemo(() => r?.trades ? runMonteCarlo(r.trades, result!.initial_capital) : [], [r?.trades, result?.initial_capital])
  const monthlyReturns = useMemo(() => r?.trades ? computeMonthlyReturns(r.trades) : [], [r?.trades])
  const drawdowns = useMemo(() => r?.equity_curve ? computeDrawdowns(r.equity_curve) : [], [r?.equity_curve])

  const handleToggleCompare = (strategyId: string) => {
    setCompareStrategies(prev =>
      prev.includes(strategyId) ? prev.filter(s => s !== strategyId) : [...prev, strategyId]
    )
  }

  const handleRunComparison = async () => {
    setCompareRunning(true)
    const results: BacktestResultsData[] = []
    for (const s of compareStrategies) {
      try {
        const data = await api.post('/backtests/run', { strategy_type: s, symbol, interval, days, initial_capital: capital, config: {} })
        results.push(data as BacktestResultsData)
      } catch { /* skip failures */ }
    }
    setCompareResults(results)
    setCompareRunning(false)
  }

  const handleRunOptimization = async () => {
    setOptRunning(true); setOptResults([])
    const values = optValues.split(',').map(v => v.trim()).filter(Boolean)
    const results: { value: string; result: BacktestResultsData }[] = []
    for (const v of values) {
      try {
        const data = await api.post('/backtests/run', {
          strategy_type: strategy, symbol, interval, days, initial_capital: capital,
          config: { [optParam]: Number(v) },
        })
        results.push({ value: v, result: data as BacktestResultsData })
      } catch { /* skip */ }
    }
    setOptResults(results)
    setOptRunning(false)
  }

  const kpiCard = (label: string, value: string, sub?: string, color?: string) => (
    <div className="t-panel" style={{ padding: 12 }}>
      <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: color || 'var(--text)', marginBottom: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: 'var(--text-faint)' }}>{sub}</div>}
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <h1 style={{ fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 18, margin: 0, color: 'var(--text)' }}>Backtest</h1>
        <p style={{ color: 'var(--text-sub)', fontSize: 12, margin: '2px 0 0' }}>Test strategies against historical data</p>
      </div>

      {/* Parameters Panel */}
      <div style={{
        background: 'var(--panel)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)', padding: 12,
      }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 8 }}>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Strategy</label>
            <select className="t-select" value={strategy} onChange={e => setStrategy(e.target.value)}>
              {STRATEGIES.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Symbol</label>
            <input className="t-input" value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} />
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Interval</label>
            <select className="t-select" value={interval} onChange={e => setInterval(e.target.value)}>
              {INTERVALS.map(i => <option key={i.id} value={i.id}>{i.label}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Days</label>
            <input className="t-input" type="number" value={days} onChange={e => setDays(Number(e.target.value))} min={1} max={365} />
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Capital</label>
            <input className="t-input" type="number" value={capital} onChange={e => setCapital(Number(e.target.value))} min={1000} />
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Slippage %</label>
            <input className="t-input" type="number" value={slippage} onChange={e => setSlippage(Number(e.target.value))} min={0} step={0.01} />
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Brokerage %</label>
            <input className="t-input" type="number" value={brokerage} onChange={e => setBrokerage(Number(e.target.value))} min={0} step={0.01} />
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button className="t-btn t-btn-primary" onClick={handleRun} disabled={running} style={{ width: '100%', height: 28 }}>
              {running ? 'Running...' : 'Run'}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div style={{
          background: 'color-mix(in srgb, var(--red) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--red) 15%, transparent)',
          borderRadius: 'var(--radius-md)', padding: '8px 12px', color: 'var(--text-red)', fontSize: 12,
        }}>{error}</div>
      )}

      {r && (
        <>
          {/* Tab Bar */}
          <div className="t-tabs">
            {(['overview', 'montecarlo', 'optimization', 'trades'] as const).map(tab => (
              <button key={tab} className={`t-tab ${activeTab === tab ? 'active' : ''}`} onClick={() => setActiveTab(tab)}>
                {tab === 'overview' ? 'Overview' : tab === 'montecarlo' ? 'Monte Carlo' : tab === 'optimization' ? 'Optimization' : 'Trade Log'}
              </button>
            ))}
          </div>

          {activeTab === 'overview' && (
            <>
              {/* KPI Row */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8 }}>
                {kpiCard('Total P&L (after costs)', `${r.total_pnl >= 0 ? '+' : ''}${r.total_pnl.toFixed(0)}`, `${r.total_trades} trades`, r.total_pnl >= 0 ? 'var(--text-green)' : 'var(--text-red)')}
                {kpiCard('Win Rate', `${r.win_rate}%`, `${r.winning_trades}W / ${r.losing_trades}L`, r.win_rate >= 50 ? 'var(--text-green)' : 'var(--text-red)')}
                {kpiCard('Sharpe', r.sharpe_ratio.toFixed(2), r.sharpe_ratio >= 1 ? 'Good' : 'Below threshold', r.sharpe_ratio >= 1 ? 'var(--text-green)' : 'var(--amber)')}
                {kpiCard('Max DD', `-${r.max_drawdown.toFixed(1)}%`, drawdowns[0] ? `${drawdowns[0].depth.toFixed(1)}% deepest` : '', 'var(--text-red)')}
                {kpiCard('Avg Win / Loss', `+${r.avg_win.toFixed(0)} / -${r.avg_loss.toFixed(0)}`, `Best: +${r.largest_win.toFixed(0)} / Worst: ${r.largest_loss.toFixed(0)}`)}
                {kpiCard('Candles', result!.candles_analyzed.toLocaleString(), `${result!.symbol} ${result!.interval}`)}
              </div>

              {/* Costs Summary */}
              <div className="t-panel" style={{ padding: 12 }}>
                <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 6 }}>Transaction Costs Applied</div>
                <div style={{ display: 'flex', gap: 16, fontSize: 11, color: 'var(--text-sub)' }}>
                  <span>Slippage: <strong>{result!.slippage_pct ?? 0.05}%</strong></span>
                  <span>Brokerage: <strong>{result!.brokerage_pct ?? 0.03}%</strong></span>
                  <span>STT: <strong>{result!.stt_pct ?? 0.025}%</strong></span>
                  <span>Exchange: <strong>{result!.exchange_pct ?? 0.003}%</strong></span>
                </div>
              </div>

              {/* Charts Row */}
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10 }}>
                {/* Equity Curve */}
                <div className="t-panel" style={{ padding: 12 }}>
                  <EquityChart curves={[r.equity_curve.map(p => p.equity)]} height={180} color={r.total_pnl >= 0 ? 'var(--green)' : 'var(--red)'} label="Equity Curve" />
                </div>

                {/* Monthly Returns */}
                <div className="t-panel" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 4, fontWeight: 700 }}>Monthly Returns</div>
                  <BarChart data={monthlyReturns.map(m => ({ label: m.month.slice(-2), value: m.return_pct }))} height={120} />
                  <div style={{ fontSize: 9, color: 'var(--text-faint)', textAlign: 'center', marginTop: 2 }}>% of total P&L</div>
                </div>
              </div>

              {/* Drawdown Analysis */}
              {drawdowns.length > 0 && (
                <div className="t-panel" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 8 }}>Largest Drawdowns</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {drawdowns.slice(0, 3).map((dd, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-faint)', width: 16 }}>#{i + 1}</span>
                        <div style={{ flex: 1, height: 6, background: 'var(--panel-2)', borderRadius: 3, overflow: 'hidden' }}>
                          <div style={{ width: `${Math.min(dd.depth / (drawdowns[0]?.depth || 1) * 100, 100)}%`, height: '100%', background: 'var(--red)', borderRadius: 3, opacity: 0.6 }} />
                        </div>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, color: 'var(--text-red)', width: 60, textAlign: 'right' }}>
                          -{dd.depth.toFixed(1)}%
                        </span>
                        <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>
                          candles {dd.from}–{dd.to}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Strategy Comparison */}
              <div className="t-panel" style={{ padding: 12 }}>
                <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700, marginBottom: 8 }}>Compare Strategies</div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                  {STRATEGIES.map(s => (
                    <button key={s.id}
                      className={`t-chip ${compareStrategies.includes(s.id) ? 'active' : ''}`}
                      onClick={() => handleToggleCompare(s.id)}
                    >{s.name}</button>
                  ))}
                </div>
                <button className="t-btn t-btn-sm t-btn-primary" onClick={handleRunComparison} disabled={compareRunning || compareStrategies.length < 2}>
                  {compareRunning ? 'Running...' : `Compare ${compareStrategies.length} Strategies`}
                </button>

                {compareResults.length > 0 && (
                  <div style={{ marginTop: 10, overflowX: 'auto' }}>
                    <table className="t-table">
                      <thead>
                        <tr>
                          <th>Metric</th>
                          {compareResults.map(cr => <th key={cr.strategy} style={{ textAlign: 'right' }}>{cr.strategy.replace('_', ' ')}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {[
                          { label: 'Total P&L', get: (cr: BacktestResultsData) => `${cr.results.total_pnl >= 0 ? '+' : ''}${cr.results.total_pnl.toFixed(0)}`, color: (cr: BacktestResultsData) => cr.results.total_pnl >= 0 ? 'var(--text-green)' : 'var(--text-red)' },
                          { label: 'Win Rate', get: (cr: BacktestResultsData) => `${cr.results.win_rate}%` },
                          { label: 'Sharpe', get: (cr: BacktestResultsData) => cr.results.sharpe_ratio.toFixed(2) },
                          { label: 'Max DD', get: (cr: BacktestResultsData) => `-${cr.results.max_drawdown.toFixed(1)}%` },
                          { label: 'Trades', get: (cr: BacktestResultsData) => cr.results.total_trades.toString() },
                          { label: 'Avg Win', get: (cr: BacktestResultsData) => `+${cr.results.avg_win.toFixed(0)}` },
                          { label: 'Avg Loss', get: (cr: BacktestResultsData) => `-${cr.results.avg_loss.toFixed(0)}` },
                        ].map(row => (
                          <tr key={row.label}>
                            <td style={{ fontWeight: 700 }}>{row.label}</td>
                            {compareResults.map(cr => (
                              <td key={cr.strategy} className="t-num" style={{ color: row.color?.(cr) || 'var(--text)' }}>{row.get(cr)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}

          {activeTab === 'montecarlo' && (
            <div className="t-panel" style={{ padding: 12 }}>
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>Monte Carlo Simulation</div>
                <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 2 }}>
                  500 simulated paths based on trade outcome distribution. Solid line = actual equity curve.
                </div>
              </div>
              <EquityChart curves={mcPaths} height={240} color="var(--violet)" />
              {mcPaths.length > 0 && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginTop: 10 }}>
                  {(() => {
                    const finalEq = mcPaths.map(p => p[p.length - 1])
                    const avg = finalEq.reduce((s, v) => s + v, 0) / finalEq.length
                    const sorted = [...finalEq].sort((a, b) => a - b)
                    const p95 = sorted[Math.floor(sorted.length * 0.95)]
                    const p05 = sorted[Math.floor(sorted.length * 0.05)]
                    return (
                      <>
                        {kpiCard('Expected Final', `₹${avg.toLocaleString(undefined, { maximumFractionDigits: 0 })}`, `from ₹${result!.initial_capital.toLocaleString()}`)}
                        {kpiCard('Best Case (P95)', `₹${p95.toLocaleString(undefined, { maximumFractionDigits: 0 })}`, `+${((p95 - result!.initial_capital) / result!.initial_capital * 100).toFixed(0)}%`, 'var(--text-green)')}
                        {kpiCard('Worst Case (P5)', `₹${p05.toLocaleString(undefined, { maximumFractionDigits: 0 })}`, `${((p05 - result!.initial_capital) / result!.initial_capital * 100).toFixed(0)}%`, p05 >= result!.initial_capital ? 'var(--text-green)' : 'var(--text-red)')}
                      </>
                    )
                  })()}
                </div>
              )}
            </div>
          )}

          {activeTab === 'optimization' && (
            <div className="t-panel" style={{ padding: 12 }}>
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>Parameter Optimization</div>
                <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 2 }}>
                  Test different parameter values to find the optimal configuration
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 10, flexWrap: 'wrap' }}>
                <div>
                  <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Parameter</label>
                  <select className="t-select" value={optParam} onChange={e => setOptParam(e.target.value)} style={{ width: 140 }}>
                    <option value="fast_period">Fast Period</option>
                    <option value="slow_period">Slow Period</option>
                    <option value="lookback">Lookback</option>
                    <option value="threshold">Threshold</option>
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Values (comma-separated)</label>
                  <input className="t-input" value={optValues} onChange={e => setOptValues(e.target.value)} style={{ width: 200 }} />
                </div>
                <button className="t-btn t-btn-primary" onClick={handleRunOptimization} disabled={optRunning}>
                  {optRunning ? 'Running...' : 'Optimize'}
                </button>
              </div>

              {optResults.length > 0 && (
                <div style={{ overflowX: 'auto' }}>
                  <table className="t-table">
                    <thead>
                      <tr>
                        <th>Value</th>
                        <th className="num">P&L</th>
                        <th className="num">Win Rate</th>
                        <th className="num">Sharpe</th>
                        <th className="num">Max DD</th>
                        <th className="num">Trades</th>
                        <th className="num">Avg Win</th>
                        <th className="num">Avg Loss</th>
                      </tr>
                    </thead>
                    <tbody>
                      {optResults.sort((a, b) => b.result.results.sharpe_ratio - a.result.results.sharpe_ratio).map(or => {
                        const cr = or.result.results
                        const best = or === optResults.sort((a, b) => b.result.results.sharpe_ratio - a.result.results.sharpe_ratio)[0]
                        return (
                          <tr key={or.value} style={best ? { background: 'color-mix(in srgb, var(--cyan) 4%, transparent)' } : {}}>
                            <td style={{ fontWeight: 700 }}>{or.value}{best ? ' ✓' : ''}</td>
                            <td className={`num ${cr.total_pnl >= 0 ? 't-up' : 't-down'}`}>{cr.total_pnl >= 0 ? '+' : ''}{cr.total_pnl.toFixed(0)}</td>
                            <td className="num">{cr.win_rate}%</td>
                            <td className="num" style={{ color: cr.sharpe_ratio >= 1 ? 'var(--text-green)' : 'var(--amber)' }}>{cr.sharpe_ratio.toFixed(2)}</td>
                            <td className="num t-down">-{cr.max_drawdown.toFixed(1)}%</td>
                            <td className="num">{cr.total_trades}</td>
                            <td className="num t-up">+{cr.avg_win.toFixed(0)}</td>
                            <td className="num t-down">-{cr.avg_loss.toFixed(0)}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {activeTab === 'trades' && r.trades.length > 0 && (
            <div className="t-panel" style={{ padding: 0 }}>
              <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>Trade Log ({r.trades.length} trades)</span>
              </div>
              <div style={{ overflowX: 'auto', maxHeight: 400, overflowY: 'auto' }}>
                <table className="t-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Symbol</th>
                      <th>Side</th>
                      <th className="num">Entry</th>
                      <th className="num">Exit</th>
                      <th className="num">Qty</th>
                      <th className="num">P&L</th>
                      <th>Entry Time</th>
                      <th>Exit Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.trades.map((t, i) => (
                      <tr key={i}>
                        <td className="t-faint">{i + 1}</td>
                        <td style={{ fontWeight: 600 }}>{t.symbol}</td>
                        <td><span className={t.side === 'BUY' ? 't-up' : 't-down'} style={{ fontWeight: 600 }}>{t.side}</span></td>
                        <td className="t-num">{t.entry_price.toFixed(1)}</td>
                        <td className="t-num">{t.exit_price.toFixed(1)}</td>
                        <td className="t-num">{t.quantity}</td>
                        <td className={`t-num ${t.pnl >= 0 ? 't-up' : 't-down'}`} style={{ fontWeight: 700 }}>{t.pnl >= 0 ? '+' : ''}{t.pnl.toFixed(0)}</td>
                        <td className="t-faint" style={{ fontSize: 10 }}>{new Date(t.entry_time).toLocaleString()}</td>
                        <td className="t-faint" style={{ fontSize: 10 }}>{new Date(t.exit_time).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {activeTab === 'trades' && r.trades.length === 0 && (
            <div className="t-panel" style={{ padding: 24, textAlign: 'center' }}>
              <p style={{ color: 'var(--text-faint)', fontSize: 12, margin: 0 }}>No trades were generated</p>
            </div>
          )}
        </>
      )}

      {!r && !running && !error && (
        <div className="t-panel" style={{ padding: 32, textAlign: 'center' }}>
          <p style={{ color: 'var(--text-faint)', fontSize: 13, margin: '0 0 4px' }}>Configure parameters and run a backtest</p>
          <p style={{ color: 'var(--text-faint)', fontSize: 11, margin: 0 }}>Compare strategies, optimize parameters, and analyze Monte Carlo simulations</p>
        </div>
      )}
    </div>
  )
}
