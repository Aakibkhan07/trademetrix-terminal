'use client'

import { usePathname, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useEffect, useState, useRef } from 'react'
import { useAuth } from '@/lib/auth-context'
import { useTheme } from '@/lib/use-theme'
import { useMarketData } from '@/lib/use-market-data'
import Logo from '@/components/logo'
import StatusBar from '@/components/status-bar'
import MarketTicker from '@/components/market-ticker'

const NAV_SECTIONS = [
  {
    label: 'Control Center',
    items: [
      { href: '/dashboard', label: 'Dashboard', icon: '◉' },
      { href: '/dashboard?tab=users', label: 'Users', icon: 'U' },
      { href: '/dashboard?tab=trades', label: 'Trades', icon: 'T' },
      { href: '/dashboard?tab=positions-book', label: 'Positions & Orders', icon: 'P' },
      { href: '/dashboard?tab=brokers', label: 'Brokers', icon: 'B' },
      { href: '/dashboard?tab=strategies', label: 'Strategies', icon: '⚔' },
    ],
  },
  {
    label: 'Operations',
    items: [
      { href: '/dashboard?tab=buyer-strategies', label: 'Buyer Strat', icon: 'S' },
      { href: '/dashboard?tab=subscriptions', label: 'Subscriptions', icon: '💳' },
      { href: '/dashboard?tab=trading-logs', label: 'Trading Logs', icon: '📋' },
      { href: '/dashboard?tab=pnl', label: 'P&L Dashboard', icon: '📊' },
      { href: '/dashboard?tab=strategy-perf', label: 'Perf Tracker', icon: '📈' },
      { href: '/dashboard?tab=user-strategies', label: 'User Algos', icon: '🤖' },
      { href: '/dashboard?tab=referrals', label: 'Referrals', icon: '🔗' },
      { href: '/dashboard?tab=webhook-tester', label: 'Webhook Tester', icon: '🔌' },
      { href: '/dashboard?tab=trade-router', label: 'Trade Router', icon: '🔀' },
      { href: '/dashboard?tab=backups', label: 'Backups', icon: '💾' },
      { href: '/dashboard?tab=ip-whitelist', label: 'IP Whitelist', icon: '🛡️' },
    ],
  },
  {
    label: 'Security',
    items: [
      { href: '/dashboard?tab=risk', label: 'Risk', icon: 'R' },
      { href: '/dashboard?tab=activity', label: 'Activity', icon: '⏱' },
      { href: '/dashboard?tab=audit', label: 'Audit Log', icon: 'A' },
      { href: '/admin/admins', label: 'Admins', icon: '#' },
    ],
  },
]

const STANDALONE_PAGES = ['/', '/auth', '/onboarding', '/status']
const STANDALONE_PREFIXES = ['/portal']

