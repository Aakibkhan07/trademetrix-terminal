'use client'

import { useState, useMemo, useCallback } from 'react'
import { useApi } from '@/lib/use-api'
import { useAuth } from '@/lib/auth-context'
import { api, AdminUser } from '@/lib/api'

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
    <div className="glass-card" style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 6 }}>
      <SkeletonLine w="50%" />
      <SkeletonLine w="70%" />
    </div>
  )
}

function SkeletonPane() {
  return (
    <div className="panel" style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <SkeletonLine w="30%" />
      <SkeletonLine w="60%" />
      <div style={{ height: 8 }} />
      <SkeletonLine w="40%" />
      <SkeletonLine w="55%" />
      <SkeletonLine w="45%" />
    </div>
  )
}

function NotAuthorized() {
  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Admin</h1>
          <p className="page-subtitle">Administration panel</p>
        </div>
      </div>
      <div className="alert alert-error">
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
        <div className="page-header">
          <h1 className="page-title">Admin</h1>
        </div>
        <SkeletonPane />
      </div>
    )
  }

  if (!isAdmin) return <NotAuthorized />

  return <AdminDashboard />
}

function AdminDashboard() {
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
      <div className="page-header">
        <div>
          <h1 className="page-title">Admin Panel</h1>
          <p className="page-subtitle">Manage users and strategy assignments</p>
        </div>
      </div>

      {usersError && (
        <div className="alert alert-error" style={{ marginBottom: 16 }}>
          {usersError.message}
        </div>
      )}

      {tierError && (
        <div className="alert alert-error" style={{ marginBottom: 12 }}>
          {tierError}
        </div>
      )}

      {tierSuccess && (
        <div className="alert alert-success" style={{ marginBottom: 12 }}>
          {tierSuccess}
        </div>
      )}

      <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>
        <div style={{ flex: '0 0 320px', minWidth: 0 }}>
          <input
            className="input"
            placeholder="Search users..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ marginBottom: 12 }}
          />

          {usersLoading && (
            <div>
              {Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)}
            </div>
          )}

          {!usersLoading && !usersError && filteredUsers.length === 0 && (
            <div style={{
              background: 'rgba(34,211,238,0.06)', border: '1px solid rgba(34,211,238,0.12)',
              borderRadius: 10, padding: '12px 16px',
            }}>
              <p style={{ margin: 0, fontSize: 13, color: '#22d3ee', fontWeight: 500 }}>
                {search ? 'No matching users' : 'No users found'}
              </p>
            </div>
          )}

          {!usersLoading && filteredUsers.map(u => (
            <div
              key={u.id}
              className="glass-card"
              onClick={() => {
                setSelectedUserId(u.id)
                setTierError('')
                setTierSuccess('')
              }}
              style={{
                padding: 12, marginBottom: 6, cursor: 'pointer',
                borderColor: selectedUserId === u.id ? 'var(--accent-violet)' : undefined,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: '#f0f0f5' }}>
                  {u.full_name || u.email.split('@')[0]}
                </span>
                <TierBadge tier={u.subscription_tier} small />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 11, color: '#555570' }}>{u.email}</span>
                <span style={{
                  fontSize: 10, color: '#8888a0', background: 'rgba(139,92,246,0.08)',
                  borderRadius: 4, padding: '1px 6px',
                }}>
                  {u.active_assignments} / {u.max_active_strategies} used
                </span>
              </div>
            </div>
          ))}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {!selectedUser && !usersLoading && (
            <div className="panel" style={{ padding: 20, textAlign: 'center' }}>
              <p style={{ margin: 0, fontSize: 13, color: '#555570' }}>
                Select a user from the list to manage their tier and strategy assignments.
              </p>
            </div>
          )}

          {selectedUser && (
            <div className="panel" style={{ padding: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                <div>
                  <h2 style={{ fontFamily: 'Outfit', fontSize: 16, margin: 0 }}>
                    {selectedUser.full_name || selectedUser.email}
                  </h2>
                  <p style={{ margin: '2px 0 0', fontSize: 11, color: '#555570' }}>
                    {selectedUser.email}
                  </p>
                </div>
                <TierBadge tier={selectedUser.subscription_tier} />
              </div>

              <div style={{ marginBottom: 20 }}>
                <label style={{ color: '#8888a0', fontSize: 11, display: 'block', marginBottom: 4, fontWeight: 600 }}>
                  Subscription Tier
                </label>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <select
                    className="select"
                    value={selectedUser.subscription_tier}
                    onChange={(e) => handleTierChange(e.target.value)}
                    disabled={tierUpdating}
                    style={{ maxWidth: 180 }}
                  >
                    {TIERS.map(t => (
                      <option key={t} value={t}>
                        {t.charAt(0).toUpperCase() + t.slice(1)}
                      </option>
                    ))}
                  </select>
                  {tierUpdating && (
                    <span style={{ fontSize: 11, color: '#8888a0' }}>Updating...</span>
                  )}
                </div>
              </div>

              <div style={{ marginBottom: 16, fontSize: 12, color: '#8888a0' }}>
                Active strategies: {activeAssignments.length} / {selectedUser.max_active_strategies}
              </div>

              <div style={{ marginBottom: 20 }}>
                <h3 style={{ fontFamily: 'Outfit', fontSize: 13, margin: '0 0 8px', color: '#f0f0f5' }}>
                  Assigned Strategies ({activeAssignments.length})
                </h3>
                {assignmentsLoading && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {Array.from({ length: 2 }).map((_, i) => (
                      <div key={i} className="glass-card" style={{ padding: 10, display: 'flex', gap: 8 }}>
                        <SkeletonLine w="30%" />
                        <SkeletonLine w="50px" />
                      </div>
                    ))}
                  </div>
                )}
                {!assignmentsLoading && activeAssignments.length === 0 && (
                  <p style={{ fontSize: 12, color: '#555570', margin: 0 }}>
                    No strategies assigned.
                  </p>
                )}
                {!assignmentsLoading && activeAssignments.map(a => {
                  const info = catalog.find(c => c.key === a.strategy_key)
                  return (
                    <div key={a.id} className="glass-card" style={{
                      padding: '8px 12px', marginBottom: 4,
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}>
                      <div>
                        <span style={{ fontSize: 12, fontWeight: 600, color: '#f0f0f5' }}>
                          {info?.name || a.strategy_key}
                        </span>
                        <span style={{ fontSize: 10, color: '#555570', marginLeft: 8 }}>
                          <TierBadge tier={a.required_tier} small />
                        </span>
                      </div>
                      <button
                        className="btn btn-sm btn-danger"
                        onClick={() => handleUnassign(a.id)}
                        style={{ fontSize: 10 }}
                      >
                        Unassign
                      </button>
                    </div>
                  )
                })}
              </div>

              <div>
                <h3 style={{ fontFamily: 'Outfit', fontSize: 13, margin: '0 0 8px', color: '#f0f0f5' }}>
                  Available to Assign ({available.length})
                </h3>
                {available.length === 0 && (
                  <p style={{ fontSize: 12, color: '#555570', margin: 0 }}>
                    All strategies assigned.
                  </p>
                )}
                {available.map(s => {
                  const userTierRank = TIER_ORDER[selectedUser.subscription_tier] ?? 0
                  const reqTierRank = TIER_ORDER[s.required_tier] ?? 99
                  const canAssign = userTierRank >= reqTierRank
                  const atLimit = activeAssignments.length >= selectedUser.max_active_strategies

                  const disabled = !canAssign || atLimit
                  const title = !canAssign
                    ? `Requires ${s.required_tier} tier`
                    : atLimit
                      ? `${selectedUser.subscription_tier} tier limit of ${selectedUser.max_active_strategies} reached`
                      : `Assign ${s.name}`

                  return (
                    <div key={s.key} className="glass-card" style={{
                      padding: '8px 12px', marginBottom: 4,
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}>
                      <div>
                        <span style={{ fontSize: 12, fontWeight: 600, color: '#f0f0f5' }}>
                          {s.name}
                        </span>
                        <span style={{ fontSize: 10, color: '#555570', marginLeft: 8 }}>
                          <TierBadge tier={s.required_tier} small />
                        </span>
                      </div>
                      <button
                        className={`btn btn-sm ${canAssign && !atLimit ? 'btn-cyan' : 'btn-secondary'}`}
                        onClick={() => !disabled && handleAssign(s.key)}
                        disabled={disabled}
                        style={{ fontSize: 10, opacity: disabled ? 0.5 : 1 }}
                        title={title}
                      >
                        {canAssign ? (atLimit ? 'limit reached' : 'Assign') : `needs ${s.required_tier}`}
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
