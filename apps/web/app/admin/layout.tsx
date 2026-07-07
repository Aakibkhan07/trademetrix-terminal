'use client'

import { usePathname, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth-context'
import { api } from '@/lib/api'
import Logo from '@/components/logo'

const ADMIN_NAV = [
  {
    label: 'Overview',
    items: [
      { href: '/admin', label: 'Dashboard', icon: 'D', tab: 'dashboard' },
      { href: '/admin?tab=users', label: 'Users', icon: 'U', tab: 'users' },
    ],
  },
  {
    label: 'Trading Ops',
    items: [
      { href: '/admin?tab=brokers', label: 'Brokers', icon: 'B', tab: 'brokers' },
      { href: '/admin?tab=buyer-strategies', label: 'Buyer Strat', icon: 'S', tab: 'buyer-strategies' },
      { href: '/admin?tab=trades', label: 'Trades', icon: 'T', tab: 'trades' },
      { href: '/admin/broadcast', label: 'Broadcast', icon: 'W', tab: '' },
    ],
  },
  {
    label: 'Security',
    items: [
      { href: '/admin?tab=risk', label: 'Risk', icon: 'R', tab: 'risk' },
      { href: '/admin?tab=audit', label: 'Audit Log', icon: 'A', tab: 'audit' },
      { href: '/admin/admins', label: 'Admins', icon: '#', tab: '' },
    ],
  },
]

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { user, loading, isAdmin, signout } = useAuth()
  const [killSwitchActive, setKillSwitchActive] = useState(false)

  const activeTab = pathname === '/admin'
    ? new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '').get('tab') || 'dashboard'
    : ''

  useEffect(() => {
    if (!loading && !isAdmin) {
      router.replace('/dashboard')
    }
  }, [loading, isAdmin, router])

  useEffect(() => {
    if (!isAdmin) return
    api.risk.killSwitchStatus().then((d: unknown) => {
      setKillSwitchActive((d as { kill_switch_enabled: boolean }).kill_switch_enabled)
    }).catch(() => {})
  }, [isAdmin])

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: 'var(--bg)', color: 'var(--text-faint)' }}>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>Loading...</p>
      </div>
    )
  }

  if (!isAdmin) return null

  return (
    <div className="t-layout">
      <nav className="t-sidebar">
        <Link href="/admin" className="t-sidebar-logo">
          <Logo size={24} />
          <span className="t-sidebar-logo-text">Admin</span>
        </Link>

        {ADMIN_NAV.map((section) => (
          <div key={section.label}>
            <div className="t-sidebar-section">
              <div className="t-sidebar-label">{section.label}</div>
            </div>
            {section.items.map((item) => {
              const active = item.href === '/admin'
                ? pathname === '/admin' && activeTab === 'dashboard'
                : item.href.includes('?')
                  ? pathname === '/admin' && activeTab === item.tab
                  : pathname === item.href
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`t-nav-item ${active ? 'active' : ''}`}
                >
                  <span className="t-nav-icon">{item.icon}</span>
                  <span className="t-nav-text">{item.label}</span>
                </Link>
              )
            })}
          </div>
        ))}

        <div className="t-sidebar-footer">
          <button
            className={`t-sidebar-footer-item ${killSwitchActive ? 'active' : ''}`}
            onClick={async () => {
              try {
                if (killSwitchActive) {
                  await api.risk.disableKillSwitch()
                  setKillSwitchActive(false)
                } else {
                  await api.risk.enableKillSwitch()
                  setKillSwitchActive(true)
                }
              } catch {}
            }}
            style={killSwitchActive ? { color: 'var(--text-red)' } : {}}
          >
            <span className={`t-dot ${killSwitchActive ? 't-dot-red t-dot-pulse' : 't-dot-sub'}`} />
            <span>{killSwitchActive ? 'KILL SWITCH ON' : 'Kill Switch'}</span>
          </button>
          <Link href="/dashboard" className="t-sidebar-footer-item" style={{ textDecoration: 'none' }}>
            <span style={{ fontSize: 11 }}>{'<-'}</span>
            <span>Back to App</span>
          </Link>
          <button className="t-sidebar-footer-item" onClick={signout}>
            <span style={{ fontSize: 11 }}>X</span>
            <span>Sign Out</span>
          </button>
        </div>
      </nav>

      <div className="t-main">
        <div style={{ padding: '0 12px' }}>
          <div style={{ marginBottom: 16, paddingTop: 12 }}>
            <h1 className="t-page-title" style={{ margin: 0, fontSize: 18 }}>Control Center</h1>
            <p className="t-sub" style={{ fontSize: 12, margin: '2px 0 0' }}>
              {user?.email}
            </p>
          </div>
          {children}
        </div>
      </div>
    </div>
  )
}
