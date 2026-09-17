'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { api, AdminStats } from '@/lib/api'
import { SkeletonBar } from '@/components/ui/skeleton'

const TABS = [
  { key: 'dashboard', label: 'Dashboard', href: '/admin?tab=dashboard' },
  { key: 'users', label: 'Users', href: '/admin?tab=users' },
  { key: 'admins', label: 'Admins', href: '/admin?tab=admins' },
  { key: 'strategies', label: 'Strategies', href: '/admin?tab=strategies' },
  { key: 'assignments', label: 'Assignments', href: '/admin?tab=assignments' },
  { key: 'brokers', label: 'Brokers', href: '/admin?tab=brokers' },
  { key: 'orders', label: 'Orders', href: '/admin?tab=orders' },
  { key: 'positions', label: 'Positions', href: '/admin?tab=positions' },
  { key: 'audit', label: 'Audit Log', href: '/admin?tab=audit' },
  { key: 'risk', label: 'Risk', href: '/admin?tab=risk' },
  { key: 'broadcast', label: 'Broadcast', href: '/admin?tab=broadcast' },
  { key: 'settings', label: 'Settings', href: '/admin?tab=settings' },
] as const

type TabKey = (typeof TABS)[number]['key']

function fmt(n: number) {
  return n.toLocaleString('en-IN', { maximumFractionDigits: 0 })
}

function StatCard({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="t-panel" style={{ padding: '12px 14px' }}>
      <div className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.04em' }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)', color: color || 'var(--text)', marginTop: 4 }}>
        {value}
      </div>
    </div>
  )
}

function TierBadge({ tier }: { tier: string }) {
  const colors: Record<string, string> = {
    free: 'var(--green)',
    starter: 'var(--cyan)',
    pro: 'var(--violet)',
    enterprise: 'var(--red)',
  }
  const c = colors[tier] || 'var(--text-sub)'
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 4, fontSize: 9, fontWeight: 600,
      background: `${c}18`, color: c, border: `1px solid ${c}30`,
      textTransform: 'capitalize', letterSpacing: '0.03em',
    }}>
      {tier}
    </span>
  )
}

