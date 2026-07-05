'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase'

export default function AuthCallbackPage() {
  const router = useRouter()
  const [error, setError] = useState('')

  useEffect(() => {
    const handleCallback = async () => {
      const supabase = createClient()
      const { data, error: sessionError } = await supabase.auth.getSession()
      if (sessionError) {
        setError(sessionError.message)
        return
      }
      if (!data?.session) {
        router.push('/auth')
        return
      }

      const provider = data.session.user.app_metadata?.provider || 'oauth'
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || ''}/auth/supabase-oauth`,
        {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': document.cookie.replace(/(?:^|;\s*)csrf_token=([^;]*)/, '$1') || '',
          },
          body: JSON.stringify({
            provider,
            access_token: data.session.access_token,
          }),
        },
      )
      if (res.ok) {
        await supabase.auth.signOut()
        router.push('/dashboard')
      } else {
        const body = await res.json().catch(() => ({ detail: 'OAuth failed' }))
        setError(body.detail || 'Authentication failed')
      }
    }
    handleCallback()
  }, [router])

  if (error) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100vh', background: 'var(--bg)', flexDirection: 'column', gap: 12,
      }}>
        <p style={{ color: 'var(--text-red)', fontSize: 14 }}>Authentication failed</p>
        <p style={{ color: 'var(--text-faint)', fontSize: 12 }}>{error}</p>
        <a href="/auth" style={{ color: 'var(--cyan)', fontSize: 12 }}>Back to login</a>
      </div>
    )
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '100vh', background: 'var(--bg)', flexDirection: 'column', gap: 8,
    }}>
      <div style={{ color: 'var(--cyan)', fontSize: 14 }}>Completing sign in...</div>
      <div style={{ color: 'var(--text-faint)', fontSize: 12 }}>Redirecting to dashboard</div>
    </div>
  )
}
