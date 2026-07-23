'use client'

import { useState } from 'react'
import { useApi } from '@/lib/use-api'

interface Referral {
  id: string
  referrer_id: string
  referred_user_id: string | null
  referred_email: string
  status: string
  reward_given: boolean
  created_at: string
  completed_at: string | null
  referrer_name: string
  referrer_email: string
  referred_name: string
}

interface ReferralStats {
  total_referrals: number
  completed_referrals: number
  pending_referrals: number
  users_with_referral_codes: number
  conversion_rate: number
}

export function ReferralsTab() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [statusFilter, setStatusFilter] = useState('')

  const { data, loading } = useApi<{ referrals: Referral[] }>(
    `/admin/referrals?${statusFilter ? `status=${statusFilter}` : ''}&_=${refreshKey}`
  )
  const { data: statsData } = useApi<ReferralStats>(`/admin/referrals/stats?_=${refreshKey}`)
  const stats = statsData as ReferralStats | undefined
  const referrals = data?.referrals || []

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <div className="t-panel" style={{ flex: '1 1 140px', padding: '10px 14px', minWidth: 120 }}>
          <p style={{ margin: 0, fontSize: 9, color: 'var(--text-faint)', textTransform: 'uppercase' }}>Total</p>
          <p style={{ margin: '4px 0 0', fontSize: 18, fontWeight: 700 }}>{stats?.total_referrals ?? '—'}</p>
        </div>
        <div className="t-panel" style={{ flex: '1 1 140px', padding: '10px 14px', minWidth: 120 }}>
          <p style={{ margin: 0, fontSize: 9, color: 'var(--text-faint)', textTransform: 'uppercase' }}>Completed</p>
          <p style={{ margin: '4px 0 0', fontSize: 18, fontWeight: 700, color: 'var(--green)' }}>{stats?.completed_referrals ?? '—'}</p>
        </div>
        <div className="t-panel" style={{ flex: '1 1 140px', padding: '10px 14px', minWidth: 120 }}>
          <p style={{ margin: 0, fontSize: 9, color: 'var(--text-faint)', textTransform: 'uppercase' }}>Conversion</p>
          <p style={{ margin: '4px 0 0', fontSize: 18, fontWeight: 700, color: 'var(--violet)' }}>{stats?.conversion_rate ?? 0}%</p>
        </div>
        <div className="t-panel" style={{ flex: '1 1 140px', padding: '10px 14px', minWidth: 120 }}>
          <p style={{ margin: 0, fontSize: 9, color: 'var(--text-faint)', textTransform: 'uppercase' }}>Users w/ Codes</p>
          <p style={{ margin: '4px 0 0', fontSize: 18, fontWeight: 700 }}>{stats?.users_with_referral_codes ?? '—'}</p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <select className="t-input" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          style={{ fontSize: 11, maxWidth: 180 }}>
          <option value="">— All statuses —</option>
          <option value="pending">Pending</option>
          <option value="completed">Completed</option>
          <option value="expired">Expired</option>
        </select>
        <span style={{ fontSize: 10, color: 'var(--text-sub)' }}>{referrals.length} referrals</span>
        <button className="t-btn t-btn-sm" onClick={() => setRefreshKey(k => k + 1)} style={{ fontSize: 10 }}>Refresh</button>
      </div>

      {loading && <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}><p style={{ fontSize: 12, color: 'var(--text-faint)' }}>Loading...</p></div>}
      {!loading && referrals.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No referrals yet.</p>
        </div>
      )}

      {!loading && referrals.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>REFERRER</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>REFERRED</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>STATUS</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>REWARD</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>DATE</th>
              </tr>
            </thead>
            <tbody>
              {referrals.map(r => (
                <tr key={r.id} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                  <td style={{ padding: '6px 8px' }}>
                    <div style={{ fontWeight: 600, color: 'var(--text)' }}>{r.referrer_name || r.referrer_email}</div>
                    <div style={{ fontSize: 8, color: 'var(--text-faint)' }}>{r.referrer_email}</div>
                  </td>
                  <td style={{ padding: '6px 8px' }}>
                    <div style={{ color: 'var(--text)' }}>{r.referred_name || '—'}</div>
                    <div style={{ fontSize: 8, color: 'var(--text-faint)' }}>{r.referred_email}</div>
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    <span style={{
                      fontSize: 9, fontWeight: 600,
                      color: r.status === 'completed' ? 'var(--green)' : r.status === 'pending' ? 'var(--amber)' : 'var(--text-faint)',
                    }}>{r.status}</span>
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    <span style={{
                      display: 'inline-block', fontSize: 9,
                      color: r.reward_given ? 'var(--green)' : 'var(--text-faint)',
                    }}>{r.reward_given ? '✓' : '—'}</span>
                  </td>
                  <td style={{ padding: '6px 8px', fontSize: 9, color: 'var(--text-faint)' }}>
                    {r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}
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
