'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { useApi } from '@/lib/use-api'
import { api } from '@/lib/api'
import { BrokerLogo } from '@/components/broker-logos'

/* -------- types -------- */

interface BrokerCred {
  id: string
  broker: string
  is_active: boolean
  created_at: string
}

interface AssignedStrategy {
  id: string
  strategy_key: string
  name: string
  required_tier: string
  mirror_enabled: boolean
  active: boolean
}

const STEPS = ['Account', 'Connect Broker', 'Done']

/* ========== Step 1: Account ========== */

function StepAccount({ onDone }: { onDone: () => void }) {
  const { token, loading: authLoading, signin, signup } = useAuth()
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const passwordHint = mode === 'signup' ? 'Min 8 chars, with uppercase, lowercase, number + symbol' : ''

  useEffect(() => {
    if (!authLoading && token) onDone()
  }, [authLoading, token, onDone])

  if (authLoading) {
    return (
      <div className="t-panel" style={{ padding: 32, textAlign: 'center' }}>
        <p className="t-sub" style={{ fontSize: 13 }}>Loading...</p>
      </div>
    )
  }

  const handle = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (mode === 'signup') {
        await signup(email, password, fullName)
      } else {
        await signin(email, password)
      }
      onDone()
    } catch (err: unknown) {
      const { friendlyApiError } = await import('@/lib/api')
      setError(friendlyApiError(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <form onSubmit={handle}>
        {mode === 'signup' && (
          <div style={{ marginBottom: 16 }}>
            <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>Full name</label>
            <input className="t-input" type="text" value={fullName} onChange={e => setFullName(e.target.value)} />
          </div>
        )}
        <div style={{ marginBottom: 16 }}>
          <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>Email address</label>
          <input className="t-input" type="email" value={email} onChange={e => setEmail(e.target.value)} required />
        </div>
        <div style={{ marginBottom: 20 }}>
          <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>Password</label>
          <input className="t-input" type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} />
          {passwordHint && <p className="t-faint" style={{ fontSize: 11, margin: '4px 0 0' }}>{passwordHint}</p>}
        </div>

        {error && (
          <div style={{ padding: '12px 16px', background: 'color-mix(in srgb, var(--red) 10%, transparent)', border: '1px solid rgba(248,113,113,0.2)', borderRadius: 8, color: 'var(--red)', fontSize: 13, marginBottom: 16 }}>{error}</div>
        )}

        <button type="submit" className="t-btn-primary" style={{ width: '100%', padding: '10px 20px' }} disabled={loading}>
          {loading ? 'Processing...' : mode === 'signup' ? 'Create Account' : 'Sign In'}
        </button>
      </form>

      <div style={{ textAlign: 'center', marginTop: 20, paddingTop: 20, borderTop: '1px solid color-mix(in srgb, var(--violet) 10%, transparent)' }}>
        <p style={{ color: 'var(--text-sub)', margin: 0, fontSize: 13 }}>
          {mode === 'signup' ? 'Already have an account?' : "Don't have an account?"}{' '}
          <button
            onClick={() => { setMode(mode === 'signup' ? 'signin' : 'signup'); setError('') }}
            style={{
              background: 'none', border: 'none',
              backgroundImage: 'linear-gradient(135deg, var(--violet), var(--cyan))',
              WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
              cursor: 'pointer', fontSize: 13, fontFamily: 'inherit', fontWeight: 600,
            }}
          >
            {mode === 'signup' ? 'Sign in' : 'Sign up'}
          </button>
        </p>
      </div>
    </div>
  )
}

/* ========== Step 2: Connect Broker ========== */

