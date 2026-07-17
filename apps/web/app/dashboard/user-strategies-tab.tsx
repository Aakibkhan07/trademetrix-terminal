'use client'

import { useState } from 'react'
import { useApi } from '@/lib/use-api'
import { AdminUser } from '@/lib/api'

interface UserStrategy {
  id: string
  user_id: string
  name: string
  type: string
  is_active: boolean
  status: string
  created_at: string
  updated_at: string
  config?: Record<string, unknown>
}

export function UserStrategiesTab() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [userFilter, setUserFilter] = useState('')
  const [deleting, setDeleting] = useState<string | null>(null)

  const { data, loading } = useApi<{ strategies: UserStrategy[] }>(
    `/admin/strategies/all-user?_=${refreshKey}${userFilter ? `&user_id=${userFilter}` : ''}`
  )
  const { data: usersData } = useApi<{ users: AdminUser[] }>('/admin/users')
  const users = usersData?.users || []
  const strategies = data?.strategies || []

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this strategy?')) return
    setDeleting(id)
    try {
      await fetch(`/api/v1/user-strategies/${id}`, { method: 'DELETE' })
      setRefreshKey(k => k + 1)
    } catch {}
    setDeleting(null)
  }

  const userName = (uid: string) => {
    const u = users.find(u => u.id === uid)
    return u?.full_name || u?.email?.split('@')[0] || uid.slice(0, 8)
  }

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
        <span style={{ fontSize: 10, color: 'var(--text-sub)' }}>{strategies.length} strategies</span>
        <button className="t-btn t-btn-sm" onClick={() => setRefreshKey(k => k + 1)} style={{ fontSize: 10 }}>Refresh</button>
        <a href="/strategies/builder" target="_blank" className="t-btn t-btn-sm"
          style={{ fontSize: 10, background: 'color-mix(in srgb, var(--violet) 12%, transparent)', borderColor: 'color-mix(in srgb, var(--violet) 20%, transparent)', color: 'var(--violet)', textDecoration: 'none' }}>
          Open Builder →
        </a>
      </div>

      {loading && <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}><p style={{ fontSize: 12, color: 'var(--text-faint)' }}>Loading...</p></div>}
      {!loading && strategies.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No user strategies found.</p>
        </div>
      )}

      {!loading && strategies.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>NAME</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>USER</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>TYPE</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>STATUS</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>ACTIVE</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>CREATED</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map(s => (
                <tr key={s.id} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                  <td style={{ padding: '6px 8px', fontWeight: 600, color: 'var(--text)' }}>{s.name}</td>
                  <td style={{ padding: '6px 8px', fontSize: 9, color: 'var(--text-sub)' }}>{userName(s.user_id)}</td>
                  <td style={{ padding: '6px 8px', textTransform: 'capitalize', fontSize: 9 }}>{s.type || '—'}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    <span style={{
                      fontSize: 9, fontWeight: 600,
                      color: s.status === 'active' ? 'var(--green)' : s.status === 'paused' ? 'var(--amber)' : 'var(--text-faint)',
                    }}>{s.status || 'draft'}</span>
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    <span style={{
                      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                      background: s.is_active ? 'var(--green)' : 'var(--text-faint)',
                    }} />
                  </td>
                  <td style={{ padding: '6px 8px', fontSize: 9, color: 'var(--text-faint)' }}>
                    {s.created_at ? new Date(s.created_at).toLocaleDateString() : '—'}
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    <button onClick={() => handleDelete(s.id)} disabled={deleting === s.id}
                      style={{
                        padding: '2px 8px', fontSize: 8, borderRadius: 3, border: 'none', cursor: 'pointer',
                        background: 'color-mix(in srgb, var(--red) 12%, transparent)', color: 'var(--red)',
                      }}>
                      {deleting === s.id ? '...' : 'Delete'}
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
