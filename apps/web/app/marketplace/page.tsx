'use client'

import { useState, useMemo } from 'react'
import { api } from '@/lib/api'
import { useApi } from '@/lib/use-api'
import { useToast } from '@/lib/use-toast'

interface StrategyInfo {
  key: string
  name: string
  description: string
  required_tier: string
}

const CATEGORIES = [
  { id: 'all', label: 'All Strategies', icon: '◆' },
  { id: 'trend', label: 'Trend Following', icon: '↗' },
  { id: 'mean_reversion', label: 'Mean Reversion', icon: '↕' },
  { id: 'options', label: 'Options Strategies', icon: '◈' },
  { id: 'breakout', label: 'Breakout', icon: '▲' },
  { id: 'scalping', label: 'Scalping', icon: '⚡' },
]

const MOCK_METRICS: Record<string, { rating: number; users: number; avg_return: string; sharpe: number }> = {
  trend_rider: { rating: 4.5, users: 128, avg_return: '+18.2%', sharpe: 1.8 },
  orb_pro: { rating: 4.8, users: 94, avg_return: '+22.1%', sharpe: 2.1 },
  smc_sniper: { rating: 4.3, users: 76, avg_return: '+15.7%', sharpe: 1.5 },
  expiry_hunter: { rating: 4.6, users: 112, avg_return: '+12.4%', sharpe: 1.3 },
  rsi_mean_reversion: { rating: 4.1, users: 65, avg_return: '+9.8%', sharpe: 1.1 },
  bollinger_bandit: { rating: 4.4, users: 83, avg_return: '+14.5%', sharpe: 1.6 },
  macd_cross: { rating: 4.2, users: 71, avg_return: '+11.2%', sharpe: 1.4 },
  vwap_band: { rating: 4.7, users: 58, avg_return: '+16.9%', sharpe: 1.9 },
}

const MOCK_CATEGORY: Record<string, string> = {
  trend_rider: 'trend',
  orb_pro: 'breakout',
  smc_sniper: 'trend',
  expiry_hunter: 'options',
  rsi_mean_reversion: 'mean_reversion',
  bollinger_bandit: 'mean_reversion',
  macd_cross: 'trend',
  vwap_band: 'scalping',
}

function StarRating({ rating }: { rating: number }) {
  return (
    <span style={{ color: '#f59e0b', fontSize: 11, letterSpacing: 1 }}>
      {'★'.repeat(Math.floor(rating))}{rating % 1 >= 0.5 ? '★' : ''}
      {'☆'.repeat(5 - Math.ceil(rating))}
      <span style={{ color: 'var(--text-sub)', marginLeft: 4, fontSize: 10 }}>{rating.toFixed(1)}</span>
    </span>
  )
}

export default function MarketplacePage() {
  const [search, setSearch] = useState('')
  const [activeCategory, setActiveCategory] = useState('all')
  const [tierFilter, setTierFilter] = useState('all')
  const [deploying, setDeploying] = useState<string | null>(null)
  const { toast } = useToast()

  const { data, loading, error } = useApi<{ strategies: StrategyInfo[] }>('/strategies/list-builtin')

  const strategies = data?.strategies || []

  const filtered = useMemo(() => {
    return strategies.filter(s => {
      const q = search.toLowerCase()
      const matchesSearch = !q || s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q) || s.key.toLowerCase().includes(q)
      const matchesTier = tierFilter === 'all' || s.required_tier === tierFilter
      const matchesCat = activeCategory === 'all' || (MOCK_CATEGORY[s.key] || 'trend') === activeCategory
      return matchesSearch && matchesTier && matchesCat
    })
  }, [strategies, search, tierFilter, activeCategory])

  const featured = useMemo(() =>
    strategies.filter(s => (MOCK_METRICS[s.key]?.rating || 0) >= 4.5),
    [strategies],
  )

  const handleDeploy = async (strategy: StrategyInfo) => {
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Page Header */}
      <div>
        <h1 style={{ fontFamily: "'Inter', sans-serif", fontWeight: 700, fontSize: 18, margin: 0, color: 'var(--text)' }}>
          Strategy Marketplace
        </h1>
        <p style={{ color: 'var(--text-sub)', fontSize: 12, margin: '2px 0 0' }}>
          Discover, compare, and deploy trading strategies
        </p>
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
              <div style={{ width: '50%', height: 14, background: 'rgba(255,255,255,0.04)', borderRadius: 4, marginBottom: 12 }} />
              <div style={{ width: '80%', height: 10, background: 'rgba(255,255,255,0.03)', borderRadius: 4, marginBottom: 8 }} />
              <div style={{ width: '60%', height: 10, background: 'rgba(255,255,255,0.03)', borderRadius: 4 }} />
            </div>
          ))}
        </div>
      )}

      {error && (
        <div style={{
          background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
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
            <span style={{ color: '#f59e0b', fontSize: 16 }}>★</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>Featured Strategies</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 10 }}>
            {featured.map(s => {
              const m = MOCK_METRICS[s.key]
              return (
                <div key={s.key} style={{
                  background: 'linear-gradient(135deg, rgba(245,158,11,0.06), rgba(124,92,252,0.06))',
                  border: '1px solid rgba(245,158,11,0.15)',
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
                  {m && (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 10 }}>
                      <div>
                        <div style={{ fontSize: 9, color: 'var(--text-faint)' }}>Rating</div>
                        <StarRating rating={m.rating} />
                      </div>
                      <div>
                        <div style={{ fontSize: 9, color: 'var(--text-faint)' }}>Users</div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{m.users}</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 9, color: 'var(--text-faint)' }}>Avg Return</div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-green)' }}>{m.avg_return}</div>
                      </div>
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      className="t-btn t-btn-sm t-btn-primary"
                      onClick={() => handleDeploy(s)}
                      disabled={deploying === s.key}
                      style={{ flex: 1 }}
                    >
                      {deploying === s.key ? 'Deploying...' : 'Deploy'}
                    </button>
                    <span className={`t-badge ${s.required_tier === 'free' ? 't-badge-sub' : 't-badge-violet'}`} style={{ fontSize: 9 }}>
                      {s.required_tier}
                    </span>
                  </div>
                </div>
              )
            })}
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
              const m = MOCK_METRICS[s.key]
              const cat = MOCK_CATEGORY[s.key] || 'trend'
              const catLabel = CATEGORIES.find(c => c.id === cat)?.label || 'General'
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
                  {m && (
                    <div style={{ display: 'flex', gap: 12, marginBottom: 10 }}>
                      <div style={{ fontSize: 10 }}>
                        <StarRating rating={m.rating} />
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--text-faint)' }}>
                        {m.users} users
                      </div>
                      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-green)' }}>
                        {m.avg_return}
                      </div>
                    </div>
                  )}
                  <button
                    className="t-btn t-btn-sm t-btn-primary"
                    onClick={() => handleDeploy(s)}
                    disabled={deploying === s.key}
                  >
                    {deploying === s.key ? 'Deploying...' : 'Deploy Strategy'}
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {!loading && !error && filtered.length === 0 && strategies.length > 0 && (
        <div style={{
          background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.1)',
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
