'use client'

import { Suspense, useState, useEffect, useMemo, useCallback } from 'react'
import { useSearchParams } from 'next/navigation'
import { api, backtestExportUrl } from '@/lib/api'

const BUILTIN_STRATEGIES = [
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

const WEEKDAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']

interface BTTrade {
  symbol: string; side: string; entry_price: number; exit_price: number
  quantity: number; pnl: number; entry_time: string; exit_time: string
}

interface BTResult {
  run_id: string; status: string; strategy_id: string
  config: { strategy_type: string; symbol: string; interval: string; days: number; initial_capital: number }
  summary: {
    total_trades: number; winning_trades: number; losing_trades: number; win_rate: number
    net_pnl: number; profit_factor: number; max_drawdown_pct: number; sharpe_ratio: number
    sortino_ratio: number; calmar_ratio: number; return_pct: number; expectancy: number
    expectancy_per_r: number; avg_risk_reward_ratio: number; median_risk_reward_ratio: number
    alpha: number; beta: number; benchmark_return_pct: number; excess_return_pct: number
    candles_analyzed: number; start_equity: number; end_equity: number
  }
  trades: BTTrade[]
  equity_curve: { index?: number; equity: number; timestamp?: string; drawdown?: number; drawdown_pct?: number }[]
  weekday_distribution: Record<string, number>
  hour_distribution: Record<string, number>
  month_distribution: Record<string, number>
  duration_seconds: number
  error?: string
}

interface OptimizeResult {
  run_id: string; status: string; method: string; strategy_type: string; symbol: string
  combos_total: number; combos_completed: number
  results: { params: Record<string, string | number>; metrics: Record<string, number>; error?: string }[]
  best: Record<string, unknown>
  distribution: Record<string, number>
  error?: string
}

interface BuilderStrategyItem { id: string; name: string; status: string }

function fmt(x: number | null | undefined, digits = 2): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—'
  return Number(x).toFixed(digits)
}

function fmtMoney(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—'
  const sign = x >= 0 ? '+' : ''
  return `${sign}₹${Math.round(x).toLocaleString('en-IN')}`
}

