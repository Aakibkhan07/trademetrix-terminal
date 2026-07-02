'use client'

import { useState } from 'react'
import { api } from '@/lib/api'

const STRATEGIES = ['trend_rider', 'orb_pro', 'smc_sniper', 'expiry_hunter']

interface Trade {
  symbol: string; side: string; entry_price: number; exit_price: number
  quantity: number; pnl: number; entry_time: string; exit_time: string
}

interface BacktestResults {
  symbol: string; strategy: string; interval: string; days: number
  initial_capital: number; candles_analyzed: number
  results: {
    total_trades: number; winning_trades: number; losing_trades: number
    win_rate: number; total_pnl: number; max_drawdown: number
    sharpe_ratio: number; avg_win: number; avg_loss: number
    largest_win: number; largest_loss: number
    trades: Trade[]
    equity_curve: { equity: number; timestamp: string }[]
  }
}

export default function BacktestPage() {
  const [strategy, setStrategy] = useState('trend_rider')
  const [symbol, setSymbol] = useState('NIFTY')
  const [interval, setInterval] = useState('15m')
  const [days, setDays] = useState(60)
  const [capital, setCapital] = useState(100000)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<BacktestResults | null>(null)
  const [error, setError] = useState('')

  const handleRun = async () => {
    setRunning(true)
    setError('')
    setResult(null)
    try {
      const data = await api.post('/backtest/run', {
        strategy_type: strategy,
        symbol,
        interval,
        days,
        initial_capital: capital,
        config: {},
      })
      setResult(data as BacktestResults)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Backtest failed')
    } finally {
      setRunning(false)
    }
  }

  const r = result?.results

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-page-title">Strategy Backtest</h1>
        <p className="t-sub" style={{ fontSize: 13 }}>
          Test strategies against historical data
        </p>
      </div>

      <div className="t-panel" style={{ marginBottom: 24 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16 }}>
          <div>
            <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>Strategy</label>
            <select className="t-select" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
              {STRATEGIES.map((s) => (
                <option key={s} value={s}>{s.replace('_', ' ').toUpperCase()}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>Symbol</label>
            <input className="t-input" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
          </div>
          <div>
            <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>Interval</label>
            <select className="t-select" value={interval} onChange={(e) => setInterval(e.target.value)}>
              <option value="5m">5 min</option>
              <option value="15m">15 min</option>
              <option value="1h">1 hour</option>
              <option value="1d">Daily</option>
            </select>
          </div>
          <div>
            <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>Days</label>
            <input className="t-input" type="number" value={days} onChange={(e) => setDays(Number(e.target.value))} min={1} max={365} />
          </div>
          <div>
            <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>Initial Capital</label>
            <input className="t-input" type="number" value={capital} onChange={(e) => setCapital(Number(e.target.value))} min={1000} />
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button className="t-btn-primary" onClick={handleRun} disabled={running} style={{ width: '100%' }}>
              {running ? 'Running...' : 'Run Backtest'}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="t-panel" style={{ borderLeft: '3px solid #ef4444', marginBottom: 24 }}>
          <p style={{ color: '#ef4444', margin: 0 }}>{error}</p>
        </div>
      )}

      {r && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
            <div className="t-panel" style={{ padding: '16px' }}>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Total P&L</p>
              <p className="t-num" style={{ fontSize: 22, fontWeight: 600, margin: 0, color: r.total_pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                {r.total_pnl >= 0 ? '+' : ''}{r.total_pnl.toFixed(2)}
              </p>
            </div>
            <div className="t-panel" style={{ padding: '16px' }}>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Win Rate</p>
              <p className="t-num neon-cyan" style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>{r.win_rate}%</p>
            </div>
            <div className="t-panel" style={{ padding: '16px' }}>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Total Trades</p>
              <p className="t-num" style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>{r.total_trades}</p>
            </div>
            <div className="t-panel" style={{ padding: '16px' }}>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Sharpe</p>
              <p className="t-num" style={{ fontSize: 22, fontWeight: 600, margin: 0, color: r.sharpe_ratio >= 1 ? '#22c55e' : '#f59e0b' }}>
                {r.sharpe_ratio.toFixed(2)}
              </p>
            </div>
            <div className="t-panel" style={{ padding: '16px' }}>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Max Drawdown</p>
              <p className="t-num t-down" style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>-{r.max_drawdown.toFixed(2)}</p>
            </div>
            <div className="t-panel" style={{ padding: '16px' }}>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Candles</p>
              <p className="t-num" style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>{result.candles_analyzed.toLocaleString()}</p>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 24 }}>
            <div className="t-panel" style={{ padding: '16px' }}>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Avg Win</p>
              <p className="t-num t-up" style={{ fontSize: 18, margin: 0 }}>+{r.avg_win.toFixed(2)}</p>
            </div>
            <div className="t-panel" style={{ padding: '16px' }}>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Avg Loss</p>
              <p className="t-num t-down" style={{ fontSize: 18, margin: 0 }}>-{r.avg_loss.toFixed(2)}</p>
            </div>
            <div className="t-panel" style={{ padding: '16px' }}>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Largest Win</p>
              <p className="t-num t-up" style={{ fontSize: 18, margin: 0 }}>+{r.largest_win.toFixed(2)}</p>
            </div>
            <div className="t-panel" style={{ padding: '16px' }}>
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Largest Loss</p>
              <p className="t-num t-down" style={{ fontSize: 18, margin: 0 }}>{r.largest_loss.toFixed(2)}</p>
            </div>
          </div>

          {r.equity_curve?.length > 1 && (
            <div className="t-panel" style={{ padding: '12px 14px', marginBottom: 16 }}>
              <h3 style={{ margin: '0 0 8px', fontSize: 11, fontWeight: 600, letterSpacing: '0.03em' }}>Equity Curve</h3>
              <svg viewBox="0 0 600 160" style={{ width: '100%', height: 'auto' }}>
                {(() => {
                  const pts = r.equity_curve; const vals = pts.map(p => p.equity)
                  const min = Math.min(...vals); const max = Math.max(...vals); const range = max - min || 1
                  const pad = { top: 16, right: 16, bottom: 24, left: 52 }; const cw = 600 - pad.left - pad.right; const ch = 160 - pad.top - pad.bottom
                  const x = (i: number) => pad.left + (i / (vals.length - 1)) * cw
                  const y = (v: number) => pad.top + ch - ((v - min) / range) * ch
                  const up = vals[vals.length - 1] >= vals[0]; const color = up ? '#22c55e' : '#ef4444'
                  const line = vals.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(v)}`).join('')
                  return (
                    <>
                      <defs><linearGradient id="be"><stop offset="0%" stopColor={color} stopOpacity="0.15" /><stop offset="100%" stopColor={color} stopOpacity="0.02" /></linearGradient></defs>
                      {Array.from({ length: 5 }).map((_, i) => {
                        const yy = pad.top + (i / 5) * ch
                        return (<g key={i}>
                          <line x1={pad.left} y1={yy} x2={600 - pad.right} y2={yy} stroke="rgba(139,92,246,0.06)" strokeWidth={1} />
                          <text x={pad.left - 6} y={yy + 3} textAnchor="end" fill="var(--text-faint)" fontSize={8} fontFamily="var(--font-mono)">{(min + (range / 5) * (5 - i)).toFixed(0)}</text>
                        </g>)
                      })}
                      <path d={`${line}L${x(vals.length - 1)},${pad.top + ch}L${x(0)},${pad.top + ch}Z`} fill="url(#be)" />
                      <path d={line} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
                    </>
                  )
                })()}
              </svg>
            </div>
          )}

          {r.trades.length > 0 && (
            <div className="t-panel">
              <div className="t-panel-header">
                <h3 className="t-panel-title">Trade Log ({r.trades.length} trades)</h3>
              </div>
              <div style={{ overflowX: 'auto', maxHeight: 400, overflowY: 'auto' }}>
                <table className="t-table">
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Side</th>
                      <th>Entry</th>
                      <th>Exit</th>
                      <th>Qty</th>
                      <th>P&L</th>
                      <th>Entry Time</th>
                      <th>Exit Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.trades.map((t, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 600 }}>{t.symbol}</td>
                        <td><span className={t.side === 'BUY' ? 't-up' : 't-down'}>{t.side}</span></td>
                        <td className="t-num">{t.entry_price.toFixed(2)}</td>
                        <td className="t-num">{t.exit_price.toFixed(2)}</td>
                        <td className="t-num">{t.quantity}</td>
                        <td className="t-num" style={{ color: t.pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                          {t.pnl >= 0 ? '+' : ''}{t.pnl.toFixed(2)}
                        </td>
                        <td style={{ fontSize: 12, color: '#555570' }}>{new Date(t.entry_time).toLocaleString()}</td>
                        <td style={{ fontSize: 12, color: '#555570' }}>{new Date(t.exit_time).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
