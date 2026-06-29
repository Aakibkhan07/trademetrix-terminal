'use client'

import { usePathname } from 'next/navigation'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth-context'
import { api } from '@/lib/api'

const NAV_SECTIONS = [
  {
    label: 'Core',
    items: [
      { href: '/dashboard', label: 'Dashboard', icon: 'D' },
      { href: '/strategies', label: 'Strategies', icon: 'S' },
      { href: '/brokers', label: 'Brokers', icon: 'B' },
    ],
  },
  {
    label: 'Trading',
    items: [
      { href: '/trade', label: 'Trade', icon: 'T' },
      { href: '/positions', label: 'Positions', icon: 'P' },
      { href: '/marketdata', label: 'Market Data', icon: 'M' },
      { href: '/backtest', label: 'Backtest', icon: 'B' },
      { href: '/risk', label: 'Risk Control', icon: 'R' },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { href: '/ai', label: 'AI Desk', icon: 'A' },
      { href: '/transparency', label: 'Reports', icon: 'R' },
    ],
  },
]

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { token, loading, signout } = useAuth()
  const [killSwitchActive, setKillSwitchActive] = useState(false)

  useEffect(() => {
    if (!token || pathname === '/auth') return
    api.risk.killSwitchStatus().then((d: unknown) => {
      const data = d as { kill_switch_enabled: boolean }
      setKillSwitchActive(data.kill_switch_enabled)
    }).catch(() => {})
  }, [token, pathname])

  if (pathname === '/auth') return <>{children}</>

  if (loading || !token) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#000', color: '#8888a0' }}>
        <p>Loading...</p>
      </div>
    )
  }

  return (
    <div className="app-layout">
      <aside className="sidebar">
        {NAV_SECTIONS.map((section) => (
          <div key={section.label}>
            <div className="nav-section-label">{section.label}</div>
            {section.items.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-item ${pathname === item.href ? 'active' : ''}`}
              >
                <span className="nav-icon">{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            ))}
          </div>
        ))}

        <div style={{ marginTop: 'auto', padding: '16px 24px', borderTop: '1px solid var(--border-subtle)', marginLeft: 16, marginRight: 16, paddingLeft: 0, paddingRight: 0 }}>
          <div
            className={`kill-switch ${killSwitchActive ? 'active' : 'inactive'}`}
            style={{ width: '100%', justifyContent: 'center' }}
            onClick={async () => {
              if (killSwitchActive) {
                await api.risk.disableKillSwitch()
                setKillSwitchActive(false)
              } else {
                await api.risk.enableKillSwitch()
                setKillSwitchActive(true)
              }
            }}
          >
            <span style={{
              width: 8, height: 8, borderRadius: '50%', display: 'inline-block',
              background: killSwitchActive ? '#ef4444' : '#555570',
              boxShadow: killSwitchActive ? '0 0 8px #ef4444' : 'none',
            }} />
            {killSwitchActive ? 'KILL SWITCH ON' : 'Kill Switch'}
          </div>

          <button
            className="btn btn-ghost"
            style={{ width: '100%', marginTop: 8, fontSize: 12 }}
            onClick={signout}
          >
            Sign Out
          </button>
        </div>
      </aside>

      <main className="main-content">
        {children}
      </main>
    </div>
  )
}
