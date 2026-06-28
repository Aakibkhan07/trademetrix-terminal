'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

export default function HomePage() {
  const router = useRouter()
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch('/api/v1/auth/me', { credentials: 'include' })
        if (res.ok) {
          router.push('/dashboard')
        } else {
          router.push('/auth')
        }
      } catch {
        router.push('/auth')
      } finally {
        setLoading(false)
      }
    }
    check()
  }, [router])

  if (loading) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100vh', background: '#000', color: '#8888a0',
      }}>
        <div>
          <h1 style={{ fontFamily: 'Outfit', color: '#8b5cf6', textAlign: 'center' }}>
            Trade Metrix
          </h1>
          <p style={{ textAlign: 'center' }}>Loading...</p>
        </div>
      </div>
    )
  }

  return null
}
