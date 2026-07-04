'use client'

import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '@/lib/auth-context'
import { api } from '@/lib/api'

const ROLES = ['super_admin', 'admin', 'support', 'analyst'] as const
const ROLE_LABELS: Record<string, string> = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  support: 'Support',
  analyst: 'Analyst',
}
const ROLE_COLORS: Record<string, string> = {
  super_admin: '#ef4444',
  admin: '#8b5cf6',
  support: '#22d3ee',
  analyst: '#f59e0b',
}

type AdminUser = {
  id: string
  email: string
  full_name: string
  is_admin: boolean
  role: string
}

function RoleBadge({ role }: { role: string }) {
  const color = ROLE_COLORS[role] || '#8888a0'
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 8px', borderRadius: 4, fontSize: 9, fontWeight: 500,
      background: `${color}22`, color,
      border: `1px solid ${color}44`,
      textTransform: 'capitalize',
    }}>
      {ROLE_LABELS[role] || role}
    </span>
  )
}

function SkeletonLine({ w }: { w: string }) {
  return <div style={{ width: w, height: 12, background: 'rgba(139,92,246,0.08)', borderRadius: 4 }} />
}

export default function AdminsPage() {
  const { user: currentUser } = useAuth()
  const [admins, setAdmins] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  const [showForm, setShowForm] = useState(false)
  const [newEmail, setNewEmail] = useState('')
  const [newRole, setNewRole] = useState('admin')
  const [submitting, setSubmitting] = useState(false)

  const isSuperAdmin = currentUser?.role === 'super_admin'

  const fetchAdmins = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const res = await api.admin.admins.list()
      setAdmins(res.admins)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchAdmins() }, [fetchAdmins, refreshKey])

  const handleCreate = async () => {
    if (!newEmail.trim()) return
    setSubmitting(true); setError('')
    try {
      await api.admin.admins.create({ email: newEmail.trim(), role: newRole })
      setShowForm(false); setNewEmail(''); setNewRole('admin')
      setRefreshKey(k => k + 1)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create admin')
    } finally {
      setSubmitting(false)
    }
  }

  const handleRoleChange = async (userId: string, role: string) => {
    try {
      await api.admin.admins.updateRole(userId, { role })
      setRefreshKey(k => k + 1)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update role')
    }
  }

  const handleRemove = async (userId: string, email: string) => {
    if (!confirm(`Remove admin access for ${email}?`)) return
    try {
      await api.admin.admins.remove(userId)
      setRefreshKey(k => k + 1)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to remove admin')
    }
  }

  const sorted = [...admins].sort((a, b) => {
    const order = ['super_admin', 'admin', 'support', 'analyst', '']
    return (order.indexOf(a.role) - order.indexOf(b.role)) || a.email.localeCompare(b.email)
  })

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <p className="t-sub" style={{ fontSize: 12, margin: 0 }}>
          {admins.length} admin{admins.length !== 1 ? 's' : ''} configured
        </p>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="t-btn t-btn-sm" onClick={() => setRefreshKey(k => k + 1)} style={{ fontSize: 10 }}>Refresh</button>
          {isSuperAdmin && (
            <button className="t-btn t-btn-sm" onClick={() => setShowForm(!showForm)}
              style={{ fontSize: 10, background: 'var(--violet)', color: '#fff' }}>
              {showForm ? 'Cancel' : '+ Add Admin'}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div style={{ padding: '8px 12px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, color: '#ef4444', fontSize: 12, marginBottom: 12 }}>
          {error}
        </div>
      )}

      {showForm && (
        <div className="t-panel" style={{ padding: 16, marginBottom: 16, maxWidth: 500 }}>
          <h3 style={{ fontFamily: 'Outfit', fontSize: 13, margin: '0 0 12px', color: '#f0f0f5' }}>Add Admin User</h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 12 }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 9, color: '#8888a0', display: 'block', marginBottom: 2 }}>User Email</label>
              <input className="t-input" value={newEmail} onChange={e => setNewEmail(e.target.value)}
                placeholder="user@example.com" style={{ fontSize: 11, width: '100%' }} />
            </div>
            <div style={{ flex: '0 0 140px' }}>
              <label style={{ fontSize: 9, color: '#8888a0', display: 'block', marginBottom: 2 }}>Role</label>
              <select className="t-select" value={newRole} onChange={e => setNewRole(e.target.value)}
                style={{ fontSize: 11, width: '100%' }}>
                {ROLES.filter(r => r !== 'super_admin').map(r => (
                  <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                ))}
              </select>
            </div>
          </div>
          <button className="t-btn" onClick={handleCreate} disabled={submitting || !newEmail.trim()}
            style={{ fontSize: 11, padding: '6px 16px' }}>
            {submitting ? 'Adding...' : 'Add Admin'}
          </button>
        </div>
      )}

      {loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="t-panel" style={{ padding: 12 }}>
              <SkeletonLine w="40%" />
              <SkeletonLine w="60%" />
            </div>
          ))}
        </div>
      )}

      {!loading && sorted.length === 0 && (
        <div className="t-panel" style={{ padding: 20, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: '#555570' }}>No admin users found.</p>
        </div>
      )}

      {!loading && sorted.length > 0 && (
        <div>
          {sorted.map(a => {
            const isSelf = a.id === currentUser?.id
            const canManage = isSuperAdmin && !isSelf && a.role !== 'super_admin'
            return (
              <div key={a.id} className="t-panel" style={{
                padding: '10px 14px', marginBottom: 6,
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                borderLeft: `3px solid ${ROLE_COLORS[a.role] || '#8888a0'}`,
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: '#f0f0f5' }}>
                      {a.full_name || a.email.split('@')[0]}
                      {isSelf && <span style={{ fontSize: 9, color: '#8888a0', marginLeft: 6, fontWeight: 400 }}>(you)</span>}
                    </span>
                    <RoleBadge role={a.role} />
                  </div>
                  <div style={{ fontSize: 10, color: '#555570' }}>{a.email}</div>
                </div>
                {canManage && (
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <select className="t-select" value={a.role}
                      onChange={e => handleRoleChange(a.id, e.target.value)}
                      style={{ fontSize: 10, maxWidth: 120 }}>
                      {ROLES.filter(r => r !== 'super_admin').map(r => (
                        <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                      ))}
                    </select>
                    <button className="t-btn t-btn-sm t-btn-danger"
                      onClick={() => handleRemove(a.id, a.email)}
                      style={{ fontSize: 9 }}>Remove</button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