function LineChart({ series, height = 180, color = 'var(--green)', yLabel = '' }: {
  series: { x: string; y: number }[]; height?: number; color?: string; yLabel?: string
}) {
  if (series.length < 2) return null
  const ys = series.map(p => p.y)
  const min = Math.min(...ys); const max = Math.max(...ys)
  const range = max - min || 1
  const width = 600
  const pad = { top: 14, right: 16, bottom: 22, left: 58 }
  const cw = width - pad.left - pad.right
  const ch = height - pad.top - pad.bottom
  const x = (i: number) => pad.left + (i / (series.length - 1)) * cw
  const y = (v: number) => pad.top + ch - ((v - min) / range) * ch
  const last = series[series.length - 1]
  const first = series[0]
  const avg = ys.reduce((s, v) => s + v, 0) / ys.length

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto' }}>
        {Array.from({ length: 5 }).map((_, i) => {
          const yy = pad.top + (i / 4) * ch
          const val = max - (range / 4) * i
          return (
            <g key={i}>
              <line x1={pad.left} y1={yy} x2={width - pad.right} y2={yy} stroke="color-mix(in srgb, var(--text-inverse) 3%, transparent)" strokeWidth={1} />
              <text x={pad.left - 5} y={yy + 3} textAnchor="end" fill="var(--text-faint)" fontSize={8} fontFamily="var(--font-mono)">
                {Math.round(val).toLocaleString()}
              </text>
            </g>
          )
        })}
        <line x1={pad.left} y1={y(avg)} x2={width - pad.right} y2={y(avg)} stroke="var(--amber)" strokeWidth={1} strokeDasharray="4 3" opacity={0.6} />
        <path d={series.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(p.y)}`).join('')}
          fill="none" stroke={color} strokeWidth={2} />
        <circle cx={x(series.length - 1)} cy={y(last.y)} r={3} fill={color} />
        <text x={x(series.length - 1) - 4} y={y(last.y) - 6} textAnchor="end" fill="var(--text)" fontSize={9} fontFamily="var(--font-mono)" fontWeight={700}>
          {Math.round(last.y).toLocaleString()}
        </text>
        <text x={pad.left + 2} y={y(first.y) + 10} fill="var(--text-faint)" fontSize={8} fontFamily="var(--font-mono)">
          {Math.round(first.y).toLocaleString()}
        </text>
        {yLabel && <text x={8} y={pad.top} fill="var(--text-faint)" fontSize={8} fontWeight={700}>{yLabel}</text>}
      </svg>
    </div>
  )
}

function BarChart({ data, height = 120, unit = '' }: { data: { label: string; value: number }[]; height?: number; unit?: string }) {
  if (data.length === 0) return null
  const maxVal = Math.max(...data.map(d => Math.abs(d.value)), 1)
  const w = 600
  const barW = Math.max(7, (w - 60) / data.length - 3)
  return (
    <svg viewBox={`0 0 ${w} ${height}`} style={{ width: '100%', height: 'auto' }}>
      <line x1={40} y1={height - 20} x2={w - 10} y2={height - 20} stroke="color-mix(in srgb, var(--text-inverse) 6%, transparent)" />
      <line x1={40} y1={16} x2={40} y2={height - 20} stroke="color-mix(in srgb, var(--text-inverse) 6%, transparent)" />
      {data.map((d, i) => {
        const xPos = 44 + i * (barW + 3)
        const barH = (Math.abs(d.value) / maxVal) * (height - 40)
        const yPos = d.value >= 0 ? height - 20 - barH : height - 20
        return (
          <g key={d.label}>
            <rect x={xPos} y={yPos} width={barW} height={Math.max(1, barH)} rx={2}
              fill={d.value >= 0 ? 'var(--green)' : 'var(--red)'} opacity={0.7} />
            <text x={xPos + barW / 2} y={height - 6} textAnchor="middle" fill="var(--text-faint)" fontSize={7} fontFamily="var(--font-sans)">
              {d.label.length > 5 ? d.label.slice(0, 5) : d.label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function Heatmap({ data, title }: { data: Record<string, number>; title: string }) {
  const hours = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0'))
  const flat = Object.values(data)
  const max = Math.max(...flat, 1)
  const min = Math.min(...flat, 0)
  const cell = 22
  return (
    <div>
      <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 6, fontWeight: 700 }}>{title}</div>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${24}, ${cell}px)`, gap: 2, overflowX: 'auto' }}>
        {hours.map(h => (
          <div key={h} style={{ fontSize: 8, color: 'var(--text-faint)', textAlign: 'center' }}>{h}</div>
        ))}
        {WEEKDAYS.map(day => (
          <div key={day}>
            {hours.map(h => {
              const v = data[`${day}-${h}`] ?? data[h] ?? 0
              const t = max > min ? (v - min) / (max - min) : 0
              const alpha = v === 0 ? 0.05 : 0.25 + t * 0.6
              return (
                <div key={`${day}-${h}`} style={{
                  width: cell, height: cell, borderRadius: 3, marginBottom: 2,
                  background: v >= 0 ? `rgba(34,197,94,${alpha})` : `rgba(239,68,68,${alpha})`,
                }} title={`${day} ${h}:00 — ${v}`} />
              )
            })}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 4, alignItems: 'center', marginTop: 4, fontSize: 8, color: 'var(--text-faint)' }}>
        <span>Mon</span>
        <div style={{ flex: 1, height: 4, borderRadius: 2, background: 'color-mix(in srgb, var(--text-inverse) 8%, transparent)' }} />
        <span>Fri</span>
      </div>
    </div>
  )
}

