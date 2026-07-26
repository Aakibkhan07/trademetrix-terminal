'use client'

import { useEffect, useState, useCallback } from 'react'
import { api, BrokerMeta, BrokerFieldMeta } from '@/lib/api'
import { BrokerLogo } from '@/components/broker-logos'

/* ========== Types ========== */

interface BrokerInfo { id: string; broker: string; is_active: boolean; created_at: string }
interface UserInfo { id: string; email: string; full_name: string; phone: string; subscription_tier: string }

/* ========== Helpers ========== */

function fmtDate(iso?: string) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}
function otpInputStyle(active: boolean) {
  return {
    width: 44, height: 48, textAlign: 'center' as const, fontSize: 20, fontWeight: 700 as const,
    fontFamily: 'var(--font-mono)', border: `2px solid ${active ? 'var(--cyan)' : 'var(--border)'}`,
    borderRadius: 8, background: active ? 'color-mix(in srgb, var(--cyan) 6%, transparent)' : 'var(--bg-tertiary)',
    color: 'var(--text)', outline: 'none', caretColor: 'var(--cyan)',
    transition: 'border-color 0.15s, background 0.15s',
  }
}

/* ===================================================================
   CLIENT PORTAL — BROKER CONNECTION & ACTIVATION
   =================================================================== */

