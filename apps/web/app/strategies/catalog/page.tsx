'use client'

import React, { useState, useMemo } from 'react'
import { useApi } from '@/lib/use-api'
import { SkeletonBar } from '@/components/ui/skeleton'
import { TierPill } from '@/components/ui/badge'

interface StrategyInfo {
  key: string
  name: string
  description: string
  required_tier: string
}

interface ListBuiltinResponse {
  strategies: StrategyInfo[]
}

const TIERS = ['free', 'starter', 'pro', 'enterprise'] as const

function TierBadge({ tier }: { tier: string }) {
  return <TierPill tier={tier} freeText="var(--text-faint)" />
}

function SkeletonCard() {
  return (
    <div className="t-panel" style={{ padding: 20, height: 140 }}>
      <SkeletonBar w="60%" h={14} background="color-mix(in srgb, var(--violet) 10%, transparent)" style={{ marginBottom: 12 }} />
      <SkeletonBar w="90%" h={10} background="color-mix(in srgb, var(--violet) 6%, transparent)" style={{ marginBottom: 8 }} />
      <SkeletonBar w="75%" h={10} background="color-mix(in srgb, var(--violet) 6%, transparent)" />
      <SkeletonBar w="60px" h={20} background="color-mix(in srgb, var(--violet) 8%, transparent)" style={{ marginTop: 16 }} />
    </div>
  )
}

