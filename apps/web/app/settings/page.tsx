'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth-context'
import { useTheme } from '@/lib/use-theme'
import { api } from '@/lib/api'

interface BrokerCred {
  broker: string
  is_active: boolean
  created_at: string
}

interface AssignedStrategy {
  strategy_key: string
  name: string
  description: string
  required_tier: string
}

const TIER_COLORS: Record<string, string> = {
  free: 't-badge-sub',
  starter: 't-badge-cyan',
  pro: 't-badge-violet',
  enterprise: 't-badge-amber',
}

const TIER_LIMITS: Record<string, string> = {
  free: '1 active strategy, basic market data',
  starter: '3 active strategies, delayed data',
  pro: '10 active strategies, real-time data, backtesting',
  enterprise: 'Unlimited strategies, real-time data, priority support',
}

export default function SettingsPage() {
  const { user, tier } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const [creds, setCreds] = useState<BrokerCred[]>([])
  const [strategies, setStrategies] = useState<AssignedStrategy[]>([])
  const [loading, setLoading] = useState(true)
  const [showPwModal, setShowPwModal] = useState(false)
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [pwMsg, setPwMsg] = useState('')
  const [pwMsgType, setPwMsgType] = useState<'success' | 'error'>('success')
  const [pwSaving, setPwSaving] = useState(false)

  useEffect(() => {
    Promise.all([
      api.brokers.credentials().catch(() => ({ credentials: [] })),
      api.strategies.assigned().catch(() => ({ strategies: [] })),
    ]).then(([c, s]) => {
      setCreds((c as { credentials: BrokerCred[] }).credentials || [])
      setStrategies((s as { strategies: AssignedStrategy[] }).strategies || [])
    }).finally(() => setLoading(false))
  }, [])

  const connectedCount = creds.filter(c => c.is_active).length
  const totalBrokers = creds.length

  const handleChangePassword = async () => {
    setPwMsg('')
    if (!currentPw) { setPwMsg('Current password is required'); setPwMsgType('error'); return }
    if (newPw.length < 6) { setPwMsg('New password must be at least 6 characters'); setPwMsgType('error'); return }
    if (newPw !== confirmPw) { setPwMsg('Passwords do not match'); setPwMsgType('error'); return }
    setPwSaving(true)
    try {
      const res = await api.auth.changePassword({ current_password: currentPw, new_password: newPw })
      setPwMsg((res as { message: string }).message || 'Password changed successfully')
      setPwMsgType('success')
      setCurrentPw('')
      setNewPw('')
      setConfirmPw('')
      setTimeout(() => setShowPwModal(false), 1500)
    } catch (e: any) {
      setPwMsg(e?.message || 'Failed to change password')
      setPwMsgType('error')
    } finally {
      setPwSaving(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 640 }}>
      <div className="t-page-header">
        <div>
          <h1 className="t-page-title">Settings</h1>
          <p className="t-page-subtitle">Account &amp; profile management</p>
        </div>
      </div>

      {/* Profile */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Profile</h3>
        </div>
        <div className="t-panel-body">
          <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 16 }}>
            <div style={{
              width: 48, height: 48, borderRadius: '50%',
              background: 'var(--gradient-primary)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 18, fontWeight: 700, color: 'var(--text-inverse)',
              flexShrink: 0,
            }}>
              {user?.full_name?.[0] || user?.email?.[0] || 'U'}
            </div>
            <div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>{user?.full_name || 'User'}</div>
              <div className="t-faint" style={{ fontSize: 12 }}>{user?.email}</div>
              {user?.id && <div className="t-faint" style={{ fontSize: 10, fontFamily: 'var(--font-mono)', marginTop: 2 }}>ID: {user.id}</div>}
            </div>
          </div>

          <div className="t-row" style={{ gap: 12 }}>
            <div style={{ flex: 1 }}>
              <span className="t-faint" style={{ fontSize: 10 }}>Full Name</span>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{user?.full_name || 'Not set'}</div>
            </div>
            <div style={{ flex: 1 }}>
              <span className="t-faint" style={{ fontSize: 10 }}>Email</span>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{user?.email}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Subscription */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Subscription</h3>
          <span className={`t-badge ${TIER_COLORS[tier] || 't-badge-sub'}`} style={{ textTransform: 'capitalize' }}>
            {tier}
          </span>
        </div>
        <div className="t-panel-body">
          <p className="t-faint" style={{ margin: '0 0 12px', fontSize: 12 }}>{TIER_LIMITS[tier] || 'Custom plan'}</p>
          <div className="t-row" style={{ gap: 16 }}>
            <div style={{ flex: 1, textAlign: 'center', padding: '8px', background: 'var(--panel-2)', borderRadius: 6 }}>
              <div style={{ fontSize: 20, fontWeight: 700 }}>{strategies.length}</div>
              <div className="t-faint" style={{ fontSize: 10 }}>Active Strategies</div>
            </div>
            <div style={{ flex: 1, textAlign: 'center', padding: '8px', background: 'var(--panel-2)', borderRadius: 6 }}>
              <div style={{ fontSize: 20, fontWeight: 700 }}>{connectedCount}/{totalBrokers}</div>
              <div className="t-faint" style={{ fontSize: 10 }}>Brokers Connected</div>
            </div>
            <div style={{ flex: 1, textAlign: 'center', padding: '8px', background: 'var(--panel-2)', borderRadius: 6 }}>
              <div style={{ fontSize: 20, fontWeight: 700 }}>{user?.is_admin ? 'Yes' : 'No'}</div>
              <div className="t-faint" style={{ fontSize: 10 }}>Admin Access</div>
            </div>
          </div>
          {tier !== 'enterprise' && (
            <div style={{ marginTop: 12 }}>
              <a href="/pricing" className="t-btn t-btn-sm t-btn-primary" style={{ textDecoration: 'none' }}>
                Upgrade Plan
              </a>
            </div>
          )}
        </div>
      </div>

      {/* Connected Brokers */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Connected Brokers</h3>
          <a href="/brokers" className="t-btn t-btn-xs t-btn-ghost">Manage</a>
        </div>
        <div className="t-panel-body">
          {loading ? (
            <span className="t-faint">Loading...</span>
          ) : creds.length === 0 ? (
            <p className="t-faint" style={{ margin: 0, fontSize: 12 }}>No brokers connected. <a href="/brokers">Connect one now</a>.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {creds.map(c => (
                <div key={c.broker} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '6px 10px', background: 'var(--panel-2)', borderRadius: 6,
                }}>
                  <span style={{ fontWeight: 600, fontSize: 12, textTransform: 'capitalize' }}>{c.broker}</span>
                  <span className={`t-badge ${c.is_active ? 't-badge-green' : 't-badge-sub'}`}>
                    {c.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Active Strategies */}
      {strategies.length > 0 && (
        <div className="t-panel" style={{ padding: 0 }}>
          <div className="t-panel-header">
            <h3 className="t-panel-title">Active Strategies</h3>
            <a href="/strategies" className="t-btn t-btn-xs t-btn-ghost">View All</a>
          </div>
          <div className="t-panel-body">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {strategies.map(s => (
                <div key={s.strategy_key} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '8px 10px', background: 'var(--panel-2)', borderRadius: 6,
                }}>
                  <div>
                    <span style={{ fontWeight: 600, fontSize: 12 }}>{s.name}</span>
                    <p className="t-faint" style={{ margin: '2px 0 0', fontSize: 10 }}>{s.description}</p>
                  </div>
                  <span className={`t-badge ${TIER_COLORS[s.required_tier] || 't-badge-sub'}`} style={{ textTransform: 'capitalize' }}>
                    {s.required_tier}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Preferences */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Preferences</h3>
        </div>
        <div className="t-panel-body">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span style={{ fontSize: 12, fontWeight: 600 }}>Theme</span>
              <p className="t-faint" style={{ margin: '2px 0 0', fontSize: 11 }}>Current: {theme === 'dark' ? 'Dark' : 'Light'} mode</p>
            </div>
            <button className="t-btn t-btn-sm" onClick={toggleTheme}>
              Switch to {theme === 'dark' ? 'Light' : 'Dark'}
            </button>
          </div>
        </div>
      </div>

      {/* Account Security */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Account Security</h3>
        </div>
        <div className="t-panel-body">
          <p className="t-faint" style={{ margin: '0 0 12px', fontSize: 12 }}>
            Manage your account security settings.
          </p>
          <div className="t-row" style={{ gap: 8 }}>
            <button className="t-btn t-btn-sm t-btn-primary" onClick={() => setShowPwModal(true)}>
              Change Password
            </button>
          </div>
        </div>
      </div>

      {/* Password Change Modal */}
      {showPwModal && (
        <div className="t-modal-overlay" onClick={() => setShowPwModal(false)}>
          <div className="t-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 400 }}>
            <div className="t-modal-title">Change Password</div>
            <div style={{ marginBottom: 12 }}>
              <label className="t-label">Current Password</label>
              <input className="t-input" type="password" value={currentPw} onChange={e => setCurrentPw(e.target.value)} />
            </div>
            <div style={{ marginBottom: 12 }}>
              <label className="t-label">New Password</label>
              <input className="t-input" type="password" value={newPw} onChange={e => setNewPw(e.target.value)} placeholder="Min. 6 characters" />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label className="t-label">Confirm New Password</label>
              <input className="t-input" type="password" value={confirmPw} onChange={e => setConfirmPw(e.target.value)} />
            </div>
            {pwMsg && (
              <div style={{
                padding: '8px 12px', borderRadius: 6, marginBottom: 12, fontSize: 12,
                background: pwMsgType === 'error' ? 'color-mix(in srgb, var(--red) 10%, transparent)' : 'color-mix(in srgb, var(--green) 10%, transparent)',
                border: `1px solid ${pwMsgType === 'error' ? 'color-mix(in srgb, var(--red) 20%, transparent)' : 'color-mix(in srgb, var(--green) 20%, transparent)'}`,
                color: pwMsgType === 'error' ? 'var(--red)' : 'var(--green)',
              }}>
                {pwMsg}
              </div>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="t-btn t-btn-ghost" onClick={() => { setShowPwModal(false); setPwMsg(''); setCurrentPw(''); setNewPw(''); setConfirmPw('') }}>Cancel</button>
              <button className="t-btn t-btn-primary" onClick={handleChangePassword} disabled={pwSaving}>
                {pwSaving ? 'Saving...' : 'Change Password'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
