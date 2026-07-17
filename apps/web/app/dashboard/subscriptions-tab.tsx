'use client'

import { useState, useCallback } from 'react'
import { useApi } from '@/lib/use-api'
import { api, AdminUser } from '@/lib/api'
function TierBadge({ tier, small }: { tier: string; small?: boolean }) {
  const map: Record<string, { bg: string; text: string }> = {
    free:       { bg: 'color-mix(in srgb, var(--text-sub) 15%, transparent)', text: 'var(--text-sub)' },
    starter:    { bg: 'color-mix(in srgb, var(--cyan) 15%, transparent)',  text: 'var(--cyan)' },
    pro:        { bg: 'color-mix(in srgb, var(--violet) 15%, transparent)',  text: 'var(--violet)' },
    enterprise: { bg: 'color-mix(in srgb, var(--red) 15%, transparent)',   text: 'var(--red)' },
  }
  const c = map[tier] || map.free
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: small ? '1px 6px' : '2px 8px',
      borderRadius: 4, fontSize: small ? 8 : 9, fontWeight: 500,
      background: c.bg, color: c.text,
      border: `1px solid color-mix(in srgb, ${c.text} 20%, transparent)`,
      textTransform: 'capitalize',
    }}>{tier}</span>
  )
}

const TIERS = ['free', 'starter', 'pro', 'enterprise']
const TIER_ORDER: Record<string, number> = { free: 0, starter: 1, pro: 2, enterprise: 3 }

function SkeletonCard() {
  return <div className="t-panel" style={{ padding: 12, height: 40, marginBottom: 6 }} />
}

