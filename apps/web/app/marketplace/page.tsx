'use client'

import { useState, useMemo } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { useApi } from '@/lib/use-api'
import { useToast } from '@/lib/use-toast'

interface MarketplaceStrategy {
  key: string
  name: string
  description: string
  required_tier: string
  category: string
  user_count: number
  total_trades: number
  total_pnl: number
  win_rate: number
  avg_return: number
}

const CATEGORIES = [
  { id: 'all', label: 'All Strategies', icon: '◆' },
  { id: 'trend', label: 'Trend Following', icon: '↗' },
  { id: 'mean_reversion', label: 'Mean Reversion', icon: '↕' },
  { id: 'options', label: 'Options Strategies', icon: '◈' },
  { id: 'breakout', label: 'Breakout', icon: '▲' },
  { id: 'scalping', label: 'Scalping', icon: '⚡' },
]

export default function MarketplacePage() {
  const [search, setSearch] = useState('')
  const [activeCategory, setActiveCategory] = useState('all')
  const [tierFilter, setTierFilter] = useState('all')
  const [deploying, setDeploying] = useState<string | null>(null)
  const { toast } = useToast()

  const { data, loading, error } = useApi<{ strategies: MarketplaceStrategy[] }>('/strategies/marketplace')

  const strategies = data?.strategies || []

  const filtered = useMemo(() => {
    return strategies.filter(s => {
      const q = search.toLowerCase()
      const matchesSearch = !q || s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q) || s.key.toLowerCase().includes(q)
      const matchesTier = tierFilter === 'all' || s.required_tier === tierFilter
      const matchesCat = activeCategory === 'all' || s.category === activeCategory
      return matchesSearch && matchesTier && matchesCat
    })
  }, [strategies, search, tierFilter, activeCategory])

  const featured = useMemo(() =>
    strategies.filter(s => s.win_rate >= 50 || s.user_count >= 10),
    [strategies],
  )

  const handleDeploy = async (strategy: MarketplaceStrategy) => {
    setDeploying(strategy.key)
    try {
      await api.userStrategies.create({
        name: strategy.name,
        strategy_type: strategy.key,
        config: { symbol: 'NIFTY' },
      })
      toast('success', `${strategy.name} deployed! Configure it in Strategies.`)
    } catch {
      toast('error', `Failed to deploy ${strategy.name}`)
    } finally {
      setDeploying(null)
    }
  }

  const stats = {
    total: strategies.length,
    avgWin: strategies.length ? (strategies.reduce((a, s) => a + s.win_rate, 0) / strategies.length).toFixed(1) : '—',
    profitable: strategies.filter(s => s.total_pnl > 0).length,
    free: strategies.filter(s => s.required_tier === 'free').length,
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Page Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 22, margin: 0, color: 'var(--text)', letterSpacing: '-0.02em' }}>Strategy Marketplace</h1>
          <p style={{ color: 'var(--text-sub)', fontSize: 12, margin: '4px 0 0' }}>
            Institutional strategies — <span style={{ color: 'var(--text)', fontWeight: 600 }}>{stats.total} listed</span> · avg <span style={{ color: 'var(--green)', fontWeight: 600 }}>{stats.avgWin}% win</span> · {stats.profitable} profitable
          </p>
        </div>
        <Link href="/strategies/builder" className="t-btn t-btn-primary" style={{ textDecoration: 'none', height: 34, padding: '0 16px', fontSize: 12 }}>+ Sell Your Strategy</Link>
      </div>

      <div className="t-grid-3" style={{ marginBottom: 4 }}>
        <div className="t-panel" style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: 'rgba(139,92,246,.12)', border: '1px solid rgba(139,92,246,.2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--violet)" strokeWidth="1.7"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Listed</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--text)' }}>{stats.total}</div>
          </div>
        </div>
        <div className="t-panel" style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: 'rgba(52,211,153,.12)', border: '1px solid rgba(52,211,153,.2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--green)" strokeWidth="1.7"><path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/></svg>
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Avg Win Rate</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--green)' }}>{stats.avgWin}%</div>
          </div>
        </div>
        <div className="t-panel" style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: 'rgba(34,211,238,.12)', border: '1px solid rgba(34,211,238,.2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--cyan)" strokeWidth="1.7"><circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 1 0-16 0"/></svg>
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Profitable</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--cyan)' }}>{stats.profitable}/{stats.total}</div>
          </div>
        </div>
      </div>

      {/* Search + Filter */}
      <div style={{
        display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap',
        background: 'var(--panel)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)', padding: '10px 12px',
      }}>
        <div style={{ flex: 1, minWidth: 160 }}>
          <input
            className="t-input"
            placeholder="Search strategies..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <select
          className="t-select"
          value={tierFilter}
          onChange={e => setTierFilter(e.target.value)}
          style={{ maxWidth: 140 }}
        >
          <option value="all">All Tiers</option>
          <option value="free">Free</option>
          <option value="starter">Starter</option>
          <option value="pro">Pro</option>
          <option value="enterprise">Enterprise</option>
        </select>
      </div>

      {/* Category Tabs */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {CATEGORIES.map(cat => (
          <button
            key={cat.id}
            className={`t-chip ${activeCategory === cat.id ? 'active' : ''}`}
            onClick={() => setActiveCategory(cat.id)}
          >
            {cat.icon} {cat.label}
          </button>
        ))}
      </div>

      {loading && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 10 }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="t-panel" style={{ padding: 20, height: 180 }}>
              <div style={{ width: '50%', height: 14, background: 'color-mix(in srgb, var(--text-inverse) 4%, transparent)', borderRadius: 4, marginBottom: 12 }} />
              <div style={{ width: '80%', height: 10, background: 'color-mix(in srgb, var(--text-inverse) 3%, transparent)', borderRadius: 4, marginBottom: 8 }} />
              <div style={{ width: '60%', height: 10, background: 'color-mix(in srgb, var(--text-inverse) 3%, transparent)', borderRadius: 4 }} />
            </div>
          ))}
        </div>
      )}

      {error && (
        <div style={{
          background: 'color-mix(in srgb, var(--red) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--red) 20%, transparent)',
          borderRadius: 'var(--radius-md)', padding: '10px 12px', color: 'var(--text-red)', fontSize: 12,
        }}>
          {error.message}
        </div>
      )}

      {/* Featured Section */}
      {!loading && !error && featured.length > 0 && activeCategory === 'all' && !search && tierFilter === 'all' && (
        <div>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10,
          }}>
            <span style={{ color: 'var(--amber)', fontSize: 16 }}>★</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>Featured Strategies</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 10 }}>
            {featured.map(s => (
              <div key={s.key} style={{
                background: 'linear-gradient(135deg, color-mix(in srgb, var(--amber) 6%, transparent), color-mix(in srgb, var(--violet) 6%, transparent))',
                border: '1px solid color-mix(in srgb, var(--amber) 15%, transparent)',
                borderRadius: 'var(--radius-md)', padding: 14,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>{s.name}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 2 }}>{s.key}</div>
                  </div>
                  <span className="t-badge t-badge-amber" style={{ fontSize: 9 }}>Featured</span>
                </div>
                <p style={{ fontSize: 11, color: 'var(--text-sub)', margin: '0 0 10px', lineHeight: 1.4 }}>
                  {s.description}
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 10 }}>
                  <div>
                    <div style={{ fontSize: 9, color: 'var(--text-faint)' }}>Trades</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{s.total_trades}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 9, color: 'var(--text-faint)' }}>Users</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{s.user_count}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 9, color: 'var(--text-faint)' }}>Win Rate</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-green)' }}>{s.win_rate}%</div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    className="t-btn t-btn-sm t-btn-primary"
                    onClick={() => handleDeploy(s)}
                    disabled={deploying === s.key}
                    style={{ flex: 1 }}
                  >
                    {deploying === s.key ? 'Deploying...' : 'Deploy'}
                  </button>
                  <Link
                    href={`/strategies/${s.key}`}
                    className="t-btn t-btn-sm"
                    style={{ fontSize: 11, textDecoration: 'none' }}
                  >
                    Details
                  </Link>
                  <span className={`t-badge ${s.required_tier === 'free' ? 't-badge-sub' : 't-badge-violet'}`} style={{ fontSize: 9 }}>
                    {s.required_tier}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* All Strategies Grid */}
      {!loading && !error && filtered.length > 0 && (
        <div>
          {(!(featured.length > 0 && activeCategory === 'all' && !search && tierFilter === 'all')) && (
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', marginBottom: 10 }}>
              {filtered.length} {filtered.length === 1 ? 'Strategy' : 'Strategies'}
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 10 }}>
            {filtered.map(s => {
              const catLabel = CATEGORIES.find(c => c.id === s.category)?.label || 'General'
              return (
                <div key={s.key} className="t-panel" style={{
                  padding: 14, display: 'flex', flexDirection: 'column',
                  borderLeft: `3px solid ${
                    s.required_tier === 'free' ? 'var(--cyan)' :
                    s.required_tier === 'starter' ? 'var(--violet)' :
                    s.required_tier === 'pro' ? 'var(--amber)' : 'var(--red)'
                  }`,
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{s.name}</div>
                      <div style={{ fontSize: 9, color: 'var(--text-faint)', marginTop: 1 }}>{catLabel}</div>
                    </div>
                    <span className={`t-badge ${s.required_tier === 'free' ? 't-badge-sub' : 't-badge-violet'}`} style={{ fontSize: 8 }}>
                      {s.required_tier}
                    </span>
                  </div>
                  <p style={{ fontSize: 11, color: 'var(--text-sub)', margin: '0 0 10px', lineHeight: 1.4, flex: 1 }}>
                    {s.description}
                  </p>
                  <div style={{ display: 'flex', gap: 12, marginBottom: 10 }}>
                    <div style={{ fontSize: 10, color: 'var(--text-faint)' }}>
                      {s.user_count} users
                    </div>
                    <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-green)' }}>
                      {s.win_rate}% win
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-faint)' }}>
                      {s.total_trades} trades
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      className="t-btn t-btn-sm t-btn-primary"
                      onClick={() => handleDeploy(s)}
                      disabled={deploying === s.key}
                      style={{ flex: 1 }}
                    >
                      {deploying === s.key ? 'Deploying...' : 'Deploy'}
                    </button>
                    <Link
                      href={`/strategies/${s.key}`}
                      className="t-btn t-btn-sm"
                      style={{ fontSize: 11, textDecoration: 'none' }}
                    >
                      Details
                    </Link>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {!loading && !error && filtered.length === 0 && strategies.length > 0 && (
        <div style={{
          background: 'color-mix(in srgb, var(--cyan) 4%, transparent)', border: '1px solid color-mix(in srgb, var(--cyan) 10%, transparent)',
          borderRadius: 'var(--radius-md)', padding: 24, textAlign: 'center',
        }}>
          <p style={{ color: 'var(--text-sub)', fontSize: 13, margin: '0 0 4px' }}>
            No strategies match your search
          </p>
          <p style={{ color: 'var(--text-faint)', fontSize: 11, margin: 0 }}>
            Try adjusting filters or search terms
          </p>
        </div>
      )}

      {!loading && !error && strategies.length === 0 && (
        <div className="t-panel" style={{ padding: 24, textAlign: 'center' }}>
          <p style={{ color: 'var(--text-faint)', fontSize: 13, margin: 0 }}>
            Marketplace is currently empty. Check back later for new strategies.
          </p>
        </div>
      )}
    </div>
  )
}
