'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const ITEMS = [
  { href: '/portfolio', label: 'Home', icon: '🏠' },
  { href: '/workspace', label: 'Trade', icon: '⚡' },
  { href: '/workspace?analyze=1', label: 'Analyze', icon: '🔬' },
  { href: '/terminal', label: 'Terminal', icon: '💻' },
  { href: '/marketdata', label: 'Option Chain', icon: '📡' },
  { href: '/strategies', label: 'Automate', icon: '🤖' },
  { href: '/portfolio', label: 'Portfolio', icon: '📊' },
  { href: '/settings', label: 'Settings', icon: '⚙' },
]

export default function WorkspaceSidebar() {
  const pathname = usePathname()
  return (
    <nav style={{
      width: 56, flexShrink: 0, borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, padding: '12px 0',
    }}>
      {ITEMS.map(item => {
        const sameRoute = item.href.split('?')[0] === pathname
        return (
          <Link
            key={item.label}
            href={item.href}
            title={item.label}
            style={{
              width: 42, height: 42, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 17, textDecoration: 'none', transition: 'all .15s',
              background: sameRoute ? 'color-mix(in srgb, var(--violet) 14%, transparent)' : 'transparent',
              border: sameRoute ? '1px solid var(--border-accent)' : '1px solid transparent',
              color: sameRoute ? 'var(--text-hi)' : 'var(--text-faint)',
            }}
          >
            {item.icon}
          </Link>
        )
      })}
    </nav>
  )
}
