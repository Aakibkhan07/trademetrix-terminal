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
              fontSize: 18, fontWeight: 700, color: '#fff',
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
            Manage your account security settings. Password change is handled by your authentication provider.
          </p>
          <div className="t-row" style={{ gap: 8 }}>
            <button className="t-btn t-btn-sm t-btn-ghost" disabled style={{ opacity: 0.5 }}>
              Change Password
            </button>
            <span className="t-faint" style={{ fontSize: 10, alignSelf: 'center' }}>Coming soon</span>
          </div>
        </div>
      </div>
    </div>
  )
}