export default function AdminPage() {
  const { isAdmin, loading: authLoading } = useAuth()
  const router = useRouter()
  const tab = (typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('tab') : '') as TabKey | null
  const activeTab = tab || 'dashboard'

  const [stats, setStats] = useState<AdminStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!authLoading && !isAdmin) {
      router.replace('/dashboard')
      return
    }
    if (isAdmin) {
      api.admin.stats().then(setStats).catch(() => {}).finally(() => setLoading(false))
    }
  }, [isAdmin, authLoading])

  if (authLoading || (!isAdmin && !loading)) return null
  if (!isAdmin) return null
  if (loading) {
    return (
      <div style={{ padding: 20 }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="t-panel" style={{ padding: '14px 16px', width: 160 }}>
              <SkeletonBar w="60%" h={10} />
              <div style={{ height: 28, marginTop: 8 }}><SkeletonBar w="80%" h={22} /></div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  const ts = stats || { total_users: 0, total_admins: 0, active_assignments: 0, total_strategies: 0, tier_distribution: {} }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <header style={{
        height: 48, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 16px', borderBottom: '1px solid var(--border)',
        background: 'var(--bg-secondary)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 700, background: 'var(--gradient-primary)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            TradeMetrix
          </span>
          <span style={{ fontSize: 9, letterSpacing: '0.06em', color: 'var(--violet)', fontWeight: 600 }}>ADMIN PANEL</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 10, color: 'var(--text-sub)' }}>ADMIN</span>
        </div>
      </header>

      {/* Sidebar + Content */}
      <div style={{ display: 'flex', flex: 1 }}>
        {/* Sidebar */}
        <aside style={{
          width: 180, borderRight: '1px solid var(--border)', background: 'var(--bg-secondary)',
          padding: '8px 0', overflowY: 'auto', flexShrink: 0,
        }}>
          <div style={{ padding: '8px 12px 4px', fontSize: 9, fontWeight: 700, letterSpacing: '0.06em', color: 'var(--text-sub)' }}>
            MENU
          </div>
          {TABS.map(tab => {
            const active = activeTab === tab.key
            return (
              <a key={tab.key} href={tab.href} style={{
                display: 'block', padding: '6px 12px', fontSize: 11, fontWeight: 500,
                color: active ? 'var(--violet)' : 'var(--text-sub)',
                background: active ? 'color-mix(in srgb, var(--violet) 8%, transparent)' : 'transparent',
                borderLeft: active ? '2px solid var(--violet)' : '2px solid transparent',
                textDecoration: 'none', transition: 'all 0.12s',
              }}>
                {tab.label}
              </a>
            )
          })}
        </aside>

        {/* Main content */}
        <main style={{ flex: 1, padding: '16px 20px', overflowY: 'auto' }}>
          {/* Page title */}
          <div style={{ marginBottom: 16 }}>
            <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, margin: 0 }}>
              {TABS.find(t => t.key === activeTab)?.label || 'Dashboard'}
            </h1>
            <p className="t-faint" style={{ fontSize: 11, margin: '4px 0 12px' }}>
              Manage users, strategies, brokers, and platform settings.
            </p>
          </div>

          {/* Stats row */}
          <div className="t-grid-4" style={{ gap: 10, marginBottom: 20 }}>
            <StatCard label="TOTAL USERS" value={fmt(ts.total_users)} />
            <StatCard label="ADMIN USERS" value={fmt(ts.total_admins)} color="var(--violet)" />
            <StatCard label="ACTIVE ASSIGNMENTS" value={fmt(ts.active_assignments)} color="var(--cyan)" />
            <StatCard label="STRATEGIES" value={fmt(ts.total_strategies)} color="var(--green)" />
          </div>

          {/* Tier distribution */}
          {Object.keys(ts.tier_distribution).length > 0 && (
            <div className="t-panel" style={{ padding: '14px 16px', marginBottom: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 10, letterSpacing: '0.03em' }}>
                TIER DISTRIBUTION
              </div>
              <div className="t-grid-4" style={{ gap: 12 }}>
                {(['free', 'starter', 'pro', 'enterprise'] as const).map(tier => {
                  const count = ts.tier_distribution[tier] || 0
                  return (
                    <div key={tier} style={{ textAlign: 'center' }}>
                      <TierBadge tier={tier} />
                      <div style={{ fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-mono)', marginTop: 4 }}>
                        {fmt(count)}
                      </div>
                      <div className="t-faint" style={{ fontSize: 9 }}>users</div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Quick actions */}
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 20 }}>
            <a href="/admin?tab=users" style={{ padding: '8px 14px', fontSize: 11, fontWeight: 600, borderRadius: 6, background: 'var(--bg-tertiary)', border: '1px solid var(--border)', color: 'var(--text)', textDecoration: 'none' }}>
              Manage Users
            </a>
            <a href="/admin?tab=assignments" style={{ padding: '8px 14px', fontSize: 11, fontWeight: 600, borderRadius: 6, background: 'var(--bg-tertiary)', border: '1px solid var(--border)', color: 'var(--text)', textDecoration: 'none' }}>
              Assign Strategies
            </a>
            <a href="/admin?tab=broadcast" style={{ padding: '8px 14px', fontSize: 11, fontWeight: 600, borderRadius: 6, background: 'var(--bg-tertiary)', border: '1px solid var(--border)', color: 'var(--text)', textDecoration: 'none' }}>
              Broadcast Trade
            </a>
            <a href="/admin?tab=risk" style={{ padding: '8px 14px', fontSize: 11, fontWeight: 600, borderRadius: 6, background: 'var(--bg-tertiary)', border: '1px solid var(--border)', color: 'var(--text)', textDecoration: 'none' }}>
              Risk Overview
            </a>
          </div>

          {/* Tab content placeholder — full content in dashboard/admin-content.tsx */}
          <div style={{ padding: '12px 0' }}>
            {/* The dashboard/admin-content.tsx handles the full tab content via the ?tab= param */}
            <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-sub)', fontSize: 12 }}>
              Loading tab content...
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
