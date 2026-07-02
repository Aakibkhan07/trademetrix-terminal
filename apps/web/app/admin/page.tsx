'use client'

import { useState, useMemo, useCallback, useEffect } from 'react'
import { useApi } from '@/lib/use-api'
import { useAuth } from '@/lib/auth-context'
import { api, AdminUser, AdminBroker, AdminOrder, AdminAuditEntry, AdminStats } from '@/lib/api'

interface StrategyInfo {
  key: string
  name: string
  description: string
  required_tier: string
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
    free:       { bg: 'rgba(136,136,160,0.15)', text: '#8888a0', border: 'rgba(136,136,160,0.2)' },
    starter:    { bg: 'rgba(34,211,238,0.15)',  text: '#22d3ee', border: 'rgba(34,211,238,0.2)' },
    pro:        { bg: 'rgba(139,92,246,0.15)',  text: '#8b5cf6', border: 'rgba(139,92,246,0.2)' },
    enterprise: { bg: 'rgba(239,68,68,0.15)',   text: '#ef4444', border: 'rgba(239,68,68,0.2)' },
  }
  return map[tier] || map.free
}

function TierBadge({ tier, small }: { tier: string; small?: boolean }) {
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
  return <div style={{ width: w, height: 12, background: 'rgba(139,92,246,0.08)', borderRadius: 4 }} />
}

function SkeletonCard() {
  return (
    <div className="t-panel" style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 6 }}>
      <SkeletonLine w="50%" />
      <SkeletonLine w="70%" />
    </div>
  )
}

const TABS = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'users', label: 'Users' },
  { key: 'brokers', label: 'Brokers' },
  { key: 'trades', label: 'Trades' },
  { key: 'audit', label: 'Audit Log' },
  { key: 'broadcast', label: 'Broadcast' },
]

