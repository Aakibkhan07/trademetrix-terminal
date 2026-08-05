'use client'

import { useEffect } from 'react'
import { initAnalytics, setAnalyticsAuthState } from '@/lib/analytics'
import { useAuth } from '@/lib/auth-context'

export default function AnalyticsTracker() {
  const { user, loading } = useAuth()

  useEffect(() => {
    const cleanup = initAnalytics()
    return cleanup
  }, [])

  useEffect(() => {
    if (user) {
      setAnalyticsAuthState(true)
    } else if (!loading) {
      setAnalyticsAuthState(false)
    }
  }, [user, loading])

  return null
}
