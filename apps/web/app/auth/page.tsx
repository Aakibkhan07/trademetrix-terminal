'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'

export default function AuthPage() {
  const router = useRouter()
  const { signin, signup } = useAuth()
  const [isSignUp, setIsSignUp] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (isSignUp) {
        await signup(email, password, fullName)
      } else {
        await signin(email, password)
      }
      router.push('/dashboard')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: '100vh',
      background: 'radial-gradient(ellipse at 50% 0%, rgba(139,92,246,0.08) 0%, transparent 60%), #000',
      padding: 16,
    }}>
      <div style={{ width: 400 }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <h1 style={{
            fontFamily: 'Outfit', fontSize: 28, margin: '0 0 8px',
            background: 'linear-gradient(135deg, #8b5cf6, #22d3ee)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}>
            Trade Metrix Trading Terminal
          </h1>
          <p style={{ color: '#8888a0', margin: 0, fontSize: 14 }}>
            {isSignUp ? 'Create your algorithmic trading account' : 'Sign in to your terminal'}
          </p>
        </div>

        <div className="panel" style={{ padding: '32px', border: '1px solid rgba(139,92,246,0.15)' }}>
          <form onSubmit={handleSubmit}>
            {isSignUp && (
              <div style={{ marginBottom: 16 }}>
                <input
                  className="input"
                  type="text"
                  placeholder="Full name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </div>
            )}
            <div style={{ marginBottom: 16 }}>
              <input
                className="input"
                type="email"
                placeholder="Email address"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div style={{ marginBottom: 24 }}>
              <input
                className="input"
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
              />
            </div>

            {error && (
              <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, padding: '8px 12px', marginBottom: 16 }}>
                <p style={{ color: '#ef4444', fontSize: 13, margin: 0 }}>{error}</p>
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary btn-lg"
              style={{ width: '100%', padding: '12px 24px' }}
              disabled={loading}
            >
              {loading ? 'Processing...' : isSignUp ? 'Create Account' : 'Sign In'}
            </button>
          </form>

          <div style={{
            textAlign: 'center', marginTop: 24, paddingTop: 24,
            borderTop: '1px solid rgba(139,92,246,0.1)',
          }}>
            <p style={{ color: '#8888a0', margin: 0, fontSize: 13 }}>
              {isSignUp ? 'Already have an account?' : "Don't have an account?"}{' '}
              <button
                onClick={() => { setIsSignUp(!isSignUp); setError('') }}
                style={{
                  background: 'none', border: 'none',
                  backgroundImage: 'linear-gradient(135deg, #8b5cf6, #22d3ee)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  cursor: 'pointer', fontSize: 13, fontFamily: 'inherit',
                  fontWeight: 600,
                }}
              >
                {isSignUp ? 'Sign in' : 'Sign up'}
              </button>
            </p>
          </div>
        </div>

        <p style={{ textAlign: 'center', marginTop: 24, color: '#555570', fontSize: 12 }}>
          Multi-broker algorithmic trading platform
        </p>
      </div>
    </div>
  )
}
