'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth-context'
import { useTheme } from '@/lib/use-theme'
import { api } from '@/lib/api'

interface BrokerCred { broker: string; name?: string; is_active: boolean; created_at: string }
interface AssignedStrategy { strategy_key: string; name: string; description: string; required_tier: string }
interface Order { id: string; symbol: string; side: string; quantity: number; price: number; status: string; created_at: string }

const TIER_STYLES: Record<string, { color: string; bg: string }> = {
  free: { color: '#9aa0a6', bg: 'rgba(154,160,166,0.12)' },
  starter: { color: '#00e5ff', bg: 'rgba(0,229,255,0.12)' },
  pro: { color: '#7c5cfc', bg: 'rgba(124,92,252,0.12)' },
  enterprise: { color: '#ffd600', bg: 'rgba(255,214,0,0.12)' },
}

const TIER_LIMITS: Record<string, { strategies: number; data: string }> = {
  free: { strategies: 1, data: 'Delayed market data' },
  starter: { strategies: 3, data: 'Real-time indices' },
  pro: { strategies: 10, data: 'Full real-time + backtesting' },
  enterprise: { strategies: 99, data: 'Everything unlimited' },
}

function generateInitials(name?: string, email?: string) {
  if (name) return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
  return (email?.[0] || 'U').toUpperCase()
}

function fmt(n: number) { return n.toLocaleString('en-IN', { maximumFractionDigits: 0 }) }

function formatDate(iso?: string) {
  if (!iso) return 'N/A'
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

function timeAgo(iso?: string) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).catch(() => {})
}

