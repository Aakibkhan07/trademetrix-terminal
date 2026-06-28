'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV_LINKS = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/strategies', label: 'Strategies' },
  { href: '/brokers', label: 'Brokers' },
  { href: '/marketdata', label: 'Market Data' },
  { href: '/backtest', label: 'Backtest' },
  { href: '/ai', label: 'AI Desk' },
]

export default function Header() {
  const pathname = usePathname()

  if (pathname === '/auth') return null

  return (
    <header className="header">
      <Link href="/dashboard" className="header-brand" style={{ textDecoration: 'none' }}>
        TradeMetrixTech
      </Link>

      <nav className="header-nav">
        {NAV_LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={pathname.startsWith(link.href) ? 'active' : ''}
          >
            {link.label}
          </Link>
        ))}
      </nav>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="badge badge-green">
          <span className="status-dot active" style={{ marginRight: 4 }} />
          System OK
        </span>
      </div>
    </header>
  )
}