function StepConnectBroker({ onDone }: { onDone: () => void }) {
  const [credentials, setCredentials] = useState<BrokerCred[]>([])
  const [available, setAvailable] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedBroker, setSelectedBroker] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [secretKey, setSecretKey] = useState('')
  const [clientCode, setClientCode] = useState('')
  const [totpSecret, setTotpSecret] = useState('')
  const [saving, setSaving] = useState(false)
  const [fyersPopup, setFyersPopup] = useState(false)
  const fyersCodeHandled = useRef(false)

  const load = useCallback(async () => {
    if (!credentials.length) setLoading(true)
    try {
      const [credData, brokerData] = await Promise.all([
        api.brokers.credentials(),
        api.brokers.list(),
      ])
      const creds = (credData as { credentials: BrokerCred[] }).credentials || []
      setCredentials(creds)
      setAvailable((brokerData as { brokers: string[] }).brokers || [])
      setError('')
      if (creds.some(c => c.is_active)) {
        onDone()
      }
    } catch (e) {
      const { friendlyApiError } = await import('@/lib/api')
      setError(friendlyApiError(e))
    } finally {
      setLoading(false)
    }
  }, [onDone])

  useEffect(() => { load() }, [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const authCode = params.get('auth_code')
    if (authCode && !fyersCodeHandled.current) {
      fyersCodeHandled.current = true
      setFyersPopup(false)
      api.brokers.fyersExchangeCode(authCode)
        .then(() => load())
        .catch((e) => setError(e instanceof Error ? e.message : 'Fyers auth failed'))
      const url = new URL(window.location.href)
      url.searchParams.delete('auth_code')
      url.searchParams.delete('state')
      url.searchParams.delete('auth_success')
      url.searchParams.delete('auth_error')
      window.history.replaceState({}, '', url.toString())
    }
  }, [load])

  const unconnected = available.filter(b => !credentials.some(c => c.broker === b))

  const handleSave = async () => {
    if (!selectedBroker || saving) return
    if (!apiKey.trim() || !secretKey.trim()) { setError('API key + secret are required'); return }
    setSaving(true)
    setError('')
    try {
      const additional: Record<string, string> = {}
      if (totpSecret) additional.totp_secret = totpSecret
      if (clientCode) additional.client_code = clientCode
      await api.brokers.saveCredentials({
        broker: selectedBroker,
        api_key: apiKey.trim(),
        secret_key: secretKey.trim(),
        additional_params: Object.keys(additional).length ? additional : undefined,
      })
      try {
        const data = await api.brokers.authUrl(selectedBroker) as { auth_url: string }
        if (data.auth_url) {
          window.open(data.auth_url, '_blank')
          setFyersPopup(true)
        }
      } catch {
        // Non-OAuth broker or auth URL unavailable — skip
      }
      await api.brokers.activate(selectedBroker)
      setSelectedBroker('')
      setApiKey('')
      setSecretKey('')
      setClientCode('')
      setTotpSecret('')
      await load()
    } catch (e) {
      const { friendlyApiError } = await import('@/lib/api')
      setError(friendlyApiError(e))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="t-panel" style={{ padding: 32, textAlign: 'center' }}>
        <p className="t-sub" style={{ fontSize: 13 }}>Loading...</p>
      </div>
    )
  }

  const displayName = (broker: string) => {
    const nm = broker.charAt(0).toUpperCase() + broker.slice(1)
    // Special cases for known display names
    const special: Record<string, string> = {
      zerodha: 'Zerodha (Kite)',
      fyers: 'Fyers',
      angelone: 'Angel One',
      dhan: 'Dhan',
      upstox: 'Upstox',
      fivepaisa: '5Paisa',
      kotakneo: 'Kotak Neo',
      finvasia: 'Finvasia',
      flattrade: 'Flattrade',
      aliceblue: 'Alice Blue',
      groww: 'Groww',
      icici: 'ICICI Direct',
      hdfc: 'HDFC Securities',
      iifl: 'IIFL Securities',
      motilal: 'Motilal Oswal',
      geojit: 'Geojit',
      reliance: 'Reliance Securities',
      axis: 'Axis Securities',
      binance: 'Binance',
      bybit: 'Bybit',
      okx: 'OKX',
      oanda: 'OANDA',
      interactive_brokers: 'Interactive Brokers',
      alpaca: 'Alpaca',
      lemonn: 'Lemonn',
    }
    return special[broker] || nm
  }

  return (
    <div>
      {error && <div style={{ padding: '12px 16px', background: 'color-mix(in srgb, var(--red) 10%, transparent)', border: '1px solid rgba(248,113,113,0.2)', borderRadius: 8, color: 'var(--red)', fontSize: 13, marginBottom: 16 }}>{error}</div>}

      {credentials.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 14, margin: '0 0 10px', color: 'var(--text)' }}>Connected Brokers</h3>
          {credentials.map(c => (
            <div key={c.id} className="t-panel" style={{ padding: '10px 14px', marginBottom: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <BrokerLogo broker={c.broker} size={32} />
                <div style={{ flex: 1 }}>
                  <p style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>{displayName(c.broker)}</p>
                  <p style={{ margin: '2px 0 0', fontSize: 11, color: 'var(--text-faint)' }}>
                    Connected {new Date(c.created_at).toLocaleDateString()}
                  </p>
                </div>
                <span className={`t-badge ${c.is_active ? 't-badge-green' : 't-badge-violet'}`} style={{ fontSize: 9, padding: '2px 8px' }}>
                  {c.is_active ? 'Active' : 'Inactive'}
                </span>
                {c.broker === 'fyers' && !c.is_active && (
                  <button className="t-btn t-btn-sm" style={{ fontSize: 10 }} onClick={async () => {
                    try {
                      const data = await api.brokers.authUrl('fyers') as { auth_url: string }
                      if (data.auth_url) { window.open(data.auth_url, '_blank'); setFyersPopup(true) }
                    } catch (e) { setError(e instanceof Error ? e.message : 'Fyers re-auth failed') }
                  }}>
                    Auth
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {selectedBroker === 'fyers' && credentials.some(c => c.broker === 'fyers' && !c.is_active) && (
        <div className="t-panel" style={{ padding: 8, marginBottom: 16, background: 'var(--violet-dim)', border: '1px solid rgba(139,92,246,0.2)', fontSize: 11 }}>
          <p style={{ margin: 0, color: 'var(--text-sub)' }}>
            Complete Fyers authorization in the new tab, then the broker will connect automatically.
          </p>
        </div>
      )}

      {unconnected.length > 0 && (
        <div>
          <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 14, margin: '0 0 10px', color: 'var(--text)' }}>Connect a Broker</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))', gap: 8, marginBottom: 16 }}>
            {unconnected.map(b => (
              <div
                key={b}
                onClick={() => setSelectedBroker(b)}
                style={{
                  padding: '10px', borderRadius: 8, cursor: 'pointer',
                  border: selectedBroker === b ? '1px solid #8b5cf6' : '1px solid color-mix(in srgb, var(--violet) 12%, transparent)',
                  background: selectedBroker === b ? 'color-mix(in srgb, var(--violet) 8%, transparent)' : 'transparent',
                  textAlign: 'center', transition: 'all var(--transition-fast)',
                }}
              >
                <BrokerLogo broker={b} size={28} />
                <p style={{ margin: 0, fontSize: 10, fontWeight: 600 }}>{b.charAt(0).toUpperCase() + b.slice(1)}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {selectedBroker && (
        <div className="t-panel" style={{ padding: 16, marginBottom: 16 }}>
          <h4 style={{ fontFamily: 'var(--font-display)', fontSize: 13, margin: '0 0 12px', color: 'var(--text)' }}>
            {displayName(selectedBroker)} Credentials
          </h4>
          <div style={{ marginBottom: 12 }}>
            <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>
              {selectedBroker === 'dhan' ? 'Client ID' : 'API Key'}
            </label>
            <input className="t-input" value={apiKey} onChange={e => setApiKey(e.target.value)} />
          </div>
          {selectedBroker === 'angelone' && (
            <div style={{ marginBottom: 12 }}>
              <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>Client ID (Angel One Login ID)</label>
              <input className="t-input" value={clientCode} onChange={e => setClientCode(e.target.value)} />
            </div>
          )}
          <div style={{ marginBottom: selectedBroker === 'angelone' ? 12 : 16 }}>
            <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>
              {selectedBroker === 'angelone' ? 'Password/PIN' : selectedBroker === 'dhan' ? 'Access Token' : 'Secret Key'}
            </label>
            <input className="t-input" type="password" value={secretKey} onChange={e => setSecretKey(e.target.value)} />
          </div>
          {selectedBroker === 'angelone' && (
            <div style={{ marginBottom: 16 }}>
              <label className="t-stat-label" style={{ display: 'block', marginBottom: 4 }}>TOTP Secret (Base32)</label>
              <input className="t-input" type="password" value={totpSecret} onChange={e => setTotpSecret(e.target.value)} />
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="t-btn t-btn-sm" onClick={() => { setSelectedBroker(''); setApiKey(''); setSecretKey(''); setClientCode(''); setTotpSecret('') }}>
              Cancel
            </button>
            <button className="t-btn t-btn-sm t-btn-primary" onClick={handleSave} disabled={!apiKey || saving}>
              {saving ? 'Connecting...' : 'Connect'}
            </button>
          </div>
        </div>
      )}

      {credentials.some(c => c.is_active) && (
        <button className="t-btn-primary" style={{ width: '100%', padding: '10px 20px' }} onClick={onDone}>
          Continue to Terminal
        </button>
      )}
    </div>
  )
}

/* ========== Step 3: Done ========== */

function StepDone() {
  const router = useRouter()
  const { isAdmin } = useAuth()
  const { data: assignedData, loading, error } = useApi<{ strategies: AssignedStrategy[] }>('/strategies/assigned')
  const assigned = assignedData?.strategies || []
  const profileUpdated = useRef(false)
  const [checks, setChecks] = useState({ broker: false, funds: false, paperTrade: false, alerts: false })

  useEffect(() => {
    if (!profileUpdated.current) {
      profileUpdated.current = true
      api.patch('/auth/profile', { onboarding_completed: true }).catch(() => {})
    }
    let alive = true
    Promise.allSettled([
      api.brokers.credentials(),
      api.engine.funds().catch(() => null),
      api.paper.trades(1).catch(() => null),
      api.notifications.telegramStatus().catch(() => null),
    ]).then(([c, f, t, tg]) => {
      if (!alive) return
      const creds = (c.status === 'fulfilled' ? (c.value as { credentials?: BrokerCred[] }).credentials : []) || []
      const funds = f.status === 'fulfilled' ? (f.value as { funds?: { available_margin?: number } })?.funds : null
      const trades = t.status === 'fulfilled' ? (t.value as { trades?: unknown[] })?.trades : null
      const linked = tg.status === 'fulfilled' ? (tg.value as { linked?: boolean })?.linked : false
      setChecks({
        broker: creds.some(x => x.is_active),
        funds: Number((funds as { available_margin?: number })?.available_margin ?? 0) > 0 || !!funds,
        paperTrade: Array.isArray(trades) && trades.length > 0,
        alerts: linked === true,
      })
    })
    return () => { alive = false }
  }, [])

  return (
    <div>
      <div style={{ textAlign: 'center', marginBottom: 28 }}>
        <div style={{
          width: 60, height: 60, borderRadius: '50%', margin: '0 auto 16px',
          background: 'linear-gradient(135deg, color-mix(in srgb, var(--green) 15%, transparent), color-mix(in srgb, var(--green) 5%, transparent))',
          border: '2px solid color-mix(in srgb, var(--green) 30%, transparent)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 24, color: 'var(--green)',
        }}>
          ✓
        </div>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 20, margin: '0 0 8px', color: 'var(--text)' }}>
          You&apos;re all set!
        </h2>
        <p style={{ color: 'var(--text-sub)', margin: 0, fontSize: 13 }}>
          Your terminal is ready. Start trading with your connected broker.
        </p>
      </div>

      {loading && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ color: 'var(--text-sub)', fontSize: 12 }}>Loading your strategies...</p>
        </div>
      )}

      {error && (
        <div style={{ padding: '12px 16px', background: 'color-mix(in srgb, var(--red) 10%, transparent)', border: '1px solid rgba(248,113,113,0.2)', borderRadius: 8, color: 'var(--red)', fontSize: 13, marginBottom: 16 }}>
          Could not load strategy assignments
        </div>
      )}

      {!loading && assigned.length > 0 && (
        <div className="t-panel" style={{ padding: 0, overflow: 'hidden', marginBottom: 20 }}>
          <div className="t-panel-header" style={{ padding: '12px 16px', margin: 0 }}>
            <h3 className="t-panel-title" style={{ fontSize: 13 }}>Your Assigned Strategies</h3>
            <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{assigned.length}</span>
          </div>
          {assigned.map((s: AssignedStrategy) => (
            <div key={s.id} className="t-panel" style={{ padding: '10px 14px', margin: '0 12px 8px', fontSize: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 600, color: 'var(--text)' }}>{s.name || s.strategy_key}</span>
                <span className="t-badge t-badge-violet" style={{ fontSize: 9, padding: '1px 6px' }}>{s.required_tier}</span>
              </div>
              <p style={{ margin: '4px 0 0', fontSize: 10, color: 'var(--text-faint)' }}>
                {s.mirror_enabled ? 'Mirror enabled' : 'Mirror disabled'} · {s.active ? 'Active' : 'Inactive'}
              </p>
            </div>
          ))}
        </div>
      )}

      {!loading && assigned.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center', marginBottom: 20 }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-sub)' }}>
            No strategies assigned yet. Your admin can assign strategies in the Admin panel.
          </p>
        </div>
      )}

      <div className="t-panel" style={{ padding: 16, marginBottom: 20 }}>
        <h3 className="t-panel-title" style={{ fontSize: 13, marginBottom: 10 }}>Launch checklist</h3>
        {[
          { done: checks.broker, label: 'Broker connected', href: '/brokers' },
          { done: checks.funds, label: 'Funds visible', href: '/funds' },
          { done: checks.paperTrade, label: 'First paper trade placed', href: '/trade' },
          { done: checks.alerts, label: 'Telegram alerts linked', href: '/settings' },
        ].map(c => (
          <div key={c.label} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0' }}>
            <span style={{ width: 20, height: 20, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, background: c.done ? 'var(--green)' : 'var(--bg-tertiary)', color: c.done ? '#052a14' : 'var(--text-faint)' }}>{c.done ? '✓' : '·'}</span>
            <span style={{ flex: 1, fontSize: 12, color: 'var(--text)' }}>{c.label}</span>
            {!c.done && <a href={c.href} style={{ fontSize: 11, color: 'var(--cyan)' }}>Do it</a>}
          </div>
        ))}
      </div>

      <button
        className="t-btn-primary"
        style={{ width: '100%', padding: '12px 24px', fontSize: 14 }}
        onClick={() => router.push(isAdmin ? '/dashboard' : '/live')}
      >
        Open Dashboard
      </button>
    </div>
  )
}

