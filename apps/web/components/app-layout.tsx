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
import BrokerStatusWidget from '@/components/BrokerStatusWidget'

function NavIcon({ href, active }: { href: string; active?: boolean }) {
  const s = active ? 'var(--cyan)' : 'currentColor'
  const common = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: s, strokeWidth: 1.7, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
  if (href === '/live') return <svg {...common}><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/></svg>
  if (href === '/go-live') return <svg {...common}><path d="M12 2l3 7h7l-5.5 4 2 7L12 16 5.5 20l2-7L2 9h7z"/><path d="M12 16v4"/></svg>
  if (href === '/trade') return <svg {...common}><path d="M9 5h6"/><path d="M9 12h6"/><path d="M9 19h6"/><path d="M5 5h.01"/><path d="M5 12h.01"/><path d="M5 19h.01"/></svg>
  if (href === '/positions') return <svg {...common}><circle cx="12" cy="12" r="3"/><path d="M12 2v3"/><path d="M12 19v3"/><path d="M2 12h3"/><path d="M19 12h3"/></svg>
  if (href === '/portfolio') return <svg {...common}><path d="M3 9h18v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9z"/><path d="M9 9V7a3 3 0 0 1 6 0v2"/></svg>
  if (href === '/funds') return <svg {...common}><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M16 10h.01"/><path d="M2 10h20"/></svg>
  if (href === '/paper') return <svg {...common}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8"/><path d="M8 17h8"/></svg>
  if (href === '/portal/brokers') return <svg {...common}><path d="M3 21h18"/><path d="M5 21V7l8-4 8 4v14"/><path d="M9 21v-6h6v6"/></svg>
  if (href === '/strategies/builder') return <svg {...common}><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><path d="M14 6h3"/><path d="M6 14v3"/></svg>
  if (href === '/backtest') return <svg {...common}><path d="M9 3H5a2 2 0 0 0-2 2v4"/><path d="M15 3h4a2 2 0 0 1 2 2v4"/><path d="M9 21H5a2 2 0 0 1-2-2v-4"/><path d="M15 21h4a2 2 0 0 1 2-2v-4"/><path d="M9 9h6v6H9z"/></svg>
  if (href === '/analytics') return <svg {...common}><path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/></svg>
  if (href === '/marketdata') return <svg {...common}><circle cx="11" cy="11" r="7"/><path d="M21 21l-3.5-3.5"/></svg>
  if (href === '/terminal') return <svg {...common}><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
  if (href === '/alerts') return <svg {...common}><path d="M6 8a6 6 0 0 1 12 0c0 7-6 11-6 11S6 15 6 8z"/><path d="M10 21h4"/></svg>
  if (href === '/reports/daily') return <svg {...common}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M10 13H8"/><path d="M16 13h-2"/><path d="M10 17H8"/><path d="M16 17h-2"/></svg>
  if (href === '/risk') return <svg {...common}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
  if (href === '/settings') return <svg {...common}><circle cx="12" cy="12" r="3"/><path d="M12 1v2"/><path d="M12 21v2"/><path d="M4.22 4.22l1.42 1.42"/><path d="M18.36 18.36l1.42 1.42"/><path d="M1 12h2"/><path d="M21 12h2"/><path d="M4.22 19.78l1.42-1.42"/><path d="M18.36 5.64l1.42-1.42"/></svg>
  if (href === '/help') return <svg {...common}><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>
  if (href === '/ai') return <svg {...common}><path d="M12 2l2.4 7.2H22l-6.2 4.5 2.4 7.2L12 16.4 5.8 20.9 8.2 13.7 2 9.2h7.6z"/></svg>
  if (href === '/strategies') return <svg {...common}><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
  return <svg {...common}><circle cx="12" cy="12" r="2"/></svg>
}

const USER_SECTIONS = [
  {
    label: 'Home',
    items: [
      { href: '/live', label: 'Live Dashboard' },
      { href: '/go-live', label: 'Go Live' },
    ],
  },
  {
    label: 'Trade',
    items: [
      { href: '/trade', label: 'Orders' },
      { href: '/positions', label: 'Positions' },
      { href: '/portfolio', label: 'Portfolio' },
      { href: '/funds', label: 'Funds' },
      { href: '/paper', label: 'Paper Trading' },
      { href: '/portal/brokers', label: 'Brokers' },
    ],
  },
  {
    label: 'Build & Analyze',
    items: [
      { href: '/strategies/builder', label: 'Strategy Builder' },
      { href: '/backtest', label: 'Backtest' },
      { href: '/analytics', label: 'Analytics' },
      { href: '/marketdata', label: 'Market Analyzer' },
      { href: '/terminal', label: 'Terminal' },
    ],
  },
  {
    label: 'Manage',
    items: [
      { href: '/reports/daily', label: 'Daily Report' },
      { href: '/alerts', label: 'Alerts' },
      { href: '/risk', label: 'Risk Control' },
      { href: '/settings', label: 'Settings' },
      { href: '/help', label: 'Help' },
    ],
  },
  {
    label: 'Platform',
    items: [
      { href: '/ai', label: 'AI Assistant' },
      { href: '/strategies', label: 'Strategies' },
    ],
  },
]