export function SubscriptionsTab() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [search, setSearch] = useState('')
  const [updating, setUpdating] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)

  const { data: usersData, loading } = useApi<{ users: AdminUser[] }>(`/admin/users?_=${refreshKey}`)
  const { data: plansData } = useApi<{ plans: { id: string; name: string; tier: string; price: number; features: string[]; most_popular: boolean }[] }>('/subscriptions/plans/')

  const users = usersData?.users || []
  const plans = plansData?.plans || []

  const filtered = search
    ? users.filter(u => u.email.toLowerCase().includes(search.toLowerCase()) || u.full_name?.toLowerCase().includes(search.toLowerCase()))
    : users

  const handleTierChange = async (userId: string, tier: string) => {
    setUpdating(userId)
    setMsg(null)
    try {
      const result = await api.admin.users.updateTier(userId, { subscription_tier: tier })
      setMsg({ text: result.message + (result.deactivated_assignments > 0 ? ` (${result.deactivated_assignments} deactivated)` : ''), ok: true })
      setRefreshKey(k => k + 1)
    } catch (err: unknown) {
      setMsg({ text: err instanceof Error ? err.message : 'Failed', ok: false })
    } finally {
      setUpdating(null)
    }
  }

  const tierDistribution = useCallback(() => {
    const dist: Record<string, number> = { free: 0, starter: 0, pro: 0, enterprise: 0 }
    users.forEach(u => { dist[u.subscription_tier] = (dist[u.subscription_tier] || 0) + 1 })
    return dist
  }, [users])

  const dist = tierDistribution()

  return (
    <div>
      <div className="t-grid-4" style={{ gap: 10, marginBottom: 16 }}>
        {TIERS.map(tier => {
          const count = dist[tier] || 0
          const pct = users.length > 0 ? (count / users.length) * 100 : 0
          const colors: Record<string, string> = { free: 'var(--text-sub)', starter: 'var(--cyan)', pro: 'var(--violet)', enterprise: 'var(--red)' }
          return (
            <div key={tier} className="t-panel" style={{ padding: '14px 16px', borderLeft: `3px solid ${colors[tier]}` }}>
              <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase' }}>{tier}</div>
              <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{count}</div>
              <div style={{ fontSize: 9, color: 'var(--text-faint)' }}>{pct.toFixed(0)}% of users</div>
            </div>
          )
        })}
      </div>

      {msg && (
        <div style={{
          padding: '8px 12px', marginBottom: 12, borderRadius: 6, fontSize: 11,
          background: msg.ok ? 'color-mix(in srgb, var(--green) 10%, transparent)' : 'color-mix(in srgb, var(--red) 10%, transparent)',
          color: msg.ok ? 'var(--green)' : 'var(--red)',
        }}>{msg.text}</div>
      )}

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <input className="t-input" placeholder="Search users..." value={search}
          onChange={e => setSearch(e.target.value)} style={{ width: 260, fontSize: 11 }} />
        <span style={{ fontSize: 10, color: 'var(--text-sub)' }}>{filtered.length} users</span>
        <button className="t-btn t-btn-sm" onClick={() => setRefreshKey(k => k + 1)} style={{ fontSize: 10 }}>Refresh</button>
      </div>

      {loading && <SkeletonCard />}
      {!loading && filtered.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No users found.</p>
        </div>
      )}

      {!loading && filtered.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>USER</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>CURRENT TIER</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>ASSIGNMENTS</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>CHANGE TIER</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>ROLE</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(u => (
                <tr key={u.id} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                  <td style={{ padding: '6px 8px' }}>
                    <div style={{ fontWeight: 600, color: 'var(--text)' }}>{u.full_name || '—'}</div>
                    <div style={{ fontSize: 8, color: 'var(--text-faint)' }}>{u.email}</div>
                  </td>
                  <td style={{ padding: '6px 8px' }}>
                    <TierBadge tier={u.subscription_tier} />
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center', fontFamily: 'var(--font-mono)' }}>
                    {u.active_assignments}/{u.max_active_strategies}
                  </td>
                  <td style={{ padding: '6px 8px' }}>
                    <div style={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                      {TIERS.map(tier => {
                        const isCurrent = tier === u.subscription_tier
                        const isDowngrade = TIER_ORDER[tier] < TIER_ORDER[u.subscription_tier]
                        return (
                          <button key={tier} onClick={() => !isCurrent && handleTierChange(u.id, tier)}
                            disabled={updating === u.id}
                            title={isCurrent ? 'Current tier' : isDowngrade ? 'Downgrade' : 'Upgrade'}
                            style={{
                              padding: '2px 6px', fontSize: 8, borderRadius: 3, border: 'none', cursor: isCurrent ? 'default' : 'pointer',
                              background: isCurrent ? 'color-mix(in srgb, var(--violet) 12%, transparent)' : 'transparent',
                              color: isCurrent ? 'var(--violet)' : 'var(--text-sub)',
                              opacity: updating === u.id ? 0.5 : 1,
                              textTransform: 'capitalize',
                            }}>{tier}</button>
                        )
                      })}
                    </div>
                  </td>
                  <td style={{ padding: '6px 8px', fontSize: 9, color: 'var(--text-faint)', textTransform: 'capitalize' }}>
                    {u.role || 'user'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {plans.length > 0 && (
        <div className="t-panel" style={{ padding: '14px 16px', marginTop: 16 }}>
          <h3 style={{ margin: '0 0 10px', fontSize: 11, fontWeight: 600, letterSpacing: '0.03em' }}>PLANS OVERVIEW</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
            {plans.map(p => (
              <div key={p.id} style={{
                padding: 12, borderRadius: 6, fontSize: 10,
                border: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)',
                background: p.most_popular ? 'color-mix(in srgb, var(--violet) 6%, transparent)' : 'transparent',
              }}>
                <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 4, textTransform: 'capitalize' }}>{p.name}</div>
                <div style={{ fontSize: 16, fontWeight: 700, fontFamily: 'var(--font-mono)', marginBottom: 6 }}>₹{p.price.toLocaleString()}</div>
                <div style={{ fontSize: 9, color: 'var(--text-sub)', textTransform: 'capitalize' }}>{p.tier} tier</div>
                {p.most_popular && <div style={{ fontSize: 8, color: 'var(--violet)', fontWeight: 600, marginTop: 2 }}>Most Popular</div>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