export default function AccountPage() {
  const { user, tier, signout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const [brokers, setBrokers] = useState<BrokerCred[]>([])
  const [strategies, setStrategies] = useState<AssignedStrategy[]>([])
  const [recentOrders, setRecentOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [copiedId, setCopiedId] = useState('')
  const [showTokens, setShowTokens] = useState(false)
  const [showPwModal, setShowPwModal] = useState(false)
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [pwMsg, setPwMsg] = useState('')
  const [pwMsgType, setPwMsgType] = useState<'success' | 'error'>('success')
  const [pwSaving, setPwSaving] = useState(false)
  const [notifPrefs, setNotifPrefs] = useState({ email: true, sms: false, inapp: true })
  const [savingNotifs, setSavingNotifs] = useState(false)

  useEffect(() => {
    Promise.all([
      api.brokers.credentials().catch(() => ({ credentials: [] })),
      api.strategies.assigned().catch(() => ({ strategies: [] })),
      api.engine.orders().catch(() => ({ orders: [] })),
      api.alerts.getNotificationPrefs().catch(() => ({ channels: ['email'] })),
    ]).then(([c, s, o, n]) => {
      setBrokers((c as { credentials: BrokerCred[] }).credentials || [])
      setStrategies((s as { strategies: AssignedStrategy[] }).strategies || [])
      setRecentOrders(((o as { orders: Order[] }).orders || []).slice(0, 8))
      const channels = (n as { channels: string[] }).channels || ['email']
      setNotifPrefs({ email: channels.includes('email'), sms: channels.includes('sms'), inapp: channels.includes('inapp') })
    }).finally(() => setLoading(false))
  }, [])

  const activeBrokers = brokers.filter(b => b.is_active).length
  const tierStyle = TIER_STYLES[tier] || TIER_STYLES.free
  const limits = TIER_LIMITS[tier] || TIER_LIMITS.free
  const initials = generateInitials(user?.full_name, user?.email)
  const isAdmin = user?.is_admin === true

  const handleCopy = (text: string, id: string) => {
    copyToClipboard(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(''), 1500)
  }

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
      setCurrentPw(''); setNewPw(''); setConfirmPw('')
      setTimeout(() => setShowPwModal(false), 1500)
    } catch (e: any) {
      setPwMsg(e?.message || 'Failed to change password')
      setPwMsgType('error')
    } finally {
      setPwSaving(false)
    }
  }

  const handleNotifToggle = async (key: keyof typeof notifPrefs) => {
    setSavingNotifs(true)
    const next = { ...notifPrefs, [key]: !notifPrefs[key] }
    setNotifPrefs(next)
    try {
      const channels = Object.entries(next).filter(([, v]) => v).map(([k]) => k)
      await api.alerts.updateNotificationPrefs(channels)
    } catch {
      setNotifPrefs(prev => ({ ...prev, [key]: !prev[key] }))
    } finally {
      setSavingNotifs(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 720 }}>
      {/* Hero Profile Card */}
      <div className="t-panel" style={{
        padding: 0, overflow: 'hidden',
        borderTop: `3px solid ${tierStyle.color}`,
      }}>
        <div style={{
          height: 80, background: 'var(--gradient-primary)',
          opacity: 0.85, position: 'relative',
        }}>
          <div style={{
            position: 'absolute', bottom: -32, left: 20,
            width: 64, height: 64, borderRadius: '50%',
            background: `linear-gradient(135deg, ${tierStyle.color}, ${tierStyle.color}88)`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 22, fontWeight: 700, color: '#000',
            border: '3px solid var(--bg-secondary)',
            boxShadow: '0 2px 12px rgba(0,0,0,0.3)',
          }}>
            {initials}
          </div>
        </div>
        <div className="t-panel-body" style={{ paddingTop: 40 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>{user?.full_name || 'User'}</h2>
              <p style={{ margin: '2px 0', fontSize: 12, color: 'var(--text-sub)' }}>{user?.email}</p>
              <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                <span style={{
                  fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em',
                  padding: '2px 10px', borderRadius: 999,
                  color: tierStyle.color, background: tierStyle.bg,
                }}>
                  {tier}
                </span>
                {isAdmin && (
                  <span style={{
                    fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em',
                    padding: '2px 10px', borderRadius: 999,
                    color: 'var(--cyan)', background: 'rgba(0,229,255,0.12)',
                  }}>
                    Admin
                  </span>
                )}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div className="t-faint" style={{ fontSize: 10 }}>Member Since</div>
              <div style={{ fontSize: 13, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                {user?.created_at ? new Date(user.created_at).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' }) : 'N/A'}
              </div>
              <div className="t-faint" style={{ fontSize: 10, marginTop: 4 }}>ID</div>
              <div style={{
                fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-sub)',
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'flex-end',
              }} onClick={() => handleCopy(user?.id || '', 'userId')}>
                {user?.id ? user.id.slice(0, 10) + '...' : '-'}
                {copiedId === 'userId' ? (
                  <span style={{ color: 'var(--green)', fontSize: 9 }}>Copied!</span>
                ) : (
                  <span style={{ opacity: 0.4, fontSize: 9 }}>Copy</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="t-grid-4">
        {[
          { label: 'Total Trades', value: recentOrders.length.toString(), color: 'var(--cyan)' },
          { label: 'Active Strategies', value: strategies.length.toString(), color: 'var(--violet)' },
          { label: 'Brokers Connected', value: `${activeBrokers}/${brokers.length}`, color: 'var(--green)' },
          { label: 'Subscription', value: tier.charAt(0).toUpperCase() + tier.slice(1), color: tierStyle.color },
        ].map(stat => (
          <div key={stat.label} className="t-panel" style={{
            padding: '14px 16px',
            transition: 'transform 0.15s, box-shadow 0.15s',
            cursor: 'default',
          }}
            onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-1px)'; e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.15)' }}
            onMouseLeave={e => { e.currentTarget.style.transform = ''; e.currentTarget.style.boxShadow = '' }}
          >
            <div className="t-faint" style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.04em', marginBottom: 4 }}>
              {stat.label}
            </div>
            <div style={{ fontSize: 22, fontWeight: 700, color: stat.color, fontFamily: 'var(--font-mono)' }}>
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      <div className="t-row" style={{ gap: 16 }}>
        {/* Subscription & Usage */}
        <div className="t-panel" style={{ flex: 1, padding: 0, minWidth: 0 }}>
          <div className="t-panel-header">
            <h3 className="t-panel-title">Usage</h3>
            <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>
              {strategies.length}/{limits.strategies} strategies
            </span>
          </div>
          <div className="t-panel-body">
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 11, color: 'var(--text-sub)' }}>Active Strategies</span>
                <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
                  {Math.round((strategies.length / Math.max(limits.strategies, 1)) * 100)}%
                </span>
              </div>
              <div style={{ height: 6, borderRadius: 3, background: 'var(--panel-2)', overflow: 'hidden' }}>
                <div style={{
                  width: `${Math.min((strategies.length / Math.max(limits.strategies, 1)) * 100, 100)}%`,
                  height: '100%', borderRadius: 3,
                  background: `linear-gradient(90deg, ${tierStyle.color}, ${tierStyle.color}66)`,
                  transition: 'width 0.6s ease',
                }} />
              </div>
            </div>
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 11, color: 'var(--text-sub)' }}>Brokers Connected</span>
                <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
                  {brokers.length > 0 ? Math.round((activeBrokers / brokers.length) * 100) : 0}%
                </span>
              </div>
              <div style={{ height: 6, borderRadius: 3, background: 'var(--panel-2)', overflow: 'hidden' }}>
                <div style={{
                  width: brokers.length > 0 ? `${(activeBrokers / brokers.length) * 100}%` : '0%',
                  height: '100%', borderRadius: 3,
                  background: 'linear-gradient(90deg, var(--green), var(--green-dim))',
                  transition: 'width 0.6s ease',
                }} />
              </div>
            </div>
            <div style={{
              padding: '10px 12px', borderRadius: 8,
              background: tierStyle.bg, fontSize: 11, color: 'var(--text-sub)',
            }}>
              <span style={{ fontWeight: 600, color: tierStyle.color, textTransform: 'capitalize' }}>
                {tier}
              </span>
              : {limits.data}
              {tier !== 'enterprise' && (
                <span style={{ display: 'block', marginTop: 6 }}>
                  <a href="/pricing" style={{ color: 'var(--cyan)', fontSize: 10, textDecoration: 'none' }}>
                    Upgrade plan →
                  </a>
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Security */}
        <div className="t-panel" style={{ flex: 1, padding: 0, minWidth: 0 }}>
          <div className="t-panel-header">
            <h3 className="t-panel-title">Security</h3>
          </div>
          <div className="t-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '8px 10px', borderRadius: 6, background: 'var(--panel-2)',
              transition: 'background 0.15s',
            }}
              onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'var(--panel-2)' }}
            >
              <div>
                <div style={{ fontSize: 12, fontWeight: 600 }}>Password</div>
                <div className="t-faint" style={{ fontSize: 10 }}>Change your login password</div>
              </div>
              <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => setShowPwModal(true)}>Change</button>
            </div>
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '8px 10px', borderRadius: 6, background: 'var(--panel-2)',
              transition: 'background 0.15s',
            }}
              onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'var(--panel-2)' }}
            >
              <div>
                <div style={{ fontSize: 12, fontWeight: 600 }}>Two-Factor Auth</div>
                <div className="t-faint" style={{ fontSize: 10 }}>Not configured</div>
              </div>
              <button className="t-btn t-btn-xs t-btn-ghost" disabled style={{ opacity: 0.5 }}>Setup</button>
            </div>
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '8px 10px', borderRadius: 6, background: 'var(--panel-2)',
              transition: 'background 0.15s',
            }}
              onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'var(--panel-2)' }}
            >
              <div>
                <div style={{ fontSize: 12, fontWeight: 600 }}>API Tokens</div>
                <div className="t-faint" style={{ fontSize: 10 }}>0 active tokens</div>
              </div>
              <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => setShowTokens(!showTokens)}>
                {showTokens ? 'Hide' : 'Manage'}
              </button>
            </div>
            {showTokens && (
              <div style={{
                padding: '10px 12px', borderRadius: 6,
                background: 'rgba(255,214,0,0.06)', border: '1px solid rgba(255,214,0,0.12)',
              }}>
                <p style={{ margin: 0, fontSize: 11, color: 'var(--text-sub)' }}>
                  API token management is handled by your account manager. Contact support to generate tokens for automated trading.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="t-row" style={{ gap: 16 }}>
        {/* Recent Activity */}
        <div className="t-panel" style={{ flex: 1, padding: 0, minWidth: 0 }}>
          <div className="t-panel-header">
            <h3 className="t-panel-title">Recent Orders</h3>
            {recentOrders.length > 0 && (
              <a href="/positions" style={{ fontSize: 10, color: 'var(--cyan)', textDecoration: 'none' }}>View all</a>
            )}
          </div>
          <div className="t-panel-body" style={{ padding: '4px 0' }}>
            {loading ? (
              <div style={{ padding: 16, textAlign: 'center' }}>
                <span className="t-faint" style={{ fontSize: 11 }}>Loading...</span>
              </div>
            ) : recentOrders.length === 0 ? (
              <div style={{ padding: 20, textAlign: 'center' }}>
                <div style={{ fontSize: 20, marginBottom: 4, opacity: 0.3 }}>O</div>
                <p className="t-faint" style={{ margin: 0, fontSize: 11 }}>No orders yet</p>
              </div>
            ) : (
              <div>
                {recentOrders.map((o, i) => (
                  <div key={o.id} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '8px 12px',
                    borderBottom: i < recentOrders.length - 1 ? '1px solid var(--border)' : 'none',
                    transition: 'background 0.12s',
                  }}
                    onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{
                        width: 6, height: 6, borderRadius: '50%',
                        background: o.side === 'BUY' ? 'var(--green)' : 'var(--red)',
                        flexShrink: 0,
                      }} />
                      <div>
                        <div style={{ fontSize: 11, fontWeight: 600 }}>{o.symbol}</div>
                        <div style={{ fontSize: 9, color: 'var(--text-faint)', marginTop: 1 }}>
                          {o.side} · {o.quantity} · {o.status}
                        </div>
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div className="t-num" style={{ fontSize: 11, fontWeight: 600 }}>
                        {o.price ? `\u20B9${fmt(o.price)}` : '-'}
                      </div>
                      <div className="t-faint" style={{ fontSize: 9 }}>{timeAgo(o.created_at)}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Notification Preferences */}
        <div className="t-panel" style={{ flex: 1, padding: 0, minWidth: 0 }}>
          <div className="t-panel-header">
            <h3 className="t-panel-title">Notifications</h3>
            {savingNotifs && <span className="t-faint" style={{ fontSize: 9 }}>Saving...</span>}
          </div>
          <div className="t-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              { key: 'email' as const, label: 'Email Alerts', desc: 'Order fills, risk alerts' },
              { key: 'sms' as const, label: 'SMS Alerts', desc: 'Price alerts, kill switch' },
              { key: 'inapp' as const, label: 'In-App', desc: 'Toast notifications, bell' },
            ].map(item => (
              <div key={item.key} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '8px 10px', borderRadius: 6, background: 'var(--panel-2)',
                transition: 'background 0.15s',
              }}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'var(--panel-2)' }}
              >
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>{item.label}</div>
                  <div className="t-faint" style={{ fontSize: 10 }}>{item.desc}</div>
                </div>
                <button
                  onClick={() => handleNotifToggle(item.key)}
                  style={{
                    width: 36, height: 20, borderRadius: 10, border: 'none', cursor: 'pointer',
                    padding: 0, position: 'relative',
                    background: notifPrefs[item.key] ? tierStyle.color : 'var(--panel-2)',
                    transition: 'background 0.2s',
                    boxShadow: notifPrefs[item.key]
                      ? `0 0 8px ${tierStyle.color}44`
                      : 'none',
                  }}
                  aria-label={`Toggle ${item.label}`}
                >
                  <span style={{
                    position: 'absolute', top: 2,
                    width: 16, height: 16, borderRadius: '50%',
                    background: '#fff',
                    transition: 'left 0.2s, box-shadow 0.2s',
                    left: notifPrefs[item.key] ? 18 : 2,
                    boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                  }} />
                </button>
              </div>
            ))}
            {savingNotifs && (
              <div className="t-faint" style={{
                fontSize: 9, textAlign: 'center', padding: '4px 0',
                opacity: 0.6,
              }}>
                Saving...
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Connected Brokers */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Brokers</h3>
          <a href="/brokers" style={{ fontSize: 10, color: 'var(--cyan)', textDecoration: 'none' }}>Manage</a>
        </div>
        <div className="t-panel-body">
          {loading ? (
            <span className="t-faint" style={{ fontSize: 11 }}>Loading...</span>
          ) : brokers.length === 0 ? (
            <div style={{ padding: '8px 0', textAlign: 'center' }}>
              <p className="t-faint" style={{ margin: 0, fontSize: 11 }}>
                No brokers connected. <a href="/brokers" style={{ color: 'var(--cyan)' }}>Connect one now</a>.
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {brokers.map(b => (
                <div key={b.broker} style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '6px 10px', borderRadius: 6, fontSize: 11,
                  background: b.is_active ? 'rgba(0,200,83,0.06)' : 'var(--panel-2)',
                  border: `1px solid ${b.is_active ? 'rgba(0,200,83,0.15)' : 'var(--border)'}`,
                  transition: 'all 0.12s',
                }}
                  onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-1px)' }}
                  onMouseLeave={e => { e.currentTarget.style.transform = '' }}
                >
                  <span style={{
                    width: 6, height: 6, borderRadius: '50%',
                    background: b.is_active ? 'var(--green)' : 'var(--text-faint)',
                    flexShrink: 0,
                  }} />
                  <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{b.broker}</span>
                  <span style={{
                    fontSize: 9, padding: '1px 6px', borderRadius: 4,
                    color: b.is_active ? 'var(--text-green)' : 'var(--text-faint)',
                    background: b.is_active ? 'rgba(0,200,83,0.1)' : 'transparent',
                  }}>
                    {b.is_active ? 'Active' : 'Inactive'}
                  </span>
                  {b.created_at && (
                    <span className="t-faint" style={{ fontSize: 9 }}>
                      since {formatDate(b.created_at)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
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

      {/* Danger Zone */}
      <div className="t-panel" style={{
        padding: 0, border: '1px solid rgba(255,23,68,0.15)',
      }}>
        <div className="t-panel-header" style={{ borderBottom: '1px solid rgba(255,23,68,0.1)' }}>
          <h3 className="t-panel-title" style={{ color: 'var(--text-red)' }}>Danger Zone</h3>
        </div>
        <div className="t-panel-body" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600 }}>Sign Out</div>
            <div className="t-faint" style={{ fontSize: 10 }}>End your current session</div>
          </div>
          <button className="t-btn t-btn-sm t-btn-danger" onClick={signout}>
            Sign Out
          </button>
        </div>
      </div>
    </div>
  )
}
