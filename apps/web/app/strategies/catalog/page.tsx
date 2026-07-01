'use client'

import { useState, useMemo } from 'react'
import { useApi } from '@/lib/use-api'

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
  const colors: Record<string, string> = {
    free: 'rgba(136,136,160,0.15)',
    starter: 'rgba(34,211,238,0.15)',
    pro: 'rgba(139,92,246,0.15)',
    enterprise: 'rgba(239,68,68,0.15)',
  }
  const textColors: Record<string, string> = {
    free: '#8888a0',
    starter: '#22d3ee',
    pro: '#8b5cf6',
    enterprise: '#ef4444',
  }
  const borderColors: Record<string, string> = {
    free: 'rgba(136,136,160,0.2)',
    starter: 'rgba(34,211,238,0.2)',
    pro: 'rgba(139,92,246,0.2)',
    enterprise: 'rgba(239,68,68,0.2)',
  }
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', padding: '2px 8px',
      borderRadius: 4, fontSize: 9, fontWeight: 500,
      background: colors[tier] || colors.free,
      color: textColors[tier] || textColors.free,
      border: `1px solid ${borderColors[tier] || borderColors.free}`,
      textTransform: 'capitalize',
    }}>
      {tier}
    </span>
  )
}

function SkeletonCard() {
  return (
    <div className="t-panel" style={{ padding: 20, height: 140 }}>
      <div style={{
        width: '60%', height: 14, background: 'rgba(139,92,246,0.1)',
        borderRadius: 4, marginBottom: 12,
      }} />
      <div style={{
        width: '90%', height: 10, background: 'rgba(139,92,246,0.06)',
        borderRadius: 4, marginBottom: 8,
      }} />
      <div style={{
        width: '75%', height: 10, background: 'rgba(139,92,246,0.06)',
        borderRadius: 4,
      }} />
      <div style={{
        width: 60, height: 20, background: 'rgba(139,92,246,0.08)',
        borderRadius: 4, marginTop: 16,
      }} />
    </div>
  )
}

export default function StrategyCatalogPage() {
  const [search, setSearch] = useState('')
  const [tierFilter, setTierFilter] = useState('all')

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

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-page-title">Strategy Catalog</h1>
        <p className="t-sub" style={{ fontSize: 13 }}>
          Browse all available built-in trading strategies
        </p>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
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
      </div>

      {error && (
        <div style={{ padding: '12px 16px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, color: '#ef4444', fontSize: 13, marginBottom: 16 }}>
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
          background: 'rgba(34,211,238,0.06)', border: '1px solid rgba(34,211,238,0.12)',
          borderRadius: 10, padding: '12px 16px', marginBottom: 20,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div>
            <p style={{ margin: 0, fontSize: 13, color: '#22d3ee', fontWeight: 500 }}>
              {search || tierFilter !== 'all' ? 'No matching strategies' : 'No strategies available'}
            </p>
            <p style={{ margin: '2px 0 0', fontSize: 12, color: '#555570' }}>
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
                <h3 style={{ fontFamily: 'Outfit', fontSize: 14, margin: 0 }}>
                  {s.name}
                </h3>
                <TierBadge tier={s.required_tier} />
              </div>
              <p style={{
                margin: 0, fontSize: 11, color: '#555570', lineHeight: 1.5, flex: 1,
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
