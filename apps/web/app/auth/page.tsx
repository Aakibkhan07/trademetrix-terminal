'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { createClient } from '@/lib/supabase'

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
  const [oauthLoading, setOauthLoading] = useState<string | null>(null)

  const handleOAuth = async (provider: 'google' | 'github') => {
    setOauthLoading(provider)
    const supabase = createClient()
    const { error } = await supabase.auth.signInWithOAuth({
      provider,
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    })
    if (error) setError(error.message)
    setOauthLoading(null)
  }

  const isValidEmail = (v: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)
  const isValidPassword = (v: string) => v.length >= 6

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')

    if (mode === 'forgot') {
      setSuccess('Password reset link sent to your email')
      return
    }

    if (!isValidEmail(email)) { setValidEmail(false); return }
    if (!isValidPassword(password)) { setValidPassword(false); return }

    setLoading(true)
    try {
      if (mode === 'signup') {
        if (!fullName.trim()) { setError('Full name is required'); setLoading(false); return }
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
      background: '#0f1419',
      position: 'relative', overflow: 'hidden',
    }}>
      {/* Animated background */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0,
        background: `
          radial-gradient(800px 500px at 0% 0%, rgba(0,212,255,0.05), transparent),
          radial-gradient(600px 400px at 100% 100%, rgba(0,150,255,0.04), transparent),
          radial-gradient(400px 300px at 50% 50%, rgba(124,92,252,0.03), transparent)
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
            fontFamily: "'Inter', sans-serif", fontWeight: 700,
            fontSize: 42, lineHeight: 1.15, margin: '0 0 16px',
            color: '#fff',
          }}>
            Algorithmic Trading
            <br />
            <span style={{
              background: 'linear-gradient(135deg, #00d4ff, #0096ff)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}>Made Simple</span>
          </h1>
          <p style={{
            color: '#a1a5b3', fontSize: 15, lineHeight: 1.6,
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
                border: '1px solid rgba(0,212,255,0.15)',
                background: 'rgba(0,212,255,0.04)',
                fontSize: 12, color: '#a1a5b3',
              }}>
                <span style={{ color: '#00d4ff', fontSize: 14 }}>✦</span>
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
          background: 'rgba(26, 31, 46, 0.7)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 16,
          padding: 40,
        }}>
          {/* Logo + Title */}
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <div style={{
              width: 48, height: 48, borderRadius: 12,
              background: 'linear-gradient(135deg, #00d4ff, #0096ff)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 16px', fontSize: 20, fontWeight: 700, color: '#fff',
            }}>TM</div>
            <h2 style={{
              fontFamily: "'Inter', sans-serif", fontWeight: 700,
              fontSize: 20, margin: '0 0 4px', color: '#fff',
            }}>
              {mode === 'login' ? 'Welcome back' : mode === 'signup' ? 'Create account' : 'Reset password'}
            </h2>
            <p style={{ color: '#a1a5b3', fontSize: 13, margin: 0 }}>
              {mode === 'login' ? 'Sign in to your trading terminal' :
               mode === 'signup' ? 'Start your algorithmic trading journey' :
               'Enter your email to receive a reset link'}
            </p>
          </div>

          {/* OAuth Buttons (login/signup only) */}
          {mode !== 'forgot' && (
            <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
              <button onClick={() => handleOAuth('google')} disabled={oauthLoading !== null} style={{
                flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
                gap: 8, height: 40, borderRadius: 8,
                border: '1px solid rgba(255,255,255,0.08)',
                background: oauthLoading === 'google' ? 'rgba(0,212,255,0.08)' : 'rgba(255,255,255,0.03)',
                color: oauthLoading === 'google' ? 'var(--cyan)' : '#a1a5b3',
                fontSize: 12, fontWeight: 600,
                cursor: 'pointer', fontFamily: "'Inter', sans-serif",
                transition: 'all 150ms ease', opacity: oauthLoading !== null && oauthLoading !== 'google' ? 0.5 : 1,
              }}
                onMouseEnter={e => { if (oauthLoading !== 'google') { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.15)'; e.currentTarget.style.color = '#fff' } }}
                onMouseLeave={e => { if (oauthLoading !== 'google') { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)'; e.currentTarget.style.color = '#a1a5b3' } }}
              >
                <span style={{ fontSize: 16 }}>G</span> {oauthLoading === 'google' ? 'Connecting...' : 'Google'}
              </button>
              <button onClick={() => handleOAuth('github')} disabled={oauthLoading !== null} style={{
                flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
                gap: 8, height: 40, borderRadius: 8,
                border: '1px solid rgba(255,255,255,0.08)',
                background: oauthLoading === 'github' ? 'rgba(0,212,255,0.08)' : 'rgba(255,255,255,0.03)',
                color: oauthLoading === 'github' ? 'var(--cyan)' : '#a1a5b3',
                fontSize: 12, fontWeight: 600,
                cursor: 'pointer', fontFamily: "'Inter', sans-serif",
                transition: 'all 150ms ease', opacity: oauthLoading !== null && oauthLoading !== 'github' ? 0.5 : 1,
              }}
                onMouseEnter={e => { if (oauthLoading !== 'github') { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.15)'; e.currentTarget.style.color = '#fff' } }}
                onMouseLeave={e => { if (oauthLoading !== 'github') { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)'; e.currentTarget.style.color = '#a1a5b3' } }}
              >
                <span style={{ fontSize: 16 }}>⌂</span> {oauthLoading === 'github' ? 'Connecting...' : 'GitHub'}
              </button>
            </div>
          )}

          {/* Divider */}
          {mode !== 'forgot' && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20,
            }}>
              <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.06)' }} />
              <span style={{ color: '#5f6368', fontSize: 11 }}>OR</span>
              <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.06)' }} />
            </div>
          )}

          <form onSubmit={handleSubmit}>
            {mode === 'signup' && (
              <div style={{ marginBottom: 16 }}>
                <label style={{
                  fontSize: 11, fontWeight: 600, color: focusedField === 'name' ? '#00d4ff' : '#a1a5b3',
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
                    background: 'rgba(255,255,255,0.04)',
                    border: `1px solid ${error && !fullName.trim() ? 'rgba(239,68,68,0.3)' : focusedField === 'name' ? 'rgba(0,212,255,0.3)' : 'rgba(255,255,255,0.08)'}`,
                    borderRadius: 8, color: '#fff', fontSize: 13,
                    fontFamily: "'Inter', sans-serif", outline: 'none',
                    transition: 'border-color 150ms ease, box-shadow 150ms ease',
                    boxShadow: focusedField === 'name' ? '0 0 0 3px rgba(0,212,255,0.06)' : 'none',
                  }}
                />
              </div>
            )}

            <div style={{ marginBottom: mode === 'login' ? 12 : 16 }}>
              <label style={{
                fontSize: 11, fontWeight: 600, color: focusedField === 'email' ? '#00d4ff' : '#a1a5b3',
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
                  background: 'rgba(255,255,255,0.04)',
                  border: `1px solid ${
                    !validEmail && email ? 'rgba(239,68,68,0.3)' :
                    focusedField === 'email' ? 'rgba(0,212,255,0.3)' : 'rgba(255,255,255,0.08)'
                  }`,
                  borderRadius: 8, color: '#fff', fontSize: 13,
                  fontFamily: "'Inter', sans-serif", outline: 'none',
                  transition: 'border-color 150ms ease, box-shadow 150ms ease',
                  boxShadow: focusedField === 'email' ? '0 0 0 3px rgba(0,212,255,0.06)' : 'none',
                }}
              />
              {!validEmail && email && (
                <p style={{ color: '#ef4444', fontSize: 11, margin: '4px 0 0' }}>Invalid email format</p>
              )}
            </div>

            {mode !== 'forgot' && (
              <div style={{ marginBottom: mode === 'login' ? 4 : 16 }}>
                <label style={{
                  fontSize: 11, fontWeight: 600, color: focusedField === 'password' ? '#00d4ff' : '#a1a5b3',
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
                      background: 'rgba(255,255,255,0.04)',
                      border: `1px solid ${
                        !validPassword && password ? 'rgba(239,68,68,0.3)' :
                        focusedField === 'password' ? 'rgba(0,212,255,0.3)' : 'rgba(255,255,255,0.08)'
                      }`,
                      borderRadius: 8, color: '#fff', fontSize: 13,
                      fontFamily: "'Inter', sans-serif", outline: 'none',
                      transition: 'border-color 150ms ease, box-shadow 150ms ease',
                      boxShadow: focusedField === 'password' ? '0 0 0 3px rgba(0,212,255,0.06)' : 'none',
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    style={{
                      position: 'absolute', right: 10, top: '50%',
                      transform: 'translateY(-50%)',
                      background: 'none', border: 'none',
                      color: '#5f6368', cursor: 'pointer',
                      fontSize: 13, fontFamily: "'Inter', sans-serif",
                      padding: 4,
                    }}
                  >
                    {showPassword ? 'Hide' : 'Show'}
                  </button>
                </div>
                {!validPassword && password && (
                  <p style={{ color: '#ef4444', fontSize: 11, margin: '4px 0 0' }}>Minimum 6 characters</p>
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
                    color: '#a1a5b3', fontSize: 12, cursor: 'pointer',
                    fontFamily: "'Inter', sans-serif", padding: 0,
                    transition: 'color 150ms ease',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.color = '#00d4ff' }}
                  onMouseLeave={e => { e.currentTarget.style.color = '#a1a5b3' }}
                >
                  Forgot password?
                </button>
              </div>
            )}

            {/* Error / Success */}
            {error && (
              <div style={{
                background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.15)',
                borderRadius: 8, padding: '10px 14px', marginBottom: 16,
                animation: 'shake 300ms ease',
              }}>
                <p style={{ color: '#ef4444', fontSize: 12, margin: 0 }}>{error}</p>
              </div>
            )}
            {success && (
              <div style={{
                background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.15)',
                borderRadius: 8, padding: '10px 14px', marginBottom: 16,
              }}>
                <p style={{ color: '#22c55e', fontSize: 12, margin: 0 }}>{success}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                width: '100%', height: 44,
                background: loading ? 'rgba(0,212,255,0.5)' : 'linear-gradient(135deg, #00d4ff, #0096ff)',
                border: 'none', borderRadius: 8,
                color: '#fff', fontSize: 13, fontWeight: 600,
                fontFamily: "'Inter', sans-serif", cursor: loading ? 'default' : 'pointer',
                transition: 'all 150ms ease', position: 'relative',
                overflow: 'hidden',
              }}
              onMouseEnter={e => {
                if (!loading) e.currentTarget.style.boxShadow = '0 0 20px rgba(0,212,255,0.3)'
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
            borderTop: '1px solid rgba(255,255,255,0.06)',
          }}>
            <p style={{ color: '#a1a5b3', margin: 0, fontSize: 12 }}>
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
                  color: '#00d4ff', cursor: 'pointer', fontSize: 12,
                  fontFamily: "'Inter', sans-serif", fontWeight: 600,
                  padding: 0, transition: 'color 150ms ease',
                }}
                onMouseEnter={e => { e.currentTarget.style.color = '#0096ff' }}
                onMouseLeave={e => { e.currentTarget.style.color = '#00d4ff' }}
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
