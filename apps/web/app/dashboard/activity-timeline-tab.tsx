'use client'

import { useState, useMemo } from 'react'
import { useApi } from '@/lib/use-api'
import { AdminUser } from '@/lib/api'

interface AuditEntry {
  id: number
  user_id: string
  action: string
  resource: string
  resource_id: string
  details: Record<string, unknown> | null
  ip_address: string
  created_at: string
}

const ACTION_ICONS: Record<string, string> = {
  signin: '🔑',
  signout: '🚪',
  signup: '✨',
  otp_verify: '📱',
  send_otp: '📨',
  register_with_otp: '📝',
  forgot_password: '🔒',
  change_password: '🔐',
  assign_strategy: '📌',
  unassign_strategy: '🗑️',
  update_tier: '⬆️',
  broadcast_notify: '📢',
  order_executed: '💰',
  order_failed: '❌',
}

function ActionIcon({ action }: { action: string }) {
  const icon = ACTION_ICONS[action] || '•'
  return <span style={{ fontSize: 14 }}>{icon}</span>
}

function ActionLabel({ action }: { action: string }) {
  const labels: Record<string, string> = {
    signin: 'Signed in',
    signout: 'Signed out',
    signup: 'Registered',
    otp_verify: 'Verified OTP',
    send_otp: 'Requested OTP',
    register_with_otp: 'Registered with OTP',
    forgot_password: 'Requested password reset',
    change_password: 'Changed password',
    assign_strategy: 'Strategy assigned',
    unassign_strategy: 'Strategy unassigned',
    update_tier: 'Tier changed',
    broadcast_notify: 'Broadcast sent',
    order_executed: 'Order executed',
    order_failed: 'Order failed',
  }
  return <span style={{ fontWeight: 500, fontSize: 11 }}>{labels[action] || action}</span>
}

