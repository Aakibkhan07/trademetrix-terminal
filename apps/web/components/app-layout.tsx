'use client'

import { usePathname, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth-context'
import { api } from '@/lib/api'
import Logo from '@/components/logo'
import Header from '@/components/header'
import MarketTicker from '@/components/market-ticker'
import StatusBar from '@/components/status-bar'

const NAV_SECTIONS = [
  {
    label: 'Overview',
    items: [
      { href: '/dashboard', label: 'Dashboard', icon: 'D' },
      { href: '/terminal', label: 'Terminal', icon: 'T' },
    ],
  },
  {
    label: 'Trading',
    items: [
      { href: '/trade', label: 'Trade', icon: 'O' },
      { href: '/positions', label: 'Positions', icon: 'P' },
      { href: '/marketdata', label: 'Market Data', icon: 'M' },
      { href: '/strategies', label: 'Strategies', icon: 'S' },
    ],
  },
  {
    label: 'Management',
    items: [
      { href: '/brokers', label: 'Brokers', icon: 'B' },
      { href: '/backtest', label: 'Backtest', icon: 'K' },
      { href: '/journal', label: 'Journal', icon: 'J' },
      { href: '/risk', label: 'Risk Control', icon: 'R' },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { href: '/ai', label: 'AI Desk', icon: 'A' },
      { href: '/transparency', label: 'Reports', icon: 'E' },
    ],
  },
  {
    label: 'System',
    items: [
      { href: '/account', label: 'Account', icon: 'U' },
    ],
  },
]

const STANDALONE_PAGES = ['/', '/auth', '/onboarding']
const STANDALONE_PREFIXES = ['/portal']

function isStandalone(pathname: string) {
  if (STANDALONE_PAGES.includes(pathname)) return true
  if (STANDALONE_PREFIXES.some(p => pathname.startsWith(p))) return true
  return false
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { user, loading, signout } = useAuth()
  const [killSwitchActive, setKillSwitchActive] = useState(false)

  const isAuthenticated = !!user
  const standalone = isStandalone(pathname)

  useEffect(() => {
    if (!isAuthenticated || standalone) return
    api.risk.killSwitchStatus().then((d: unknown) => {
      const data = d as { kill_switch_enabled: boolean }
      setKillSwitchActive(data.kill_switch_enabled)
    }).catch(() => {})
  }, [isAuthenticated, standalone])

  useEffect(() => {
    if (!loading && !isAuthenticated && !standalone) {
      router.replace('/auth')
    }
  }, [loading, isAuthenticated, standalone, router])

  if (standalone) return <>{children}</>

  if (loading || !isAuthenticated) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: 'var(--bg)', color: 'var(--text-faint)' }}>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>Loading...</p>
      </div>
    )
  }

  return (
    <div className="t-layout">
      <nav className="t-sidebar">
        <Link href="/dashboard" className="t-sidebar-logo">
          <Logo size={24} />
          <span className="t-sidebar-logo-text">TradeMetrix</span>
        </Link>

        {NAV_SECTIONS.map((section) => (
          <div key={section.label}>
            <div className="t-sidebar-section">
              <div className="t-sidebar-label">{section.label}</div>
            </div>
            {section.items.map((item) => {
              const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href))
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`t-nav-item ${isActive ? 'active' : ''}`}
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
              if (killSwitchActive) {
                await api.risk.disableKillSwitch()
                setKillSwitchActive(false)
              } else {
                await api.risk.enableKillSwitch()
                setKillSwitchActive(true)
              }
            }}
            style={killSwitchActive ? { color: 'var(--text-red)' } : {}}
          >
            <span className={`t-dot ${killSwitchActive ? 't-dot-red t-dot-pulse' : 't-dot-sub'}`} />
            <span>{killSwitchActive ? 'KILL SWITCH ON' : 'Kill Switch'}</span>
          </button>
          <button className="t-sidebar-footer-item" onClick={signout}>
            <span style={{ fontSize: 11 }}>X</span>
            <span>Sign Out</span>
          </button>
        </div>
      </nav>

      <div className="t-main">
        <Header />
        <MarketTicker />
        <div className="t-content">
          {children}
        </div>
        <StatusBar />
      </div>
    </div>
  )
}
