'use client'

import { useState, useMemo, useCallback, useEffect } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { useApi } from '@/lib/use-api'
import { api, AdminUser, AdminBroker, AdminOrder, AdminAuditEntry, AdminStats, AdminRiskSetting, BrokerMeta, FyersHealthResult, BuyerStrategyStatus } from '@/lib/api'
import { BroadcastDialog } from './broadcast-dialog'
import { SubscriptionsTab } from './subscriptions-tab'
import { TradingLogsTab } from './trading-logs-tab'
import { ActivityTimelineTab } from './activity-timeline-tab'
import { PnLDashboardTab } from './pnl-dashboard-tab'
import { StrategyPerformanceTab } from './strategy-performance-tab'
import { UserStrategiesTab } from './user-strategies-tab'
import { ReferralsTab } from './referrals-tab'

interface HealthData {
  status: string
  service: string
  version: string
  uptime_seconds: number
}

interface HealthReady {
  status: string
  dependencies: { database: boolean; cache: boolean }
}


interface StrategyInfo {
  key: string
  name: string
  description: string
  required_tier: string
  category?: string
  db_id?: string | null
}

interface Assignment {
  id: string
  user_id: string
  strategy_key: string
  required_tier: string
  active: boolean
  assigned_by: string
  created_at: string
}

const TIERS = ['free', 'starter', 'pro', 'enterprise'] as const
const TIER_ORDER: Record<string, number> = { free: 0, starter: 1, pro: 2, enterprise: 3 }

function TierColor(tier: string) {
  const map: Record<string, { bg: string; text: string; border: string }> = {
    free:       { bg: 'color-mix(in srgb, var(--text-sub) 15%, transparent)', text: 'var(--text-sub)', border: 'color-mix(in srgb, var(--text-sub) 20%, transparent)' },
    starter:    { bg: 'color-mix(in srgb, var(--cyan) 15%, transparent)',  text: 'var(--cyan)', border: 'color-mix(in srgb, var(--cyan) 20%, transparent)' },
    pro:        { bg: 'color-mix(in srgb, var(--violet) 15%, transparent)',  text: 'var(--violet)', border: 'color-mix(in srgb, var(--violet) 20%, transparent)' },
    enterprise: { bg: 'color-mix(in srgb, var(--red) 15%, transparent)',   text: 'var(--red)', border: 'color-mix(in srgb, var(--red) 20%, transparent)' },
  }
  return map[tier] || map.free
}

export function TierBadge({ tier, small }: { tier: string; small?: boolean }) {
  const c = TierColor(tier)
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: small ? '1px 6px' : '2px 8px',
      borderRadius: 4, fontSize: small ? 8 : 9, fontWeight: 500,
      background: c.bg, color: c.text,
      border: `1px solid ${c.border}`,
      textTransform: 'capitalize',
    }}>
      {tier}
    </span>
  )
}

function SkeletonLine({ w }: { w: string }) {
  return <div style={{ width: w, height: 12, background: 'color-mix(in srgb, var(--violet) 8%, transparent)', borderRadius: 4 }} />
}

function SkeletonCard() {
  return (
    <div className="t-panel" style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 6 }}>
      <SkeletonLine w="50%" />
      <SkeletonLine w="70%" />
    </div>
  )
}



export function NotAuthorized() {
  return (
    <div>
      <div style={{ padding: '12px 16px', background: 'color-mix(in srgb, var(--red) 10%, transparent)', border: '1px solid color-mix(in srgb, var(--red) 20%, transparent)', borderRadius: 8, color: 'var(--red)', fontSize: 13 }}>
        You do not have admin access.
      </div>
    </div>
  )
}

export function AdminDashboard() {
  const searchParams = useSearchParams()
  const tab = searchParams.get('tab') || 'dashboard'
  const [showBroadcast, setShowBroadcast] = useState(false)

  return (
    <>
      {tab === 'dashboard' && <DashboardTab onBroadcast={() => setShowBroadcast(true)} />}
      {tab === 'users' && <UsersTab />}
      {tab === 'brokers' && <BrokersTab />}
      {tab === 'trades' && <TradesTab />}
      {tab === 'positions-book' && <PositionsOrderBookTab />}
      {tab === 'audit' && <AuditTab />}
      {tab === 'risk' && <RiskTab />}
      {tab === 'strategies' && <StrategiesTab />}
      {tab === 'buyer-strategies' && <BuyerStrategiesTab />}
      {tab === 'subscriptions' && <SubscriptionsTab />}
      {tab === 'trading-logs' && <TradingLogsTab />}
      {tab === 'activity' && <ActivityTimelineTab />}
      {tab === 'pnl' && <PnLDashboardTab />}
      {tab === 'strategy-perf' && <StrategyPerformanceTab />}
      {tab === 'user-strategies' && <UserStrategiesTab />}
      {tab === 'referrals' && <ReferralsTab />}
      {showBroadcast && <BroadcastDialog onClose={() => setShowBroadcast(false)} />}
    </>
  )
}

