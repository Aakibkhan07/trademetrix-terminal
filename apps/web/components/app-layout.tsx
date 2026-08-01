'use client'

import { usePathname, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useEffect, useState, useRef } from 'react'
import { useAuth } from '@/lib/auth-context'
import { useTheme } from '@/lib/use-theme'
import { useMarketData } from '@/lib/use-market-data'
import { api } from '@/lib/api'
import Logo from '@/components/logo'
import StatusBar from '@/components/status-bar'
import MarketTicker from '@/components/market-ticker'

const NAV_SECTIONS = [
  {
    label: 'Trading',
    items: [
      { href: '/dashboard?tab=trade-router', label: 'Place Trade', icon: '⚡' },
      { href: '/dashboard?tab=trades', label: 'Trades', icon: 'T' },
      { href: '/dashboard?tab=positions-book', label: 'Positions & Orders', icon: 'P' },
    ],
  },
  {
    label: 'Control Center',
    items: [
      { href: '/ai', label: 'AI Assistant', icon: '✦' },
      { href: '/dashboard', label: 'Dashboard', icon: '◉' },
      { href: '/dashboard?tab=users', label: 'Users', icon: 'U' },
      { href: '/dashboard?tab=brokers', label: 'Brokers', icon: 'B' },
      { href: '/dashboard?tab=strategies', label: 'Strategies', icon: '⚔' },
    ],
  },
  {
    label: 'Operations',
    items: [
      { href: '/dashboard?tab=buyer-strategies', label: 'Buyer Strat', icon: 'S' },
      { href: '/dashboard?tab=trading-logs', label: 'Trading Logs', icon: '📋' },
      { href: '/dashboard?tab=pnl', label: 'P&L Dashboard', icon: '📊' },
      { href: '/dashboard?tab=strategy-perf', label: 'Perf Tracker', icon: '📈' },
      { href: '/dashboard?tab=user-strategies', label: 'User Algos', icon: '🤖' },
      { href: '/dashboard?tab=referrals', label: 'Referrals', icon: '🔗' },
      { href: '/dashboard?tab=webhook-tester', label: 'Webhook Tester', icon: '🔌' },
      { href: '/dashboard?tab=backups', label: 'Backups', icon: '💾' },
      { href: '/dashboard?tab=scheduled-tasks', label: 'Scheduled', icon: '⏰' },
    ],
  },
  {
    label: 'Security',
    items: [
      { href: '/dashboard?tab=risk', label: 'Risk', icon: 'R' },
      { href: '/dashboard?tab=activity', label: 'Activity', icon: '⏱' },
      { href: '/dashboard?tab=audit', label: 'Audit Log', icon: 'A' },
      { href: '/dashboard?tab=ip-whitelist', label: 'IP Whitelist', icon: '🛡️' },
      { href: '/admin/admins', label: 'Admins', icon: '#' },
    ],
  },
]

