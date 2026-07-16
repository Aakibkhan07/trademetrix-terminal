'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'

export default function AdminSubLayout({ children }: { children: React.ReactNode }) {
  const { isAdmin, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading && !isAdmin) {
      router.replace('/dashboard')
    }
  }, [loading, isAdmin, router])

  if (loading) return null
  if (!isAdmin) return null

  return <>{children}</>
}