function ClientPortal({ email, user, onSignOut }: { email: string; user: UserInfo | null; onSignOut: () => void }) {
  const [brokers, setBrokers] = useState<BrokerInfo[]>([])
  const [availBrokers, setAvailBrokers] = useState<string[]>([])
  const [brokerMeta, setBrokerMeta] = useState<BrokerMeta[]>([])
  const [loading, setLoading] = useState(true)

  const loadData = useCallback(async () => {
    try {
      const [bc, bl, bm] = await Promise.all([
        api.brokers.credentials().catch((e: unknown) => { console.error('load credentials', e); return { credentials: [] } }),
        api.brokers.list().catch((e: unknown) => { console.error('load broker list', e); return { brokers: [] } }),
        api.brokers.metadata().catch((e: unknown) => { console.error('load broker metadata', e); return { brokers: [] } }),
      ])
      setBrokers((bc as { credentials: BrokerInfo[] }).credentials || [])
      setAvailBrokers((bl as { brokers: string[] }).brokers || [])
      setBrokerMeta((bm as { brokers: BrokerMeta[] }).brokers || [])
    } catch (e) { console.error('loadData', e) } finally { setLoading(false) }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const [connectForm, setConnectForm] = useState<{
    broker: string; fields: Record<string, string>; additional_params: Record<string, string>
  } | null>(null)
  const [connecting, setConnecting] = useState(false)
  const [brokerError, setBrokerError] = useState('')
  const [authUrl, setAuthUrl] = useState<string | null>(null)

  const getBrokerMeta = useCallback((b: string) => brokerMeta.find(m => m.broker === b), [brokerMeta])

  const handleConnectBroker = async () => {
    if (!connectForm) return
    setConnecting(true); setBrokerError('')
    try {
      const f = connectForm.fields
      const ap = connectForm.additional_params
      const payload: Record<string, unknown> = { broker: connectForm.broker }
      if (f.api_key) payload.api_key = f.api_key
      if (f.secret_key) payload.secret_key = f.secret_key
      if (f.client_id) payload.client_id = f.client_id
      if (f.client_code) payload.client_code = f.client_code
      if (f.access_token) payload.access_token = f.access_token
      if (Object.keys(ap).length > 0) payload.additional_params = ap

      await api.brokers.saveCredentials(payload as Parameters<typeof api.brokers.saveCredentials>[0])

      const meta = getBrokerMeta(connectForm.broker)
      if (meta?.oauth_available) {
        try {
          if (connectForm.broker === 'fyers') {
            const authRes = await api.brokers.fyersAuthUrl() as { auth_url: string }
            setAuthUrl(authRes.auth_url)
          }
        } catch (e) { console.error('fyers auth url', e) }
      }
      await loadData()
      setConnectForm(null)
    } catch (e: unknown) {
      setBrokerError(e instanceof Error ? e.message : 'Failed to connect')
    } finally { setConnecting(false) }
  }

  const handleDisconnectBroker = async (broker: string) => {
    try {
      await api.brokers.deleteCredentials(broker)
      setBrokers(brokers.filter(b => b.broker !== broker))
    } catch (e) { console.error('disconnect broker', e) }
  }

  const handleActivateBroker = async (broker: string) => {
    try {
      await api.brokers.activate(broker)
      const bc = await api.brokers.credentials()
      setBrokers((bc as { credentials: BrokerInfo[] }).credentials || [])
    } catch (e) { console.error('activate broker', e) }
  }

  const activeBroker = brokers.find(b => b.is_active)
  const hasBroker = brokers.length > 0

  if (loading) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
      <div className="t-dot t-dot-green t-dot-pulse" />
    </div>
  )

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>

      {/* Header */}
      <header style={{
        height: 48, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 16px', borderBottom: '1px solid var(--border)', background: 'var(--bg-secondary)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{
            fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 700,
            background: 'var(--gradient-primary)', WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}>TradeMetrix</span>
          <span className="t-badge t-badge-cyan" style={{ fontSize: 9, letterSpacing: '0.06em' }}>CLIENT PORTAL</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{
            display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
            background: activeBroker ? 'var(--green)' : 'var(--text-faint)',
          }} />
          <span style={{ fontSize: 10, color: 'var(--text-sub)', fontFamily: 'var(--font-mono)' }}>
            {activeBroker ? `${activeBroker.broker.toUpperCase()} ACTIVE` : 'NO BROKER'}
          </span>
          <span style={{ fontSize: 10, color: 'var(--text-sub)' }}>{user?.full_name || email}</span>
          <button className="t-btn t-btn-xs t-btn-ghost" onClick={onSignOut}
            style={{ color: 'var(--text-red)' }}>Sign Out</button>
        </div>
      </header>

      <div style={{ flex: 1, padding: 24, overflowY: 'auto', maxWidth: 640, margin: '0 auto', width: '100%' }}>

        {/* Status Card */}
        <div style={{
          padding: '18px 20px', borderRadius: 10, marginBottom: 20,
          background: activeBroker
            ? 'linear-gradient(135deg, color-mix(in srgb, var(--green) 8%, transparent), color-mix(in srgb, var(--cyan) 6%, transparent))'
            : 'color-mix(in srgb, var(--amber) 6%, transparent)',
          border: `1px solid ${activeBroker ? 'color-mix(in srgb, var(--green) 12%, transparent)' : 'color-mix(in srgb, var(--amber) 12%, transparent)'}`,
        }}>
          {activeBroker ? (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                <BrokerLogo broker={activeBroker.broker} size={32} />
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>
                    {(getBrokerMeta(activeBroker.broker)?.display_name || activeBroker.broker)} Active
                  </div>
                  <div className="t-faint" style={{ fontSize: 10 }}>
                    Connected since {fmtDate(activeBroker.created_at)}
                  </div>
                </div>
              </div>
              <p style={{ fontSize: 11, color: 'var(--text-sub)', margin: '8px 0 0', lineHeight: 1.5 }}>
                Your broker is connected and active. The admin will assign strategies and broadcast trades to your account. All trades execute automatically through your active broker.
              </p>
            </>
          ) : hasBroker ? (
            <>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>Activate Your Broker</div>
              <p style={{ fontSize: 11, color: 'var(--text-sub)', margin: 0, lineHeight: 1.5 }}>
                You have connected brokers but none are active. Click <strong>Activate</strong> on the broker you want to use for live trading.
              </p>
            </>
          ) : (
            <>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>Connect Your Trading Broker</div>
              <p style={{ fontSize: 11, color: 'var(--text-sub)', margin: 0, lineHeight: 1.5 }}>
                Connect your broker account below. Once connected and activated, the admin can assign strategies and broadcast trades to you. All trades are placed through your broker automatically.
              </p>
            </>
          )}
        </div>

        {/* Connected Brokers */}
        <div className="t-panel" style={{ padding: 0, marginBottom: 20 }}>
          <div className="t-panel-header">
            <h3 className="t-panel-title">Connected Brokers ({brokers.length})</h3>
          </div>
          {brokers.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {brokers.map(b => {
                const meta = getBrokerMeta(b.broker)
                const displayName = meta?.display_name || b.broker
                return (
                  <div key={b.id} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '14px 16px', borderBottom: '1px solid var(--border)',
                    background: b.is_active ? 'color-mix(in srgb, var(--green) 3%, transparent)' : undefined,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <BrokerLogo broker={b.broker} size={28} />
                      <div>
                        <span style={{ fontWeight: 600, fontSize: 13 }}>{displayName}</span>
                        {b.is_active && (
                          <span className="t-badge t-badge-green" style={{ fontSize: 9, marginLeft: 8 }}>Active</span>
                        )}
                        <div className="t-faint" style={{ fontSize: 9, marginTop: 2 }}>Connected {fmtDate(b.created_at)}</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      {b.is_active ? (
                        <span className="t-badge t-badge-green" style={{ fontSize: 9 }}>LIVE</span>
                      ) : (
                        <button className="t-btn t-btn-xs t-btn-primary" onClick={() => handleActivateBroker(b.broker)}>
                          Activate
                        </button>
                      )}
                      {!b.is_active && (
                        <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => handleDisconnectBroker(b.broker)}
                          style={{ color: 'var(--text-red)' }}>Remove</button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="t-panel-body" style={{ textAlign: 'center', padding: 20 }}>
              <span className="t-faint">No brokers connected yet</span>
            </div>
          )}
        </div>

        {/* Connect New Broker */}
        <div className="t-panel" style={{ padding: '16px 18px' }}>
          <h3 style={{ margin: '0 0 10px', fontSize: 12, fontWeight: 600, letterSpacing: '0.03em' }}>
            {connectForm ? `Connect ${(getBrokerMeta(connectForm.broker)?.display_name || connectForm.broker)}` : 'Available Brokers'}
          </h3>
          {authUrl && (
            <div style={{
              padding: '8px 12px', borderRadius: 6, fontSize: 10, marginBottom: 10,
              background: 'color-mix(in srgb, var(--green) 8%, transparent)', color: 'var(--text-green)',
              border: '1px solid color-mix(in srgb, var(--green) 12%, transparent)',
            }}>
              Credentials saved.{' '}
              <a href={authUrl} target="_blank" rel="noopener noreferrer"
                style={{ color: 'var(--cyan)', textDecoration: 'underline' }}>
                Click here to authorize via OAuth
              </a>
            </div>
          )}
          {connectForm ? (() => {
            const meta = getBrokerMeta(connectForm.broker)
            return (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {meta?.instructions && (
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', whiteSpace: 'pre-line', lineHeight: 1.5, padding: '6px 10px', background: 'var(--bg-sub)', borderRadius: 6 }}>
                    {meta.instructions}
                  </div>
                )}
                {meta?.fields.map((field: BrokerFieldMeta) => (
                  <div key={field.key}>
                    <label className="t-label" style={{ fontSize: 10 }}>{field.label}</label>
                    <input className="t-input" style={{ width: '100%' }}
                      type={field.type === 'password' ? 'password' : 'text'}
                      placeholder={field.placeholder || ''}
                      value={connectForm.fields[field.key] || ''}
                      onChange={e => setConnectForm({
                        ...connectForm,
                        fields: { ...connectForm.fields, [field.key]: e.target.value },
                      })} />
                  </div>
                ))}
                {meta?.has_additional_params && meta.additional_params_fields?.map((field: BrokerFieldMeta) => (
                  <div key={field.key}>
                    <label className="t-label" style={{ fontSize: 10 }}>{field.label}</label>
                    <input className="t-input" style={{ width: '100%' }}
                      type={field.type === 'password' ? 'password' : 'text'}
                      placeholder={field.placeholder || ''}
                      value={connectForm.additional_params[field.key] || ''}
                      onChange={e => setConnectForm({
                        ...connectForm,
                        additional_params: { ...connectForm.additional_params, [field.key]: e.target.value },
                      })} />
                  </div>
                ))}
                {brokerError && <span className="t-down" style={{ fontSize: 10 }}>{brokerError}</span>}
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="t-btn t-btn-sm t-btn-primary" onClick={handleConnectBroker} disabled={connecting}>
                    {connecting ? 'Connecting...' : 'Connect'}
                  </button>
                  <button className="t-btn t-btn-sm t-btn-ghost" onClick={() => { setConnectForm(null); setBrokerError('') }}>
                    Cancel
                  </button>
                </div>
                {meta?.oauth_available && (
                  <div className="t-faint" style={{ fontSize: 9, lineHeight: 1.4 }}>
                    After saving credentials, you'll need to authorize via OAuth.
                  </div>
                )}
              </div>
            )
          })() : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {brokerMeta.filter(m => availBrokers.includes(m.broker)).map(m => {
                const connected = brokers.some(c => c.broker === m.broker)
                return (
                  <div key={m.broker} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '10px 12px', borderRadius: 6,
                    background: 'var(--bg-sub)', border: '1px solid var(--border)',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <BrokerLogo broker={m.broker} size={24} />
                      <div>
                        <span style={{ fontWeight: 600, fontSize: 12 }}>{m.display_name}</span>
                        <span className="t-faint" style={{ fontSize: 9, marginLeft: 6 }}>({m.auth_type})</span>
                        <p style={{ margin: '2px 0 0', fontSize: 9, color: 'var(--text-faint)', lineHeight: 1.3 }}>{m.description}</p>
                      </div>
                    </div>
                    <button className={`t-btn t-btn-xs ${connected ? 't-btn-ghost' : 't-btn-primary'}`}
                      onClick={() => {
                        if (!connected) setConnectForm({ broker: m.broker, fields: {}, additional_params: {} })
                      }}
                      disabled={connected}>
                      {connected ? '\u2713 Connected' : '+ Connect'}
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>

      </div>

      {/* Footer */}
      <footer style={{
        height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
        borderTop: '1px solid var(--border)', fontSize: 9, color: 'var(--text-faint)',
        fontFamily: 'var(--font-mono)',
      }}>
        TradeMetrix Terminal v0.1 &middot; Client Portal
      </footer>
    </div>
  )
}

/* ===================================================================
   OTP LOGIN / SIGNUP SCREEN
   =================================================================== */

function OTPScreen({ onVerify }: { onVerify: (email: string) => void }) {
  const [step, setStep] = useState<'email' | 'otp' | 'register'>('email')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [otp, setOtp] = useState(['', '', '', '', '', ''])
  const [sending, setSending] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState('')
  const [resendTimer, setResendTimer] = useState(0)
  const [userExists, setUserExists] = useState<boolean | null>(null)

  useEffect(() => {
    if (resendTimer <= 0) return
    const t = setInterval(() => setResendTimer(p => p - 1), 1000)
    return () => clearInterval(t)
  }, [resendTimer])

  const handleSendOTP = async () => {
    if (!email || !email.includes('@')) { setError('Enter a valid email'); return }
    setError(''); setSending(true)
    try {
      const res = await api.auth.sendOTP({ email })
      setUserExists(res.exists)
      setSending(false)
      if (res.exists) {
        setStep('otp')
        setResendTimer(30)
      } else {
        setStep('register')
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to send OTP')
      setSending(false)
    }
  }

  const handleRegister = async () => {
    if (!email || !password || password.length < 6) { setError('Email and password (min 6 chars) required'); return }
    setError(''); setSending(true)
    try {
      await api.auth.registerWithOTP({ email, password, full_name: fullName || undefined, phone: phone || undefined })
      setSending(false)
      setStep('otp')
      setResendTimer(30)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Registration failed')
      setSending(false)
    }
  }

  const handleVerifyOTP = async () => {
    const entered = otp.join('')
    if (entered.length !== 6) { setError('Enter the full 6-digit code'); return }
    setError(''); setVerifying(true)
    try {
      await api.auth.verifyOTP({ email, otp: entered })
      setVerifying(false)
      onVerify(email)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Invalid OTP')
      setVerifying(false)
    }
  }

  const handleResend = async () => {
    if (resendTimer > 0) return
    setError(''); setSending(true)
    try {
      await api.auth.sendOTP({ email })
      setSending(false)
      setResendTimer(30)
      setOtp(['', '', '', '', '', ''])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to resend')
      setSending(false)
    }
  }

  const handleOtpInput = (i: number, val: string) => {
    if (!/^\d?$/.test(val)) return
    const newOtp = [...otp]; newOtp[i] = val; setOtp(newOtp)
    if (val && i < 5) document.getElementById(`otp-${i + 1}`)?.focus()
  }
  const handleOtpKey = (i: number, key: string) => {
    if (key === 'Backspace' && !otp[i] && i > 0) document.getElementById(`otp-${i - 1}`)?.focus()
    if (key === 'Enter') handleVerifyOTP()
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg)', padding: 16,
    }}>
      <div style={{
        width: '100%', maxWidth: 400,
        padding: '32px 28px', borderRadius: 12,
        border: '1px solid var(--border)',
        background: 'var(--bg-secondary)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 48, height: 48, borderRadius: 12,
            background: 'var(--gradient-primary)', marginBottom: 12,
            fontSize: 20, fontWeight: 700, color: 'var(--text-inverse)',
          }}>TM</div>
          <h2 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 4px' }}>Client Portal</h2>
          <p className="t-faint" style={{ fontSize: 11, margin: 0 }}>
            {step === 'email' ? 'Sign in to connect your broker' :
             step === 'register' ? 'Create your account' :
             `Enter the code sent to ${email}`}
          </p>
        </div>

        {step === 'email' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label className="t-label" style={{ fontSize: 10 }}>Email Address</label>
            <input className="t-input" type="email" placeholder="you@example.com" value={email}
              onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSendOTP()}
              autoFocus />
            {error && <span className="t-down" style={{ fontSize: 10 }}>{error}</span>}
            <button className="t-btn t-btn-primary" onClick={handleSendOTP} disabled={sending}
              style={{ width: '100%', height: 36 }}>
              {sending ? 'Sending OTP...' : 'Send OTP'}
            </button>
          </div>
        )}

        {step === 'register' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label className="t-label" style={{ fontSize: 10 }}>Full Name</label>
            <input className="t-input" placeholder="Your name" value={fullName}
              onChange={e => setFullName(e.target.value)} autoFocus />
            <label className="t-label" style={{ fontSize: 10 }}>Email Address</label>
            <input className="t-input" type="email" placeholder="you@example.com" value={email}
              onChange={e => setEmail(e.target.value)} />
            <label className="t-label" style={{ fontSize: 10 }}>Phone (for OTP)</label>
            <input className="t-input" type="tel" placeholder="+919876543210" value={phone}
              onChange={e => setPhone(e.target.value)} />
            <label className="t-label" style={{ fontSize: 10 }}>Password</label>
            <input className="t-input" type="password" placeholder="Min 6 characters" value={password}
              onChange={e => setPassword(e.target.value)} />
            {error && <span className="t-down" style={{ fontSize: 10 }}>{error}</span>}
            <button className="t-btn t-btn-primary" onClick={handleRegister} disabled={sending}
              style={{ width: '100%', height: 36 }}>
              {sending ? 'Creating account...' : 'Create Account & Send OTP'}
            </button>
            <div style={{ textAlign: 'center' }}>
              <button style={{
                background: 'none', border: 'none', color: 'var(--text-sub)', fontSize: 10,
                cursor: 'pointer', fontFamily: 'var(--font-sans)',
                textDecoration: 'underline', textUnderlineOffset: 2,
              }} onClick={() => setStep('email')}>
                Already have an account? Sign in
              </button>
            </div>
          </div>
        )}

        {step === 'otp' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, alignItems: 'center' }}>
            <div style={{
              padding: '8px 12px', borderRadius: 6, fontSize: 10,
              background: 'color-mix(in srgb, var(--green) 8%, transparent)', color: 'var(--text-green)',
              width: '100%', textAlign: 'center',
              border: '1px solid color-mix(in srgb, var(--green) 12%, transparent)',
            }}>
              OTP sent to {email}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              {otp.map((d, i) => (
                <input key={i} id={`otp-${i}`}
                  style={otpInputStyle(d !== '')}
                  type="text" inputMode="numeric" maxLength={1}
                  value={d}
                  onChange={e => handleOtpInput(i, e.target.value)}
                  onKeyDown={e => handleOtpKey(i, e.key)}
                  autoFocus={i === 0}
                />
              ))}
            </div>
            {error && <span className="t-down" style={{ fontSize: 10 }}>{error}</span>}
            <button className="t-btn t-btn-primary" onClick={handleVerifyOTP} disabled={verifying}
              style={{ width: '100%', height: 36 }}>
              {verifying ? 'Verifying...' : 'Verify & Sign In'}
            </button>
            <button className="t-btn t-btn-ghost" onClick={handleResend} disabled={sending || resendTimer > 0}
              style={{ width: '100%', height: 32, fontSize: 11 }}>
              {resendTimer > 0 ? `Resend in ${resendTimer}s` : sending ? 'Resending...' : 'Resend OTP'}
            </button>
            <button style={{
              background: 'none', border: 'none', color: 'var(--text-sub)', fontSize: 10,
              cursor: 'pointer', fontFamily: 'var(--font-sans)',
            }} onClick={() => { setStep('email'); setError(''); setUserExists(null) }}>
              Change email
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

/* ===================================================================
   PORTAL PAGE ROOT
   =================================================================== */

export default function PortalPage() {
  const [authenticated, setAuthenticated] = useState(false)
  const [email, setEmail] = useState('')
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const savedEmail = sessionStorage.getItem('tm_portal_email')
    const savedUser = sessionStorage.getItem('tm_portal_user')
    if (savedEmail) {
      setEmail(savedEmail)
      if (savedUser) {
        try { setUser(JSON.parse(savedUser)) } catch {}
      }
      setAuthenticated(true)
    }
    setLoading(false)
  }, [])

  const handleVerify = async (newEmail: string) => {
    sessionStorage.setItem('tm_portal_email', newEmail)
    setEmail(newEmail)
    try {
      const me = await api.auth.me()
      const info: UserInfo = {
        id: me.id, email: me.email, full_name: me.full_name || '',
        phone: (me as { phone?: string }).phone || '',
        subscription_tier: me.subscription_tier || 'free',
      }
      sessionStorage.setItem('tm_portal_user', JSON.stringify(info))
      setUser(info)
    } catch {
      setUser(null)
    }
    setAuthenticated(true)
  }

  const handleSignOut = () => {
    sessionStorage.removeItem('tm_portal_email')
    sessionStorage.removeItem('tm_portal_user')
    api.auth.signout().catch(() => {})
    setAuthenticated(false)
    setEmail('')
    setUser(null)
  }

  if (loading) return <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
    <div className="t-dot t-dot-green t-dot-pulse" />
  </div>

  if (!authenticated) {
    return <OTPScreen onVerify={handleVerify} />
  }

  return <ClientPortal email={email} user={user} onSignOut={handleSignOut} />
}
