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
      <div className="page-header">
        <div>
          <h1 className="page-title">Strategy Backtest</h1>
          <p className="page-subtitle">
            Test strategies against historical data
          </p>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 24 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16 }}>
          <div>
            <label style={{ color: '#8888a0', fontSize: 12, display: 'block', marginBottom: 4 }}>Strategy</label>
            <select className="select" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
              {STRATEGIES.map((s) => (
                <option key={s} value={s}>{s.replace('_', ' ').toUpperCase()}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ color: '#8888a0', fontSize: 12, display: 'block', marginBottom: 4 }}>Symbol</label>
            <input className="input" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
          </div>
          <div>
            <label style={{ color: '#8888a0', fontSize: 12, display: 'block', marginBottom: 4 }}>Interval</label>
            <select className="select" value={interval} onChange={(e) => setInterval(e.target.value)}>
              <option value="5m">5 min</option>
              <option value="15m">15 min</option>
              <option value="1h">1 hour</option>
              <option value="1d">Daily</option>
            </select>
          </div>
          <div>
            <label style={{ color: '#8888a0', fontSize: 12, display: 'block', marginBottom: 4 }}>Days</label>
            <input className="input" type="number" value={days} onChange={(e) => setDays(Number(e.target.value))} min={1} max={365} />
          </div>
          <div>
            <label style={{ color: '#8888a0', fontSize: 12, display: 'block', marginBottom: 4 }}>Initial Capital</label>
            <input className="input" type="number" value={capital} onChange={(e) => setCapital(Number(e.target.value))} min={1000} />
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button className="btn btn-primary" onClick={handleRun} disabled={running} style={{ width: '100%' }}>
              {running ? 'Running...' : 'Run Backtest'}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="panel" style={{ borderLeft: '3px solid #ef4444', marginBottom: 24 }}>
          <p style={{ color: '#ef4444', margin: 0 }}>{error}</p>
        </div>
      )}

      {r && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
            <div className="glass-card">
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Total P&L</p>
              <p className="numeric" style={{ fontSize: 22, fontWeight: 600, margin: 0, color: r.total_pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                {r.total_pnl >= 0 ? '+' : ''}{r.total_pnl.toFixed(2)}
              </p>
            </div>
            <div className="glass-card">
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Win Rate</p>
              <p className="numeric neon-cyan" style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>{r.win_rate}%</p>
            </div>
            <div className="glass-card">
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Total Trades</p>
              <p className="numeric" style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>{r.total_trades}</p>
            </div>
            <div className="glass-card">
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Sharpe</p>
              <p className="numeric" style={{ fontSize: 22, fontWeight: 600, margin: 0, color: r.sharpe_ratio >= 1 ? '#22c55e' : '#f59e0b' }}>
                {r.sharpe_ratio.toFixed(2)}
              </p>
            </div>
            <div className="glass-card">
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Max Drawdown</p>
              <p className="numeric negative" style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>-{r.max_drawdown.toFixed(2)}</p>
            </div>
            <div className="glass-card">
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Candles</p>
              <p className="numeric" style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>{result.candles_analyzed.toLocaleString()}</p>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 24 }}>
            <div className="glass-card">
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Avg Win</p>
              <p className="numeric positive" style={{ fontSize: 18, margin: 0 }}>+{r.avg_win.toFixed(2)}</p>
            </div>
            <div className="glass-card">
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Avg Loss</p>
              <p className="numeric negative" style={{ fontSize: 18, margin: 0 }}>-{r.avg_loss.toFixed(2)}</p>
            </div>
            <div className="glass-card">
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Largest Win</p>
              <p className="numeric positive" style={{ fontSize: 18, margin: 0 }}>+{r.largest_win.toFixed(2)}</p>
            </div>
            <div className="glass-card">
              <p style={{ color: '#8888a0', fontSize: 11, textTransform: 'uppercase', margin: '0 0 4px' }}>Largest Loss</p>
              <p className="numeric negative" style={{ fontSize: 18, margin: 0 }}>{r.largest_loss.toFixed(2)}</p>
            </div>
          </div>

          {r.trades.length > 0 && (
            <div className="panel">
              <div className="panel-header">
                <h3 className="panel-title">Trade Log ({r.trades.length} trades)</h3>
              </div>
              <div style={{ overflowX: 'auto', maxHeight: 400, overflowY: 'auto' }}>
                <table className="data-table">
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
                        <td><span className={t.side === 'BUY' ? 'positive' : 'negative'}>{t.side}</span></td>
                        <td className="numeric">{t.entry_price.toFixed(2)}</td>
                        <td className="numeric">{t.exit_price.toFixed(2)}</td>
                        <td className="numeric">{t.quantity}</td>
                        <td className="numeric" style={{ color: t.pnl >= 0 ? '#22c55e' : '#ef4444' }}>
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
