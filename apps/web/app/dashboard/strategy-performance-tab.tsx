'use client'

import { useState } from 'react'
import { useApi } from '@/lib/use-api'

interface StratPerf {
  key: string
  name: string
  tier: string
  category: string
  users_assigned: number
  total_trades: number
  paper_trades: number
  live_trades: number
  win_rate: number
  avg_return: number
  sharpe_ratio: number
  total_pnl: number
  active_runs: number
  paper_runs: number
  live_runs: number
}

interface PerfSummary {
  total_strategies: number
  total_trades: number
  win_rate: number
  avg_return: number
  sharpe_ratio: number
  total_pnl: number
}

interface PerfData {
  strategies: StratPerf[]
  summary: PerfSummary
}

const TIER_COLORS: Record<string, string> = {
  free: 'var(--text-sub)', starter: 'var(--cyan)', pro: 'var(--violet)', enterprise: 'var(--red)',
}

function TierBadge({ tier }: { tier: string }) {
  const c = TIER_COLORS[tier] || 'var(--text-sub)'
  return <span style={{
    padding: '1px 6px', borderRadius: 4, fontSize: 8, fontWeight: 500,
    background: `color-mix(in srgb, ${c} 15%, transparent)`, color: c,
    border: `1px solid color-mix(in srgb, ${c} 20%, transparent)`,
    textTransform: 'capitalize',
  }}>{tier}</span>
}

