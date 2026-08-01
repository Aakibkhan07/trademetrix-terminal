'use client'

import { useEffect } from 'react'
import { initAnalytics } from '@/lib/analytics'

export default function AnalyticsTracker() {
  useEffect(() => {
    const cleanup = initAnalytics()
    return cleanup
  }, [])
  return null
}