const ADMIN_SECTIONS = [
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
    ],
  },
  {
    label: 'Beta',
    items: [
      { href: '/admin/beta', label: 'Beta Dashboard', icon: 'β' },
      { href: '/admin/broadcast', label: 'Broadcast', icon: '📢' },
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

const STANDALONE_PAGES = ['/', '/auth', '/auth/callback', '/onboarding', '/status']
const STANDALONE_PREFIXES = ['/portal']
const ADMIN_ROUTE_RE = /^\/admin(\/|$)|\/dashboard(\/|$)/

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
  const [mobileOpen, setMobileOpen] = useState(false)
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
    } else if (!isAdmin && ADMIN_ROUTE_RE.test(pathname)) {
      router.replace('/live')
    }
  }, [loading, isAuthenticated, isAdmin, standalone, router, pathname])

  useEffect(() => {
    const stored = localStorage.getItem('sidebar-collapsed')
    if (stored === 'true') localStorage.setItem('sidebar-collapsed', 'false')
    setCollapsed(false)
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

  const sections = isAdmin ? [...USER_SECTIONS, ...ADMIN_SECTIONS] : USER_SECTIONS

  const isActive_ = (href: string) => {
    if (href === '/dashboard') return pathname === '/dashboard'
    if (href.includes('?')) return false
    return pathname === href || pathname.startsWith(href + '/')
  }

  return (
    <div style={{
      display: 'flex', height: '100dvh', width: '100%', overflow: 'hidden',
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
      <nav className={`tm-sidebar${mobileOpen ? ' tm-open' : ''}`} style={{
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
            <Link href={isAdmin ? '/dashboard' : '/live'} style={{
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
              className="tm-collapse-btn"
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
              className="tm-collapse-btn"
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
          {sections.map((section) => (
            <div key={section.label}>
              {(!collapsed || mobileOpen) && (
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
                     onClick={() => setMobileOpen(false)}
                      style={{
                       display: 'flex', alignItems: 'center', gap: 8,
                       padding: collapsed && !mobileOpen ? '8px' : '6px 12px',
                       margin: collapsed && !mobileOpen ? '2px 6px' : '0 6px',
                       borderRadius: 'var(--radius-sm)',
                       color: active ? 'var(--cyan)' : 'var(--text-sub)',
                       fontSize: active ? 12 : 11, fontWeight: 700,
                       textDecoration: 'none',
                       background: active ? 'var(--bg-active)' : 'transparent',
                       transition: 'all 150ms ease',
                       justifyContent: collapsed && !mobileOpen ? 'center' : 'flex-start',
                     }}
                    onMouseEnter={e => {
                      if (!active) { e.currentTarget.style.color = 'var(--text)'; e.currentTarget.style.background = 'var(--bg-hover)' }
                    }}
                    onMouseLeave={e => {
                      if (!active) { e.currentTarget.style.color = 'var(--text-sub)'; e.currentTarget.style.background = 'transparent' }
                    }}
                  >
                    <span style={{
                      width: 20, display: 'flex', alignItems: 'center', justifyContent: 'center',
                      flexShrink: 0, opacity: active ? 1 : 0.6,
                    }}>{(item as any).icon ? <span style={{ fontSize: 14 }}>{(item as any).icon}</span> : <NavIcon href={item.href} active={active} />}</span>
                    {(!collapsed || mobileOpen) && (
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
          padding: collapsed && !mobileOpen ? 4 : 8, borderTop: '1px solid var(--border)',
        }}>
          <button
            onClick={signout}
            aria-label="Sign out"
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: collapsed && !mobileOpen ? '8px' : '6px 8px',
              width: '100%', borderRadius: 'var(--radius-sm)',
              border: 'none', background: 'none', color: 'var(--text-sub)',
              fontFamily: 'var(--font-sans)', fontSize: 11, fontWeight: 700,
              cursor: 'pointer', transition: 'all 150ms ease',
              justifyContent: collapsed && !mobileOpen ? 'center' : 'flex-start',
            }}
            onMouseEnter={e => { e.currentTarget.style.color = 'var(--text)'; e.currentTarget.style.background = 'var(--bg-hover)' }}
            onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-sub)'; e.currentTarget.style.background = 'none' }}
          >
            <span style={{ fontSize: 14, opacity: 0.5 }}>⏻</span>
            {(!collapsed || mobileOpen) && <span>Sign Out</span>}
          </button>
        </div>
      </nav>

      {/* Mobile drawer backdrop */}
      {mobileOpen && (
        <div
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 55 }}
        />
      )}

      {/* Main */}
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0 }}>
        {/* Top Navbar */}
        <header className="tm-topbar" style={{
          height: 'var(--header-height)', display: 'flex', alignItems: 'center',
          padding: '0 12px', background: 'var(--bg-secondary)',
          borderBottom: '1px solid var(--border)', gap: 8, flexShrink: 0,
        }}>
          {/* Hamburger (mobile) */}
          <button
            onClick={() => setMobileOpen(o => !o)}
            aria-label="Toggle navigation menu"
            aria-expanded={mobileOpen}
            className="tm-hamburger"
            style={{
              display: 'none', alignItems: 'center', justifyContent: 'center',
              width: 30, height: 30, borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)', background: 'transparent',
              color: 'var(--text-sub)', cursor: 'pointer', flexShrink: 0, fontSize: 16,
            }}
          >☰</button>

          {/* Search */}
          <button
            onClick={() => { setSearchOpen(true); setTimeout(() => searchRef.current?.focus(), 50) }}
            data-search-open
            aria-label="Search symbols, strategies, pages (⌘K)"
            className="tm-search-btn"
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
          <div className="tm-ticker" style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
            <MarketTicker />
          </div>

          {/* AI Assistant button */}
          <Link href="/ai" className="tm-ai-btn" style={{
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

          {/* Broker connection status */}
          <span className="tm-broker-widget"><BrokerStatusWidget /></span>

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
              <span className="tm-profile-email" style={{ color: 'var(--text)', fontSize: 11, fontWeight: 600, fontFamily: 'var(--font-sans)' }}>
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
                <Link href="/account" style={{
                  display: 'block', padding: '8px 12px', color: 'var(--text-sub)',
                  fontSize: 12, textDecoration: 'none',
                  transition: 'all 100ms ease',
                }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)'; e.currentTarget.style.color = 'var(--text)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'var(--text-sub)' }}
                >Account</Link>
                <Link href="/feedback" style={{
                  display: 'block', padding: '8px 12px', color: 'var(--text-sub)',
                  fontSize: 12, textDecoration: 'none',
                  transition: 'all 100ms ease',
                }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)'; e.currentTarget.style.color = 'var(--text)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'var(--text-sub)' }}
                >Feedback</Link>
                <Link href="/changelog" style={{
                  display: 'block', padding: '8px 12px', color: 'var(--text-sub)',
                  fontSize: 12, textDecoration: 'none',
                  transition: 'all 100ms ease',
                }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)'; e.currentTarget.style.color = 'var(--text)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'var(--text-sub)' }}
                >Changelog</Link>
                <Link href="/transparency" style={{
                  display: 'block', padding: '8px 12px', color: 'var(--text-sub)',
                  fontSize: 12, textDecoration: 'none',
                  transition: 'all 100ms ease',
                }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)'; e.currentTarget.style.color = 'var(--text)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'var(--text-sub)' }}
                >Transparency</Link>
                <Link href="/status" style={{
                  display: 'block', padding: '8px 12px', color: 'var(--text-sub)',
                  fontSize: 12, textDecoration: 'none',
                  transition: 'all 100ms ease',
                }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)'; e.currentTarget.style.color = 'var(--text)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'var(--text-sub)' }}
                >Status</Link>
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

      <style jsx global>{`
        .t-content {
          flex: 1 1 auto;
          min-width: 0;
          overflow-y: auto;
        }

        @media (max-width: 860px) {
          .tm-sidebar {
            position: fixed !important;
            top: 0;
            bottom: 0;
            left: 0;
            width: min(264px, 85vw) !important;
            z-index: 61 !important;
            transform: translateX(-100%);
            transition: transform 200ms cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 0 40px rgba(0, 0, 0, 0.5);
          }
          .tm-sidebar.tm-open {
            transform: translateX(0);
          }
          .tm-topbar { z-index: 50 !important; }
          .tm-collapse-btn {
            display: none !important;
          }
          .tm-hamburger {
            display: flex !important;
            width: 44px !important;
            height: 44px !important;
            min-width: 44px !important;
            min-height: 44px !important;
          }
          .tm-topbar {
            padding: 0 8px !important;
            gap: 6px !important;
          }
          .tm-search-btn {
            width: 44px !important;
            height: 44px !important;
            min-width: 44px !important;
            min-height: 44px !important;
            padding: 0 !important;
            justify-content: center !important;
          }
          .tm-search-btn > span:not(:first-child) {
            display: none !important;
          }
          .tm-ticker {
            display: none !important;
          }
          .tm-broker-widget {
            display: none !important;
          }
          .tm-ai-btn > span:last-child {
            display: none !important;
          }
          .tm-ai-btn, .tm-topbar button { min-height: 44px !important; }
          .tm-profile-email {
            display: none !important;
          }
        }

        @media (min-width: 861px) {
          .tm-hamburger {
            display: none !important;
          }
        }
      `}</style>
    </div>
  )
}