/* ========== Progress Indicator ========== */

function ProgressBar({ current }: { current: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0, marginBottom: 32 }}>
      {STEPS.map((label, i) => {
        const done = i < current
        const active = i === current
        return (
          <div key={i} style={{ display: 'flex', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{
                width: 28, height: 28, borderRadius: '50%', display: 'flex',
                alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700,
                background: done ? 'linear-gradient(135deg, var(--violet), var(--cyan))' : active ? 'color-mix(in srgb, var(--violet) 20%, transparent)' : 'color-mix(in srgb, var(--text-inverse) 4%, transparent)',
                border: active ? '1px solid #8b5cf6' : done ? 'none' : '1px solid color-mix(in srgb, var(--text-inverse) 8%, transparent)',
                color: done || active ? 'var(--text)' : 'var(--text-faint)',
                transition: 'all 200ms ease',
              }}>
                {done ? '✓' : i + 1}
              </div>
              <span style={{
                fontSize: 11, fontWeight: active || done ? 600 : 400,
                color: done ? 'var(--cyan)' : active ? 'var(--text)' : 'var(--text-faint)',
                transition: 'color 200ms ease',
              }}>
                {label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div style={{
                width: 32, height: 1,
                background: done ? 'linear-gradient(90deg, var(--violet), var(--cyan))' : 'color-mix(in srgb, var(--text-inverse) 6%, transparent)',
                margin: '0 8px', transition: 'background 200ms ease',
              }} />
            )}
          </div>
        )
      })}
    </div>
  )
}

