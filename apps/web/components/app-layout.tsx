'use client'

import { usePathname, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth-context'
import { api } from '@/lib/api'

const NAV_ITEMS = [
  { href: '/dashboard', label: 'Dashboard', icon: 'D' },
  { href: '/terminal', label: 'Terminal', icon: 'T' },
  { href: '/trade', label: 'Trade', icon: 'O' },
  { href: '/positions', label: 'Positions', icon: 'P' },
  { href: '/marketdata', label: 'Market', icon: 'M' },
  { href: '/strategies', label: 'Strategies', icon: 'S' },
  { href: '/brokers', label: 'Brokers', icon: 'B' },
  { href: '/backtest', label: 'Backtest', icon: 'K' },
  { href: '/risk', label: 'Risk', icon: 'R' },
  { href: '/ai', label: 'AI', icon: 'A' },
  { href: '/transparency', label: 'Reports', icon: 'E' },
]

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { user, loading, signout } = useAuth()
  const [killSwitchActive, setKillSwitchActive] = useState(false)

  const isAuthenticated = !!user

  useEffect(() => {
    if (!isAuthenticated || pathname === '/auth') return
    api.risk.killSwitchStatus().then((d: unknown) => {
      const data = d as { kill_switch_enabled: boolean }
      setKillSwitchActive(data.kill_switch_enabled)
    }).catch(() => {})
  }, [isAuthenticated, pathname])

  useEffect(() => {
    if (!loading && !isAuthenticated && pathname !== '/auth' && pathname !== '/onboarding') {
      router.replace('/auth')
    }
  }, [loading, isAuthenticated, pathname, router])

  if (pathname === '/auth' || pathname === '/onboarding') return <>{children}</>

  if (loading || !isAuthenticated) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: 'var(--bg)', color: 'var(--text-faint)' }}>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>Loading...</p>
      </div>
    )
  }

  return (
    <>
      <nav className="t-sidebar">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href))
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`t-nav-item ${isActive ? 'active' : ''}`}
              title={item.label}
            >
              {item.icon}
            </Link>
          )
        })}

        <div className="t-nav-spacer" />

        <button
          className={`t-kill ${killSwitchActive ? 'active' : 'inactive'}`}
          style={{ width: 36, justifyContent: 'center' }}
          onClick={async () => {
            if (killSwitchActive) {
              await api.risk.disableKillSwitch()
              setKillSwitchActive(false)
            } else {
              await api.risk.enableKillSwitch()
              setKillSwitchActive(true)
            }
          }}
          title={killSwitchActive ? 'Kill Switch ON' : 'Kill Switch'}
        >
          <span className={`t-dot ${killSwitchActive ? 't-dot-red t-dot-pulse' : 't-dot-sub'}`} />
        </button>

        <button
          className="t-nav-item"
          onClick={signout}
          title="Sign Out"
          style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 10 }}
        >
          X
        </button>
      </nav>

      {children}
    </>
  )
}