export function StrategyPerformanceTab() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [sortBy, setSortBy] = useState<'win_rate' | 'total_pnl' | 'total_trades'>('total_pnl')
  const [filterTier, setFilterTier] = useState('')

  const { data, loading } = useApi<PerfData>(`/admin/strategy-performance?_=${refreshKey}`)
  const strategies = data?.strategies || []
  const summary = data?.summary

  const sorted = [...strategies]
    .filter(s => !filterTier || s.tier === filterTier)
    .sort((a, b) => {
      if (sortBy === 'win_rate') return b.win_rate - a.win_rate
      if (sortBy === 'total_trades') return b.total_trades - a.total_trades
      return b.total_pnl - a.total_pnl
    })

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: 2, borderRadius: 4, overflow: 'hidden', border: '1px solid color-mix(in srgb, var(--violet) 15%, transparent)' }}>
          {(['total_pnl', 'win_rate', 'total_trades'] as const).map(s => (
            <button key={s} onClick={() => setSortBy(s)}
              style={{
                padding: '4px 10px', fontSize: 9, fontWeight: 600, border: 'none', cursor: 'pointer',
                background: sortBy === s ? 'var(--violet)' : 'transparent',
                color: sortBy === s ? '#fff' : 'var(--text-sub)',
              }}>{s.replace('_', ' ').toUpperCase()}</button>
          ))}
        </div>
        <select className="t-input" value={filterTier} onChange={e => setFilterTier(e.target.value)}
          style={{ fontSize: 11, maxWidth: 120 }}>
          <option value="">All tiers</option>
          <option value="free">Free</option>
          <option value="starter">Starter</option>
          <option value="pro">Pro</option>
          <option value="enterprise">Enterprise</option>
        </select>
        <span style={{ fontSize: 10, color: 'var(--text-sub)' }}>{sorted.length} strategies</span>
        <button className="t-btn t-btn-sm" onClick={() => setRefreshKey(k => k + 1)} style={{ fontSize: 10 }}>Refresh</button>
      </div>

      {summary && (
        <div className="t-grid-4" style={{ gap: 10, marginBottom: 16 }}>
          <div className="t-panel" style={{ padding: '12px 14px', borderLeft: '3px solid var(--violet)' }}>
            <div className="t-faint" style={{ fontSize: 8, fontWeight: 600 }}>TOTAL P&L</div>
            <div style={{ fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-mono)', color: summary.total_pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
              ₹{Math.abs(summary.total_pnl).toLocaleString()}
            </div>
          </div>
          <div className="t-panel" style={{ padding: '12px 14px', borderLeft: '3px solid var(--green)' }}>
            <div className="t-faint" style={{ fontSize: 8, fontWeight: 600 }}>WIN RATE</div>
            <div style={{ fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{summary.win_rate}%</div>
          </div>
          <div className="t-panel" style={{ padding: '12px 14px', borderLeft: '3px solid var(--cyan)' }}>
            <div className="t-faint" style={{ fontSize: 8, fontWeight: 600 }}>SHARPE RATIO</div>
            <div style={{ fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-mono)', color: summary.sharpe_ratio > 1 ? 'var(--green)' : summary.sharpe_ratio > 0 ? 'var(--amber)' : 'var(--red)' }}>
              {summary.sharpe_ratio}
            </div>
          </div>
          <div className="t-panel" style={{ padding: '12px 14px', borderLeft: '3px solid var(--amber)' }}>
            <div className="t-faint" style={{ fontSize: 8, fontWeight: 600 }}>TOTAL TRADES</div>
            <div style={{ fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{summary.total_trades}</div>
          </div>
        </div>
      )}

      {loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {[1, 2, 3].map(i => <div key={i} className="t-panel" style={{ padding: 16, height: 60 }} />)}
        </div>
      )}

      {!loading && sorted.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No strategy performance data.</p>
        </div>
      )}

      {!loading && sorted.map(s => (
        <div key={s.key} className="t-panel" style={{ padding: '12px 14px', marginBottom: 6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontWeight: 600, fontSize: 12 }}>{s.name}</span>
                <TierBadge tier={s.tier} />
                <span style={{ fontSize: 9, color: 'var(--text-faint)', textTransform: 'capitalize' }}>{s.category}</span>
              </div>
              <div style={{ fontSize: 9, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>{s.key}</div>
            </div>
            <div style={{
              fontSize: 16, fontWeight: 700, fontFamily: 'var(--font-mono)',
              color: s.total_pnl >= 0 ? 'var(--green)' : 'var(--red)',
            }}>
              ₹{Math.abs(s.total_pnl).toLocaleString()}
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8 }}>
            <div>
              <div className="t-faint" style={{ fontSize: 8 }}>Win Rate</div>
              <div style={{
                fontSize: 13, fontWeight: 600, fontFamily: 'var(--font-mono)',
                color: s.win_rate >= 60 ? 'var(--green)' : s.win_rate >= 40 ? 'var(--amber)' : 'var(--red)',
              }}>{s.win_rate}%</div>
              <div style={{ width: '100%', height: 3, background: 'color-mix(in srgb, var(--violet) 10%, transparent)', borderRadius: 2, marginTop: 2 }}>
                <div style={{ width: `${Math.min(s.win_rate, 100)}%`, height: '100%', background: s.win_rate >= 60 ? 'var(--green)' : s.win_rate >= 40 ? 'var(--amber)' : 'var(--red)', borderRadius: 2 }} />
              </div>
            </div>
            <div>
              <div className="t-faint" style={{ fontSize: 8 }}>Avg Return</div>
              <div style={{ fontSize: 13, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                ₹{s.avg_return.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="t-faint" style={{ fontSize: 8 }}>Sharpe</div>
              <div style={{
                fontSize: 13, fontWeight: 600, fontFamily: 'var(--font-mono)',
                color: s.sharpe_ratio > 1 ? 'var(--green)' : s.sharpe_ratio > 0 ? 'var(--amber)' : 'var(--red)',
              }}>{s.sharpe_ratio}</div>
            </div>
            <div>
              <div className="t-faint" style={{ fontSize: 8 }}>Trades</div>
              <div style={{ fontSize: 13, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                {s.total_trades} <span style={{ fontSize: 9, color: 'var(--text-faint)' }}>({s.live_trades} live)</span>
              </div>
            </div>
            <div>
              <div className="t-faint" style={{ fontSize: 8 }}>Users</div>
              <div style={{ fontSize: 13, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                {s.users_assigned}
              </div>
            </div>
            <div>
              <div className="t-faint" style={{ fontSize: 8 }}>Runs</div>
              <div style={{ fontSize: 13, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                {s.active_runs} active / {s.live_runs} live
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
