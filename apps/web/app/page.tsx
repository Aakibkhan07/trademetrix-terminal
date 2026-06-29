'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'

export default function HomePage() {
  const router = useRouter()

  useEffect(() => {
    const token = localStorage.getItem('trademetrix_token')
    if (token) {
      api.setToken(token)
      router.push('/dashboard')
    } else {
      router.push('/auth')
    }
  }, [router])

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '100vh', background: '#000', color: '#8888a0',
    }}>
      <div>
        <h1 style={{ fontFamily: 'Outfit', color: '#8b5cf6', textAlign: 'center' }}>
          Trade Metrix Trading Terminal
        </h1>
        <p style={{ textAlign: 'center' }}>Loading...</p>
      </div>
    </div>
  )
}