function TabBar({ active, onChange }: { active: string; onChange: (k: string) => void }) {
  return (
    <div style={{ display: 'flex', gap: 0, marginBottom: 20, borderBottom: '1px solid rgba(139,92,246,0.15)', overflowX: 'auto' }}>
      {TABS.map(t => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          style={{
            padding: '8px 16px', fontSize: 12, fontWeight: active === t.key ? 600 : 400,
            background: 'none', border: 'none', borderBottom: active === t.key ? '2px solid var(--violet)' : '2px solid transparent',
            color: active === t.key ? 'var(--violet)' : '#8888a0', cursor: 'pointer', whiteSpace: 'nowrap',
            fontFamily: 'inherit',
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

function NotAuthorized() {
  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-page-title">Control Center</h1>
        <p className="t-sub" style={{ fontSize: 13 }}>Administration panel</p>
      </div>
      <div style={{ padding: '12px 16px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, color: '#ef4444', fontSize: 13 }}>
        You do not have admin access.
      </div>
    </div>
  )
}

export default function AdminPage() {
  const { isAdmin, loading: authLoading } = useAuth()

  if (authLoading) {
    return (
      <div>
        <div style={{ marginBottom: 24 }}>
          <h1 className="t-page-title">Control Center</h1>
        </div>
        <SkeletonCard />
      </div>
    )
  }

  if (!isAdmin) return <NotAuthorized />

  return <AdminDashboard />
}

function AdminDashboard() {
  const [tab, setTab] = useState('dashboard')

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-page-title">Control Center</h1>
        <p className="t-sub" style={{ fontSize: 13 }}>Full system administration</p>
      </div>
      <TabBar active={tab} onChange={setTab} />
      {tab === 'dashboard' && <DashboardTab />}
      {tab === 'users' && <UsersTab />}
      {tab === 'brokers' && <BrokersTab />}
      {tab === 'trades' && <TradesTab />}
      {tab === 'audit' && <AuditTab />}
      {tab === 'broadcast' && <BroadcastTab />}
    </div>
  )
}

function DashboardTab() {
  const { data: statsData } = useApi<AdminStats>('/admin/stats')

  return (
    <div>
      {statsData && (
        <div className="t-grid-4" style={{ gap: 10, marginBottom: 20 }}>
          <div className="t-panel" style={{ padding: '14px 16px', borderLeft: '3px solid var(--cyan)' }}>
            <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>TOTAL USERS</div>
            <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{statsData.total_users}</div>
          </div>
          <div className="t-panel" style={{ padding: '14px 16px', borderLeft: '3px solid var(--violet)' }}>
            <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>ADMINS</div>
            <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{statsData.total_admins}</div>
          </div>
          <div className="t-panel" style={{ padding: '14px 16px', borderLeft: '3px solid var(--green)' }}>
            <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>ACTIVE ASSIGNMENTS</div>
            <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{statsData.active_assignments}</div>
          </div>
          <div className="t-panel" style={{ padding: '14px 16px', borderLeft: '3px solid var(--amber)' }}>
            <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>STRATEGIES</div>
            <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{statsData.total_strategies}</div>
          </div>
        </div>
      )}

      {statsData && (
        <div className="t-panel" style={{ padding: '14px 16px', marginBottom: 20 }}>
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
                    background: tier === 'free' ? '#8888a0' : tier === 'starter' ? '#22d3ee' : tier === 'pro' ? '#8b5cf6' : '#ef4444',
                    borderRadius: 3,
                  }} />
              )
            })}
          </div>
          <div style={{ display: 'flex', gap: 16, marginTop: 8, flexWrap: 'wrap' }}>
            {['free', 'starter', 'pro', 'enterprise'].map(tier => {
              const count = statsData.tier_distribution[tier] || 0
              if (count === 0) return null
              const color = tier === 'free' ? '#8888a0' : tier === 'starter' ? '#22d3ee' : tier === 'pro' ? '#8b5cf6' : '#ef4444'
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
        <div style={{ padding: '8px 12px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, color: '#ef4444', fontSize: 12, marginBottom: 12 }}>
          {tierError}
        </div>
      )}
      {tierSuccess && (
        <div style={{ padding: '8px 12px', background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.2)', borderRadius: 8, color: '#22c55e', fontSize: 12, marginBottom: 12 }}>
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
            <div style={{ background: 'rgba(34,211,238,0.06)', border: '1px solid rgba(34,211,238,0.12)', borderRadius: 10, padding: '12px 16px' }}>
              <p style={{ margin: 0, fontSize: 12, color: '#22d3ee', fontWeight: 500 }}>
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
                <span style={{ fontSize: 12, fontWeight: 600, color: '#f0f0f5' }}>
                  {u.full_name || u.email.split('@')[0]}
                </span>
                <TierBadge tier={u.subscription_tier} small />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 10, color: '#555570' }}>{u.email}</span>
                <span style={{ fontSize: 9, color: '#8888a0', background: 'rgba(139,92,246,0.08)', borderRadius: 4, padding: '1px 6px' }}>
                  {u.active_assignments}/{u.max_active_strategies}
                </span>
              </div>
            </div>
          ))}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {!selectedUser && !usersLoading && (
            <div className="t-panel" style={{ padding: 20, textAlign: 'center' }}>
              <p style={{ margin: 0, fontSize: 12, color: '#555570' }}>Select a user from the list.</p>
            </div>
          )}
          {selectedUser && (
            <div className="t-panel" style={{ padding: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                <div>
                  <h2 style={{ fontFamily: 'Outfit', fontSize: 15, margin: 0 }}>{selectedUser.full_name || selectedUser.email}</h2>
                  <p style={{ margin: '2px 0 0', fontSize: 10, color: '#555570' }}>{selectedUser.email}</p>
                </div>
                <TierBadge tier={selectedUser.subscription_tier} />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ color: '#8888a0', fontSize: 10, display: 'block', marginBottom: 3, fontWeight: 600 }}>Subscription Tier</label>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <select className="t-select" value={selectedUser.subscription_tier}
                    onChange={(e) => handleTierChange(e.target.value)} disabled={tierUpdating} style={{ maxWidth: 160, fontSize: 12 }}>
                    {TIERS.map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
                  </select>
                  {tierUpdating && <span style={{ fontSize: 10, color: '#8888a0' }}>Updating...</span>}
                </div>
              </div>

              <div style={{ fontSize: 11, color: '#8888a0', marginBottom: 12 }}>
                Active strategies: {activeAssignments.length}/{selectedUser.max_active_strategies}
              </div>

              <div style={{ marginBottom: 16 }}>
                <h3 style={{ fontFamily: 'Outfit', fontSize: 12, margin: '0 0 6px', color: '#f0f0f5' }}>Assigned ({activeAssignments.length})</h3>
                {assignmentsLoading && <SkeletonLine w="60%" />}
                {!assignmentsLoading && activeAssignments.length === 0 && <p style={{ fontSize: 11, color: '#555570', margin: 0 }}>None.</p>}
                {!assignmentsLoading && activeAssignments.map(a => {
                  const info = catalog.find(c => c.key === a.strategy_key)
                  return (
                    <div key={a.id} className="t-panel" style={{ padding: '6px 10px', marginBottom: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <span style={{ fontSize: 11, fontWeight: 600, color: '#f0f0f5' }}>{info?.name || a.strategy_key}</span>
                        <span style={{ fontSize: 9, color: '#555570', marginLeft: 6 }}><TierBadge tier={a.required_tier} small /></span>
                      </div>
                      <button className="t-btn t-btn-sm t-btn-danger" onClick={() => handleUnassign(a.id)} style={{ fontSize: 9 }}>Remove</button>
                    </div>
                  )
                })}
              </div>

              <div>
                <h3 style={{ fontFamily: 'Outfit', fontSize: 12, margin: '0 0 6px', color: '#f0f0f5' }}>Available ({available.length})</h3>
                {available.length === 0 && <p style={{ fontSize: 11, color: '#555570', margin: 0 }}>All assigned.</p>}
                {available.map(s => {
                  const userTierRank = TIER_ORDER[selectedUser.subscription_tier] ?? 0
                  const reqTierRank = TIER_ORDER[s.required_tier] ?? 99
                  const canAssign = userTierRank >= reqTierRank
                  const atLimit = activeAssignments.length >= selectedUser.max_active_strategies
                  const disabled = !canAssign || atLimit
                  return (
                    <div key={s.key} className="t-panel" style={{ padding: '6px 10px', marginBottom: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <span style={{ fontSize: 11, fontWeight: 600, color: '#f0f0f5' }}>{s.name}</span>
                        <span style={{ fontSize: 9, color: '#555570', marginLeft: 6 }}><TierBadge tier={s.required_tier} small /></span>
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

  const brokers = data?.brokers || []

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <p className="t-sub" style={{ fontSize: 12, margin: 0 }}>All users' broker connections &amp; OAuth status</p>
        <button className="t-btn t-btn-sm" onClick={() => setRefreshKey(k => k + 1)} style={{ fontSize: 10 }}>Refresh</button>
      </div>
      {loading && <SkeletonCard />}
      {!loading && brokers.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: '#555570' }}>No broker connections found.</p>
        </div>
      )}
      {!loading && brokers.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="t-table" style={{ fontSize: 11, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(139,92,246,0.12)' }}>
                <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>USER</th>
                <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>BROKER</th>
                <th style={{ padding: '8px 10px', textAlign: 'center', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>ACTIVE</th>
                <th style={{ padding: '8px 10px', textAlign: 'center', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>OAUTH</th>
                <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>CONNECTED</th>
              </tr>
            </thead>
            <tbody>
              {brokers.map(b => (
                <tr key={b.id} style={{ borderBottom: '1px solid rgba(139,92,246,0.06)' }}>
                  <td style={{ padding: '8px 10px' }}>
                    <div style={{ fontWeight: 600, color: '#f0f0f5' }}>{b.full_name || b.email?.split('@')[0] || '—'}</div>
                    <div style={{ fontSize: 9, color: '#555570' }}>{b.email}</div>
                  </td>
                  <td style={{ padding: '8px 10px', textTransform: 'capitalize' }}>{b.broker}</td>
                  <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                    <span style={{
                      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                      background: b.is_active ? '#22c55e' : '#555570',
                    }} />
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                    {b.has_access_token
                      ? <span style={{ color: '#22c55e', fontSize: 10 }}>Authenticated</span>
                      : <span style={{ color: '#ef4444', fontSize: 10 }}>Not authorized</span>
                    }
                  </td>
                  <td style={{ padding: '8px 10px', fontSize: 10, color: '#555570' }}>
                    {b.created_at ? new Date(b.created_at).toLocaleDateString() : '—'}
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

  const params = new URLSearchParams()
  if (filterUser) params.set('user_id', filterUser)
  if (filterPaper) params.set('is_paper', filterPaper)

  const { data, loading } = useApi<{ orders: AdminOrder[]; count: number }>(
    `/admin/orders?limit=100&${params.toString()}&_=${refreshKey}`
  )

  const orders = data?.orders || []

  useEffect(() => {
    const int = setInterval(() => setRefreshKey(k => k + 1), 10000)
    return () => clearInterval(int)
  }, [])

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <input className="t-input" placeholder="Filter by user ID" value={filterUser}
          onChange={e => setFilterUser(e.target.value)} style={{ width: 200, fontSize: 11 }} />
        <select className="t-select" value={filterPaper} onChange={e => setFilterPaper(e.target.value)}
          style={{ fontSize: 11, maxWidth: 120 }}>
          <option value="">All types</option>
          <option value="true">Paper</option>
          <option value="false">Live</option>
        </select>
        <span style={{ fontSize: 10, color: '#8888a0' }}>{data?.count || orders.length} orders</span>
        <span style={{ fontSize: 10, color: '#555570' }}>(auto-refreshes)</span>
      </div>
      {loading && <SkeletonCard />}
      {!loading && orders.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: '#555570' }}>No orders found.</p>
        </div>
      )}
      {!loading && orders.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(139,92,246,0.12)' }}>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 8 }}>USER</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 8 }}>SYMBOL</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 8 }}>SIDE</th>
                <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: '#8888a0', fontSize: 8 }}>QTY</th>
                <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: '#8888a0', fontSize: 8 }}>PRICE</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 8 }}>BROKER</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: '#8888a0', fontSize: 8 }}>STATUS</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: '#8888a0', fontSize: 8 }}>TYPE</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 8 }}>AT</th>
              </tr>
            </thead>
            <tbody>
              {orders.map(o => (
                <tr key={o.id} style={{ borderBottom: '1px solid rgba(139,92,246,0.06)' }}>
                  <td style={{ padding: '6px 8px' }}>
                    <div style={{ color: '#f0f0f5', fontWeight: 500 }}>{o.full_name || '—'}</div>
                    <div style={{ fontSize: 8, color: '#555570' }}>{o.email}</div>
                  </td>
                  <td style={{ padding: '6px 8px', fontWeight: 600, color: '#f0f0f5' }}>{o.symbol}</td>
                  <td style={{ padding: '6px 8px', color: o.side === 'BUY' ? '#22c55e' : '#ef4444', fontWeight: 600 }}>{o.side}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{o.quantity}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{o.price ? o.price.toFixed(2) : '—'}</td>
                  <td style={{ padding: '6px 8px', textTransform: 'capitalize' }}>{o.broker}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    <span style={{
                      color: o.status === 'FILLED' || o.status === 'OPEN' ? '#22c55e'
                        : o.status === 'REJECTED' ? '#ef4444' : '#f59e0b',
                      fontSize: 9, fontWeight: 600,
                    }}>
                      {o.status}
                    </span>
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    {o.is_paper
                      ? <span style={{ color: '#f59e0b', fontSize: 9 }}>Paper</span>
                      : <span style={{ color: '#22c55e', fontSize: 9 }}>Live</span>
                    }
                  </td>
                  <td style={{ padding: '6px 8px', fontSize: 9, color: '#555570' }}>
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
        <span style={{ fontSize: 10, color: '#8888a0' }}>{data?.count || entries.length} entries</span>
        <button className="t-btn t-btn-sm" onClick={() => setRefreshKey(k => k + 1)} style={{ fontSize: 10 }}>Refresh</button>
      </div>
      {loading && <SkeletonCard />}
      {!loading && entries.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: '#555570' }}>No audit entries found.</p>
        </div>
      )}
      {!loading && entries.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(139,92,246,0.12)' }}>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 8 }}>TIME</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 8 }}>USER ID</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 8 }}>ACTION</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 8 }}>RESOURCE</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 8 }}>DETAILS</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(e => (
                <tr key={e.id} style={{ borderBottom: '1px solid rgba(139,92,246,0.06)' }}>
                  <td style={{ padding: '6px 8px', fontSize: 9, color: '#555570', whiteSpace: 'nowrap' }}>
                    {e.created_at ? new Date(e.created_at).toLocaleString() : '—'}
                  </td>
                  <td style={{ padding: '6px 8px', fontFamily: 'var(--font-mono)', fontSize: 8, color: '#8888a0' }}>
                    {e.user_id?.slice(0, 12)}...
                  </td>
                  <td style={{ padding: '6px 8px', fontWeight: 500 }}>
                    <span style={{
                      color: e.action?.includes('error') || e.action?.includes('fail') ? '#ef4444'
                        : e.action?.includes('assign') || e.action?.includes('create') ? '#22c55e'
                        : e.action?.includes('delete') || e.action?.includes('remove') || e.action?.includes('unassign') ? '#f59e0b'
                        : '#8888a0',
                    }}>
                      {e.action}
                    </span>
                  </td>
                  <td style={{ padding: '6px 8px', color: '#555570' }}>{e.resource}</td>
                  <td style={{ padding: '6px 8px', fontSize: 9, color: '#555570', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
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

function BroadcastTab() {
  const [strategyKey, setStrategyKey] = useState('')
  const [symbol, setSymbol] = useState('')
  const [action, setAction] = useState('BUY')
  const [quantity, setQuantity] = useState(1)
  const [price, setPrice] = useState(0)
  const [exchange, setExchange] = useState('NSE')
  const [orderType, setOrderType] = useState('MARKET')
  const [product, setProduct] = useState('INTRADAY')
  const [reason, setReason] = useState('')
  const [paper, setPaper] = useState(true)
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')

  const { data: catalogData } = useApi<{ strategies: StrategyInfo[] }>('/strategies/list-builtin')
  const catalog = catalogData?.strategies || []

  const handleBroadcast = async () => {
    if (!strategyKey || !symbol || !action || !quantity) {
      setError('Fill required fields')
      return
    }
    setSending(true)
    setError('')
    setResult(null)
    try {
      const res = await api.admin.broadcast.send({
        strategy_key: strategyKey, symbol, action, quantity,
        price: price || undefined, exchange, order_type: orderType,
        product, reason, paper,
      })
      setResult(res)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Broadcast failed')
    } finally {
      setSending(false)
    }
  }

  return (
    <div>
      <div className="t-panel" style={{ padding: 16, maxWidth: 600 }}>
        <h3 style={{ fontFamily: 'Outfit', fontSize: 13, margin: '0 0 12px', color: '#f0f0f5' }}>Broadcast Trade to Strategy Recipients</h3>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
          <div>
            <label style={{ fontSize: 9, color: '#8888a0', display: 'block', marginBottom: 2 }}>Strategy</label>
            <select className="t-select" value={strategyKey} onChange={e => setStrategyKey(e.target.value)} style={{ fontSize: 11, width: '100%' }}>
              <option value="">Select...</option>
              {catalog.map(s => <option key={s.key} value={s.key}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 9, color: '#8888a0', display: 'block', marginBottom: 2 }}>Symbol</label>
            <input className="t-input" value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} placeholder="e.g. RELIANCE" style={{ fontSize: 11, width: '100%' }} />
          </div>
          <div>
            <label style={{ fontSize: 9, color: '#8888a0', display: 'block', marginBottom: 2 }}>Action</label>
            <select className="t-select" value={action} onChange={e => setAction(e.target.value)} style={{ fontSize: 11, width: '100%' }}>
              <option value="BUY">BUY</option>
              <option value="SELL">SELL</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: 9, color: '#8888a0', display: 'block', marginBottom: 2 }}>Quantity</label>
            <input className="t-input" type="number" value={quantity} onChange={e => setQuantity(Number(e.target.value))} style={{ fontSize: 11, width: '100%' }} />
          </div>
          <div>
            <label style={{ fontSize: 9, color: '#8888a0', display: 'block', marginBottom: 2 }}>Price</label>
            <input className="t-input" type="number" step="0.01" value={price} onChange={e => setPrice(Number(e.target.value))} placeholder="0 = market" style={{ fontSize: 11, width: '100%' }} />
          </div>
          <div>
            <label style={{ fontSize: 9, color: '#8888a0', display: 'block', marginBottom: 2 }}>Exchange</label>
            <select className="t-select" value={exchange} onChange={e => setExchange(e.target.value)} style={{ fontSize: 11, width: '100%' }}>
              <option>NSE</option>
              <option>BSE</option>
              <option>NFO</option>
              <option>MCX</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: 9, color: '#8888a0', display: 'block', marginBottom: 2 }}>Order Type</label>
            <select className="t-select" value={orderType} onChange={e => setOrderType(e.target.value)} style={{ fontSize: 11, width: '100%' }}>
              <option>MARKET</option>
              <option>LIMIT</option>
              <option>SL</option>
              <option>SL-M</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: 9, color: '#8888a0', display: 'block', marginBottom: 2 }}>Product</label>
            <select className="t-select" value={product} onChange={e => setProduct(e.target.value)} style={{ fontSize: 11, width: '100%' }}>
              <option>INTRADAY</option>
              <option>DELIVERY</option>
              <option>FNO</option>
              <option>CURRENCY</option>
            </select>
          </div>
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 9, color: '#8888a0', display: 'block', marginBottom: 2 }}>Reason (optional)</label>
          <input className="t-input" value={reason} onChange={e => setReason(e.target.value)} style={{ fontSize: 11, width: '100%' }} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <input type="checkbox" id="paper-mode" checked={paper} onChange={e => setPaper(e.target.checked)}
            style={{ accentColor: '#8b5cf6' }} />
          <label htmlFor="paper-mode" style={{ fontSize: 11, color: '#8888a0' }}>Paper trade (simulated)</label>
        </div>

        {error && (
          <div style={{ padding: '8px 12px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, color: '#ef4444', fontSize: 11, marginBottom: 12 }}>
            {error}
          </div>
        )}

        <button className="t-btn" onClick={handleBroadcast} disabled={sending}
          style={{ fontSize: 12, padding: '8px 20px' }}>
          {sending ? 'Broadcasting...' : 'Broadcast Trade'}
        </button>

        {result && (
          <div style={{ marginTop: 16 }}>
            <h4 style={{ fontSize: 11, color: '#f0f0f5', margin: '0 0 8px' }}>
              Results ({result.count} recipients, {result.paper ? 'paper' : 'live'})
            </h4>
            {result.results?.map((r: any, i: number) => (
              <div key={i} className="t-panel" style={{
                padding: '8px 10px', marginBottom: 4, fontSize: 10,
                borderLeft: r.success ? '3px solid #22c55e' : '3px solid #ef4444',
              }}>
                <div style={{ fontWeight: 600, color: '#f0f0f5' }}>{r.full_name || r.email}</div>
                <div style={{ color: r.success ? '#22c55e' : '#ef4444' }}>
                  {r.success ? `✓ Order placed (${r.broker_order_id})` : `✗ ${r.message}`}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