function UserBadge({ userId, userMap }: { userId: string; userMap: Record<string, AdminUser> }) {
  const u = userMap[userId]
  if (!u) return <span style={{ fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--text-faint)' }}>{userId.slice(0, 8)}</span>
  return (
    <span style={{ fontSize: 10, fontWeight: 500, color: 'var(--text)' }}>
      {u.full_name || u.email?.split('@')[0] || userId.slice(0, 8)}
    </span>
  )
}

export function ActivityTimelineTab() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [userFilter, setUserFilter] = useState('')
  const [actionFilter, setActionFilter] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')

  const params: Record<string, string> = { limit: '100' }
  if (userFilter) params.user_id = userFilter
  if (actionFilter) params.action = actionFilter
  if (fromDate) params.from_date = fromDate
  if (toDate) params.to_date = toDate

  const { data, loading } = useApi<{ entries: AuditEntry[]; count: number }>(
    `/admin/audit-log?${new URLSearchParams(params)}&_=${refreshKey}`
  )
  const { data: usersData } = useApi<{ users: AdminUser[] }>('/admin/users')

  const users = usersData?.users || []
  const entries = data?.entries || []
  const userMap = useMemo(() => {
    const m: Record<string, AdminUser> = {}
    users.forEach(u => { m[u.id] = u })
    return m
  }, [users])

  const distinctActions = useMemo(() => {
    const s = new Set<string>()
    entries.forEach(e => { if (e.action) s.add(e.action) })
    return Array.from(s).sort()
  }, [entries])

  const groupByDate = useMemo(() => {
    const groups: Record<string, AuditEntry[]> = {}
    entries.forEach(e => {
      const date = e.created_at ? new Date(e.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : 'Unknown'
      if (!groups[date]) groups[date] = []
      groups[date].push(e)
    })
    return groups
  }, [entries])

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <select className="t-input" value={userFilter} onChange={e => setUserFilter(e.target.value)}
          style={{ fontSize: 11, maxWidth: 220 }}>
          <option value="">— All users —</option>
          {users.map(u => (
            <option key={u.id} value={u.id}>{u.full_name || u.email} ({u.email})</option>
          ))}
        </select>
        <select className="t-input" value={actionFilter} onChange={e => setActionFilter(e.target.value)}
          style={{ fontSize: 11, maxWidth: 160 }}>
          <option value="">All actions</option>
          {Object.entries(ACTION_ICONS).map(([a, icon]) => (
            <option key={a} value={a}>{icon} {a.replace(/_/g, ' ')}</option>
          ))}
        </select>
        <input className="t-input" type="date" value={fromDate}
          onChange={e => setFromDate(e.target.value)} style={{ width: 130, fontSize: 11 }} />
        <input className="t-input" type="date" value={toDate}
          onChange={e => setToDate(e.target.value)} style={{ width: 130, fontSize: 11 }} />
        <span style={{ fontSize: 10, color: 'var(--text-sub)' }}>{entries.length} events</span>
        <button className="t-btn t-btn-sm" onClick={() => setRefreshKey(k => k + 1)} style={{ fontSize: 10 }}>Refresh</button>
      </div>

      {loading && (
        <div className="t-panel" style={{ padding: 16 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {[1, 2, 3, 4].map(i => (
              <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'color-mix(in srgb, var(--violet) 8%, transparent)' }} />
                <div style={{ flex: 1 }}>
                  <div style={{ width: '40%', height: 10, background: 'color-mix(in srgb, var(--violet) 8%, transparent)', borderRadius: 4 }} />
                  <div style={{ height: 4 }} />
                  <div style={{ width: '60%', height: 8, background: 'color-mix(in srgb, var(--violet) 6%, transparent)', borderRadius: 4 }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && entries.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No activity found.</p>
        </div>
      )}

      {!loading && entries.length > 0 && (
        <div style={{ position: 'relative' }}>
          {Object.entries(groupByDate).map(([date, items]) => (
            <div key={date} style={{ marginBottom: 20 }}>
              <div style={{
                position: 'sticky', top: 0, zIndex: 1,
                padding: '4px 12px', marginBottom: 8,
                fontSize: 10, fontWeight: 600, color: 'var(--text-sub)',
                background: 'color-mix(in srgb, var(--bg) 90%, transparent)',
                backdropFilter: 'blur(8px)',
                borderRadius: 4,
              }}>{date}</div>
              <div style={{ position: 'relative', paddingLeft: 32 }}>
                <div style={{
                  position: 'absolute', left: 14, top: 0, bottom: 0,
                  width: 2, background: 'color-mix(in srgb, var(--violet) 12%, transparent)',
                }} />
                {items.map(e => {
                  const details = e.details ? Object.entries(e.details).map(([k, v]) => `${k}: ${v}`).join(', ') : ''
                  return (
                    <div key={e.id} style={{
                      position: 'relative',
                      padding: '8px 12px', marginBottom: 4,
                      borderRadius: 6,
                      background: 'color-mix(in srgb, var(--violet) 3%, transparent)',
                      border: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)',
                    }}>
                      <div style={{
                        position: 'absolute', left: -26, top: 10,
                        width: 20, height: 20, borderRadius: '50%',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        background: 'color-mix(in srgb, var(--violet) 10%, transparent)',
                        border: '2px solid color-mix(in srgb, var(--violet) 15%, transparent)',
                      }}>
                        <ActionIcon action={e.action} />
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                        <ActionLabel action={e.action} />
                        <span style={{ fontSize: 9, color: 'var(--text-sub)' }}>by</span>
                        <UserBadge userId={e.user_id} userMap={userMap} />
                        <span style={{ fontSize: 9, color: 'var(--text-faint)', marginLeft: 'auto' }}>
                          {e.created_at ? new Date(e.created_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : ''}
                        </span>
                      </div>
                      {details && (
                        <div style={{ fontSize: 9, color: 'var(--text-faint)', marginTop: 2 }}>{details}</div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
