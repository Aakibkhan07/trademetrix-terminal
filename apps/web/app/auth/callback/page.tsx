'use client'

// Google OAuth callback: Supabase GoTrue redirects here with session tokens in the
// URL fragment (#access_token=...) or error in the query string (?error=...).
// We exchange the GoTrue token for the app's own session via POST /auth/google.

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'

export default function AuthCallbackPage() {
  const router = useRouter()
  const [error, setError] = useState('')
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return
    ran.current = true

    const run = async () => {
      const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''))
      const query = new URLSearchParams(window.location.search)
      const oauthError = query.get('error') || hash.get('error')
      const accessToken = hash.get('access_token')

      if (oauthError) {
        const desc = query.get('error_description') || hash.get('error_description') || 'Google sign-in was cancelled'
        setError(decodeURIComponent(desc).replace(/\+/g, ' '))
        return
      }

      if (!accessToken) {
        setError('No sign-in session found. Please try signing in again.')
        return
      }

      try {
        await api.auth.exchangeOAuth({ access_token: accessToken })
        const me = await api.auth.me().catch(() => null) as { is_admin?: boolean; onboarding_completed?: boolean } | null
        if (me?.is_admin) {
          router.replace('/dashboard')
        } else if (me && me.onboarding_completed === false) {
          router.replace('/onboarding')
        } else {
          router.replace('/live')
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Google sign-in failed')
      }
    }
    run()
  }, [router])

  return (
    <main style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div style={{ textAlign: 'center', maxWidth: 420 }}>
        {error ? (
          <>
            <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 20, marginBottom: 8 }}>Sign-in failed</h1>
            <p style={{ color: 'var(--text-faint)', fontSize: 14, marginBottom: 16 }}>{error}</p>
            <Link href="/auth" className="t-btn t-btn-primary">Back to Sign In</Link>
          </>
        ) : (
          <>
            <span style={{
              width: 28, height: 28, borderRadius: '50%', border: '3px solid rgba(139,92,246,0.25)',
              borderTopColor: '#8b5cf6', display: 'inline-block', animation: 'spin 0.7s linear infinite',
              marginBottom: 16,
            }} />
            <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 18 }}>Completing Google sign-in…</h1>
          </>
        )}
      </div>
    </main>
  )
}