const kpiCard = (label: string, value: string, sub?: string, color?: string) => (
  <div className="t-panel" style={{ padding: 12 }}>
    <div style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>{label}</div>
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 19, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: color || 'var(--text)', marginBottom: 1 }}>{value}</div>
    {sub && <div style={{ fontSize: 10, color: 'var(--text-faint)' }}>{sub}</div>}
  </div>
)

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

  const [source, setSource] = useState<'builtin' | 'builder'>(initialStrategy === 'trend_rider' ? 'builtin' : 'builder')
  const [strategy, setStrategy] = useState(initialStrategy)
  const [builderStrategies, setBuilderStrategies] = useState<BuilderStrategyItem[]>([])
  const [symbol, setSymbol] = useState('NIFTY')
  const [interval, setInterval] = useState('15m')
  const [days, setDays] = useState(60)
  const [capital, setCapital] = useState(100000)
  const [slippage, setSlippage] = useState(0.05)
  const [latency, setLatency] = useState(0)
  const [partialFill, setPartialFill] = useState(0)
  const [riskEnabled, setRiskEnabled] = useState(true)

  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<BTResult | null>(null)
  const [error, setError] = useState('')

  const [activeTab, setActiveTab] = useState<'overview' | 'optimizer' | 'compare' | 'trades'>('overview')

  const [optMethod, setOptMethod] = useState('grid')
  const [optMetric, setOptMetric] = useState('sharpe_ratio')
  const [optParamsText, setOptParamsText] = useState('fast_period=5,9,14,21\nslow_period=13,26')
  const [optRunning, setOptRunning] = useState(false)
  const [optResult, setOptResult] = useState<OptimizeResult | null>(null)
  const [optError, setOptError] = useState('')

  const [compareIdsText, setCompareIdsText] = useState('')
  const [compareRunning, setCompareRunning] = useState(false)
  const [comparison, setComparison] = useState<Record<string, Record<string, unknown>> | null>(null)
  const [compareError, setCompareError] = useState('')

  const [exporting, setExporting] = useState<string | null>(null)
  const [deploying, setDeploying] = useState(false)
  const [deployMsg, setDeployMsg] = useState('')

  useEffect(() => {
    api.builder.list().then(res => {
      const items = Array.isArray(res) ? res : (res as { strategies?: BuilderStrategyItem[] }).strategies || []
      setBuilderStrategies(items.filter(s => s.status !== 'ARCHIVED' && s.status !== 'STOPPED'))
    }).catch(() => { /* skip */ })
  }, [])

  const handleRun = useCallback(async () => {
    setRunning(true); setError(''); setResult(null)
    try {
      let data: BTResult
      if (source === 'builder') {
        if (!strategy) throw new Error('Select a builder strategy')
        data = await api.backtest.runV3({
          strategy_id: strategy, symbol, interval, days,
          initial_capital: capital, risk_enabled: riskEnabled,
          slippage_pct: slippage, latency_candles: latency,
          partial_fill_probability: partialFill,
        })
      } else {
        data = await api.backtest.run({
          strategy_type: strategy, symbol, interval, days,
          initial_capital: capital, config: {},
          slippage_pct: slippage,
        })
      }
      setResult(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Backtest failed')
    } finally { setRunning(false) }
  }, [source, strategy, symbol, interval, days, capital, slippage, latency, partialFill, riskEnabled])

  const handleRunOptimize = useCallback(async () => {
    setOptRunning(true); setOptError(''); setOptResult(null)
    const paramRanges: Record<string, (string | number)[]> = {}
    for (const line of optParamsText.split('\n')) {
      const eq = line.indexOf('=')
      if (eq <= 0) continue
      const key = line.slice(0, eq).trim()
      const values = line.slice(eq + 1).split(',').map(v => {
        const n = Number(v.trim())
        return Number.isNaN(n) ? v.trim() : n
      }).filter(v => v !== '')
      if (key && values.length) paramRanges[key] = values
    }
    if (Object.keys(paramRanges).length === 0) {
      setOptError('Enter at least one parameter range (e.g. fast_period=5,9,14)')
      setOptRunning(false)
      return
    }
    try {
      const data = await api.backtest.optimize({
        strategy_type: strategy,
        method: optMethod,
        param_ranges: paramRanges,
        metric: optMetric,
        symbol, interval, days,
      })
      setOptResult(data as OptimizeResult)
    } catch (err: unknown) {
      setOptError(err instanceof Error ? err.message : 'Optimization failed')
    } finally { setOptRunning(false) }
  }, [strategy, optMethod, optMetric, optParamsText, symbol, interval, days])

  const handleCompare = useCallback(async () => {
    setCompareRunning(true); setCompareError(''); setComparison(null)
    const ids = compareIdsText.split(',').map(s => s.trim()).filter(Boolean)
    if (ids.length < 2) {
      setCompareError('Enter at least 2 run IDs (comma-separated)')
      setCompareRunning(false)
      return
    }
    try {
      const data = await api.backtest.compare<{ comparison: Record<string, Record<string, unknown>> }>(ids)
      setComparison(data.comparison)
    } catch (err: unknown) {
      setCompareError(err instanceof Error ? err.message : 'Compare failed')
    } finally { setCompareRunning(false) }
  }, [compareIdsText])

  const handleExport = useCallback(async (format: 'json' | 'csv' | 'pdf') => {
    if (!result) return
    setExporting(format)
    try {
      const url = backtestExportUrl(result.run_id, format)
      const res = await fetch(url, { credentials: 'include' })
      if (!res.ok) {
        const t = await res.text()
        try { const j = JSON.parse(t); throw new Error(j.detail || `Export failed: ${res.status}`) } catch (e) { throw e }
      }
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `backtest-${result.run_id}.${format}`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Export failed')
    } finally { setExporting(null) }
  }, [result])

  const handleDeployToPaper = useCallback(async () => {
    if (!result) return
    setDeploying(true); setDeployMsg('')
    try {
      const data = await api.backtest.deployToPaper(result.run_id)
      setDeployMsg(`Deployed to paper — ${data.status} (${data.strategy_id})`)
    } catch (err: unknown) {
      setDeployMsg(err instanceof Error ? err.message : 'Deploy failed')
    } finally { setDeploying(false) }
  }, [result])

  const s = result?.summary
  const equityPoints = useMemo(() => (result?.equity_curve || []).map((p, i) => ({
    x: p.timestamp || String(p.index ?? i),
    y: p.equity,
  })), [result])

  const drawdownSeries = useMemo(() => {
    let peak = -Infinity
    return (result?.equity_curve || []).map((p, i) => {
      if (p.equity > peak) peak = p.equity
      return { x: p.timestamp || String(p.index ?? i), y: peak > 0 ? ((peak - p.equity) / peak) * 100 : 0 }
    })
  }, [result])

  const weekdayBars = useMemo(() => WEEKDAYS
    .map(d => ({ label: d, value: result?.weekday_distribution?.[d] || 0 }))
    .filter(d => d.value !== 0), [result])

  const hourBars = useMemo(() => Array.from({ length: 24 }, (_, h) => {
    const key = String(h).padStart(2, '0')
    return { label: key, value: result?.hour_distribution?.[key] || 0 }
  }).filter(d => d.value !== 0), [result])

  const monthBars = useMemo(() => Object.entries(result?.month_distribution || {})
    .map(([k, v]) => ({ label: k.slice(5, 7) || k, value: v })), [result])

  const bestCombo = useMemo(() => {
    if (!optResult?.results?.length) return null
    const key = optMetric
    return [...optResult.results].sort((a, b) => (b.metrics?.[key] ?? -Infinity) - (a.metrics?.[key] ?? -Infinity))[0]
  }, [optResult, optMetric])

  const selectedBuilderName = builderStrategies.find(b => b.id === strategy)?.name || strategy

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 18, margin: 0, color: 'var(--text)' }}>Backtest Engine</h1>
          <p style={{ color: 'var(--text-sub)', fontSize: 12, margin: '2px 0 0' }}>Institutional-grade backtesting for Indian markets — costs, corporate actions, continuous futures</p>
        </div>
        {result?.run_id && (
          <div style={{ fontSize: 10, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>
            run {result.run_id} · {(result.duration_seconds || 0).toFixed(1)}s
          </div>
        )}
      </div>

      {/* Run Form */}
      <div style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: 12 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 8 }}>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Source</label>
            <select className="t-select" value={source} onChange={e => {
              setSource(e.target.value as 'builtin' | 'builder')
              if (e.target.value === 'builder') setStrategy(builderStrategies[0]?.id || '')
            }}>
              <option value="builtin">Built-in</option>
              <option value="builder">Builder (DSL)</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Strategy</label>
            {source === 'builtin' ? (
              <select className="t-select" value={strategy} onChange={e => setStrategy(e.target.value)}>
                {BUILTIN_STRATEGIES.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            ) : (
              <select className="t-select" value={strategy} onChange={e => setStrategy(e.target.value)}>
                {builderStrategies.length === 0 && <option value="">No builder strategies</option>}
                {builderStrategies.map(s => <option key={s.id} value={s.id}>{s.name} ({s.status.toLowerCase()})</option>)}
              </select>
            )}
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
            <input className="t-input" type="number" value={days} onChange={e => setDays(Number(e.target.value))} min={1} max={730} />
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
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Latency (candles)</label>
            <input className="t-input" type="number" value={latency} onChange={e => setLatency(Number(e.target.value))} min={0} max={5} />
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Partial fill %</label>
            <input className="t-input" type="number" value={partialFill} onChange={e => setPartialFill(Number(e.target.value))} min={0} max={100} />
          </div>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Risk checks</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, height: 28 }}>
              <button className={`t-chip ${riskEnabled ? 'active' : ''}`} onClick={() => setRiskEnabled(!riskEnabled)} style={{ fontSize: 10 }}>
                {riskEnabled ? 'ON' : 'OFF'}
              </button>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button className="t-btn t-btn-primary" onClick={handleRun} disabled={running} style={{ width: '100%', height: 28 }}>
              {running ? 'Running…' : 'Run Backtest'}
            </button>
          </div>
        </div>
        <div style={{ marginTop: 8, fontSize: 10, color: 'var(--text-faint)' }}>
          {source === 'builder' ? `Running DSL strategy "${selectedBuilderName}" via the GraphStrategy runtime — same code path as paper/live deployment.` : 'Built-in strategy path. Use Builder source to backtest DSL strategies and deploy them to paper with one click.'}
        </div>
      </div>

      {error && (
        <div style={{ background: 'color-mix(in srgb, var(--red) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--red) 15%, transparent)', borderRadius: 'var(--radius-md)', padding: '8px 12px', color: 'var(--text-red)', fontSize: 12 }}>{error}</div>
      )}

      {s && (
        <>
          <div className="t-tabs">
            {(['overview', 'optimizer', 'compare', 'trades'] as const).map(tab => (
              <button key={tab} className={`t-tab ${activeTab === tab ? 'active' : ''}`} onClick={() => setActiveTab(tab)}>
                {tab === 'overview' ? 'Overview' : tab === 'optimizer' ? 'Optimizer' : tab === 'compare' ? 'Compare Runs' : `Trades (${s.total_trades})`}
              </button>
            ))}
          </div>

          {activeTab === 'overview' && (
            <>
              {/* KPI grid */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 8 }}>
                {kpiCard('Net P&L (after costs)', fmtMoney(s.net_pnl), `${s.total_trades} trades`, s.net_pnl >= 0 ? 'var(--text-green)' : 'var(--text-red)')}
                {kpiCard('Return', `${s.return_pct >= 0 ? '+' : ''}${fmt(s.return_pct)}%`, `from ₹${Math.round(s.start_equity).toLocaleString('en-IN')}`)}
                {kpiCard('Win Rate', `${fmt(s.win_rate, 1)}%`, `${s.winning_trades}W / ${s.losing_trades}L`, s.win_rate >= 50 ? 'var(--text-green)' : 'var(--text-red)')}
                {kpiCard('Profit Factor', fmt(s.profit_factor), s.profit_factor >= 1.5 ? 'Healthy' : s.profit_factor >= 1 ? 'Positive' : 'Below 1', s.profit_factor >= 1 ? 'var(--text-green)' : 'var(--text-red)')}
                {kpiCard('Expectancy', fmtMoney(s.expectancy), `${fmt(s.expectancy_per_r)}R per trade`, s.expectancy >= 0 ? 'var(--text-green)' : 'var(--text-red)')}
                {kpiCard('Sharpe', fmt(s.sharpe_ratio), s.sharpe_ratio >= 1 ? 'Good' : 'Below threshold', s.sharpe_ratio >= 1 ? 'var(--text-green)' : 'var(--amber)')}
                {kpiCard('Sortino', fmt(s.sortino_ratio), 'downside-adjusted')}
                {kpiCard('Calmar', fmt(s.calmar_ratio), 'return / max DD')}
                {kpiCard('Max Drawdown', `-${fmt(s.max_drawdown_pct)}%`, `peak-to-trough`, 'var(--text-red)')}
                {kpiCard('Alpha (252d)', `${s.alpha >= 0 ? '+' : ''}${fmt(s.alpha)}%`, `vs ${s.benchmark_return_pct >= 0 ? '+' : ''}${fmt(s.benchmark_return_pct)}% benchmark`, s.alpha >= 0 ? 'var(--text-green)' : 'var(--text-red)')}
                {kpiCard('Beta (252d)', fmt(s.beta), s.beta <= 1 ? 'Lower vol than market' : 'Higher vol than market')}
                {kpiCard('Avg / Med RR', `${fmt(s.avg_risk_reward_ratio)} / ${fmt(s.median_risk_reward_ratio)}`, 'risk-reward per trade')}
                {kpiCard('Candles', (s.candles_analyzed || 0).toLocaleString(), `${result!.config.symbol} ${result!.config.interval}`)}
                {kpiCard('Final Equity', fmtMoney(s.end_equity), `+${fmt(s.return_pct)}%`) }
              </div>

              {/* Equity + Drawdown */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div className="t-panel" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 4, fontWeight: 700 }}>Equity Curve</div>
                  <LineChart series={equityPoints} height={170} color={s.net_pnl >= 0 ? 'var(--green)' : 'var(--red)'} />
                </div>
                <div className="t-panel" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 4, fontWeight: 700 }}>Drawdown %</div>
                  <LineChart series={drawdownSeries} height={170} color="var(--red)" />
                </div>
              </div>

              {/* Distributions */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div className="t-panel" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 4, fontWeight: 700 }}>By Weekday</div>
                  <BarChart data={weekdayBars} height={110} />
                </div>
                <div className="t-panel" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 4, fontWeight: 700 }}>By Hour (IST)</div>
                  <BarChart data={hourBars} height={110} />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div className="t-panel" style={{ padding: 12 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 4, fontWeight: 700 }}>P&L by Month (₹)</div>
                  <BarChart data={monthBars} height={110} />
                </div>
                <div className="t-panel" style={{ padding: 12 }}>
                  <Heatmap data={result?.weekday_distribution || {}} title="Weekday × Hour P&L Heatmap" />
                </div>
              </div>

              {/* Export + Deploy */}
              <div className="t-panel" style={{ padding: 12, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 700 }}>Export run</span>
                <button className="t-btn t-btn-sm" onClick={() => handleExport('json')} disabled={exporting !== null}>{exporting === 'json' ? '…' : 'JSON'}</button>
                <button className="t-btn t-btn-sm" onClick={() => handleExport('csv')} disabled={exporting !== null}>{exporting === 'csv' ? '…' : 'CSV'}</button>
                <button className="t-btn t-btn-sm" onClick={() => handleExport('pdf')} disabled={exporting !== null}>{exporting === 'pdf' ? '…' : 'PDF report'}</button>
                <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
                {result?.strategy_id ? (
                  <>
                    <button className="t-btn t-btn-sm t-btn-primary" onClick={handleDeployToPaper} disabled={deploying}>
                      {deploying ? 'Deploying…' : 'Deploy to Paper'}
                    </button>
                    <span style={{ fontSize: 10, color: deployMsg && !deployMsg.includes('Error') ? 'var(--text-green)' : 'var(--text-red)' }}>
                      {deployMsg}
                    </span>
                  </>
                ) : (
                  <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>Deploy-to-paper available for builder (DSL) runs only</span>
                )}
              </div>
            </>
          )}

          {activeTab === 'optimizer' && (
            <div className="t-panel" style={{ padding: 12 }}>
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>Parameter Optimizer</div>
                <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 2 }}>
                  Grid (≤512 combos), walk-forward (train prior folds), Monte Carlo (2000 bootstrap paths) and OFAT ±20% sensitivity on the server.
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 10, flexWrap: 'wrap' }}>
                <div>
                  <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Method</label>
                  <select className="t-select" value={optMethod} onChange={e => setOptMethod(e.target.value)} style={{ width: 140 }}>
                    <option value="grid">Grid search</option>
                    <option value="walk_forward">Walk-forward</option>
                    <option value="monte_carlo">Monte Carlo</option>
                    <option value="sensitivity">Sensitivity (OFAT)</option>
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Optimize metric</label>
                  <select className="t-select" value={optMetric} onChange={e => setOptMetric(e.target.value)} style={{ width: 150 }}>
                    <option value="sharpe_ratio">Sharpe</option>
                    <option value="net_pnl">Net P&L</option>
                    <option value="return_pct">Return %</option>
                    <option value="win_rate">Win rate</option>
                    <option value="profit_factor">Profit factor</option>
                    <option value="sortino_ratio">Sortino</option>
                    <option value="calmar_ratio">Calmar</option>
                    <option value="max_drawdown_pct">Max DD (min)</option>
                  </select>
                </div>
                <div style={{ flex: 1, minWidth: 220 }}>
                  <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Param ranges (one per line: param=v1,v2,…)</label>
                  <textarea className="t-input" value={optParamsText} onChange={e => setOptParamsText(e.target.value)}
                    style={{ minHeight: 46, fontFamily: 'var(--font-mono)', fontSize: 11, resize: 'vertical' }} />
                </div>
                <button className="t-btn t-btn-primary" onClick={handleRunOptimize} disabled={optRunning}>
                  {optRunning ? 'Optimizing…' : 'Optimize'}
                </button>
              </div>
              {optError && <div style={{ color: 'var(--text-red)', fontSize: 11, marginBottom: 8 }}>{optError}</div>}

              {optResult && (
                <>
                  <div style={{ display: 'flex', gap: 14, fontSize: 10, color: 'var(--text-faint)', marginBottom: 8, flexWrap: 'wrap' }}>
                    <span>status: <strong>{optResult.status}</strong></span>
                    <span>method: <strong>{optResult.method}</strong></span>
                    <span>combos: <strong>{optResult.combos_completed}/{optResult.combos_total}</strong></span>
                    {bestCombo && (
                      <span style={{ color: 'var(--text-green)' }}>
                        best: {Object.entries(bestCombo.params).map(([k, v]) => `${k}=${v}`).join(', ')}
                      </span>
                    )}
                  </div>
                  {optResult.error && <div style={{ color: 'var(--text-red)', fontSize: 11, marginBottom: 8 }}>{optResult.error}</div>}
                  {optResult.results.length > 0 && (
                    <div style={{ overflowX: 'auto' }}>
                      <table className="t-table">
                        <thead>
                          <tr>
                            <th>Params</th>
                            <th className="num">Net P&L</th>
                            <th className="num">Return %</th>
                            <th className="num">Win %</th>
                            <th className="num">PF</th>
                            <th className="num">Sharpe</th>
                            <th className="num">Sortino</th>
                            <th className="num">Max DD %</th>
                            <th className="num">Trades</th>
                          </tr>
                        </thead>
                        <tbody>
                          {optResult.results.map((c, idx) => {
                            const isBest = bestCombo === c
                            return (
                              <tr key={idx} style={isBest ? { background: 'color-mix(in srgb, var(--cyan) 4%, transparent)' } : {}}>
                                <td style={{ fontWeight: 700, fontSize: 11 }}>
                                  {Object.entries(c.params).map(([k, v]) => `${k}=${v}`).join(' ')}
                                  {isBest && <span style={{ color: 'var(--cyan)' }}> ✓</span>}
                                </td>
                                <td className={`num ${(c.metrics?.net_pnl ?? 0) >= 0 ? 't-up' : 't-down'}`}>{fmtMoney(c.metrics?.net_pnl)}</td>
                                <td className="num">{fmt(c.metrics?.return_pct)}%</td>
                                <td className="num">{fmt(c.metrics?.win_rate, 1)}%</td>
                                <td className="num">{fmt(c.metrics?.profit_factor)}</td>
                                <td className="num" style={{ color: (c.metrics?.sharpe_ratio ?? 0) >= 1 ? 'var(--text-green)' : 'var(--amber)' }}>{fmt(c.metrics?.sharpe_ratio)}</td>
                                <td className="num">{fmt(c.metrics?.sortino_ratio)}</td>
                                <td className="num t-down">-{fmt(c.metrics?.max_drawdown_pct)}%</td>
                                <td className="num">{Math.round(c.metrics?.total_trades ?? 0)}</td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {activeTab === 'compare' && (
            <div className="t-panel" style={{ padding: 12 }}>
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>Compare Runs</div>
                <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 2 }}>
                  Compare up to 10 saved runs by run ID (comma-separated). The current run is {result.run_id}.
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 8, flexWrap: 'wrap' }}>
                <div style={{ flex: 1, minWidth: 220 }}>
                  <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', display: 'block', marginBottom: 3 }}>Run IDs</label>
                  <input className="t-input" value={compareIdsText} onChange={e => setCompareIdsText(e.target.value)}
                    placeholder={`${result.run_id}, <another run id>`} style={{ width: '100%' }} />
                </div>
                <button className="t-btn t-btn-primary" onClick={handleCompare} disabled={compareRunning}>
                  {compareRunning ? 'Comparing…' : 'Compare'}
                </button>
              </div>
              {compareError && <div style={{ color: 'var(--text-red)', fontSize: 11, marginBottom: 8 }}>{compareError}</div>}

              {comparison && Object.keys(comparison).length > 0 && (
                <div style={{ overflowX: 'auto' }}>
                  <table className="t-table">
                    <thead>
                      <tr>
                        <th>Metric</th>
                        {Object.keys(comparison).map(id => <th key={id} style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 10 }}>{id.slice(0, 8)}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {([
                        ['total_trades', (v: any) => String(Math.round(v))],
                        ['net_pnl', (v: any) => fmtMoney(v)],
                        ['return_pct', (v: any) => `${v >= 0 ? '+' : ''}${fmt(v)}%`],
                        ['win_rate', (v: any) => `${fmt(v, 1)}%`],
                        ['profit_factor', (v: any) => fmt(v)],
                        ['max_drawdown_pct', (v: any) => `-${fmt(v)}%`],
                        ['sharpe_ratio', (v: any) => fmt(v)],
                        ['sortino_ratio', (v: any) => fmt(v)],
                        ['expectancy', (v: any) => fmtMoney(v)],
                        ['alpha', (v: any) => `${v >= 0 ? '+' : ''}${fmt(v)}%`],
                        ['beta', (v: any) => fmt(v)],
                      ] as [string, (v: any) => string][]).map(([key, render]) => (
                        <tr key={key}>
                          <td style={{ fontWeight: 700, fontSize: 11 }}>{key.replace(/_/g, ' ')}</td>
                          {Object.entries(comparison).map(([id, row]) => {
                            const v = (row as Record<string, unknown>)[key] as number
                            const isPnl = key === 'net_pnl'
                            return (
                              <td key={id} className="t-num" style={{
                                color: isPnl ? (v >= 0 ? 'var(--text-green)' : 'var(--text-red)') : 'var(--text)',
                                fontSize: 11,
                              }}>{render(v)}</td>
                            )
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {comparison && Object.keys(comparison).length === 0 && (
                <p style={{ fontSize: 11, color: 'var(--text-faint)', margin: 0 }}>No matching runs found for the given IDs.</p>
              )}
            </div>
          )}

          {activeTab === 'trades' && s.total_trades > 0 && (
            <div className="t-panel" style={{ padding: 0 }}>
              <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>Trade Log ({s.total_trades} trades)</span>
                <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>costs applied</span>
              </div>
              <div style={{ overflowX: 'auto', maxHeight: 480, overflowY: 'auto' }}>
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
                      <th>Entry</th>
                      <th>Exit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result!.trades.map((t, idx) => (
                      <tr key={idx}>
                        <td className="t-faint">{idx + 1}</td>
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

          {activeTab === 'trades' && s.total_trades === 0 && (
            <div className="t-panel" style={{ padding: 24, textAlign: 'center' }}>
              <p style={{ color: 'var(--text-faint)', fontSize: 12, margin: 0 }}>No trades were generated</p>
            </div>
          )}
        </>
      )}

      {!s && !running && !error && (
        <div className="t-panel" style={{ padding: 32, textAlign: 'center' }}>
          <p style={{ color: 'var(--text-faint)', fontSize: 13, margin: '0 0 4px' }}>Configure parameters and run a backtest</p>
          <p style={{ color: 'var(--text-faint)', fontSize: 11, margin: 0 }}>Realistic Indian-market costs · corporate actions · continuous futures · deploy to paper</p>
        </div>
      )}
    </div>
  )
}
