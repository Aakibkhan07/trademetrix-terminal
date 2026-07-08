'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'

export default function AuthPage() {
  const router = useRouter()
  const { signin, signup } = useAuth()
  const [mode, setMode] = useState<'login' | 'signup' | 'forgot'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [validEmail, setValidEmail] = useState(true)
  const [validPassword, setValidPassword] = useState(true)
  const [focusedField, setFocusedField] = useState<string | null>(null)


  const isValidEmail = (v: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)
  const isValidPassword = (v: string) => v.length >= 6

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')

    if (mode === 'forgot') {
      if (!isValidEmail(email)) { setValidEmail(false); return }
      setLoading(true)
      try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/forgot-password`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email }),
        })
        const body = await res.json()
        setSuccess(body.message || 'Password reset link sent to your email')
      } catch {
        setSuccess('If that email is registered, a password reset link has been sent')
      } finally {
        setLoading(false)
      }
      return
    }

    if (!isValidEmail(email)) { setValidEmail(false); return }
    if (!isValidPassword(password)) { setValidPassword(false); return }

    setLoading(true)
    try {
      if (mode === 'signup') {
        if (!fullName.trim()) { setError('Full name is required'); setLoading(false); return }
        await signup(email, password, fullName)
        router.push('/onboarding')
      } else {
        await signin(email, password)
        router.push('/dashboard')
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        setError('Request timed out — server slow or unreachable. Please try again.')
      } else {
        setError(err instanceof Error ? err.message : 'Authentication failed')
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (email && !isValidEmail(email)) setValidEmail(false)
    else setValidEmail(true)
  }, [email])

  useEffect(() => {
    if (password && !isValidPassword(password)) setValidPassword(false)
    else setValidPassword(true)
  }, [password])

  return (
    <div style={{
      display: 'flex', minHeight: '100vh',
      background: 'var(--bg)',
      position: 'relative', overflow: 'hidden',
    }}>
      {/* Animated background */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0,
        background: `
          radial-gradient(900px 900px at -260px -420px, rgba(139,92,246,.13), transparent 62%),
          radial-gradient(800px 800px at calc(100% + 220px) calc(100% + 420px), rgba(34,211,238,.09), transparent 62%)
        `,
      }} />

      {/* Left: Hero */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        justifyContent: 'center', padding: '0 80px',
        position: 'relative', zIndex: 1,
        minWidth: 0,
      }}>
        <div>
          <h1 style={{
            fontWeight: 700,
            fontSize: 42, lineHeight: 1.15, margin: '0 0 16px',
            color: 'var(--text)',
          }}>
            Algorithmic Trading
            <br />
            <span style={{
              background: 'var(--gradient-primary)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}>Made Simple</span>
          </h1>
          <p style={{
            color: 'var(--text-sub)', fontSize: 15, lineHeight: 1.6,
            margin: '0 0 32px', maxWidth: 440,
          }}>
            Build, backtest, and deploy trading strategies across 35+ brokers.
            AI-powered analytics. Real-time execution. No coding required.
          </p>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            {['Visual Strategy Builder', '35+ Brokers', 'AI Assistant', 'Backtesting'].map((feature) => (
              <div key={feature} style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '4px 12px', borderRadius: 999,
                border: '1px solid var(--border)',
                background: 'var(--panel)',
                fontSize: 12, color: 'var(--text-sub)',
              }}>
                <span style={{ color: 'var(--violet)', fontSize: 14 }}>✦</span>
                {feature}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right: Auth Card */}
      <div style={{
        width: 440, display: 'flex', alignItems: 'center',
        padding: '0 40px', position: 'relative', zIndex: 1,
      }}>
        <div style={{
          width: '100%',
          background: 'linear-gradient(165deg, rgba(255,255,255,.06), rgba(255,255,255,.02))',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          border: '1px solid var(--border)',
          borderRadius: 16,
          padding: 40,
        }}>
          {/* Logo + Title */}
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <div style={{
              width: 48, height: 48, borderRadius: 12,
              background: 'var(--gradient-primary)',
              boxShadow: '0 0 24px rgba(139,92,246,.45)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 16px', fontSize: 20, fontWeight: 700, color: '#fff',
            }}>TM</div>
            <h2 style={{
              fontWeight: 700,
              fontSize: 20, margin: '0 0 4px', color: 'var(--text)',
            }}>
              {mode === 'login' ? 'Welcome back' : mode === 'signup' ? 'Create account' : 'Reset password'}
            </h2>
            <p style={{ color: 'var(--text-sub)', fontSize: 13, margin: 0 }}>
              {mode === 'login' ? 'Sign in to your trading terminal' :
               mode === 'signup' ? 'Start your algorithmic trading journey' :
               'Enter your email to receive a reset link'}
            </p>
          </div>


          <form onSubmit={handleSubmit}>
            {mode === 'signup' && (
              <div style={{ marginBottom: 16 }}>
                <label style={{
                  fontSize: 11, fontWeight: 600, color: focusedField === 'name' ? 'var(--violet)' : 'var(--text-sub)',
                  marginBottom: 6, display: 'block',
                  transition: 'color 150ms ease',
                }}>Full Name</label>
                <input
                  type="text"
                  placeholder="Your full name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  onFocus={() => setFocusedField('name')}
                  onBlur={() => setFocusedField(null)}
                  style={{
                    width: '100%', height: 44, padding: '0 14px',
                    background: 'var(--bg-tertiary)',
                    border: `1px solid ${error && !fullName.trim() ? 'rgba(248,113,113,0.3)' : focusedField === 'name' ? 'rgba(139,92,246,0.3)' : 'var(--border)'}`,
                    borderRadius: 8, color: 'var(--text)', fontSize: 13,
                    outline: 'none',
                    transition: 'border-color 150ms ease, box-shadow 150ms ease',
                    boxShadow: focusedField === 'name' ? '0 0 0 3px rgba(139,92,246,0.15)' : 'none',
                  }}
                />
              </div>
            )}

            <div style={{ marginBottom: mode === 'login' ? 12 : 16 }}>
              <label style={{
                fontSize: 11, fontWeight: 600, color: focusedField === 'email' ? 'var(--violet)' : 'var(--text-sub)',
                marginBottom: 6, display: 'block',
                transition: 'color 150ms ease',
              }}>Email Address</label>
              <input
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onFocus={() => setFocusedField('email')}
                onBlur={() => setFocusedField(null)}
                style={{
                  width: '100%', height: 44, padding: '0 14px',
                  background: 'var(--bg-tertiary)',
                  border: `1px solid ${
                    !validEmail && email ? 'rgba(248,113,113,0.3)' :
                    focusedField === 'email' ? 'rgba(139,92,246,0.3)' : 'var(--border)'
                  }`,
                  borderRadius: 8, color: 'var(--text)', fontSize: 13,
                  outline: 'none',
                  transition: 'border-color 150ms ease, box-shadow 150ms ease',
                  boxShadow: focusedField === 'email' ? '0 0 0 3px rgba(139,92,246,0.15)' : 'none',
                }}
              />
              {!validEmail && email && (
                <p style={{ color: 'var(--text-red)', fontSize: 11, margin: '4px 0 0' }}>Invalid email format</p>
              )}
            </div>

            {mode !== 'forgot' && (
              <div style={{ marginBottom: mode === 'login' ? 4 : 16 }}>
                <label style={{
                  fontSize: 11, fontWeight: 600, color: focusedField === 'password' ? 'var(--violet)' : 'var(--text-sub)',
                  marginBottom: 6, display: 'block',
                  transition: 'color 150ms ease',
                }}>Password</label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    placeholder="Min. 6 characters"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onFocus={() => setFocusedField('password')}
                    onBlur={() => setFocusedField(null)}
                    style={{
                      width: '100%', height: 44, padding: '0 40px 0 14px',
                      background: 'var(--bg-tertiary)',
                      border: `1px solid ${
                        !validPassword && password ? 'rgba(248,113,113,0.3)' :
                        focusedField === 'password' ? 'rgba(139,92,246,0.3)' : 'var(--border)'
                      }`,
                      borderRadius: 8, color: 'var(--text)', fontSize: 13,
                      outline: 'none',
                      transition: 'border-color 150ms ease, box-shadow 150ms ease',
                      boxShadow: focusedField === 'password' ? '0 0 0 3px rgba(139,92,246,0.15)' : 'none',
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    style={{
                      position: 'absolute', right: 10, top: '50%',
                      transform: 'translateY(-50%)',
                      background: 'none', border: 'none',
                      color: 'var(--text-faint)', cursor: 'pointer',
                      fontSize: 13, padding: 4,
                    }}
                  >
                    {showPassword ? 'Hide' : 'Show'}
                  </button>
                </div>
                {!validPassword && password && (
                  <p style={{ color: 'var(--text-red)', fontSize: 11, margin: '4px 0 0' }}>Minimum 6 characters</p>
                )}
              </div>
            )}

            {mode === 'login' && (
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 20 }}>
                <button
                  type="button"
                  onClick={() => { setMode('forgot'); setError(''); setSuccess('') }}
                  style={{
                    background: 'none', border: 'none',
                    color: 'var(--text-sub)', fontSize: 12, cursor: 'pointer',
                    padding: 0,
                    transition: 'color 150ms ease',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.color = 'var(--violet)' }}
                  onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-sub)' }}
                >
                  Forgot password?
                </button>
              </div>
            )}

            {/* Error / Success */}
            {error && (
              <div style={{
                background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.15)',
                borderRadius: 8, padding: '10px 14px', marginBottom: 16,
              }}>
                <p style={{ color: 'var(--text-red)', fontSize: 12, margin: 0 }}>{error}</p>
              </div>
            )}
            {success && (
              <div style={{
                background: 'rgba(52,211,153,0.08)', border: '1px solid rgba(52,211,153,0.15)',
                borderRadius: 8, padding: '10px 14px', marginBottom: 16,
              }}>
                <p style={{ color: 'var(--text-green)', fontSize: 12, margin: 0 }}>{success}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                width: '100%', height: 44,
                background: loading ? 'rgba(139,92,246,0.5)' : 'var(--gradient-primary)',
                border: 'none', borderRadius: 8,
                color: '#fff', fontSize: 13, fontWeight: 600,
                cursor: loading ? 'default' : 'pointer',
                transition: 'all 150ms ease', position: 'relative',
                overflow: 'hidden',
              }}
              onMouseEnter={e => {
                if (!loading) e.currentTarget.style.boxShadow = '0 0 24px rgba(139,92,246,0.35)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.boxShadow = 'none'
              }}
            >
              {loading ? (
                <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  <span style={{
                    width: 14, height: 14, borderRadius: '50%',
                    border: '2px solid rgba(255,255,255,0.3)',
                    borderTopColor: '#fff',
                    display: 'inline-block',
                    animation: 'spin 0.6s linear infinite',
                  }} />
                  Processing...
                </span>
              ) : (
                mode === 'login' ? 'Sign In' : mode === 'signup' ? 'Create Account' : 'Send Reset Link'
              )}
            </button>
          </form>

          {/* Switch mode */}
          <div style={{
            textAlign: 'center', marginTop: 24, paddingTop: 20,
            borderTop: '1px solid var(--border)',
          }}>
            <p style={{ color: 'var(--text-sub)', margin: 0, fontSize: 12 }}>
              {mode === 'login' ? "Don't have an account?" :
               mode === 'signup' ? 'Already have an account?' :
               'Remember your password?'}{' '}
              <button
                onClick={() => {
                  setMode(mode === 'login' ? 'signup' : mode === 'signup' ? 'login' : 'login')
                  setError(''); setSuccess('')
                }}
                style={{
                  background: 'none', border: 'none',
                  color: 'var(--violet)', cursor: 'pointer', fontSize: 12,
                  fontWeight: 600,
                  padding: 0, transition: 'color 150ms ease',
                }}
                onMouseEnter={e => { e.currentTarget.style.color = 'var(--cyan)' }}
                onMouseLeave={e => { e.currentTarget.style.color = 'var(--violet)' }}
              >
                {mode === 'login' ? 'Sign up' : mode === 'signup' ? 'Sign in' : 'Sign in'}
              </button>
            </p>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          25% { transform: translateX(-4px); }
          75% { transform: translateX(4px); }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