/* ========== Main ========== */

export default function OnboardingPage() {
  const { token, loading: authLoading } = useAuth()
  const router = useRouter()
  const [step, setStep] = useState(0)
  const [guardChecked, setGuardChecked] = useState(false)

  const handleNext = useCallback(() => {
    setStep(s => Math.min(s + 1, 2))
  }, [])

  useEffect(() => {
    if (!authLoading && token && !guardChecked) {
      setGuardChecked(true)
      api.auth.me().then((user) => {
        if ((user as any).onboarding_completed) {
          router.push((user as any).is_admin ? '/dashboard' : '/live')
        }
      }).catch(() => {})
    }
  }, [authLoading, token, guardChecked, router])

  useEffect(() => {
    if (!authLoading && token && step === 0) {
      setStep(prev => Math.min(prev + 1, 2))
    }
  }, [authLoading, token, step])

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: '100vh',
      background: 'radial-gradient(ellipse at 50% 0%, color-mix(in srgb, var(--violet) 8%, transparent) 0%, transparent 60%), #000',
      padding: 16,
    }}>
      <div style={{ width: 480 }}>
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <h1 style={{
            fontFamily: 'var(--font-display)', fontSize: 26, margin: '0 0 6px',
            background: 'linear-gradient(135deg, var(--violet), var(--cyan))',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          }}>
            Welcome to Trade Metrix
          </h1>
          <p style={{ color: 'var(--text-sub)', margin: 0, fontSize: 14 }}>
            Set up your terminal in a few steps
          </p>
        </div>

        <ProgressBar current={step} />

        <div className="t-panel" style={{ padding: 28, border: '1px solid color-mix(in srgb, var(--violet) 15%, transparent)' }}>
          {step === 0 && <StepAccount onDone={handleNext} />}
          {step === 1 && <StepConnectBroker onDone={handleNext} />}
          {step === 2 && <StepDone />}
        </div>

      </div>
    </div>
  )
}
