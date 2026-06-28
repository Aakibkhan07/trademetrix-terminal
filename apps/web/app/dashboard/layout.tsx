'use client'

import { usePathname, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth-context'
import { api } from '@/lib/api'

const NAV_ITEMS = [
  { href: '/dashboard', label: 'Dashboard', icon: 'D' },
  { href: '/strategies', label: 'Strategies', icon: 'S' },
  { href: '/brokers', label: 'Brokers', icon: 'B' },
  { href: '/marketdata', label: 'Market Data', icon: 'M' },
  { href: '/backtest', label: 'Backtest', icon: 'T' },
  { href: '/risk', label: 'Risk Control', icon: 'R' },
  { href: '/ai', label: 'AI Desk', icon: 'A' },
  { href: '/transparency', label: 'Transparency', icon: 'T' },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { token, signout, loading } = useAuth()
  const [killSwitchActive, setKillSwitchActive] = useState(false)

  useEffect(() => {
    if (!loading && !token) {
      router.push('/auth')
    }
  }, [token, loading, router])

  useEffect(() => {
    if (!token) return
    api.risk.killSwitchStatus().then((d: unknown) => {
      const data = d as { kill_switch_enabled: boolean }
      setKillSwitchActive(data.kill_switch_enabled)
    }).catch(() => {})
  }, [token])

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
        <div style={{ padding: '16px 24px', marginBottom: 16 }}>
          <h2 style={{
            fontFamily: 'Outfit', fontSize: 18, color: '#8b5cf6', margin: 0,
            textShadow: '0 0 10px rgba(139, 92, 246, 0.3)',
          }}>
            Trade Metrix
          </h2>
        </div>

        <nav>
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`nav-item ${pathname === item.href ? 'active' : ''}`}
            >
              <span style={{
                width: 24, height: 24, display: 'flex', alignItems: 'center',
                justifyContent: 'center', fontSize: 12, fontWeight: 600,
                border: '1px solid currentColor', borderRadius: 4,
              }}>
                {item.icon}
              </span>
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>

        <div style={{ marginTop: 'auto', padding: '16px 24px' }}>
          <div
            className={`kill-switch ${killSwitchActive ? 'active' : 'inactive'}`}
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
            <span style={{ width: 8, height: 8, borderRadius: '50%', display: 'inline-block',
              background: killSwitchActive ? '#ef4444' : '#555570',
              boxShadow: killSwitchActive ? '0 0 8px #ef4444' : 'none' }}
            />
            {killSwitchActive ? 'KILL SWITCH ON' : 'Kill Switch'}
          </div>

          <button
            className="btn btn-ghost"
            style={{ width: '100%', marginTop: 8 }}
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
