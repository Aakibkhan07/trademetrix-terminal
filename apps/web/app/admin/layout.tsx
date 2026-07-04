'use client'

import { Suspense } from 'react'
import { useSearchParams, usePathname } from 'next/navigation'
import Link from 'next/link'
import { AppVersion } from '@/components/app-version'

const TABS = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'users', label: 'Users' },
  { key: 'brokers', label: 'Brokers' },
  { key: 'trades', label: 'Trades' },
  { key: 'audit', label: 'Audit Log' },
  { key: 'risk', label: 'Risk' },
  { key: 'founder', label: 'Founder', href: '/admin/founder' },
  { key: 'admins', label: 'Admins', href: '/admin/admins' },
  { key: 'beta', label: 'Beta', href: '/admin/beta' },
]

function TabBar() {
  const searchParams = useSearchParams()
  const pathname = usePathname()
  const activeTab = pathname === '/admin' ? (searchParams.get('tab') || 'dashboard') : ''

  return (
    <div style={{ display: 'flex', gap: 0, marginBottom: 20, borderBottom: '1px solid rgba(139,92,246,0.15)', overflowX: 'auto' }}>
      {TABS.map(tab => {
        const href = tab.href ? tab.href : `/admin?tab=${tab.key}`
        const isActive = tab.href ? pathname === tab.href : pathname === '/admin' && activeTab === tab.key
        return (
          <Link key={tab.key} href={href} style={{
            padding: '8px 16px', fontSize: 12, fontWeight: isActive ? 600 : 400,
            background: 'none', border: 'none', borderBottom: isActive ? '2px solid var(--violet)' : '2px solid transparent',
            color: isActive ? 'var(--violet)' : '#8888a0', cursor: 'pointer', whiteSpace: 'nowrap',
            fontFamily: 'inherit', textDecoration: 'none',
          }}>
            {tab.label}
          </Link>
        )
      })}
    </div>
  )
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-page-title" style={{ margin: 0 }}>Control Center</h1>
        <p className="t-sub" style={{ fontSize: 13, margin: '2px 0 0' }}>Full system administration · <AppVersion /></p>
      </div>
      <Suspense fallback={
        <div style={{ display: 'flex', gap: 0, marginBottom: 20, borderBottom: '1px solid rgba(139,92,246,0.15)', height: 33 }} />
      }>
        <TabBar />
      </Suspense>
      {children}
    </div>
  )
}
