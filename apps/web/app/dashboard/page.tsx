'use client'

import { useState, useEffect, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { SkeletonCard } from '@/components/skeleton'
import { AdminDashboard, NotAuthorized } from './admin-content'

function DashboardInner() {
  const { isAdmin, loading } = useAuth()
  const searchParams = useSearchParams()
  const tab = searchParams.get('tab') || 'dashboard'

  if (loading) {
    return (
      <div>
        <div style={{ marginBottom: 24 }}>
          <h1 className="t-page-title">Control Center</h1>
        </div>
        <SkeletonCard />
      </div>
    )
  }

  if (!isAdmin) return <NotAuthorized />

  const tabTitle = tab === 'dashboard' ? 'Dashboard'
    : tab === 'users' ? 'Users'
    : tab === 'brokers' ? 'Brokers'
    : tab === 'trades' ? 'Trades'
    : tab === 'audit' ? 'Audit Log'
    : tab === 'risk' ? 'Risk'
    : tab === 'buyer-strategies' ? 'Buyer Strategies'
    : 'Control Center'

  return (
    <Suspense fallback={<SkeletonCard />}>
      <div style={{ marginBottom: 16 }}>
        <h1 className="t-page-title" style={{ margin: 0, fontSize: 18 }}>{tabTitle}</h1>
      </div>
      <AdminDashboard />
    </Suspense>
  )
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<SkeletonCard />}>
      <DashboardInner />
    </Suspense>
  )
}