function isStandalone(pathname: string) {
  if (STANDALONE_PAGES.includes(pathname)) return true
  if (STANDALONE_PREFIXES.some(p => pathname.startsWith(p))) return true
  return false
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { user, loading, isAdmin, signout } = useAuth()
  const [collapsed, setCollapsed] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [notifOpen, setNotifOpen] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)
  const { theme, toggleTheme } = useTheme()
  const { connected } = useMarketData()

  const isAuthenticated = !!user
  const standalone = isStandalone(pathname)

  useEffect(() => {
    if (loading || standalone) return
    if (!isAuthenticated) {
      router.replace('/auth')
    } else if (!isAdmin) {
      router.replace('/portal')
    }
  }, [loading, isAuthenticated, isAdmin, standalone, router])

  useEffect(() => {
    const stored = localStorage.getItem('sidebar-collapsed')
    if (stored === 'true') setCollapsed(true)
  }, [])

  useEffect(() => {
    localStorage.setItem('sidebar-collapsed', String(collapsed))
  }, [collapsed])

  useEffect(() => {
    const handleClick = () => { setProfileOpen(false); setNotifOpen(false) }
    window.addEventListener('click', handleClick)
    return () => window.removeEventListener('click', handleClick)
  }, [])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSearchOpen(false)
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); setSearchOpen(true) }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [])

  if (standalone) return <>{children}</>

  if (loading || !isAuthenticated) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100vh', background: 'var(--bg)',
        color: 'var(--text-faint)',
      }}>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>Loading...</p>
      </div>
    )
  }

  const isActive_ = (href: string) => {
    if (href === '/dashboard') return pathname === '/dashboard'
    return pathname.startsWith(href)
  }

  return (
    <div style={{
      display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden',
      background: 'var(--bg)',
    }}>
      {/* Sidebar */}
      <nav style={{
        width: collapsed ? 'var(--sidebar-collapsed)' : 'var(--sidebar-width)',
        background: 'var(--bg-secondary)',
        borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', flexShrink: 0,
        overflow: 'hidden',
        transition: 'width 200ms cubic-bezier(0.4, 0, 0.2, 1)',
        position: 'relative', zIndex: 10,
      }}>
        {/* Logo + Toggle */}
        <div style={{
          display: 'flex', alignItems: 'center',
          padding: collapsed ? '10px 8px' : '10px 12px',
          borderBottom: '1px solid var(--border)',
          gap: 8, height: 48, boxSizing: 'border-box',
        }}>
          {!collapsed && (
            <Link href="/dashboard" style={{
              display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none', flex: 1, minWidth: 0,
            }}>
              <div style={{
                width: 24, height: 24, borderRadius: 6,
                background: 'var(--gradient-primary)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700, color: '#fff', flexShrink: 0,
              }}>TM</div>
              <span style={{
                fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 700,
                background: 'var(--gradient-primary)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>TradeMetrix</span>
            </Link>
          )}
          {collapsed && (
            <div style={{
              width: 24, height: 24, borderRadius: 6,
              background: 'var(--gradient-primary)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, fontWeight: 700, color: '#fff', flexShrink: 0,
              margin: '0 auto',
            }}>TM</div>
          )}
          {!collapsed && (
            <button
              onClick={() => setCollapsed(true)}
              style={{
                background: 'none', border: 'none', color: 'var(--text-faint)',
                cursor: 'pointer', fontSize: 14, padding: 4, flexShrink: 0,
                fontFamily: 'var(--font-sans)',
                transition: 'color 150ms ease',
              }}
              onMouseEnter={e => { e.currentTarget.style.color = 'var(--text)' }}
              onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-faint)' }}
            >◁</button>
          )}
          {collapsed && (
            <button
              onClick={() => setCollapsed(false)}
              style={{
                position: 'absolute', right: -12, top: 12, zIndex: 20,
                width: 20, height: 20, borderRadius: '50%',
                background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
                color: 'var(--text-sub)', cursor: 'pointer', fontSize: 10,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                padding: 0,
                transition: 'all 150ms ease',
              }}
              onMouseEnter={e => { e.currentTarget.style.color = 'var(--cyan)'; e.currentTarget.style.borderColor = 'var(--border-accent)' }}
              onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-sub)'; e.currentTarget.style.borderColor = 'var(--border)' }}
            >▷</button>
          )}
        </div>

        {/* Navigation */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
          {NAV_SECTIONS.map((section) => (
            <div key={section.label}>
              {!collapsed && (
                <div style={{ padding: '8px 12px 2px' }}>
                  <div style={{
                    fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
                    letterSpacing: '0.12em', color: 'var(--text-faint)',
                  }}>{section.label}</div>
                </div>
              )}
              {section.items.map((item) => {
                const active = isActive_(item.href)
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: collapsed ? '8px' : '6px 12px',
                      margin: collapsed ? '2px 6px' : '0 6px',
                      borderRadius: 'var(--radius-sm)',
                      color: active ? 'var(--cyan)' : 'var(--text-sub)',
                      fontSize: active ? 12 : 11, fontWeight: 700,
                      textDecoration: 'none',
                      background: active ? 'var(--bg-active)' : 'transparent',
                      transition: 'all 150ms ease',
                      justifyContent: collapsed ? 'center' : 'flex-start',
                    }}
                    onMouseEnter={e => {
                      if (!active) { e.currentTarget.style.color = 'var(--text)'; e.currentTarget.style.background = 'var(--bg-hover)' }
                    }}
                    onMouseLeave={e => {
                      if (!active) { e.currentTarget.style.color = 'var(--text-sub)'; e.currentTarget.style.background = 'transparent' }
                    }}
                  >
                    <span style={{
                      fontSize: 14, width: 20, textAlign: 'center',
                      flexShrink: 0, opacity: active ? 1 : 0.5,
                    }}>{item.icon}</span>
                    {!collapsed && (
                      <span style={{
                        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>{item.label}</span>
                    )}
                  </Link>
                )
              })}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div style={{
          padding: collapsed ? 4 : 8, borderTop: '1px solid var(--border)',
        }}>
          <button
            onClick={signout}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: collapsed ? '8px' : '6px 8px',
              width: '100%', borderRadius: 'var(--radius-sm)',
              border: 'none', background: 'none', color: 'var(--text-sub)',
              fontFamily: 'var(--font-sans)', fontSize: 11, fontWeight: 700,
              cursor: 'pointer', transition: 'all 150ms ease',
              justifyContent: collapsed ? 'center' : 'flex-start',
            }}
            onMouseEnter={e => { e.currentTarget.style.color = 'var(--text)'; e.currentTarget.style.background = 'var(--bg-hover)' }}
            onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-sub)'; e.currentTarget.style.background = 'none' }}
          >
            <span style={{ fontSize: 14, opacity: 0.5 }}>⏻</span>
            {!collapsed && <span>Sign Out</span>}
          </button>
        </div>
      </nav>

      {/* Main */}
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0 }}>
        {/* Top Navbar */}
        <header style={{
          height: 'var(--header-height)', display: 'flex', alignItems: 'center',
          padding: '0 12px', background: 'var(--bg-secondary)',
          borderBottom: '1px solid var(--border)', gap: 8, flexShrink: 0,
        }}>
          {/* Search */}
          <div
            onClick={() => { setSearchOpen(true); setTimeout(() => searchRef.current?.focus(), 50) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)', padding: '0 10px',
              height: 30, width: 240, cursor: 'text', flexShrink: 0,
            }}>
            <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>🔍</span>
            <span style={{ color: 'var(--text-faint)', fontSize: 12, flex: 1 }}>
              {searchQuery || 'Search...'}
            </span>
            <span style={{ color: 'var(--text-faint)', fontSize: 10, fontFamily: 'var(--font-mono)' }}>⌘K</span>
          </div>

          {/* Market Ticker */}
          <div style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
            <MarketTicker />
          </div>

          {/* AI Assistant button */}
          <Link href="/ai" style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 10px', borderRadius: 'var(--radius-sm)',
            background: 'rgba(0,212,255,0.08)', border: '1px solid rgba(0,212,255,0.15)',
            color: 'var(--cyan)', fontSize: 11, fontWeight: 600,
            textDecoration: 'none', height: 28, flexShrink: 0,
            transition: 'all 150ms ease',
          }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(0,212,255,0.12)'; e.currentTarget.style.boxShadow = '0 0 12px rgba(0,212,255,0.15)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(0,212,255,0.08)'; e.currentTarget.style.boxShadow = 'none' }}
          >
            <span style={{ fontSize: 14 }}>✦</span>
            AI
          </Link>

          {/* Theme toggle */}
          <button onClick={toggleTheme} style={{
            width: 28, height: 28, borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border)', background: 'transparent',
            color: 'var(--text-sub)', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 14, flexShrink: 0,
            transition: 'all 150ms ease',
          }}
            onMouseEnter={e => { e.currentTarget.style.color = 'var(--text)'; e.currentTarget.style.borderColor = 'var(--border-hi)' }}
            onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-sub)'; e.currentTarget.style.borderColor = 'var(--border)' }}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          >
            {theme === 'dark' ? '☀' : '☽'}
          </button>

          {/* Notifications */}
          <div style={{ position: 'relative' }}>
            <button onClick={(e) => { e.stopPropagation(); setNotifOpen(!notifOpen) }} style={{
              width: 28, height: 28, borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)', background: 'transparent',
              color: 'var(--text-sub)', cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 14, position: 'relative', flexShrink: 0,
              transition: 'all 150ms ease',
            }}
              onMouseEnter={e => { e.currentTarget.style.color = 'var(--text)'; e.currentTarget.style.borderColor = 'var(--border-hi)' }}
              onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-sub)'; e.currentTarget.style.borderColor = 'var(--border)' }}
            >
              🔔
              <span style={{
                position: 'absolute', top: 2, right: 2, width: 6, height: 6,
                borderRadius: '50%', background: 'var(--red)',
              }} />
            </button>
            {notifOpen && (
              <div style={{
                position: 'absolute', top: '100%', right: 0, marginTop: 4,
                width: 280, background: 'var(--bg-secondary)',
                border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
                boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                zIndex: 100, overflow: 'hidden',
              }} onClick={e => e.stopPropagation()}>
                <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ color: 'var(--text)', fontSize: 12, fontWeight: 600 }}>Notifications</div>
                </div>
                <div style={{ padding: '16px 12px', textAlign: 'center' }}>
                  <span className="t-faint" style={{ fontSize: 11 }}>No new notifications</span>
                </div>
                <Link href="/alerts" style={{
                  display: 'block', padding: '8px 12px', borderTop: '1px solid var(--border)',
                  color: 'var(--cyan)', fontSize: 11, fontWeight: 600, textDecoration: 'none', textAlign: 'center',
                }}>View all alerts →</Link>
              </div>
            )}
          </div>

          {/* User Profile */}
          <div style={{ position: 'relative' }}>
            <button
              onClick={(e) => { e.stopPropagation(); setProfileOpen(!profileOpen) }}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '2px 8px 2px 2px', borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border)', background: 'transparent',
                cursor: 'pointer', height: 30,
                transition: 'all 150ms ease', flexShrink: 0,
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--border-hi)' }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)' }}
            >
              <div style={{
                width: 22, height: 22, borderRadius: '50%',
                background: 'var(--gradient-primary)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 10, fontWeight: 700, color: '#fff',
              }}>
                {user?.email?.[0]?.toUpperCase() || 'U'}
              </div>
              <span style={{ color: 'var(--text)', fontSize: 11, fontWeight: 600, fontFamily: 'var(--font-sans)' }}>
                {user?.email?.split('@')[0] || 'User'}
              </span>
              <span className={`t-dot ${connected ? 't-dot-green' : 't-dot-red'}`} style={{ width: 5, height: 5 }} />
            </button>

            {profileOpen && (
              <div style={{
                position: 'absolute', top: '100%', right: 0, marginTop: 4,
                minWidth: 180, background: 'var(--bg-secondary)',
                border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
                boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                zIndex: 100, overflow: 'hidden',
              }} onClick={e => e.stopPropagation()}>
                <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ color: 'var(--text)', fontSize: 12, fontWeight: 600 }}>{user?.email}</div>
                  <div style={{ color: 'var(--text-faint)', fontSize: 10, marginTop: 2 }}>
                    {isAdmin ? 'Administrator' : 'Trader'}
                  </div>
                </div>
                <Link href="/settings" style={{
                  display: 'block', padding: '8px 12px', color: 'var(--text-sub)',
                  fontSize: 12, textDecoration: 'none',
                  transition: 'all 100ms ease',
                }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)'; e.currentTarget.style.color = 'var(--text)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'var(--text-sub)' }}
                >Settings</Link>
                <button onClick={signout} style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  padding: '8px 12px', color: 'var(--red)',
                  fontSize: 12, background: 'none', border: 'none',
                  cursor: 'pointer', fontFamily: 'var(--font-sans)',
                  transition: 'all 100ms ease',
                }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.08)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
                >Sign Out</button>
              </div>
            )}
          </div>
        </header>

        {/* Search Overlay */}
        {searchOpen && (
          <div style={{
            position: 'fixed', inset: 0, zIndex: 200,
            background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
            display: 'flex', justifyContent: 'center', paddingTop: '15vh',
          }} onClick={() => setSearchOpen(false)}>
            <div className="t-panel" style={{
              width: 480, maxWidth: '90vw', padding: 0, maxHeight: '60vh', overflow: 'hidden',
              display: 'flex', flexDirection: 'column',
            }} onClick={e => e.stopPropagation()}>
              <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{ color: 'var(--text-faint)', fontSize: 14 }}>🔍</span>
                <input
                  ref={searchRef}
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  placeholder="Search symbols, strategies, pages..."
                  style={{
                    background: 'none', border: 'none', outline: 'none',
                    color: 'var(--text)', fontFamily: 'var(--font-sans)',
                    fontSize: 14, width: '100%',
                  }}
                />
                <span style={{ color: 'var(--text-faint)', fontSize: 10 }}>ESC</span>
              </div>
              <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
                {searchQuery.length < 2 ? (
                  <div style={{ padding: '16px', textAlign: 'center' }}>
                    <span className="t-faint" style={{ fontSize: 12 }}>Type at least 2 characters to search</span>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <Link href={`/terminal?symbol=${searchQuery}`} onClick={() => setSearchOpen(false)} style={{
                      display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
                      borderRadius: 'var(--radius-sm)', color: 'var(--text)', fontSize: 12,
                      textDecoration: 'none', transition: 'all 100ms ease',
                    }}
                      onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
                    >
                      <span style={{ fontSize: 14 }}>▶</span>
                      <div>
                        <div style={{ fontWeight: 600 }}>Trade {searchQuery}</div>
                        <span className="t-faint" style={{ fontSize: 10 }}>Open in terminal</span>
                      </div>
                    </Link>
                    <Link href={`/marketdata?symbol=${searchQuery}`} onClick={() => setSearchOpen(false)} style={{
                      display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
                      borderRadius: 'var(--radius-sm)', color: 'var(--text)', fontSize: 12,
                      textDecoration: 'none', transition: 'all 100ms ease',
                    }}
                      onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
                    >
                      <span style={{ fontSize: 14 }}>▲</span>
                      <div>
                        <div style={{ fontWeight: 600 }}>Analyze {searchQuery}</div>
                        <span className="t-faint" style={{ fontSize: 10 }}>Market analysis & chart</span>
                      </div>
                    </Link>
                    <Link href={`/strategies?search=${searchQuery}`} onClick={() => setSearchOpen(false)} style={{
                      display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
                      borderRadius: 'var(--radius-sm)', color: 'var(--text)', fontSize: 12,
                      textDecoration: 'none', transition: 'all 100ms ease',
                    }}
                      onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
                    >
                      <span style={{ fontSize: 14 }}>◈</span>
                      <div>
                        <div style={{ fontWeight: 600 }}>Strategies</div>
                        <span className="t-faint" style={{ fontSize: 10 }}>Search strategies</span>
                      </div>
                    </Link>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Content */}
        <div className="t-content">
          {children}
        </div>

        {/* Status Bar */}
        <StatusBar />
      </div>
    </div>
  )
}