const STANDALONE_PAGES = ['/', '/auth', '/onboarding', '/status', '/portfolio']
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
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const searchTimer = useRef<ReturnType<typeof setTimeout>>()
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
      router.replace('/portfolio')
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
      if (e.key === 'Escape') {
        setSearchOpen(false); setSearchQuery(''); setSearchResults([])
        restoreFocus()
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'k' && pathname !== '/workspace') { e.preventDefault(); setSearchOpen(true) }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [pathname])

  const closeSearch = () => {
    setSearchOpen(false); setSearchQuery(''); setSearchResults([])
    restoreFocus()
  }

  const restoreFocus = () => {
    const prev = document.activeElement as HTMLElement | null
    const inOverlay = prev && prev.closest('[data-search-overlay]')
    if (inOverlay) {
      const openButton = document.querySelector<HTMLElement>('[data-search-open]')
      openButton?.focus()
    }
  }

  useEffect(() => {
    if (!searchOpen) return
    const handleTab = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      const overlay = document.querySelector<HTMLElement>('[data-search-overlay]')
      if (!overlay) return
      const focusables = Array.from(overlay.querySelectorAll<HTMLElement>(
        'a[href], input, button, [tabindex]:not([tabindex="-1"])',
      )).filter(el => !el.hasAttribute('disabled'))
      if (focusables.length === 0) { e.preventDefault(); return }
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', handleTab)
    return () => window.removeEventListener('keydown', handleTab)
  }, [searchOpen])

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current)
    if (searchQuery.length < 2) { setSearchResults([]); return }
    setSearchLoading(true)
    searchTimer.current = setTimeout(async () => {
      try {
        const data = await api.get<{ results: { symbol: string; name: string; instrument_type: string; exchange: string }[] }>(`/market/instruments?query=${encodeURIComponent(searchQuery)}&limit=8`)
        setSearchResults(data.results || [])
      } catch { setSearchResults([]) }
      setSearchLoading(false)
    }, 300)
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current) }
  }, [searchQuery])

  if (standalone) return <>{children}</>

  const isActive_ = (href: string) => {
    if (href === '/dashboard') return pathname === '/dashboard'
    return pathname.startsWith(href)
  }

  return (
    <div style={{
      display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden',
      background: 'var(--bg)',
    }}>
      <a href="#main-content" style={{
        position: 'fixed', top: -48, left: 12, zIndex: 300,
        padding: '8px 14px', borderRadius: 'var(--radius-md)',
        background: 'var(--bg-tertiary)', color: 'var(--text)',
        fontSize: 12, fontWeight: 700, border: '1px solid var(--border-accent)',
        textDecoration: 'none', transition: 'top 150ms ease',
      }}
        onFocus={e => { e.currentTarget.style.top = '12px' }}
        onBlur={e => { e.currentTarget.style.top = '-48px' }}
      >Skip to content</a>
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
              <Logo size={24} />
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
            <Logo size={24} />
          )}
          {!collapsed && (
            <button
              onClick={() => setCollapsed(true)}
              aria-label="Collapse sidebar"
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
              aria-label="Expand sidebar"
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
                    aria-current={active ? 'page' : undefined}
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
            aria-label="Sign out"
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
          <button
            onClick={() => { setSearchOpen(true); setTimeout(() => searchRef.current?.focus(), 50) }}
            data-search-open
            aria-label="Search symbols, strategies, pages (⌘K)"
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)', padding: '0 10px',
              height: 30, width: 240, cursor: 'pointer', flexShrink: 0,
              fontFamily: 'var(--font-sans)', textAlign: 'left',
              transition: 'border-color 150ms ease',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--border-hi)' }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)' }}
          >
            <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>🔍</span>
            <span style={{ color: 'var(--text-faint)', fontSize: 12, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {searchQuery || 'Search...'}
            </span>
            <span style={{ color: 'var(--text-faint)', fontSize: 10, fontFamily: 'var(--font-mono)' }}>⌘K</span>
          </button>

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
          <button onClick={toggleTheme} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`} style={{
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
            <button onClick={(e) => { e.stopPropagation(); setNotifOpen(!notifOpen) }} aria-label="Notifications" aria-expanded={notifOpen} aria-controls="notifications-popover" style={{
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
              <div id="notifications-popover" role="menu" aria-label="Notifications" onClick={e => e.stopPropagation()} style={{
                position: 'absolute', top: '100%', right: 0, marginTop: 4,
                width: 280, background: 'var(--bg-secondary)',
                border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
                boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                zIndex: 100, overflow: 'hidden',
              }}>
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
              aria-label="Account menu" aria-expanded={profileOpen} aria-controls="profile-popover"
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
                {user?.email?.[0]?.toUpperCase() || '?'}
              </div>
              <span style={{ color: 'var(--text)', fontSize: 11, fontWeight: 600, fontFamily: 'var(--font-sans)' }}>
                {user?.email?.split('@')[0] || '—'}
              </span>
              <span className={`t-dot ${connected ? 't-dot-green' : 't-dot-red'}`} style={{ width: 5, height: 5 }} />
            </button>

            {profileOpen && (
              <div id="profile-popover" role="menu" aria-label="Account" onClick={e => e.stopPropagation()} style={{
                position: 'absolute', top: '100%', right: 0, marginTop: 4,
                minWidth: 180, background: 'var(--bg-secondary)',
                border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
                boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                zIndex: 100, overflow: 'hidden',
              }}>
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
          <div data-search-overlay role="dialog" aria-modal="true" aria-label="Global search"
            style={{
            position: 'fixed', inset: 0, zIndex: 200,
            background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
            display: 'flex', justifyContent: 'center', paddingTop: '15vh',
          }} onClick={closeSearch}>
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
                    {searchLoading && (
                      <div style={{ padding: '12px', textAlign: 'center' }}>
                        <span className="t-faint" style={{ fontSize: 11 }}>Searching...</span>
                      </div>
                    )}
                    {searchResults.length > 0 && (
                      <>
                        <div style={{ padding: '4px 12px' }}>
                          <span className="t-faint" style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Symbols</span>
                        </div>
                        {searchResults.map((r: any, i: number) => (
                          <Link key={i} href={`/terminal?symbol=${r.symbol}`} onClick={() => setSearchOpen(false)} style={{
                            display: 'flex', alignItems: 'center', gap: 10, padding: '6px 12px',
                            borderRadius: 'var(--radius-sm)', color: 'var(--text)', fontSize: 12,
                            textDecoration: 'none', transition: 'all 100ms ease',
                          }}
                            onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
                            onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
                          >
                            <span style={{ fontSize: 12, width: 20, textAlign: 'center', color: 'var(--cyan)' }}>
                              {r.instrument_type === 'option' ? '⚡' : r.instrument_type === 'future' ? '📊' : '📈'}
                            </span>
                            <div style={{ flex: 1 }}>
                              <div style={{ fontWeight: 600 }}>{r.symbol}</div>
                              <span className="t-faint" style={{ fontSize: 10 }}>{r.name}</span>
                            </div>
                            <span style={{ fontSize: 10, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>
                              {r.instrument_type?.toUpperCase()}
                            </span>
                          </Link>
                        ))}
                        <div style={{ height: 1, background: 'var(--border)', margin: '4px 0' }} />
                      </>
                    )}
                    {!searchLoading && searchQuery.length >= 2 && searchResults.length === 0 && (
                      <div style={{ padding: '8px 12px', textAlign: 'center' }}>
                        <span className="t-faint" style={{ fontSize: 11 }}>No matching symbols found</span>
                      </div>
                    )}
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
        <div className="t-content" id="main-content">
          {children}
        </div>

        {/* Status Bar */}
        <StatusBar />
      </div>
    </div>
  )
}
