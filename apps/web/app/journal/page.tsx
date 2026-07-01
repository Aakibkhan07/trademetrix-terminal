'use client'

import { useEffect, useState } from 'react'
import { useApi } from '@/lib/use-api'
import { api } from '@/lib/api'

function downloadCSV(rows: string[][], filename: string) {
  const csv = rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

interface Trade {
  id: string
  symbol: string
  side: 'BUY' | 'SELL'
  quantity: number
  price: number
  pnl: number
  status: string
  timestamp: string
  strategy: string
}

interface JournalEntry {
  date: string
  pnl: number
  trades_count: number
  win_rate: number
}

interface JournalData {
  entries: JournalEntry[]
  total_pnl: number
  win_rate: number
  sharpe_ratio: number
  max_drawdown: number
  total_trades: number
  avg_win: number
  avg_loss: number
  largest_win: number
  largest_loss: number
  monthly_returns: { month: string; return_pct: number }[]
  equity_curve: number[]
}

function fmt(n: number) {
  return n.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

function SvgEquityCurve({ points, height = 160 }: { points: number[]; height?: number }) {
  if (!points || points.length < 2) {
    return (
      <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span className="t-faint" style={{ fontSize: 12 }}>No equity data available</span>
      </div>
    )
  }
  const w = 800
  const h = height
  const min = Math.min(...points)
  const max = Math.max(...points)
  const range = max - min || 1
  const pad = 16
  const chartW = w - pad * 2
  const chartH = h - pad * 2

  const xScale = (i: number) => pad + (i / Math.max(points.length - 1, 1)) * chartW
  const yScale = (v: number) => pad + chartH - ((v - min) / range) * chartH

  const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${xScale(i)},${yScale(p)}`).join(' ')

  const isUp = points[points.length - 1] >= points[0]
  const color = isUp ? 'var(--green)' : 'var(--red)'

  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', height }} preserveAspectRatio="none">
      <defs>
        <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.2" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${d} L${xScale(points.length - 1)},${pad + chartH} L${xScale(0)},${pad + chartH} Z`}
        fill="url(#eqGrad)" />
      <path d={d} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function MonthlyBars({ data }: { data: { month: string; return_pct: number }[] }) {
  if (!data || !data.length) {
    return (
      <div style={{ height: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span className="t-faint" style={{ fontSize: 12 }}>No monthly data</span>
      </div>
    )
  }
  const maxAbs = Math.max(...data.map(d => Math.abs(d.return_pct)), 1)

  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'flex-end', height: 100, padding: '8px 0' }}>
      {data.map(d => {
        const h = (Math.abs(d.return_pct) / maxAbs) * 80
        const isPos = d.return_pct >= 0
        return (
          <div key={d.month} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
            <span style={{ fontSize: 8, color: isPos ? 'var(--text-green)' : 'var(--text-red)' }}>
              {d.return_pct.toFixed(1)}%
            </span>
            <div style={{
              width: '100%', height: Math.max(h, 4), borderRadius: '3px 3px 0 0',
              background: isPos ? 'var(--green)' : 'var(--red)',
              opacity: 0.8,
            }} />
            <span className="t-faint" style={{ fontSize: 7, writingMode: 'vertical-lr', textOrientation: 'mixed' }}>
              {d.month}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export default function JournalPage() {
  const { data: journalData, loading, error } = useApi<JournalData>('/ai/journal?lookback_days=30')

  const [trades, setTrades] = useState<Trade[]>([])
  const [tradesLoading, setTradesLoading] = useState(true)
  const [tradesError, setTradesError] = useState('')
  const [sideFilter, setSideFilter] = useState<'ALL' | 'BUY' | 'SELL'>('ALL')
  const [searchFilter, setSearchFilter] = useState('')

  useEffect(() => {
    api.ai.journalEntries().then((d: unknown) => {
      const data = d as { entries: Trade[] } | Trade[]
      setTrades(Array.isArray(data) ? data : (data as { entries: Trade[] }).entries || [])
    }).catch((e) => {
      setTradesError(e?.message || 'Failed to load trades')
    }).finally(() => setTradesLoading(false))
  }, [])

  const hasData = journalData && (journalData.total_trades > 0 || journalData.entries?.length > 0)

  const filteredTrades = trades.filter(t => {
    if (sideFilter !== 'ALL' && t.side !== sideFilter) return false
    if (searchFilter && !t.symbol.toLowerCase().includes(searchFilter.toLowerCase())) return false
    return true
  })

  const totalPnl = filteredTrades.reduce((sum, t) => sum + (t.pnl || 0), 0)
  const winTrades = filteredTrades.filter(t => (t.pnl || 0) > 0)
  const lossTrades = filteredTrades.filter(t => (t.pnl || 0) < 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="t-page-header">
        <div>
          <h1 className="t-page-title">Trade Journal</h1>
          <p className="t-page-subtitle">Performance analytics & trade history</p>
        </div>
      </div>

      {loading && (
        <div className="t-panel" style={{ padding: 20, textAlign: 'center' }}>
          <span className="t-faint">Loading analytics...</span>
        </div>
      )}

      {error && !loading && (
        <div className="t-panel" style={{ padding: 20, borderLeft: '3px solid var(--red)' }}>
          <span className="t-down">{error?.message || 'Failed to load journal data'}</span>
        </div>
      )}

      {!hasData && !loading && !error && (
        <div className="t-panel" style={{ padding: 24, textAlign: 'center' }}>
          <div style={{ fontSize: 24, marginBottom: 8 }}>T</div>
          <h3 style={{ fontSize: 16, marginBottom: 4 }}>No trading data yet</h3>
          <p className="t-faint" style={{ fontSize: 12, margin: 0 }}>
            Start trading to see your performance analytics here.
          </p>
        </div>
      )}

      {hasData && (
        <>
          {/* KPI Cards */}
          <div className="t-grid-4">
            <div className="t-panel" style={{ padding: '12px 16px' }}>
              <span className="t-stat-label">Total P&amp;L</span>
              <p className="t-stat-value" style={{ color: journalData!.total_pnl >= 0 ? 'var(--text-green)' : 'var(--text-red)' }}>
                {journalData!.total_pnl >= 0 ? '+' : ''}\u20B9{fmt(journalData!.total_pnl)}
              </p>
            </div>
            <div className="t-panel" style={{ padding: '12px 16px' }}>
              <span className="t-stat-label">Win Rate</span>
              <p className="t-stat-value">{journalData!.win_rate.toFixed(1)}%</p>
            </div>
            <div className="t-panel" style={{ padding: '12px 16px' }}>
              <span className="t-stat-label">Sharpe Ratio</span>
              <p className="t-stat-value" style={{
                color: journalData!.sharpe_ratio >= 1.5 ? 'var(--text-green)' :
                       journalData!.sharpe_ratio >= 0 ? 'var(--amber)' : 'var(--text-red)'
              }}>
                {journalData!.sharpe_ratio.toFixed(2)}
              </p>
            </div>
            <div className="t-panel" style={{ padding: '12px 16px' }}>
              <span className="t-stat-label">Max Drawdown</span>
              <p className="t-stat-value" style={{ color: 'var(--text-red)' }}>
                {journalData!.max_drawdown.toFixed(1)}%
              </p>
            </div>
          </div>

          <div className="t-grid-4">
            <div className="t-panel" style={{ padding: '12px 16px' }}>
              <span className="t-stat-label">Total Trades</span>
              <p className="t-stat-value">{journalData!.total_trades}</p>
            </div>
            <div className="t-panel" style={{ padding: '12px 16px' }}>
              <span className="t-stat-label">Avg Win</span>
              <p className="t-stat-value t-up">\u20B9{fmt(journalData!.avg_win)}</p>
            </div>
            <div className="t-panel" style={{ padding: '12px 16px' }}>
              <span className="t-stat-label">Avg Loss</span>
              <p className="t-stat-value t-down">\u20B9{fmt(Math.abs(journalData!.avg_loss))}</p>
            </div>
            <div className="t-panel" style={{ padding: '12px 16px' }}>
              <span className="t-stat-label">Best / Worst</span>
              <p className="t-stat-value" style={{ fontSize: 13 }}>
                <span className="t-up">\u20B9{fmt(journalData!.largest_win)}</span>
                <span className="t-faint" style={{ margin: '0 4px' }}>/</span>
                <span className="t-down">\u20B9{fmt(Math.abs(journalData!.largest_loss))}</span>
              </p>
            </div>
          </div>

          {/* Equity Curve */}
          <div className="t-panel" style={{ padding: 0 }}>
            <div className="t-panel-header">
              <h3 className="t-panel-title">Equity Curve</h3>
            </div>
            <div className="t-panel-body">
              <SvgEquityCurve points={journalData!.equity_curve || []} height={180} />
            </div>
          </div>

          {/* Monthly Returns */}
          <div className="t-panel" style={{ padding: 0 }}>
            <div className="t-panel-header">
              <h3 className="t-panel-title">Monthly Returns</h3>
              <span className="t-faint">{journalData!.monthly_returns?.length || 0} months</span>
            </div>
            <div className="t-panel-body">
              <MonthlyBars data={journalData!.monthly_returns || []} />
            </div>
          </div>
        </>
      )}

      {/* Trade Details */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Trade History</h3>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {filteredTrades.length > 0 && (
              <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => {
                const header = ['Symbol', 'Side', 'Qty', 'Price', 'P&L', 'Strategy', 'Time']
                const data = filteredTrades.map(t => [t.symbol, t.side, String(t.quantity), String(t.price), String(t.pnl || 0), t.strategy || '', t.timestamp])
                downloadCSV([header, ...data], `trades-${new Date().toISOString().slice(0, 10)}.csv`)
              }}>
                Export CSV
              </button>
            )}
            <input className="t-input" placeholder="Filter symbol..."
              value={searchFilter} onChange={e => setSearchFilter(e.target.value)}
              style={{ width: 140, height: 24, fontSize: 11, padding: '2px 8px' }} />
            <select className="t-select" value={sideFilter}
              onChange={e => setSideFilter(e.target.value as 'ALL' | 'BUY' | 'SELL')}
              style={{ width: 80, height: 24, fontSize: 11, padding: '2px 8px' }}>
              <option value="ALL">All</option>
              <option value="BUY">Buy</option>
              <option value="SELL">Sell</option>
            </select>
            <span className="t-faint" style={{ fontSize: 11 }}>{filteredTrades.length} trades</span>
          </div>
        </div>
        {tradesLoading ? (
          <div className="t-panel-body">
            <span className="t-faint">Loading trades...</span>
          </div>
        ) : tradesError ? (
          <div className="t-panel-body">
            <span className="t-down">{tradesError}</span>
          </div>
        ) : filteredTrades.length > 0 ? (
          <div className="t-table-wrap">
            <table className="t-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Qty</th>
                  <th>Price</th>
                  <th>P&amp;L</th>
                  <th>Strategy</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {filteredTrades.map(t => (
                  <tr key={t.id}>
                    <td style={{ fontWeight: 600 }}>{t.symbol}</td>
                    <td className={t.side === 'BUY' ? 't-up' : 't-down'}>{t.side}</td>
                    <td className="t-num">{t.quantity}</td>
                    <td className="t-num">\u20B9{fmt(t.price)}</td>
                    <td className={`t-num ${(t.pnl || 0) >= 0 ? 't-up' : 't-down'}`}>
                      {(t.pnl || 0) >= 0 ? '+' : ''}\u20B9{fmt(t.pnl || 0)}
                    </td>
                    <td className="t-faint">{t.strategy || '-'}</td>
                    <td className="t-faint">
                      {t.timestamp ? new Date(t.timestamp).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="t-panel-body">
            <span className="t-faint">No trades found.</span>
          </div>
        )}
      </div>

      {/* Win/Loss Breakdown */}
      {filteredTrades.length > 0 && (
        <div className="t-row" style={{ gap: 16 }}>
          <div className="t-panel" style={{ flex: 1, padding: '12px 16px' }}>
            <h3 className="t-panel-title" style={{ marginBottom: 8 }}>Win/Loss Breakdown</h3>
            <div style={{ display: 'flex', gap: 16 }}>
              <div style={{ flex: 1, textAlign: 'center' }}>
                <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-green)' }}>{winTrades.length}</div>
                <div className="t-faint" style={{ fontSize: 10 }}>Wins</div>
              </div>
              <div style={{ flex: 1, textAlign: 'center' }}>
                <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-red)' }}>{lossTrades.length}</div>
                <div className="t-faint" style={{ fontSize: 10 }}>Losses</div>
              </div>
              <div style={{ flex: 1, textAlign: 'center' }}>
                <div style={{ fontSize: 24, fontWeight: 700 }}>{filteredTrades.length}</div>
                <div className="t-faint" style={{ fontSize: 10 }}>Total</div>
              </div>
            </div>
            <div style={{
              marginTop: 8, height: 8, borderRadius: 4, overflow: 'hidden',
              background: 'rgba(255,23,68,0.15)', display: 'flex',
            }}>
              <div style={{
                width: `${(winTrades.length / Math.max(filteredTrades.length, 1)) * 100}%`,
                background: 'var(--green)', height: '100%', borderRadius: 4,
              }} />
            </div>
          </div>
          <div className="t-panel" style={{ flex: 1, padding: '12px 16px' }}>
            <h3 className="t-panel-title" style={{ marginBottom: 8 }}>P&amp;L Summary</h3>
            <div className="t-grid-2" style={{ gap: 8 }}>
              <div>
                <div className="t-faint" style={{ fontSize: 10 }}>Gross Profit</div>
                <div className="t-up" style={{ fontSize: 16, fontWeight: 700 }}>
                  \u20B9{fmt(winTrades.reduce((s, t) => s + (t.pnl || 0), 0))}
                </div>
              </div>
              <div>
                <div className="t-faint" style={{ fontSize: 10 }}>Gross Loss</div>
                <div className="t-down" style={{ fontSize: 16, fontWeight: 700 }}>
                  -\u20B9{fmt(Math.abs(lossTrades.reduce((s, t) => s + (t.pnl || 0), 0)))}
                </div>
              </div>
            </div>
            <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border)' }}>
              <div className="t-faint" style={{ fontSize: 10 }}>Net P&amp;L</div>
              <div style={{
                fontSize: 18, fontWeight: 700,
                color: totalPnl >= 0 ? 'var(--text-green)' : 'var(--text-red)',
              }}>
                {totalPnl >= 0 ? '+' : ''}\u20B9{fmt(totalPnl)}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