function DashboardTab({ onBroadcast }: { onBroadcast?: () => void }) {
  const { data: statsData, loading, error } = useApi<AdminStats>('/admin/stats')
  const [health, setHealth] = useState<HealthData | null>(null)
  const [healthReady, setHealthReady] = useState<HealthReady | null>(null)
  const router = useRouter()

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
  const API_ROOT = API_BASE.replace('/api/v1', '')

  useEffect(() => {
    fetch(`${API_ROOT}/health`).then(r => r.json()).then(setHealth).catch(() => {})
    fetch(`${API_ROOT}/health/ready`).then(r => r.json()).then(setHealthReady).catch(() => {})
  }, [API_ROOT])

  if (loading) {
    return (
      <div className="t-grid-4" style={{ gap: 10 }}>
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="t-panel" style={{ padding: '14px 16px' }}>
            <SkeletonLine w="40%" />
            <div style={{ height: 8 }} />
            <SkeletonLine w="60%" />
          </div>
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="t-panel" style={{ padding: '14px 16px', borderLeft: '3px solid var(--red)' }}>
        <div className="t-faint" style={{ fontSize: 9, fontWeight: 600 }}>ERROR</div>
        <div style={{ fontSize: 13, marginTop: 4 }}>Failed to load dashboard stats.</div>
        <div className="t-faint" style={{ fontSize: 11, marginTop: 4 }}>{error.message}</div>
      </div>
    )
  }

  const fmtUptime = (s: number) => {
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    return `${h}h ${m}m`
  }

  return (
    <div>
      <div className="t-grid-4" style={{ gap: 10, marginBottom: 16 }}>
        <div className="t-panel" style={{ padding: '14px 16px', borderLeft: '3px solid var(--cyan)' }}>
          <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>TOTAL USERS</div>
          <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
            {statsData ? statsData.total_users : '—'}
          </div>
        </div>
        <div className="t-panel" style={{ padding: '14px 16px', borderLeft: '3px solid var(--green)' }}>
          <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>ACTIVE ASSIGNMENTS</div>
          <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
            {statsData ? statsData.active_assignments : '—'}
          </div>
        </div>
        <div className="t-panel" style={{ padding: '14px 16px', borderLeft: '3px solid var(--violet)' }}>
          <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>ADMINS</div>
          <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
            {statsData ? statsData.total_admins : '—'}
          </div>
        </div>
        <div className="t-panel" style={{ padding: '14px 16px', borderLeft: '3px solid var(--amber)' }}>
          <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>STRATEGIES</div>
          <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
            {statsData ? statsData.total_strategies : '—'}
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="t-panel" style={{ padding: '14px 16px', marginBottom: 16 }}>
        <h3 style={{ margin: '0 0 10px', fontSize: 11, fontWeight: 600, letterSpacing: '0.03em' }}>QUICK ACTIONS</h3>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="t-btn t-btn-sm" onClick={() => router.push('/admin?tab=users')}
            style={{ fontSize: 10, background: 'color-mix(in srgb, var(--cyan) 12%, transparent)', borderColor: 'color-mix(in srgb, var(--cyan) 20%, transparent)' }}>
            Manage Users
          </button>
          <button className="t-btn t-btn-sm" onClick={() => router.push('/admin?tab=users')}
            style={{ fontSize: 10, background: 'color-mix(in srgb, var(--violet) 12%, transparent)', borderColor: 'color-mix(in srgb, var(--violet) 20%, transparent)' }}>
            Assign Strategy
          </button>
          <button className="t-btn t-btn-sm" onClick={() => router.push('/admin?tab=trades')}
            style={{ fontSize: 10, background: 'color-mix(in srgb, var(--green) 12%, transparent)', borderColor: 'color-mix(in srgb, var(--green) 20%, transparent)' }}>
            Place Trade
          </button>
          <button className="t-btn t-btn-sm" onClick={() => onBroadcast?.()}
            style={{ fontSize: 10, background: 'color-mix(in srgb, var(--amber) 12%, transparent)', borderColor: 'color-mix(in srgb, var(--amber) 20%, transparent)' }}>
            Broadcast
          </button>
          <button className="t-btn t-btn-sm" onClick={() => router.push('/admin?tab=risk')}
            style={{ fontSize: 10, background: 'color-mix(in srgb, var(--red) 12%, transparent)', borderColor: 'color-mix(in srgb, var(--red) 20%, transparent)' }}>
            Risk Controls
          </button>
          <button className="t-btn t-btn-sm" onClick={() => router.push('/admin?tab=audit')}
            style={{ fontSize: 10 }}>
            Audit Log
          </button>
          <button className="t-btn t-btn-sm" onClick={() => router.push('/admin?tab=subscriptions')}
            style={{ fontSize: 10, background: 'color-mix(in srgb, var(--cyan) 12%, transparent)', borderColor: 'color-mix(in srgb, var(--cyan) 20%, transparent)' }}>
            Subscriptions
          </button>
          <button className="t-btn t-btn-sm" onClick={() => router.push('/admin?tab=trading-logs')}
            style={{ fontSize: 10, background: 'color-mix(in srgb, var(--green) 12%, transparent)', borderColor: 'color-mix(in srgb, var(--green) 20%, transparent)' }}>
            Trading Logs
          </button>
          <button className="t-btn t-btn-sm" onClick={() => router.push('/admin?tab=activity')}
            style={{ fontSize: 10, background: 'color-mix(in srgb, var(--amber) 12%, transparent)', borderColor: 'color-mix(in srgb, var(--amber) 20%, transparent)' }}>
            Activity Timeline
          </button>
          <button className="t-btn t-btn-sm" onClick={() => router.push('/admin?tab=pnl')}
            style={{ fontSize: 10, background: 'color-mix(in srgb, var(--green) 12%, transparent)', borderColor: 'color-mix(in srgb, var(--green) 20%, transparent)' }}>
            P&L Dashboard
          </button>
        </div>
      </div>

      <div className="t-grid-2" style={{ gap: 10, marginBottom: 16 }}>
        <div className="t-panel" style={{ padding: '14px 16px' }}>
          <h3 style={{ margin: '0 0 10px', fontSize: 11, fontWeight: 600, letterSpacing: '0.03em' }}>SYSTEM HEALTH</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <span className="t-faint">Service</span>
              <span style={{ fontWeight: 600 }}>{health?.service || '—'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <span className="t-faint">Version</span>
              <span style={{ fontWeight: 600 }}>{health?.version || '—'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <span className="t-faint">Uptime</span>
              <span style={{ fontWeight: 600 }}>{health ? fmtUptime(health.uptime_seconds) : '—'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <span className="t-faint">API Status</span>
              <span style={{ fontWeight: 600, color: health?.status === 'ok' ? 'var(--green)' : 'var(--red)' }}>
                {health?.status?.toUpperCase() || '—'}
              </span>
            </div>
            <div style={{ display: 'flex', gap: 16, marginTop: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10 }}>
                <span className={`t-dot ${healthReady?.dependencies?.database ? 't-dot-green' : 't-dot-red'}`} />
                <span>Database</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10 }}>
                <span className={`t-dot ${healthReady?.dependencies?.cache ? 't-dot-green' : 't-dot-red'}`} />
                <span>Cache</span>
              </div>
            </div>
          </div>
        </div>

        <div className="t-panel" style={{ padding: '14px 16px' }}>
          <h3 style={{ margin: '0 0 10px', fontSize: 11, fontWeight: 600, letterSpacing: '0.03em' }}>OVERVIEW</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <span className="t-faint">Tier Distribution</span>
              <span style={{ fontWeight: 600 }}>
                {statsData ? Object.entries(statsData.tier_distribution).filter(([,c]) => c > 0).length + ' tiers active' : '—'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <span className="t-faint">Strategies per User</span>
              <span style={{ fontWeight: 600 }}>
                {statsData && statsData.total_users > 0
                  ? (statsData.active_assignments / statsData.total_users).toFixed(1)
                  : '—'
                }
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <span className="t-faint">Admin Ratio</span>
              <span style={{ fontWeight: 600 }}>
                {statsData && statsData.total_users > 0
                  ? ((statsData.total_admins / statsData.total_users) * 100).toFixed(1) + '%'
                  : '—'
                }
              </span>
            </div>
          </div>
        </div>
      </div>

      {statsData && (
        <div className="t-panel" style={{ padding: '14px 16px', marginBottom: 16 }}>
          <h3 style={{ margin: '0 0 10px', fontSize: 11, fontWeight: 600, letterSpacing: '0.03em' }}>TIER DISTRIBUTION</h3>
          <div style={{ display: 'flex', gap: 4, height: 6, borderRadius: 3, overflow: 'hidden' }}>
            {['free', 'starter', 'pro', 'enterprise'].map(tier => {
              const count = statsData.tier_distribution[tier] || 0
              const pct = statsData.total_users > 0 ? (count / statsData.total_users) * 100 : 0
              if (count === 0) return null
              return (
                <div key={tier} title={`${tier}: ${count} users (${pct.toFixed(0)}%)`}
                  style={{
                    width: `${pct}%`, height: '100%',
                    background: tier === 'free' ? 'var(--text-sub)' : tier === 'starter' ? 'var(--cyan)' : tier === 'pro' ? 'var(--violet)' : 'var(--red)',
                    borderRadius: 3,
                  }} />
              )
            })}
          </div>
          <div style={{ display: 'flex', gap: 16, marginTop: 8, flexWrap: 'wrap' }}>
            {['free', 'starter', 'pro', 'enterprise'].map(tier => {
              const count = statsData.tier_distribution[tier] || 0
              if (count === 0) return null
              const color = tier === 'free' ? 'var(--text-sub)' : tier === 'starter' ? 'var(--cyan)' : tier === 'pro' ? 'var(--violet)' : 'var(--red)'
              return (
                <div key={tier} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: color, display: 'inline-block' }} />
                  <span style={{ textTransform: 'capitalize', color: 'var(--text-sub)' }}>{tier}</span>
                  <span style={{ fontWeight: 600 }}>{count}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {!statsData && (
        <div className="t-panel" style={{ padding: '14px 16px' }}>
          <div className="t-faint" style={{ fontSize: 12 }}>No stats available yet.</div>
        </div>
      )}
    </div>
  )
}

function UsersTab() {
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [tierUpdating, setTierUpdating] = useState(false)
  const [tierError, setTierError] = useState('')
  const [tierSuccess, setTierSuccess] = useState('')

  const triggerRefresh = useCallback(() => {
    setRefreshKey(k => k + 1)
    setTierError('')
    setTierSuccess('')
  }, [])

  const { data: usersData, loading: usersLoading, error: usersError } =
    useApi<{ users: AdminUser[] }>(`/admin/users?_=${refreshKey}`)

  const { data: catalogData } =
    useApi<{ strategies: StrategyInfo[] }>(`/strategies/list-builtin?_=${refreshKey}`)

  const { data: assignmentsData, loading: assignmentsLoading } =
    useApi<{ assignments: Assignment[] }>(
      selectedUserId ? `/admin/assignments?user_id=${selectedUserId}&_=${refreshKey}` : null,
    )

  const users = usersData?.users || []
  const catalog = catalogData?.strategies || []
  const assignments = assignmentsData?.assignments || []
  const selectedUser = users.find(u => u.id === selectedUserId) || null

  const filteredUsers = useMemo(() => {
    const q = search.toLowerCase()
    return users.filter(u =>
      !q || u.email.toLowerCase().includes(q) || u.full_name.toLowerCase().includes(q),
    )
  }, [users, search])

  const assignedKeys = useMemo(
    () => new Set(assignments.filter(a => a.active).map(a => a.strategy_key)),
    [assignments],
  )

  const activeAssignments = useMemo(
    () => assignments.filter(a => a.active),
    [assignments],
  )

  const available = catalog.filter(s => !assignedKeys.has(s.key))

  const handleTierChange = async (newTier: string) => {
    if (!selectedUserId) return
    setTierUpdating(true)
    setTierError('')
    setTierSuccess('')
    try {
      const result = await api.admin.users.updateTier(selectedUserId, { subscription_tier: newTier })
      const msg = result.deactivated_assignments > 0
        ? `${result.message}. ${result.deactivated_assignments} assignment(s) deactivated.`
        : result.message
      setTierSuccess(msg)
      triggerRefresh()
    } catch (err: unknown) {
      setTierError(err instanceof Error ? err.message : 'Failed to update tier')
    } finally {
      setTierUpdating(false)
    }
  }

  const handleAssign = async (strategyKey: string) => {
    if (!selectedUserId) return
    setTierError('')
    setTierSuccess('')
    try {
      await api.admin.assignments.create({ user_id: selectedUserId, strategy_key: strategyKey })
      triggerRefresh()
    } catch (err: unknown) {
      setTierError(err instanceof Error ? err.message : 'Failed to assign')
    }
  }

  const handleUnassign = async (assignmentId: string) => {
    setTierError('')
    setTierSuccess('')
    try {
      await api.admin.assignments.remove(assignmentId)
      triggerRefresh()
    } catch (err: unknown) {
      setTierError(err instanceof Error ? err.message : 'Failed to unassign')
    }
  }

  return (
    <div>
      {tierError && (
        <div style={{ padding: '8px 12px', background: 'color-mix(in srgb, var(--red) 10%, transparent)', border: '1px solid color-mix(in srgb, var(--red) 20%, transparent)', borderRadius: 8, color: 'var(--red)', fontSize: 12, marginBottom: 12 }}>
          {tierError}
        </div>
      )}
      {tierSuccess && (
        <div style={{ padding: '8px 12px', background: 'color-mix(in srgb, var(--green) 10%, transparent)', border: '1px solid color-mix(in srgb, var(--green) 20%, transparent)', borderRadius: 8, color: 'var(--green)', fontSize: 12, marginBottom: 12 }}>
          {tierSuccess}
        </div>
      )}
      <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>
        <div style={{ flex: '0 0 300px', minWidth: 0 }}>
          <input
            className="t-input"
            placeholder="Search users..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ marginBottom: 8, fontSize: 12 }}
          />
          {usersLoading && Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)}
          {!usersLoading && filteredUsers.length === 0 && (
            <div style={{ background: 'color-mix(in srgb, var(--cyan) 6%, transparent)', border: '1px solid color-mix(in srgb, var(--cyan) 12%, transparent)', borderRadius: 10, padding: '12px 16px' }}>
              <p style={{ margin: 0, fontSize: 12, color: 'var(--cyan)', fontWeight: 500 }}>
                {search ? 'No matching users' : 'No users found'}
              </p>
            </div>
          )}
          {!usersLoading && filteredUsers.map(u => (
            <div
              key={u.id}
              className="t-panel"
              onClick={() => { setSelectedUserId(u.id); setTierError(''); setTierSuccess('') }}
              style={{
                padding: 10, marginBottom: 5, cursor: 'pointer',
                borderColor: selectedUserId === u.id ? 'var(--accent-violet)' : undefined,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 3 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)' }}>
                  {u.full_name || u.email.split('@')[0]}
                </span>
                <TierBadge tier={u.subscription_tier} small />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>{u.email}</span>
                <span style={{ fontSize: 9, color: 'var(--text-sub)', background: 'color-mix(in srgb, var(--violet) 8%, transparent)', borderRadius: 4, padding: '1px 6px' }}>
                  {u.active_assignments}/{u.max_active_strategies}
                </span>
              </div>
            </div>
          ))}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {!selectedUser && !usersLoading && (
            <div className="t-panel" style={{ padding: 20, textAlign: 'center' }}>
              <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>Select a user from the list.</p>
            </div>
          )}
          {selectedUser && (
            <div className="t-panel" style={{ padding: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                <div>
                  <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 15, margin: 0 }}>{selectedUser.full_name || selectedUser.email}</h2>
                  <p style={{ margin: '2px 0 0', fontSize: 10, color: 'var(--text-faint)' }}>{selectedUser.email}</p>
                </div>
                <TierBadge tier={selectedUser.subscription_tier} />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ color: 'var(--text-sub)', fontSize: 10, display: 'block', marginBottom: 3, fontWeight: 600 }}>Subscription Tier</label>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <select className="t-select" value={selectedUser.subscription_tier}
                    onChange={(e) => handleTierChange(e.target.value)} disabled={tierUpdating} style={{ maxWidth: 160, fontSize: 12 }}>
                    {TIERS.map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
                  </select>
                  {tierUpdating && <span style={{ fontSize: 10, color: 'var(--text-sub)' }}>Updating...</span>}
                </div>
              </div>

              <div style={{ fontSize: 11, color: 'var(--text-sub)', marginBottom: 12 }}>
                Active strategies: {activeAssignments.length}/{selectedUser.max_active_strategies}
              </div>

              <div style={{ marginBottom: 16 }}>
                <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 12, margin: '0 0 6px', color: 'var(--text)' }}>Assigned ({activeAssignments.length})</h3>
                {assignmentsLoading && <SkeletonLine w="60%" />}
                {!assignmentsLoading && activeAssignments.length === 0 && <p style={{ fontSize: 11, color: 'var(--text-faint)', margin: 0 }}>None.</p>}
                {!assignmentsLoading && activeAssignments.map(a => {
                  const info = catalog.find(c => c.key === a.strategy_key)
                  return (
                    <div key={a.id} className="t-panel" style={{ padding: '6px 10px', marginBottom: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text)' }}>{info?.name || a.strategy_key}</span>
                        <span style={{ fontSize: 9, color: 'var(--text-faint)', marginLeft: 6 }}><TierBadge tier={a.required_tier} small /></span>
                      </div>
                      <button className="t-btn t-btn-sm t-btn-danger" onClick={() => handleUnassign(a.id)} style={{ fontSize: 9 }}>Remove</button>
                    </div>
                  )
                })}
              </div>

              <div>
                <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 12, margin: '0 0 6px', color: 'var(--text)' }}>Available ({available.length})</h3>
                {available.length === 0 && <p style={{ fontSize: 11, color: 'var(--text-faint)', margin: 0 }}>All assigned.</p>}
                {available.map(s => {
                  const userTierRank = TIER_ORDER[selectedUser.subscription_tier] ?? 0
                  const reqTierRank = TIER_ORDER[s.required_tier] ?? 99
                  const canAssign = userTierRank >= reqTierRank
                  const atLimit = activeAssignments.length >= selectedUser.max_active_strategies
                  const disabled = !canAssign || atLimit
                  return (
                    <div key={s.key} className="t-panel" style={{ padding: '6px 10px', marginBottom: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text)' }}>{s.name}</span>
                        <span style={{ fontSize: 9, color: 'var(--text-faint)', marginLeft: 6 }}><TierBadge tier={s.required_tier} small /></span>
                      </div>
                      <button className={`t-btn t-btn-sm`} onClick={() => !disabled && handleAssign(s.key)}
                        disabled={disabled} style={{ fontSize: 9, opacity: disabled ? 0.5 : 1 }}
                        title={!canAssign ? `Requires ${s.required_tier}` : atLimit ? 'Limit reached' : `Assign ${s.name}`}>
                        {canAssign ? (atLimit ? 'limit' : 'Assign') : `needs ${s.required_tier}`}
                      </button>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function BrokersTab() {
  const [refreshKey, setRefreshKey] = useState(0)
  const { data, loading } = useApi<{ brokers: AdminBroker[] }>(`/admin/brokers?_=${refreshKey}`)

  const [brokerMeta, setBrokerMeta] = useState<BrokerMeta[]>([])
  const [selectedBroker, setSelectedBroker] = useState('')
  const [fields, setFields] = useState<Record<string, string>>({})
  const [additionalParams, setAdditionalParams] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [authUrl, setAuthUrl] = useState('')

  const brokers = data?.brokers || []

  useEffect(() => { api.brokers.metadata().then(r => setBrokerMeta(r.brokers)).catch(() => {}) }, [])

  const getMeta = useCallback((b: string) => brokerMeta.find(m => m.broker === b), [brokerMeta])

  const handleSave = async () => {
    const meta = getMeta(selectedBroker)
    if (!meta) return
    for (const f of meta.fields) {
      if (f.required && !fields[f.key]) { setMsg(`Fill ${f.label}`); return }
    }
    setSaving(true); setMsg('')
    try {
      const payload: Record<string, unknown> = { broker: selectedBroker }
      if (fields.api_key) payload.api_key = fields.api_key
      if (fields.secret_key) payload.secret_key = fields.secret_key
      if (fields.client_id) payload.client_id = fields.client_id
      if (fields.client_code) payload.client_code = fields.client_code
      if (fields.access_token) payload.access_token = fields.access_token
      if (Object.keys(additionalParams).length > 0) payload.additional_params = additionalParams
      await api.brokers.saveCredentials(payload as Parameters<typeof api.brokers.saveCredentials>[0])
      setMsg(`${meta.display_name} credentials saved!`)
      setFields({}); setAdditionalParams({}); setRefreshKey(k => k + 1)

      if (meta.oauth_available && selectedBroker === 'fyers') {
        const res = await api.get<{ auth_url: string }>('/brokers/fyers/auth-url')
        setAuthUrl(res.auth_url)
      }
    } catch (err: unknown) {
      setMsg(err instanceof Error ? err.message : 'Save failed')
    } finally { setSaving(false) }
  }

  return (
    <div>
      {/* Admin Broker Credentials Setup */}
      <div className="t-panel" style={{ padding: 16, marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 13, margin: 0, color: 'var(--text)' }}>My Broker Credentials</h3>
        </div>
        <div style={{ marginBottom: 10 }}>
          <label className="t-label" style={{ fontSize: 10, marginBottom: 4 }}>Select Broker</label>
          <select className="t-input" style={{ fontSize: 11, width: '100%' }}
            value={selectedBroker}
            onChange={e => { setSelectedBroker(e.target.value); setFields({}); setAdditionalParams({}); setMsg(''); setAuthUrl('') }}>
            <option value="">-- Choose a broker --</option>
            {brokerMeta.map(m => (
              <option key={m.broker} value={m.broker}>{m.display_name} ({m.auth_type})</option>
            ))}
          </select>
        </div>
        {selectedBroker && (() => {
          const meta = getMeta(selectedBroker)
          if (!meta) return null
          return (
            <>
              {meta.instructions && (
                <div style={{ fontSize: 10, color: 'var(--text-sub)', lineHeight: 1.5, marginBottom: 10, padding: 8, background: 'color-mix(in srgb, var(--violet) 6%, transparent)', borderRadius: 6, whiteSpace: 'pre-line' }}>
                  {meta.instructions}
                </div>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 8 }}>
                {meta.fields.map(f => (
                  <input key={f.key} className="t-input"
                    type={f.type === 'password' ? 'password' : 'text'}
                    value={fields[f.key] || ''}
                    placeholder={f.placeholder || f.label}
                    style={{ fontSize: 11, width: '100%' }}
                    onChange={e => setFields(s => ({ ...s, [f.key]: e.target.value }))} />
                ))}
                {meta.has_additional_params && meta.additional_params_fields?.map(f => (
                  <input key={f.key} className="t-input"
                    type={f.type === 'password' ? 'password' : 'text'}
                    value={additionalParams[f.key] || ''}
                    placeholder={f.placeholder || f.label}
                    style={{ fontSize: 11, width: '100%' }}
                    onChange={e => setAdditionalParams(s => ({ ...s, [f.key]: e.target.value }))} />
                ))}
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <button className="t-btn t-btn-sm" onClick={handleSave} disabled={saving} style={{ fontSize: 10 }}>
                  {saving ? 'Saving...' : 'Save Credentials'}
                </button>
                {meta.oauth_available && (
                  <button className="t-btn t-btn-sm" style={{ fontSize: 10 }}
                    onClick={async () => {
                      try {
                        if (selectedBroker === 'fyers') {
                          const res = await api.get<{ auth_url: string }>('/brokers/fyers/auth-url')
                          setAuthUrl(res.auth_url)
                          window.open(res.auth_url, '_blank', 'width=600,height=700')
                        }
                      } catch (err: unknown) {
                        setMsg(err instanceof Error ? err.message : 'Auth failed')
                      }
                    }}>
                    {authUrl ? 'Re-authorize' : `Authorize with ${meta.display_name}`}
                  </button>
                )}
              </div>
              {authUrl && (
                <a href={authUrl} target="_blank" rel="noopener noreferrer"
                  style={{ display: 'inline-block', marginTop: 8, fontSize: 10, color: 'var(--cyan)' }}>
                  Open {getMeta(selectedBroker)?.display_name || selectedBroker} login page
                </a>
              )}
              {msg && <p style={{ fontSize: 10, margin: '4px 0 0', color: msg.includes('saved') || msg.includes('success') ? 'var(--green)' : 'var(--red)' }}>{msg}</p>}
            </>
          )
        })()}
      </div>

      {/* All user connections */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <p className="t-sub" style={{ fontSize: 12, margin: 0 }}>All users' broker connections</p>
        <button className="t-btn t-btn-sm" onClick={() => setRefreshKey(k => k + 1)} style={{ fontSize: 10 }}>Refresh</button>
      </div>
      {loading && <SkeletonCard />}
      {!loading && brokers.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No broker connections found.</p>
        </div>
      )}
      {!loading && brokers.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="t-table" style={{ fontSize: 11, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 9 }}>USER</th>
                <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 9 }}>BROKER</th>
                <th style={{ padding: '8px 10px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 9 }}>ACTIVE</th>
                <th style={{ padding: '8px 10px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 9 }}>AUTH</th>
                <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 9 }}>CONNECTED</th>
              </tr>
            </thead>
            <tbody>
              {brokers.map(b => {
                const meta = getMeta(b.broker)
                return (
                  <tr key={b.id} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                    <td style={{ padding: '8px 10px' }}>
                      <div style={{ fontWeight: 600, color: 'var(--text)' }}>{b.full_name || b.email?.split('@')[0] || '—'}</div>
                      <div style={{ fontSize: 9, color: 'var(--text-faint)' }}>{b.email}</div>
                    </td>
                    <td style={{ padding: '8px 10px' }}>
                      <span>{meta?.display_name || b.broker}</span>
                      {b.broker === 'fyers' && !b.has_access_token && (
                        <button className="t-btn t-btn-xs" style={{ marginLeft: 6, fontSize: 8 }}
                          onClick={async () => {
                            try {
                              const res = await api.get<{ auth_url: string }>('/brokers/fyers/auth-url')
                              window.open(res.auth_url, '_blank', 'width=600,height=700')
                            } catch {}
                          }}>
                          OAuth
                        </button>
                      )}
                    </td>
                    <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                      <span style={{
                        display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                        background: b.is_active ? 'var(--green)' : 'var(--text-faint)',
                      }} />
                    </td>
                    <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                      {b.has_access_token
                        ? <span style={{ color: 'var(--green)', fontSize: 10 }}>Authenticated</span>
                        : <span style={{ color: 'var(--red)', fontSize: 10 }}>Not authorized</span>
                      }
                    </td>
                    <td style={{ padding: '8px 10px', fontSize: 10, color: 'var(--text-faint)' }}>
                      {b.created_at ? new Date(b.created_at).toLocaleDateString() : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Fyers Token Management */}
      <FyersTokenSection />
    </div>
  )
}

function FyersTokenSection() {
  const [healthResults, setHealthResults] = useState<FyersHealthResult[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState('')

  const runValidate = async () => {
    setLoading(true); setMsg(''); setHealthResults(null)
    try {
      const res = await api.admin.fyersValidate()
      setHealthResults(res.results)
      const expired = res.results.filter((r: FyersHealthResult) => r.has_token && !r.valid)
      if (expired.length) setMsg(`${expired.length} token(s) expired`)
      else setMsg('All tokens valid')
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : 'Validation failed')
    } finally { setLoading(false) }
  }

  const reAuth = async (credId: string) => {
    try {
      const res = await api.admin.fyersReAuth(credId)
      setMsg('Opening Fyers authorization page...')
      window.open(res.auth_url, '_blank', 'width=600,height=700')
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : 'Re-auth failed')
    }
  }

  return (
    <div className="t-panel" style={{ padding: 16, marginTop: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 13, margin: 0, color: 'var(--text)' }}>Fyers Token Management</h3>
        <button className="t-btn t-btn-sm" onClick={runValidate} disabled={loading} style={{ fontSize: 10 }}>
          {loading ? 'Checking...' : 'Validate All Tokens'}
        </button>
      </div>
      {msg && <p style={{ fontSize: 10, margin: '0 0 10px', color: msg.includes('expired') ? 'var(--red)' : 'var(--green)' }}>{msg}</p>}
      {healthResults && healthResults.length === 0 && (
        <p style={{ fontSize: 11, color: 'var(--text-faint)' }}>No Fyers credentials found.</p>
      )}
      {healthResults && healthResults.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="t-table" style={{ fontSize: 11, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 9 }}>USER</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 9 }}>TOKEN</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 9 }}>STATUS</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 9 }}>ERROR</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 9 }}>ACTION</th>
              </tr>
            </thead>
            <tbody>
              {healthResults.map(r => {
                const statusColor = !r.has_token ? 'var(--text-faint)' : r.valid ? 'var(--green)' : 'var(--red)'
                const statusText = !r.has_token ? 'No Token' : r.valid ? 'Valid' : 'Expired'
                return (
                  <tr key={r.id} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                    <td style={{ padding: '6px 8px' }}>
                      <div style={{ fontWeight: 600, color: 'var(--text)' }}>{r.full_name || '—'}</div>
                      <div style={{ fontSize: 9, color: 'var(--text-faint)' }}>{r.email}</div>
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                      <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: statusColor }} />
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'center', fontSize: 10, fontWeight: 600, color: statusColor }}>
                      {statusText}
                    </td>
                    <td style={{ padding: '6px 8px', fontSize: 9, color: 'var(--red)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {r.error || '—'}
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                      {(!r.has_token || !r.valid) && (
                        <button className="t-btn t-btn-xs" style={{ fontSize: 8 }}
                          onClick={() => reAuth(r.id)}>
                          Re-authorize
                        </button>
                      )}
                      {r.has_token && r.valid && (
                        <button className="t-btn t-btn-xs" style={{ fontSize: 8 }}
                          onClick={() => reAuth(r.id)}>
                          Refresh
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function StrategyComparisonChart({ catalog, assignments, users, compact }: {
  catalog: StrategyInfo[]; assignments: Assignment[]; users: AdminUser[]; compact?: boolean
}) {
  const tiers = ['free', 'starter', 'pro', 'enterprise']
  const cats = ['trend', 'breakout', 'mean_reversion', 'scalping', 'options', 'options_buying']
  const catLabels: Record<string, string> = {
    trend: 'Trend Following', breakout: 'Breakout', mean_reversion: 'Mean Reversion',
    scalping: 'Scalping', options: 'Options', options_buying: 'Options Buying',
  }
  const groupedByTier: Record<string, StrategyInfo[]> = {}
  tiers.forEach(t => { groupedByTier[t] = catalog.filter(s => s.required_tier === t) })

  return (
    <div className="t-panel" style={{ padding: compact ? 10 : 14 }}>
      <h3 style={{ margin: '0 0 compact ? 8 : 12', fontSize: compact ? 11 : 12, fontWeight: 600, letterSpacing: '0.02em' }}>
        Strategy Comparison — Find the Right Fit
      </h3>
      <p className="t-faint" style={{ fontSize: compact ? 9 : 10, marginBottom: 10 }}>
        Compare strategies by tier. Upgrade users to unlock higher-tier strategies for better results.
      </p>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: compact ? 9 : 10 }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '6px 8px', borderBottom: '2px solid color-mix(in srgb, var(--violet) 20%, transparent)', fontWeight: 600, color: 'var(--text)', fontSize: compact ? 8 : 9 }}>Strategy</th>
              <th style={{ textAlign: 'center', padding: '6px 8px', borderBottom: '2px solid color-mix(in srgb, var(--violet) 20%, transparent)', fontWeight: 600, color: 'var(--text)', fontSize: compact ? 8 : 9 }}>Tier</th>
              {!compact && <th style={{ textAlign: 'left', padding: '6px 8px', borderBottom: '2px solid color-mix(in srgb, var(--violet) 20%, transparent)', fontWeight: 600, color: 'var(--text)', fontSize: compact ? 8 : 9 }}>Category</th>}
              <th style={{ textAlign: 'left', padding: '6px 8px', borderBottom: '2px solid color-mix(in srgb, var(--violet) 20%, transparent)', fontWeight: 600, color: 'var(--text)', fontSize: compact ? 8 : 9 }}>Description</th>
              {!compact && <th style={{ textAlign: 'center', padding: '6px 8px', borderBottom: '2px solid color-mix(in srgb, var(--violet) 20%, transparent)', fontWeight: 600, color: 'var(--text)', fontSize: compact ? 8 : 9 }}>Users</th>}
              {!compact && <th style={{ textAlign: 'center', padding: '6px 8px', borderBottom: '2px solid color-mix(in srgb, var(--violet) 20%, transparent)', fontWeight: 600, color: 'var(--text)', fontSize: compact ? 8 : 9 }}>Action</th>}
            </tr>
          </thead>
          <tbody>
            {tiers.map(tier => {
              const strats = groupedByTier[tier] || []
              if (strats.length === 0) return null
              const tierColor = tier === 'free' ? 'var(--text-sub)' : tier === 'starter' ? 'var(--cyan)' : tier === 'pro' ? 'var(--violet)' : 'var(--red)'
              return (
                <>
                  <tr>
                    <td colSpan={compact ? 3 : 6} style={{
                      padding: '4px 8px', fontWeight: 700, fontSize: compact ? 8 : 10,
                      textTransform: 'uppercase', letterSpacing: '0.06em',
                      color: tierColor,
                      borderBottom: `1px solid color-mix(in srgb, ${tierColor} 15%, transparent)`,
                      background: `color-mix(in srgb, ${tierColor} 4%, transparent)`,
                    }}>
                      {tier.toUpperCase()} TIER — {strats.length} {strats.length === 1 ? 'strategy' : 'strategies'}
                    </td>
                  </tr>
                  {strats.map(s => {
                    const assigned = assignments.filter(a => a.strategy_key === s.key)
                    return (
                      <tr key={s.key} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                        <td style={{ padding: '5px 8px', fontWeight: 600 }}>{s.name}</td>
                        <td style={{ padding: '5px 8px', textAlign: 'center' }}><TierBadge tier={s.required_tier} small /></td>
                        {!compact && <td style={{ padding: '5px 8px', color: 'var(--text-sub)', textTransform: 'capitalize' }}>{catLabels[s.key] || s.key}</td>}
                        <td style={{ padding: '5px 8px', color: 'var(--text-sub)', fontSize: compact ? 8 : 9 }}>{s.description}</td>
                        {!compact && <td style={{ padding: '5px 8px', textAlign: 'center' }}>
                          <span style={{ fontWeight: 600 }}>{assigned.length}</span>
                          <span className="t-faint" style={{ fontSize: 8, marginLeft: 2 }}>/ {users.length}</span>
                        </td>}
                        {!compact && <td style={{ padding: '5px 8px', textAlign: 'center' }}>
                          {assigned.length < users.length && (
                            <span style={{ fontSize: 9, color: 'var(--cyan)', cursor: 'default' }}>Upgrade eligible</span>
                          )}
                        </td>}
                      </tr>
                    )
                  })}
                </>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function StrategiesTab() {
  const router = useRouter()
  const [refreshKey, setRefreshKey] = useState(0)
  const { data: catalogData, loading: catalogLoading } = useApi<{ strategies: StrategyInfo[] }>(`/admin/strategies?_=${refreshKey}`)
  const { data: assignData, loading: assignLoading } = useApi<{ assignments: Assignment[] }>(`/admin/assignments?_=${refreshKey}`)
  const { data: usersData } = useApi<{ users: AdminUser[] }>('/admin/users')
  const [assigning, setAssigning] = useState(false)
  const [assignMsg, setAssignMsg] = useState('')
  const [selUser, setSelUser] = useState('')
  const [selStrategy, setSelStrategy] = useState('')
  const [showChart, setShowChart] = useState(true)
  const [showAddForm, setShowAddForm] = useState(false)
  const [addKey, setAddKey] = useState('')
  const [addName, setAddName] = useState('')
  const [addDesc, setAddDesc] = useState('')
  const [addTier, setAddTier] = useState('free')
  const [addCat, setAddCat] = useState('trend')
  const [adding, setAdding] = useState(false)
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [editTier, setEditTier] = useState('')
  const [editCat, setEditCat] = useState('')
  const [deleting, setDeleting] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [showBatchAssign, setShowBatchAssign] = useState(false)
  const [batchStrategy, setBatchStrategy] = useState('')
  const [batchUsers, setBatchUsers] = useState<Set<string>>(new Set())
  const [batchMsg, setBatchMsg] = useState('')
  const [importing, setImporting] = useState(false)

  const catalog = catalogData?.strategies || []
  const assignments = assignData?.assignments || []
  const users = usersData?.users || []

  const triggerRefresh = useCallback(() => setRefreshKey(k => k + 1), [])

  const handleAssign = async () => {
    if (!selUser || !selStrategy) return
    setAssigning(true); setAssignMsg('')
    try {
      await api.admin.assignments.create({ user_id: selUser, strategy_key: selStrategy })
      setAssignMsg('Assigned successfully')
      triggerRefresh()
    } catch (e: any) {
      setAssignMsg(e?.message || 'Failed to assign')
    } finally {
      setAssigning(false)
    }
  }

  const handleUnassign = async (id: string) => {
    try {
      await api.admin.assignments.remove(id)
      triggerRefresh()
    } catch {}
  }

  const handleAdd = async () => {
    if (!addKey || !addName) return
    setAdding(true); setAssignMsg('')
    try {
      await api.admin.strategies.create({ key: addKey, name: addName, description: addDesc, required_tier: addTier, category: addCat })
      setAssignMsg(`Strategy '${addName}' created`)
      setShowAddForm(false); setAddKey(''); setAddName(''); setAddDesc(''); setAddTier('free'); setAddCat('trend')
      triggerRefresh()
    } catch (e: any) {
      setAssignMsg(e?.message || 'Failed to create')
    } finally { setAdding(false) }
  }

  const handleEditSave = async (key: string) => {
    setSaving(true)
    try {
      await api.admin.strategies.update(key, { name: editName, description: editDesc, required_tier: editTier, category: editCat })
      setEditingKey(null)
      triggerRefresh()
    } catch (e: any) {
      setAssignMsg(e?.message || 'Failed to update')
    } finally { setSaving(false) }
  }

  const handleDelete = async (key: string) => {
    setSaving(true)
    try {
      await api.admin.strategies.delete(key)
      setDeleting(null)
      triggerRefresh()
    } catch (e: any) {
      setAssignMsg(e?.message || 'Failed to delete')
    } finally { setSaving(false) }
  }

  const handleBatchAssign = async () => {
    if (!batchStrategy || batchUsers.size === 0) return
    setAssignMsg(''); setBatchMsg('')
    try {
      const res = await api.admin.assignments.batch({ user_ids: Array.from(batchUsers), strategy_key: batchStrategy })
      setBatchMsg(`Created ${res.created}, skipped ${res.skipped}`)
      setShowBatchAssign(false); setBatchUsers(new Set())
      triggerRefresh()
    } catch (e: any) {
      setBatchMsg(e?.message || 'Batch assign failed')
    }
  }

  const handleExport = async () => {
    try {
      const data = await api.admin.assignments.export()
      const blob = new Blob([JSON.stringify(data.assignments, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = 'assignments-export.json'; a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      setAssignMsg(e?.message || 'Export failed')
    }
  }

  const startEdit = (s: StrategyInfo) => {
    setEditingKey(s.key)
    setEditName(s.name)
    setEditDesc(s.description)
    setEditTier(s.required_tier)
    setEditCat(s.category || 'trend')
  }

  const strategyAssignments = (key: string) =>
    assignments.filter(a => a.strategy_key === key)

  const CAT_OPTIONS = ['trend', 'breakout', 'mean_reversion', 'scalping', 'options', 'options_buying']
  const catLabels: Record<string, string> = {
    trend: 'Trend', breakout: 'Breakout', mean_reversion: 'Mean Rev',
    scalping: 'Scalping', options: 'Options', options_buying: 'Options Buy',
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <p className="t-sub" style={{ fontSize: 11, margin: 0 }}>Strategy catalog &amp; assignment management</p>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className="t-btn t-btn-sm" onClick={handleExport} style={{ fontSize: 9 }}>Export</button>
          <label className="t-btn t-btn-sm" style={{ fontSize: 9, cursor: 'pointer' }}>
            Import
            <input type="file" accept=".json" style={{ display: 'none' }} onChange={async (e) => {
              const file = e.target.files?.[0]; if (!file) return; setImporting(true)
              try {
                const text = await file.text(); const entries = JSON.parse(text)
                const res = await api.admin.assignments.import(Array.isArray(entries) ? entries : entries.assignments || [])
                setAssignMsg(`Import: ${res.created} created, ${res.skipped} skipped`)
                triggerRefresh()
              } catch (err: any) { setAssignMsg(err?.message || 'Import failed') }
              finally { setImporting(false); e.target.value = '' }
            }} />
          </label>
          <button className="t-btn t-btn-sm" onClick={() => setShowBatchAssign(!showBatchAssign)} style={{ fontSize: 9 }}>
            {showBatchAssign ? 'Cancel' : 'Batch Assign'}
          </button>
          <button className="t-btn t-btn-sm" onClick={() => setShowAddForm(!showAddForm)} style={{ fontSize: 10 }}>
            {showAddForm ? 'Cancel' : '+ Add Strategy'}
          </button>
        </div>
      </div>

      {showBatchAssign && (
        <div className="t-panel" style={{ padding: 12, marginBottom: 12 }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 11, fontWeight: 600 }}>Batch Assign Strategy</h4>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
            <select value={batchStrategy} onChange={e => setBatchStrategy(e.target.value)}
              className="t-input" style={{ fontSize: 10, maxWidth: 200 }}>
              <option value="">Select strategy...</option>
              {catalog.map(s => <option key={s.key} value={s.key}>{s.name}</option>)}
            </select>
            <span style={{ fontSize: 10, color: 'var(--text-sub)' }}>{batchUsers.size} user(s) selected</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, maxHeight: 150, overflowY: 'auto', marginBottom: 8 }}>
            {users.map(u => (
              <label key={u.id} style={{
                display: 'flex', alignItems: 'center', gap: 4, padding: '2px 6px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                background: batchUsers.has(u.id) ? 'color-mix(in srgb, var(--violet) 15%, transparent)' : 'color-mix(in srgb, var(--violet) 5%, transparent)',
              }}>
                <input type="checkbox" checked={batchUsers.has(u.id)} onChange={() => {
                  const next = new Set(batchUsers)
                  if (next.has(u.id)) next.delete(u.id); else next.add(u.id)
                  setBatchUsers(next)
                }} style={{ accentColor: 'var(--violet)' }} />
                {u.full_name || u.email}
              </label>
            ))}
          </div>
          <button className="t-btn t-btn-xs" onClick={handleBatchAssign} disabled={!batchStrategy || batchUsers.size === 0}
            style={{ fontSize: 9 }}>
            Assign to {batchUsers.size} user(s)
          </button>
          {batchMsg && <span style={{ marginLeft: 8, fontSize: 10, color: batchMsg.includes('fail') ? 'var(--red)' : 'var(--green)' }}>{batchMsg}</span>}
        </div>
      )}

      {showAddForm && (
        <div className="t-panel" style={{ padding: 12, marginBottom: 12 }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 11, fontWeight: 600 }}>New Strategy</h4>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
            <input className="t-input" value={addKey} onChange={e => setAddKey(e.target.value)}
              placeholder="Key (e.g. my_strategy)" style={{ fontSize: 10, width: 140 }} />
            <input className="t-input" value={addName} onChange={e => setAddName(e.target.value)}
              placeholder="Display name" style={{ fontSize: 10, width: 140 }} />
            <input className="t-input" value={addDesc} onChange={e => setAddDesc(e.target.value)}
              placeholder="Description" style={{ fontSize: 10, width: 200 }} />
            <select value={addTier} onChange={e => setAddTier(e.target.value)} className="t-input" style={{ fontSize: 10, width: 90 }}>
              {TIERS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <select value={addCat} onChange={e => setAddCat(e.target.value)} className="t-input" style={{ fontSize: 10, width: 100 }}>
              {CAT_OPTIONS.map(c => <option key={c} value={c}>{catLabels[c]}</option>)}
            </select>
            <button className="t-btn t-btn-xs" onClick={handleAdd} disabled={adding} style={{ fontSize: 9 }}>
              {adding ? '...' : 'Create'}
            </button>
          </div>
        </div>
      )}

      {!catalogLoading && catalog.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <h3 style={{ fontSize: 11, fontWeight: 600, margin: 0, letterSpacing: '0.03em' }}>STRATEGY COMPARISON</h3>
            <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => setShowChart(!showChart)} style={{ fontSize: 9 }}>
              {showChart ? 'Hide' : 'Show'}
            </button>
          </div>
          {showChart && (
            <StrategyComparisonChart catalog={catalog} assignments={assignments} users={users} />
          )}
        </div>
      )}

      {catalogLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {[1,2,3].map(i => <SkeletonCard key={i} />)}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {catalog.map(s => (
            <div key={s.key} className="t-panel" style={{ padding: '10px 12px', borderLeft: '3px solid var(--violet)' }}>
              {editingKey === s.key ? (
                <div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 6 }}>
                    <input className="t-input" value={editName} onChange={e => setEditName(e.target.value)}
                      placeholder="Name" style={{ fontSize: 10, width: 140 }} />
                    <select value={editTier} onChange={e => setEditTier(e.target.value)} className="t-input" style={{ fontSize: 10, width: 80 }}>
                      {TIERS.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                    <select value={editCat} onChange={e => setEditCat(e.target.value)} className="t-input" style={{ fontSize: 10, width: 90 }}>
                      {CAT_OPTIONS.map(c => <option key={c} value={c}>{catLabels[c]}</option>)}
                    </select>
                    <span className="t-faint" style={{ fontSize: 9, fontFamily: 'var(--font-mono)' }}>{s.key}</span>
                  </div>
                  <input className="t-input" value={editDesc} onChange={e => setEditDesc(e.target.value)}
                    placeholder="Description" style={{ fontSize: 10, width: '100%', marginBottom: 6 }} />
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button className="t-btn t-btn-xs" onClick={() => handleEditSave(s.key)} disabled={saving} style={{ fontSize: 9 }}>
                      {saving ? '...' : 'Save'}
                    </button>
                    <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => setEditingKey(null)} style={{ fontSize: 9 }}>Cancel</button>
                  </div>
                </div>
              ) : (
                <>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontWeight: 600, fontSize: 13 }}>{s.name}</span>
                      <TierBadge tier={s.required_tier} small />
                      {s.category && <span className="t-faint" style={{ fontSize: 8, textTransform: 'uppercase' }}>{catLabels[s.category] || s.category}</span>}
                    </div>
                    <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                      <span className="t-faint" style={{ fontSize: 9, fontFamily: 'var(--font-mono)' }}>{s.key}</span>
                      {s.db_id && (
                        <>
                          <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => startEdit(s)} style={{ fontSize: 8, padding: '1px 4px' }}>Edit</button>
                          {deleting === s.key ? (
                            <>
                              <button className="t-btn t-btn-xs" onClick={() => handleDelete(s.key)} disabled={saving} style={{ fontSize: 8, padding: '1px 4px', color: 'var(--red)' }}>
                                {saving ? '...' : 'Confirm'}
                              </button>
                              <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => setDeleting(null)} style={{ fontSize: 8, padding: '1px 4px' }}>No</button>
                            </>
                          ) : (
                            <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => setDeleting(s.key)} style={{ fontSize: 8, padding: '1px 4px', color: 'var(--text-faint)' }}>Del</button>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                  <div className="t-faint" style={{ fontSize: 11, marginBottom: 6 }}>{s.description}</div>
                </>
              )}

              {editingKey !== s.key && (
                <>
                  {strategyAssignments(s.key).length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
                      {strategyAssignments(s.key).map(a => {
                        const u = users.find(us => us.id === a.user_id)
                        return (
                          <span key={a.id} style={{
                            display: 'inline-flex', alignItems: 'center', gap: 4,
                            padding: '1px 6px', borderRadius: 4, fontSize: 10,
                            background: 'color-mix(in srgb, var(--green) 12%, transparent)',
                            border: '1px solid color-mix(in srgb, var(--green) 20%, transparent)',
                          }}>
                            {u?.email || a.user_id.slice(0, 8)}
                            <span onClick={() => handleUnassign(a.id)}
                              style={{ cursor: 'pointer', opacity: 0.6, marginLeft: 2 }}>✕</span>
                          </span>
                        )
                      })}
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    <select value={selStrategy === s.key ? selUser : ''}
                      onChange={e => { setSelStrategy(s.key); setSelUser(e.target.value) }}
                      style={{ fontSize: 10, padding: '2px 6px', maxWidth: 180 }}>
                      <option value="">Assign to user...</option>
                      {users.map(u => (
                        <option key={u.id} value={u.id}>{u.full_name || u.email} ({u.subscription_tier})</option>
                      ))}
                    </select>
                    {selStrategy === s.key && selUser && (
                      <button className="t-btn t-btn-xs" onClick={handleAssign} disabled={assigning}
                        style={{ fontSize: 9, padding: '2px 8px' }}>
                        {assigning ? '...' : 'Assign'}
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {assignMsg && (
        <div style={{ marginTop: 8, fontSize: 11, color: assignMsg.includes('Failed') || assignMsg.includes('fail') ? 'var(--red)' : 'var(--green)' }}>
          {assignMsg}
        </div>
      )}
    </div>
  )
}

const BUYER_STRATEGY_OPTIONS = [
  { key: 'momentum_breakout_buyer', name: 'Momentum Breakout Buyer', tier: 'starter', desc: 'OR breakout + volume + premium management' },
  { key: 'trend_rider_buyer', name: 'Trend Rider Buyer', tier: 'pro', desc: 'EMA9/21 + VWAP + ADX + Supertrend trail' },
  { key: 'long_straddle', name: 'Long Straddle', tier: 'enterprise', desc: 'ATM CE+PE buy, IV gate, combined loss cap' },
]

function BuyerStrategiesTab() {
  const [refreshKey, setRefreshKey] = useState(0)
  const { data, loading } = useApi<{ strategies: BuyerStrategyStatus[] }>(`/buyer-strategies/status?_=${refreshKey}`)
  const [activating, setActivating] = useState(false)
  const [msg, setMsg] = useState('')
  const [strategyKey, setStrategyKey] = useState('momentum_breakout_buyer')
  const [index, setIndex] = useState('NIFTY')
  const [capital, setCapital] = useState('100000')
  const [targetDelta, setTargetDelta] = useState('')

  const strategies = data?.strategies || []

  const handleActivate = async () => {
    setActivating(true); setMsg('')
    try {
      const cfg: Record<string, unknown> = { capital: Number(capital), risk_per_trade_pct: 1.0, max_outlay_pct: 10.0 }
      if (targetDelta) cfg.target_delta = Number(targetDelta)
      const res = await api.admin.buyerStrategies.activate({
        strategy_id: `${strategyKey}_${Date.now()}`,
        strategy_key: strategyKey,
        index,
        config: cfg,
      })
      setMsg(`Activated: ${res.strategy_id}`)
      setRefreshKey(k => k + 1)
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : 'Activation failed')
    } finally { setActivating(false) }
  }

  const handleDeactivate = async (id: string) => {
    try {
      await api.admin.buyerStrategies.deactivate(id)
      setRefreshKey(k => k + 1)
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : 'Deactivate failed')
    }
  }

  return (
    <div>
      <div className="t-panel" style={{ padding: 16, marginBottom: 16 }}>
        <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 13, margin: '0 0 12px', color: 'var(--text)' }}>Activate Buyer Strategy</h3>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8 }}>
          <select className="t-input" value={strategyKey} onChange={e => setStrategyKey(e.target.value)}
            style={{ fontSize: 11, width: 220 }}>
            {BUYER_STRATEGY_OPTIONS.map(s => (
              <option key={s.key} value={s.key}>{s.name} ({s.tier})</option>
            ))}
          </select>
          <select className="t-input" value={index} onChange={e => setIndex(e.target.value)}
            style={{ fontSize: 11, width: 100 }}>
            <option value="NIFTY">NIFTY</option>
            <option value="SENSEX">SENSEX</option>
          </select>
          <input className="t-input" type="number" value={capital} onChange={e => setCapital(e.target.value)}
            placeholder="Capital" style={{ fontSize: 11, width: 120 }} />
          <input className="t-input" type="number" value={targetDelta} onChange={e => setTargetDelta(e.target.value)}
            placeholder="Delta (0=ATM)" step="0.05" style={{ fontSize: 11, width: 100 }} />
          <button className="t-btn t-btn-sm" onClick={handleActivate} disabled={activating} style={{ fontSize: 10 }}>
            {activating ? 'Activating...' : 'Activate'}
          </button>
        </div>
        {BUYER_STRATEGY_OPTIONS.filter(s => s.key === strategyKey).map(s => (
          <p key={s.key} style={{ fontSize: 10, color: 'var(--text-sub)', margin: 0 }}>{s.desc}</p>
        ))}
        {msg && <p style={{ fontSize: 10, marginTop: 6, color: msg.includes('fail') ? 'var(--red)' : 'var(--green)' }}>{msg}</p>}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <p className="t-sub" style={{ fontSize: 12, margin: 0 }}>Active Strategies</p>
        <button className="t-btn t-btn-sm" onClick={() => setRefreshKey(k => k + 1)} style={{ fontSize: 10 }}>Refresh</button>
      </div>
      {loading && <SkeletonCard />}
      {!loading && strategies.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No active buyer strategies.</p>
        </div>
      )}
      {!loading && strategies.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="t-table" style={{ fontSize: 11, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 9 }}>ID</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 9 }}>STRATEGY</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 9 }}>INDEX</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 9 }}>STATUS</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 9 }}>ACTION</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map(s => (
                <tr key={s.strategy_id} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                  <td style={{ padding: '6px 8px', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text)' }}>{s.strategy_id}</td>
                  <td style={{ padding: '6px 8px', fontWeight: 600, color: 'var(--text)' }}>{s.strategy_key}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>{s.index}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    <span style={{ color: s.running ? 'var(--green)' : 'var(--amber)', fontSize: 10, fontWeight: 600 }}>
                      {s.running ? 'Running' : 'Idle'}
                    </span>
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    <button className="t-btn t-btn-xs" style={{ fontSize: 8 }}
                      onClick={() => handleDeactivate(s.strategy_id)}>
                      Deactivate
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function TradesTab() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [filterUser, setFilterUser] = useState('')
  const [filterPaper, setFilterPaper] = useState('')
  const [placeOpen, setPlaceOpen] = useState(false)
  const [placeUserId, setPlaceUserId] = useState('')
  const [placeSymbol, setPlaceSymbol] = useState('')
  const [placeSide, setPlaceSide] = useState('BUY')
  const [placeQty, setPlaceQty] = useState(1)
  const [placePrice, setPlacePrice] = useState('')
  const [placeTrigger, setPlaceTrigger] = useState('')
  const [placeExchange, setPlaceExchange] = useState('NSE')
  const [placeType, setPlaceType] = useState('MARKET')
  const [placeProduct, setPlaceProduct] = useState('INTRADAY')
  const [placeInstType, setPlaceInstType] = useState('EQ')
  const [placeExpiry, setPlaceExpiry] = useState('')
  const [placeStrike, setPlaceStrike] = useState('')
  const [placeOptionType, setPlaceOptionType] = useState('CE')
  const [placing, setPlacing] = useState(false)
  const [placeMsg, setPlaceMsg] = useState('')

  const { data: usersData } = useApi<{ users: AdminUser[] }>('/admin/users')

  const params = new URLSearchParams()
  if (filterUser) params.set('user_id', filterUser)
  if (filterPaper) params.set('is_paper', filterPaper)

  const { data, loading } = useApi<{ orders: AdminOrder[]; count: number }>(
    `/admin/orders?limit=100&${params.toString()}&_=${refreshKey}`
  )

  const orders = data?.orders || []
  const users = usersData?.users || []

  useEffect(() => {
    const int = setInterval(() => setRefreshKey(k => k + 1), 10000)
    return () => clearInterval(int)
  }, [])

  useEffect(() => {
    if (placeInstType === 'FUT' || placeInstType === 'OPT') {
      setPlaceExchange('NFO')
    } else if (placeInstType === 'EQ') {
      setPlaceExchange('NSE')
    }
  }, [placeInstType])

  const handlePlaceTrade = async () => {
    if (!placeUserId || !placeSymbol || !placeQty) { setPlaceMsg('Fill user, symbol, and qty'); return }
    setPlacing(true); setPlaceMsg('')
    try {
      const body: Parameters<typeof api.admin.executeTrade>[0] = {
        user_id: placeUserId, symbol: placeSymbol.toUpperCase(), side: placeSide,
        quantity: placeQty, exchange: placeExchange, order_type: placeType, product: placeProduct,
        instrument_type: placeInstType,
      }
      if (placePrice) body.price = parseFloat(placePrice)
      if (placeTrigger) body.trigger_price = parseFloat(placeTrigger)
      if (placeInstType === 'FUT' && placeExpiry) body.expiry_date = placeExpiry
      if (placeInstType === 'OPT') {
        if (placeExpiry) body.expiry_date = placeExpiry
        if (placeStrike) body.strike_price = parseFloat(placeStrike)
        body.option_type = placeOptionType
      }
      await api.admin.executeTrade(body)
      setPlaceMsg('Trade placed successfully')
      setRefreshKey(k => k + 1)
    } catch (e: unknown) {
      setPlaceMsg(e instanceof Error ? e.message : 'Trade failed')
    } finally { setPlacing(false) }
  }

  const segLabel = (t: string) => t === 'EQ' ? 'Cash' : t === 'FUT' ? 'Futures' : 'Options'

  return (
    <div>
      <div className="t-panel" style={{ padding: 12, marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: placeOpen ? 12 : 0 }}>
          <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 12, margin: 0, color: 'var(--text)' }}>Place Trade for User</h3>
          <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => setPlaceOpen(!placeOpen)} style={{ fontSize: 10 }}>
            {placeOpen ? 'Close' : 'Open'}
          </button>
        </div>
        {placeOpen && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <select className="t-input" value={placeUserId} onChange={e => setPlaceUserId(e.target.value)}
                style={{ fontSize: 11, maxWidth: 200 }}>
                <option value="">— Select user —</option>
                {users.map(u => (
                  <option key={u.id} value={u.id}>{u.full_name || u.email} ({u.email})</option>
                ))}
              </select>
              <input className="t-input" placeholder="Symbol (e.g. RELIANCE)" value={placeSymbol}
                onChange={e => setPlaceSymbol(e.target.value)} style={{ width: 120, fontSize: 11, fontFamily: 'var(--font-mono)' }} />
              <div style={{ display: 'flex', gap: 4, background: 'color-mix(in srgb, var(--violet) 6%, transparent)', borderRadius: 6, padding: 2 }}>
                {['EQ', 'FUT', 'OPT'].map(t => (
                  <button key={t} onClick={() => setPlaceInstType(t)}
                    style={{
                      padding: '3px 10px', fontSize: 9, fontWeight: 600, borderRadius: 4, border: 'none', cursor: 'pointer',
                      background: placeInstType === t ? 'var(--violet)' : 'transparent',
                      color: placeInstType === t ? '#fff' : 'var(--text-sub)',
                    }}>{segLabel(t)}</button>
                ))}
              </div>
              <select className="t-input" value={placeSide} onChange={e => setPlaceSide(e.target.value)}
                style={{ fontSize: 11, maxWidth: 70 }}>
                <option value="BUY">BUY</option>
                <option value="SELL">SELL</option>
              </select>
              <input className="t-input" type="number" placeholder="Qty" value={placeQty}
                onChange={e => setPlaceQty(parseInt(e.target.value) || 0)} style={{ width: 55, fontSize: 11 }} />
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <input className="t-input" type="number" placeholder="Price" value={placePrice}
                onChange={e => setPlacePrice(e.target.value)} style={{ width: 70, fontSize: 11 }} step="0.05" />
              {(placeType === 'SL' || placeType === 'SL-M') && (
                <input className="t-input" type="number" placeholder="Trigger" value={placeTrigger}
                  onChange={e => setPlaceTrigger(e.target.value)} style={{ width: 70, fontSize: 11 }} step="0.05" />
              )}
              {(placeInstType === 'FUT' || placeInstType === 'OPT') && (
                <input className="t-input" type="text" placeholder="Expiry (e.g. 25JUL)" value={placeExpiry}
                  onChange={e => setPlaceExpiry(e.target.value.toUpperCase())} style={{ width: 90, fontSize: 11 }} />
              )}
              {placeInstType === 'OPT' && (
                <>
                  <input className="t-input" type="number" placeholder="Strike" value={placeStrike}
                    onChange={e => setPlaceStrike(e.target.value)} style={{ width: 70, fontSize: 11 }} />
                  <select className="t-input" value={placeOptionType} onChange={e => setPlaceOptionType(e.target.value)}
                    style={{ fontSize: 11, maxWidth: 60 }}>
                    <option value="CE">CE</option>
                    <option value="PE">PE</option>
                  </select>
                </>
              )}
              <select className="t-input" value={placeType} onChange={e => setPlaceType(e.target.value)}
                style={{ fontSize: 11, maxWidth: 80 }}>
                <option value="MARKET">MARKET</option>
                <option value="LIMIT">LIMIT</option>
                <option value="SL">SL</option>
                <option value="SL-M">SL-M</option>
              </select>
              <select className="t-input" value={placeExchange} onChange={e => setPlaceExchange(e.target.value)}
                style={{ fontSize: 11, maxWidth: 70 }}>
                <option value="NSE">NSE</option>
                <option value="BSE">BSE</option>
                <option value="NFO">NFO</option>
                <option value="CDS">CDS</option>
              </select>
              <select className="t-input" value={placeProduct} onChange={e => setPlaceProduct(e.target.value)}
                style={{ fontSize: 11, maxWidth: 90 }}>
                <option value="INTRADAY">INTRADAY</option>
                <option value="CNC">CNC</option>
                <option value="MIS">MIS</option>
                <option value="NRML">NRML</option>
              </select>
              <button className="t-btn t-btn-sm" onClick={handlePlaceTrade} disabled={placing}
                style={{ fontSize: 10, background: 'color-mix(in srgb, var(--green) 15%, transparent)', color: 'var(--green)', border: '1px solid color-mix(in srgb, var(--green) 20%, transparent)' }}>
                {placing ? 'Placing...' : 'Place Trade'}
              </button>
            </div>
            {placeMsg && <p style={{ margin: 0, fontSize: 10, color: placeMsg.includes('success') || placeMsg.includes('placed') ? 'var(--green)' : 'var(--red)' }}>{placeMsg}</p>}
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <input className="t-input" placeholder="Filter by user ID" value={filterUser}
          onChange={e => setFilterUser(e.target.value)} style={{ width: 200, fontSize: 11 }} />
        <select className="t-select" value={filterPaper} onChange={e => setFilterPaper(e.target.value)}
          style={{ fontSize: 11, maxWidth: 120 }}>
          <option value="">All types</option>
          <option value="true">Paper</option>
          <option value="false">Live</option>
        </select>
        <span style={{ fontSize: 10, color: 'var(--text-sub)' }}>{data?.count || orders.length} orders</span>
        <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>(auto-refreshes)</span>
      </div>
      {loading && <SkeletonCard />}
      {!loading && orders.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No orders found.</p>
        </div>
      )}
      {!loading && orders.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>USER</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>SYMBOL</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>SEG</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>SIDE</th>
                <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>QTY</th>
                <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>PRICE</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>BROKER</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>STATUS</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>TYPE</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>AT</th>
              </tr>
            </thead>
            <tbody>
              {orders.map(o => (
                <tr key={o.id} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                  <td style={{ padding: '6px 8px' }}>
                    <div style={{ color: 'var(--text)', fontWeight: 500 }}>{o.full_name || '—'}</div>
                    <div style={{ fontSize: 8, color: 'var(--text-faint)' }}>{o.email}</div>
                  </td>
                  <td style={{ padding: '6px 8px', fontWeight: 600, color: 'var(--text)' }}>{o.symbol?.split(':').pop()}</td>
                  <td style={{ padding: '6px 8px' }}>
                    <span className={`t-badge ${o.instrument_type === 'OPT' ? 't-badge-violet' : o.instrument_type === 'FUT' ? 't-badge-cyan' : 't-badge-green'}`}
                      style={{ fontSize: 8, padding: '0 4px' }}>{o.instrument_type || 'EQ'}</span>
                  </td>
                  <td style={{ padding: '6px 8px', color: o.side === 'BUY' ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>{o.side}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{o.quantity}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{o.price ? o.price.toFixed(2) : '—'}</td>
                  <td style={{ padding: '6px 8px', textTransform: 'capitalize' }}>{o.broker}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    <span style={{
                      color: o.status === 'FILLED' || o.status === 'OPEN' ? 'var(--green)'
                        : o.status === 'REJECTED' ? 'var(--red)' : 'var(--amber)',
                      fontSize: 9, fontWeight: 600,
                    }}>
                      {o.status}
                    </span>
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    {o.is_paper
                      ? <span style={{ color: 'var(--amber)', fontSize: 9 }}>Paper</span>
                      : <span style={{ color: 'var(--green)', fontSize: 9 }}>Live</span>
                    }
                  </td>
                  <td style={{ padding: '6px 8px', fontSize: 9, color: 'var(--text-faint)' }}>
                    {o.created_at ? new Date(o.created_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function PositionsOrderBookTab() {
  const [userFilter, setUserFilter] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [livePositions, setLivePositions] = useState(false)
  const [liveData, setLiveData] = useState<any[] | null>(null)
  const [liveLoading, setLiveLoading] = useState(false)

  const { data: posData, loading: posLoading } = useApi<{ positions: any[]; count: number }>(
    livePositions ? null : `/admin/positions${userFilter ? `?user_id=${userFilter}` : ''}&_=${refreshKey}`
  )
  const { data: ordData, loading: ordLoading } = useApi<{ orders: any[]; count: number }>(
    `/admin/orders?limit=100${userFilter ? `&user_id=${userFilter}` : ''}&_=${refreshKey}`
  )
  const { data: usersData } = useApi<{ users: AdminUser[] }>('/admin/users')

  const positions = liveData || posData?.positions || []
  const orders = ordData?.orders || []
  const users = usersData?.users || []
  const [tab, setTab] = useState<'positions' | 'orders'>('positions')

  const fetchLivePositions = useCallback(async () => {
    if (!userFilter) return
    setLiveLoading(true)
    try {
      const res = await api.admin.fetch<{ positions: any[]; count: number; source: string }>(`/positions/live/${userFilter}`)
      setLiveData(res.positions)
    } catch {
      setLiveData([])
    } finally { setLiveLoading(false) }
  }, [userFilter])

  useEffect(() => {
    const int = setInterval(() => setRefreshKey(k => k + 1), 10000)
    return () => clearInterval(int)
  }, [])

  useEffect(() => {
    if (!livePositions) setLiveData(null)
  }, [livePositions])

  const segmentBadge = (t: string) => {
    const map: Record<string, string> = { EQ: 't-badge-green', FUT: 't-badge-cyan', OPT: 't-badge-violet' }
    return <span className={`t-badge ${map[t] || 't-badge-green'}`} style={{ fontSize: 9 }}>{t || 'EQ'}</span>
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <select className="t-input" value={userFilter} onChange={e => { setUserFilter(e.target.value); if (livePositions && !e.target.value) { setLivePositions(false); setLiveData(null) }}}
          style={{ fontSize: 11, maxWidth: 220 }}>
          <option value="">— All users —</option>
          {users.map(u => (
            <option key={u.id} value={u.id}>{u.full_name || u.email} ({u.email})</option>
          ))}
        </select>
        <div style={{ display: 'flex', gap: 4, background: 'color-mix(in srgb, var(--violet) 6%, transparent)', borderRadius: 6, padding: 2 }}>
          {(['positions', 'orders'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              style={{
                padding: '4px 14px', fontSize: 10, fontWeight: 600, borderRadius: 4, border: 'none', cursor: 'pointer',
                background: tab === t ? 'var(--violet)' : 'transparent',
                color: tab === t ? '#fff' : 'var(--text-sub)',
                textTransform: 'capitalize',
              }}>{t} {t === 'positions' ? `(${positions.length})` : `(${orders.length})`}</button>
          ))}
        </div>
        {tab === 'positions' && (
          <button className={`t-btn t-btn-xs`} onClick={() => { setLivePositions(!livePositions); if (!livePositions && userFilter) fetchLivePositions() }}
            style={{ fontSize: 9, color: livePositions ? 'var(--green)' : 'var(--text-sub)' }}>
            {livePositions ? 'Live' : 'DB'}
          </button>
        )}
        {livePositions && userFilter && (
          <button className="t-btn t-btn-xs" onClick={fetchLivePositions} disabled={liveLoading}
            style={{ fontSize: 9 }}>
            {liveLoading ? '...' : 'Refresh'}
          </button>
        )}
        <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>{livePositions ? 'live broker' : 'auto-refreshes'}</span>
      </div>

      {tab === 'positions' && (
        posLoading ? <SkeletonCard /> :
        positions.length === 0 ? (
          <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No open positions.</p>
          </div>
        ) : (
          <div className="t-panel" style={{ padding: 0 }}>
            <div style={{ overflowX: 'auto' }}>
              <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                    <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>USER</th>
                    <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>SYMBOL</th>
                    <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>SEG</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>QTY</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>BUY AVG</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>Unrealised P&L</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>Realised P&L</th>
                    <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>PRODUCT</th>
                    <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>BROKER</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p: any, i: number) => (
                    <tr key={i} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                      <td style={{ padding: '6px 8px' }}>
                        <div style={{ fontWeight: 500 }}>{p.full_name || '—'}</div>
                        <div style={{ fontSize: 8, color: 'var(--text-faint)' }}>{p.email}</div>
                      </td>
                      <td style={{ padding: '6px 8px', fontWeight: 600 }}>{p.symbol?.split(':').pop()}</td>
                      <td style={{ padding: '6px 8px' }}>{segmentBadge(p.instrument_type)}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{p.quantity}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{p.average_buy_price?.toFixed(1) || '-'}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: (p.unrealised_pnl || 0) >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
                        {(p.unrealised_pnl || 0) >= 0 ? '+' : ''}{p.unrealised_pnl?.toFixed(0) || '0'}
                      </td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: (p.realised_pnl || 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>
                        {(p.realised_pnl || 0) >= 0 ? '+' : ''}{p.realised_pnl?.toFixed(0) || '0'}
                      </td>
                      <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                        <span style={{ fontSize: 9, opacity: 0.7 }}>{p.product}</span>
                      </td>
                      <td style={{ padding: '6px 8px', textTransform: 'capitalize' }}>{p.broker}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      )}

      {tab === 'orders' && (
        ordLoading ? <SkeletonCard /> :
        orders.length === 0 ? (
          <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No orders found.</p>
          </div>
        ) : (
          <div className="t-panel" style={{ padding: 0 }}>
            <div style={{ overflowX: 'auto' }}>
              <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                    <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>USER</th>
                    <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>SYMBOL</th>
                    <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>SEG</th>
                    <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>SIDE</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>QTY</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>PRICE</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>FILLED</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>AVG</th>
                    <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>STATUS</th>
                    <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>TYPE</th>
                    <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>AT</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o: any) => (
                    <tr key={o.id} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                      <td style={{ padding: '6px 8px' }}>
                        <div style={{ fontWeight: 500 }}>{o.full_name || '—'}</div>
                        <div style={{ fontSize: 8, color: 'var(--text-faint)' }}>{o.email}</div>
                      </td>
                      <td style={{ padding: '6px 8px', fontWeight: 600 }}>{o.symbol?.split(':').pop()}</td>
                      <td style={{ padding: '6px 8px' }}>{segmentBadge(o.instrument_type)}</td>
                      <td style={{ padding: '6px 8px', color: o.side === 'BUY' ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>{o.side}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{o.quantity}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{o.price?.toFixed(2) || '—'}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{o.filled_quantity || 0}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{o.average_price?.toFixed(1) || '-'}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                        <span className={`t-badge ${o.status === 'FILLED' ? 't-badge-green' : o.status === 'OPEN' || o.status === 'PENDING' ? 't-badge-cyan' : o.status === 'REJECTED' ? 't-badge-red' : 't-badge-violet'}`}
                          style={{ fontSize: 8 }}>{o.status}</span>
                      </td>
                      <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                        {o.is_paper
                          ? <span style={{ color: 'var(--amber)', fontSize: 9 }}>Paper</span>
                          : <span style={{ color: 'var(--green)', fontSize: 9 }}>Live</span>
                        }
                      </td>
                      <td style={{ padding: '6px 8px', fontSize: 9, color: 'var(--text-faint)' }}>
                        {o.created_at ? new Date(o.created_at).toLocaleString() : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      )}
    </div>
  )
}

function AuditTab() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [filterAction, setFilterAction] = useState('')

  const { data, loading } = useApi<{ entries: AdminAuditEntry[]; count: number }>(
    `/admin/audit-log?limit=100${filterAction ? `&action=${filterAction}` : ''}&_=${refreshKey}`
  )

  const entries = data?.entries || []

  const distinctActions = useMemo(() => {
    const s = new Set<string>()
    entries.forEach(e => { if (e.action) s.add(e.action) })
    return Array.from(s).sort()
  }, [entries])

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <select className="t-select" value={filterAction} onChange={e => setFilterAction(e.target.value)}
          style={{ fontSize: 11, maxWidth: 200 }}>
          <option value="">All actions</option>
          {distinctActions.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <span style={{ fontSize: 10, color: 'var(--text-sub)' }}>{data?.count || entries.length} entries</span>
        <button className="t-btn t-btn-sm" onClick={() => setRefreshKey(k => k + 1)} style={{ fontSize: 10 }}>Refresh</button>
      </div>
      {loading && <SkeletonCard />}
      {!loading && entries.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No audit entries found.</p>
        </div>
      )}
      {!loading && entries.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>TIME</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>USER ID</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>ACTION</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>RESOURCE</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>DETAILS</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(e => (
                <tr key={e.id} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                  <td style={{ padding: '6px 8px', fontSize: 9, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>
                    {e.created_at ? new Date(e.created_at).toLocaleString() : '—'}
                  </td>
                  <td style={{ padding: '6px 8px', fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--text-sub)' }}>
                    {e.user_id?.slice(0, 12)}...
                  </td>
                  <td style={{ padding: '6px 8px', fontWeight: 500 }}>
                    <span style={{
                      color: e.action?.includes('error') || e.action?.includes('fail') ? 'var(--red)'
                        : e.action?.includes('assign') || e.action?.includes('create') ? 'var(--green)'
                        : e.action?.includes('delete') || e.action?.includes('remove') || e.action?.includes('unassign') ? 'var(--amber)'
                        : 'var(--text-sub)',
                    }}>
                      {e.action}
                    </span>
                  </td>
                  <td style={{ padding: '6px 8px', color: 'var(--text-faint)' }}>{e.resource}</td>
                  <td style={{ padding: '6px 8px', fontSize: 9, color: 'var(--text-faint)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {e.details ? JSON.stringify(e.details).slice(0, 80) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function RiskTab() {
  const { data, loading } = useApi<{ settings: AdminRiskSetting[]; count: number }>('/admin/risk')
  const settings = data?.settings || []

  return (
    <div>
      <p className="t-sub" style={{ fontSize: 11, marginBottom: 12 }}>All users' risk settings &amp; controls</p>
      {loading && <SkeletonCard />}
      {!loading && settings.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No risk settings configured.</p>
        </div>
      )}
      {!loading && settings.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>USER</th>
                <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>CAPITAL</th>
                <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>MAX POS</th>
                <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>MAX LOSS</th>
                <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>DRAWDOWN</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>OPEN POS</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>KILL</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>LIVE</th>
              </tr>
            </thead>
            <tbody>
              {settings.map((s, i) => (
                <tr key={s.user_id + '-' + i} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                  <td style={{ padding: '6px 8px' }}>
                    <div style={{ fontWeight: 600, color: 'var(--text)' }}>{s.full_name || s.email?.split('@')[0] || '—'}</div>
                    <div style={{ fontSize: 8, color: 'var(--text-faint)' }}>{s.email}</div>
                  </td>
                  <td className="t-num" style={{ fontFamily: 'var(--font-mono)' }}>{s.max_capital ? `₹${s.max_capital.toLocaleString()}` : '—'}</td>
                  <td className="t-num" style={{ fontFamily: 'var(--font-mono)' }}>{s.max_position_size ? `₹${s.max_position_size.toLocaleString()}` : '—'}</td>
                  <td className="t-num" style={{ fontFamily: 'var(--font-mono)', color: s.max_daily_loss ? 'var(--red)' : 'inherit' }}>
                    {s.max_daily_loss ? `₹${s.max_daily_loss.toLocaleString()}` : '—'}
                  </td>
                  <td className="t-num" style={{ fontFamily: 'var(--font-mono)', color: s.max_drawdown_pct ? 'var(--amber)' : 'inherit' }}>
                    {s.max_drawdown_pct ? `${s.max_drawdown_pct}%` : '—'}
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>{s.max_open_positions}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    <span style={{
                      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                      background: s.kill_switch_enabled ? 'var(--red)' : 'var(--green)',
                    }} />
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    {s.is_live
                      ? <span style={{ color: 'var(--green)', fontSize: 9, fontWeight: 600 }}>LIVE</span>
                      : <span style={{ color: 'var(--amber)', fontSize: 9 }}>Paper</span>
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}