export default function StrategyCatalogPage() {
  const [search, setSearch] = useState('')
  const [tierFilter, setTierFilter] = useState('all')
  const [showCompare, setShowCompare] = useState(false)

  const { data, loading, error } = useApi<ListBuiltinResponse>('/strategies/list-builtin')

  const strategies = data?.strategies || []

  const filtered = useMemo(() =>
    strategies.filter((s) => {
      const q = search.toLowerCase()
      const matchesSearch = !q || s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q)
      const matchesTier = tierFilter === 'all' || s.required_tier === tierFilter
      return matchesSearch && matchesTier
    }),
    [strategies, search, tierFilter],
  )

  const tiers = ['free', 'starter', 'pro', 'enterprise']
  const groupedByTier: Record<string, StrategyInfo[]> = {}
  tiers.forEach(t => { groupedByTier[t] = strategies.filter(s => s.required_tier === t) })

  const tierColor = (t: string) => t === 'free' ? 'var(--text-sub)' : t === 'starter' ? 'var(--cyan)' : t === 'pro' ? 'var(--violet)' : 'var(--red)'
  const tierButton = (t: string) => t === 'free' ? 'Free' : t === 'starter' ? 'Get Starter' : t === 'pro' ? 'Go Pro' : 'Enterprise'

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-page-title">Strategy Catalog</h1>
        <p className="t-sub" style={{ fontSize: 13 }}>
          Browse all available built-in trading strategies
        </p>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
        <input
          className="t-input"
          placeholder="Search strategies..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ maxWidth: 300 }}
        />
        <select
          className="t-select"
          value={tierFilter}
          onChange={(e) => setTierFilter(e.target.value)}
          style={{ maxWidth: 160 }}
        >
          <option value="all">All Tiers</option>
          {TIERS.map((t) => (
            <option key={t} value={t}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </option>
          ))}
        </select>
        <button className="t-btn t-btn-sm" onClick={() => setShowCompare(!showCompare)}
          style={{ fontSize: 10, marginLeft: 'auto', background: showCompare ? 'var(--violet)' : 'color-mix(in srgb, var(--violet) 10%, transparent)', color: showCompare ? '#fff' : 'var(--text)', border: '1px solid color-mix(in srgb, var(--violet) 20%, transparent)' }}>
          {showCompare ? 'Hide Comparison' : 'Compare All Strategies'}
        </button>
      </div>

      {!loading && !error && strategies.length > 0 && showCompare && (
        <div className="t-panel" style={{ padding: 14, marginBottom: 20 }}>
          <h3 style={{ margin: '0 0 8px', fontSize: 12, fontWeight: 600 }}>Side-by-Side Comparison</h3>
          <p className="t-faint" style={{ fontSize: 10, marginBottom: 10 }}>
            Compare all strategies by tier to find what works best for your trading style. Upgrade your plan to unlock higher-tier strategies.
          </p>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: '6px 8px', borderBottom: '2px solid color-mix(in srgb, var(--violet) 20%, transparent)', fontWeight: 600, fontSize: 9 }}>Strategy</th>
                  <th style={{ textAlign: 'center', padding: '6px 8px', borderBottom: '2px solid color-mix(in srgb, var(--violet) 20%, transparent)', fontWeight: 600, fontSize: 9 }}>Tier</th>
                  <th style={{ textAlign: 'left', padding: '6px 8px', borderBottom: '2px solid color-mix(in srgb, var(--violet) 20%, transparent)', fontWeight: 600, fontSize: 9 }}>Description</th>
                  <th style={{ textAlign: 'center', padding: '6px 8px', borderBottom: '2px solid color-mix(in srgb, var(--violet) 20%, transparent)', fontWeight: 600, fontSize: 9 }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {tiers.map(tier => {
                  const strats = groupedByTier[tier] || []
                  if (strats.length === 0) return null
                  return (
                    <React.Fragment key={tier}>
                      <tr>
                        <td colSpan={4} style={{
                          padding: '4px 8px', fontWeight: 700, fontSize: 9,
                          textTransform: 'uppercase', letterSpacing: '0.06em',
                          color: tierColor(tier),
                          borderBottom: `1px solid color-mix(in srgb, ${tierColor(tier)} 15%, transparent)`,
                          background: `color-mix(in srgb, ${tierColor(tier)} 4%, transparent)`,
                        }}>
                          {tier.toUpperCase()} TIER — {strats.length} {strats.length === 1 ? 'strategy' : 'strategies'}
                        </td>
                      </tr>
                      {strats.map(s => (
                        <tr key={s.key} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                          <td style={{ padding: '5px 8px', fontWeight: 600 }}>{s.name}</td>
                          <td style={{ padding: '5px 8px', textAlign: 'center' }}>
                            <TierBadge tier={s.required_tier} />
                          </td>
                          <td style={{ padding: '5px 8px', color: 'var(--text-sub)', fontSize: 9 }}>{s.description}</td>
                          <td style={{ padding: '5px 8px', textAlign: 'center' }}>
                            <a href={`/pricing?ref=${s.required_tier}`}
                              style={{
                                display: 'inline-block', padding: '3px 12px', borderRadius: 4,
                                fontSize: 9, fontWeight: 600, textDecoration: 'none',
                                background: s.required_tier === 'free' ? 'color-mix(in srgb, var(--green) 15%, transparent)' : 'var(--gradient-primary)',
                                color: s.required_tier === 'free' ? 'var(--green)' : '#fff',
                              }}>
                              {tierButton(s.required_tier)}
                            </a>
                          </td>
                        </tr>
                      ))}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {error && (
        <div style={{ padding: '12px 16px', background: 'color-mix(in srgb, var(--red) 10%, transparent)', border: '1px solid color-mix(in srgb, var(--red) 20%, transparent)', borderRadius: 8, color: 'var(--red)', fontSize: 13, marginBottom: 16 }}>
          {error.message}
        </div>
      )}

      {loading && (
        <div className="t-grid-auto">
          {Array.from({ length: 8 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}

      {!loading && !error && filtered.length === 0 && (
        <div style={{
          background: 'color-mix(in srgb, var(--cyan) 6%, transparent)', border: '1px solid color-mix(in srgb, var(--cyan) 12%, transparent)',
          borderRadius: 10, padding: '12px 16px', marginBottom: 20,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div>
            <p style={{ margin: 0, fontSize: 13, color: '#22d3ee', fontWeight: 500 }}>
              {search || tierFilter !== 'all' ? 'No matching strategies' : 'No strategies available'}
            </p>
            <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--text-faint)' }}>
              {search || tierFilter !== 'all'
                ? 'Try adjusting your search or filter.'
                : 'The strategy catalog is currently empty.'}
            </p>
          </div>
        </div>
      )}

      {!loading && !error && filtered.length > 0 && (
        <div className="t-grid-auto">
          {filtered.map((s) => (
            <div key={s.key} className="t-panel" style={{
              padding: 20, display: 'flex', flexDirection: 'column',
            }}>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12,
              }}>
                <h3 style={{ fontFamily: 'var(--font-body)', fontSize: 14, margin: 0 }}>
                  {s.name}
                </h3>
                <TierBadge tier={s.required_tier} />
              </div>
              <p style={{
                margin: 0, fontSize: 11, color: 'var(--text-faint)', lineHeight: 1.5, flex: 1,
              }}>
                {s.description}
              </p>
              <div style={{ marginTop: 12 }}>
                <span className="t-badge t-badge-violet" style={{ fontSize: 9, padding: '2px 8px' }}>
                  {s.key}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
