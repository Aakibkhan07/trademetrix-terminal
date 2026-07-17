'use client'

import { useState, useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import dynamic from 'next/dynamic'
import { useAuth } from '@/lib/auth-context'
import { SkeletonCard } from '@/components/skeleton'

const AdminDashboard = dynamic(() => import('./admin-content').then(m => ({ default: m.AdminDashboard })), {
  loading: () => (
    <div>
      <div className="t-grid-4" style={{ gap: 10 }}>
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="t-panel" style={{ padding: '14px 16px' }}>
            <SkeletonCard />
          </div>
        ))}
      </div>
    </div>
  ),
})

const NotAuthorized = dynamic(() => import('./admin-content').then(m => ({ default: m.NotAuthorized })))

function DashboardInner() {
  const { isAdmin, loading } = useAuth()
  const searchParams = useSearchParams()
  const tab = searchParams.get('tab') || 'dashboard'

  if (loading) {
    return (
      <div>
        <div className="t-grid-4" style={{ gap: 10 }}>
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="t-panel" style={{ padding: '14px 16px' }}>
              <div style={{ width: '40%', height: 12, background: 'color-mix(in srgb, var(--violet) 8%, transparent)', borderRadius: 4 }} />
              <div style={{ height: 8 }} />
              <div style={{ width: '60%', height: 12, background: 'color-mix(in srgb, var(--violet) 8%, transparent)', borderRadius: 4 }} />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (!isAdmin) return <NotAuthorized />

  const tabTitle = tab === 'dashboard' ? 'Dashboard'
    : tab === 'users' ? 'Users'
    : tab === 'brokers' ? 'Brokers'
    : tab === 'trades' ? 'Trades'
    : tab === 'positions-book' ? 'Positions & Orders'
    : tab === 'audit' ? 'Audit Log'
    : tab === 'risk' ? 'Risk'
    : tab === 'strategies' ? 'Strategies'
    : tab === 'buyer-strategies' ? 'Buyer Strategies'
    : tab === 'subscriptions' ? 'Subscriptions'
    : tab === 'trading-logs' ? 'Trading Logs'
    : tab === 'activity' ? 'Activity Timeline'
    : tab === 'pnl' ? 'P&L Dashboard'
    : tab === 'strategy-perf' ? 'Strategy Performance'
    : tab === 'user-strategies' ? 'User Algo Builder'
    : tab === 'referrals' ? 'Referral System'
    : tab === 'webhook-tester' ? 'Webhook Tester'
    : tab === 'trade-router' ? 'Multi-Broker Trade Router'
    : tab === 'backups' ? 'Automated Backup'
    : tab === 'ip-whitelist' ? 'IP Whitelist'
    : 'Control Center'

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h1 className="t-page-title" style={{ margin: 0, fontSize: 18 }}>{tabTitle}</h1>
      </div>
      <AdminDashboard />
    </div>
  )
}

export default function DashboardPage() {
  return <DashboardInner />
}
