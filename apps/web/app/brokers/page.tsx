'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { Dialog } from '@/components/ui/dialog'
import { api, friendlyApiError, type BrokerMeta, type BrokerCred, type BrokerFieldMeta } from "@/lib/api";
import { BrokerLogo } from '@/components/broker-logos'

const PLACEHOLDER_BROKERS = new Set([
  'hdfc', 'iifl', 'motilal', 'geojit', 'reliance', 'axis',
  'binance', 'bybit', 'okx', 'oanda', 'interactive_brokers', 'alpaca',
  'icici', 'aliceblue', 'fivepaisa', 'finvasia', 'flattrade', 'groww',
])

function isPlaceholder(broker: string): boolean {
  return PLACEHOLDER_BROKERS.has(broker)
}

export default function BrokersPage() {
  const [credentials, setCredentials] = useState<BrokerCred[]>([])
  const [metadataMap, setMetadataMap] = useState<Record<string, BrokerMeta>>({})
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [formBroker, setFormBroker] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ text: string; type: 'success' | 'error' } | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const form = useRef<{
    broker: string
    api_key: string
    secret_key: string
    client_id: string
    client_code: string
    totp_secret: string
  }>({
    broker: '',
    api_key: '',
    secret_key: '',
    client_id: '',
    client_code: '',
    totp_secret: '',
  }).current

  const msgTimer = useRef<ReturnType<typeof setTimeout>>()

  const showMsg = (text: string, type: 'success' | 'error' = 'success') => {
    setMsg({ text, type })
    if (msgTimer.current) clearTimeout(msgTimer.current)
    msgTimer.current = setTimeout(() => setMsg(null), 10000)
  }

  const displayName = useCallback((broker: string) => {
    return metadataMap[broker]?.display_name || broker.charAt(0).toUpperCase() + broker.slice(1)
  }, [metadataMap])

  const load = useCallback(async () => {
    try {
      const [credData, metaData] = await Promise.all([
        api.brokers.credentials(),
        api.brokers.metadata(),
      ])
      setCredentials((credData as { credentials: BrokerCred[] }).credentials || [])
      const metaArr = (metaData as { brokers: BrokerMeta[] }).brokers || []
      const mm: Record<string, BrokerMeta> = {}
      metaArr.forEach(m => { mm[m.broker] = m })
      setMetadataMap(mm)
      setLoadError(null)
    } catch (e) {
      setLoadError(friendlyApiError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const authCode = params.get('auth_code')
    const authSuccess = params.get('auth_success')
    const authError = params.get('auth_error')
    let cancelled = false

    if (authCode) {
      api.brokers.fyersExchangeCode(authCode).then(() => {
        if (cancelled) return
        showMsg('Fyers authenticated successfully!')
        load()
      }).catch(() => {
        if (cancelled) return
        showMsg('Failed to exchange Fyers auth code.', 'error')
      })
    } else if (authSuccess) {
      showMsg('Broker authenticated successfully!')
      load()
    } else if (authError) {
      showMsg(decodeURIComponent(authError), 'error')
    }

    if (authCode || authSuccess || authError) {
      const url = new URL(window.location.href)
      url.searchParams.delete('auth_code')
      url.searchParams.delete('state')
      url.searchParams.delete('auth_success')
      url.searchParams.delete('auth_error')
      window.history.replaceState({}, '', url.toString())
    }
    return () => { cancelled = true }
  }, [load])

  const openForm = (broker: string) => {
    form.broker = broker
    form.api_key = ''
    form.secret_key = ''
    form.client_id = ''
    form.client_code = ''
    form.totp_secret = ''
    setFormBroker(broker)
    setShowForm(true)
  }

  const closeForm = () => {
    setShowForm(false)
    setFormBroker('')
  }

  const handleSave = async () => {
    if (saving) return
    if (!form.broker || !form.api_key.trim() || !form.secret_key.trim()) {
      showMsg('API key + secret are required', 'error')
      return
    }
    setSaving(true)
    try {
      const additional_params: Record<string, string> = {}
      if (form.totp_secret) additional_params.totp_secret = form.totp_secret

      const payload: Parameters<typeof api.brokers.saveCredentials>[0] = {
        broker: form.broker,
        api_key: form.api_key,
        secret_key: form.secret_key,
        client_id: form.client_id || undefined,
        client_code: form.client_code || undefined,
        additional_params: Object.keys(additional_params).length ? additional_params : undefined,
      }
      await api.brokers.saveCredentials(payload)

      const meta = metadataMap[form.broker]
      if (meta?.oauth_available) {
        const { auth_url } = await api.brokers.authUrl(form.broker) as { auth_url: string }
        if (auth_url) {
          showMsg(`${displayName(form.broker)} saved! OAuth link opened.`)
          window.open(auth_url, '_blank')
        } else {
          showMsg(`${displayName(form.broker)} connected!`)
        }
      } else {
        showMsg(`${displayName(form.broker)} credentials saved!`)
      }
      load()
      closeForm()
    } catch (e: any) {
      showMsg(friendlyApiError(e), 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleReAuth = async (broker: string) => {
    try {
      const { auth_url } = await api.brokers.reAuth(broker) as { auth_url?: string }
      if (auth_url) {
        window.open(auth_url, '_blank')
        showMsg(`${displayName(broker)} re-auth link opened.`)
      } else {
        showMsg(`Re-auth initiated for ${displayName(broker)}`, 'success')
      }
    } catch (e: any) {
      showMsg(e?.message || 'Re-auth failed', 'error')
    }
  }

  const handleDelete = async (broker: string) => {
    try {
      await api.brokers.deleteCredentials(broker)
      showMsg(`${displayName(broker)} disconnected`)
      load()
    } catch {
      showMsg('Failed to disconnect', 'error')
    }
  }

  const connectedBrokers = credentials.filter(c => c.is_active)
  const availableBrokers = Object.keys(metadataMap).filter(
    b => !connectedBrokers.some(c => c.broker === b) && !isPlaceholder(b)
  )
  const placeholderBrokers = Object.keys(metadataMap).filter(
    b => !connectedBrokers.some(c => c.broker === b) && isPlaceholder(b)
  )

  const stats = {
    connected: connectedBrokers.length,
    available: availableBrokers.length,
    activeTokens: credentials.filter(c => c.token_expires_at && new Date(c.token_expires_at).getTime() > Date.now()).length,
  }

  const tokenBadge = (c: BrokerCred) => {
    if (!c.token_expires_at) return null
    const expiry = new Date(c.token_expires_at)
    const hoursLeft = (expiry.getTime() - Date.now()) / 3600000
    let cls = 't-badge-green'
    let label = `Valid until ${expiry.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`
    if (hoursLeft <= 0) {
      cls = 't-badge-red'
      label = 'Expired — re-auth required'
    } else if (hoursLeft <= 24) {
      cls = 't-badge-amber'
      label = `Expires in ${hoursLeft < 1 ? Math.round(hoursLeft * 60) + 'm' : Math.round(hoursLeft) + 'h'}`
    }
    return (
      <span className={`t-badge ${cls}`} style={{ fontSize: 9, padding: '2px 8px', marginTop: 2 }}>
        {label}
      </span>
    )
  }

  return (
    <div>
      {loadError && (
        <div className="t-panel" style={{ marginBottom: 12, padding: '10px 14px', borderColor: 'var(--red)' }}>
          <span className="t-error">{loadError}</span>{' '}
          <button className="t-btn t-btn-xs" onClick={load}>Retry</button>
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, margin: 0, color: 'var(--text)', letterSpacing: '-0.02em' }}>
            Brokers
          </h1>
          <p className="t-faint" style={{ margin: '4px 0 0', fontSize: 12 }}>
            Institutional connectivity —{' '}
            <span style={{ color: 'var(--text)', fontWeight: 600 }}>{stats.connected} connected</span>
            {' · '}{stats.available} available
            {' · '}{stats.activeTokens} tokens live
          </p>
        </div>
        <button
          className="t-btn t-btn-primary"
          onClick={() => availableBrokers.length > 0 ? openForm(availableBrokers[0]) : null}
          disabled={availableBrokers.length === 0}
          style={{ height: 34, padding: '0 16px', fontSize: 12 }}
        >
          + Connect Broker
        </button>
      </div>

      {/* Stats row */}
      <div className="t-grid-3" style={{ marginBottom: 20 }}>
        <div className="t-panel" style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: 'var(--green-dim)', border: '1px solid var(--green-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--green)" strokeWidth="1.7"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Connected</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--text)' }}>{stats.connected}</div>
          </div>
          {stats.connected > 0 && <span className="t-dot t-dot-green t-dot-pulse" style={{ marginLeft: 'auto' }} />}
        </div>
        <div className="t-panel" style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: 'var(--violet-dim)', border: '1px solid var(--violet-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--violet)" strokeWidth="1.7"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a4 4 0 0 1 8 0v2"/></svg>
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Available</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--text)' }}>{stats.available}</div>
          </div>
        </div>
        <div className="t-panel" style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: stats.activeTokens ? 'var(--cyan-dim)' : 'var(--red-dim)', border: `1px solid ${stats.activeTokens ? 'var(--cyan-dim)' : 'var(--red-dim)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={stats.activeTokens ? 'var(--cyan)' : 'var(--red)'} strokeWidth="1.7"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Live Tokens</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: stats.activeTokens ? 'var(--cyan)' : 'var(--red)' }}>{stats.activeTokens}</div>
          </div>
        </div>
      </div>

      {msg && (
        <div style={{
          background: msg.type === 'error' ? 'color-mix(in srgb, var(--red) 10%, transparent)' : 'color-mix(in srgb, var(--green) 10%, transparent)',
          border: `1px solid ${msg.type === 'error' ? 'color-mix(in srgb, var(--red) 20%, transparent)' : 'color-mix(in srgb, var(--green) 20%, transparent)'}`,
          borderRadius: 8, padding: '10px 14px', marginBottom: 16,
        }}>
          <p style={{ color: msg.type === 'error' ? 'var(--red)' : 'var(--green)', fontSize: 13, margin: 0 }}>{msg.text}</p>
        </div>
      )}

      {/* Connected brokers */}
      {credentials.length > 0 && (
        <>
          <h2 className="t-panel-title" style={{ fontSize: 15, marginBottom: 12 }}>
            Connected Brokers ({connectedBrokers.length})
          </h2>
          <div className="t-grid-auto" style={{ marginBottom: 28 }}>
            {credentials.map(c => (
              <div key={c.id} className="t-panel" style={{ padding: 0, opacity: c.is_active ? 1 : 0.5 }}>
                <div style={{ padding: 18, display: 'flex', alignItems: 'center', gap: 14 }}>
                  <BrokerLogo broker={c.broker} size={40} />
                  <div style={{ flex: 1 }}>
                    <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 14, margin: 0 }}>
                      {displayName(c.broker)}
                    </h3>
                    <p className="t-faint" style={{ margin: '2px 0 0', fontSize: 11 }}>
                      Added {new Date(c.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
                    <span className={`t-badge ${c.is_active ? 't-badge-green' : 't-badge-violet'}`} style={{ fontSize: 9, padding: '2px 8px' }}>
                      {c.is_active ? 'Active' : 'Inactive'}
                    </span>
                    {tokenBadge(c)}
                    <div style={{ display: 'flex', gap: 4 }}>
                      {c.is_active && (
                        <>
                          <button className="t-btn t-btn-sm t-btn-ghost" style={{ fontSize: 10, padding: '3px 8px' }} onClick={() => handleReAuth(c.broker)}>
                            Re-auth
                          </button>
                          <button className="t-btn t-btn-sm t-btn-danger" style={{ fontSize: 10, padding: '3px 8px' }} onClick={() => handleDelete(c.broker)}>
                            Disconnect
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Available brokers (non-placeholder) */}
      {availableBrokers.length > 0 && (
        <>
          <h2 className="t-panel-title" style={{ fontSize: 15, marginBottom: 12 }}>
            Available Brokers
          </h2>
          <div className="t-grid-3">
            {availableBrokers.map(broker => {
              const meta = metadataMap[broker]
              const isOAuth = meta?.oauth_available ?? false
              return (
                <div
                  key={broker}
                  className="t-panel"
                  style={{ padding: 16, textAlign: 'center', cursor: 'pointer' }}
                  onClick={() => openForm(broker)}
                >
                  <div style={{
                    width: 40, height: 40, borderRadius: 10,
                    background: 'var(--cyan-dim)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    margin: '0 auto 8px', fontSize: 18, fontWeight: 700,
                    color: 'var(--cyan)',
                  }}>
                    {displayName(broker)[0]}
                  </div>
                  <p style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>{displayName(broker)}</p>
                  {isOAuth ? (
                    <span className="t-badge t-badge-cyan" style={{ fontSize: 9, padding: '1px 6px', marginTop: 6 }}>OAuth</span>
                  ) : (
                    <span className="t-badge t-badge-violet" style={{ fontSize: 9, padding: '1px 6px', marginTop: 6 }}>API Keys</span>
                  )}
                  <p className="t-faint" style={{ fontSize: 10, marginTop: 8 }}>
                    {meta?.description?.slice(0, 60)}…
                  </p>
                </div>
              )
            })}
          </div>
        </>
      )}

      {/* Placeholder brokers */}
      {placeholderBrokers.length > 0 && (
        <>
          <h2 className="t-panel-title" style={{ fontSize: 15, marginBottom: 8 }}>
            Coming Soon
          </h2>
          <div style={{ padding: 12, background: 'rgba(255,255,255,0.02)', border: '1px dashed var(--border)', borderRadius: 8, marginBottom: 20 }}>
            <p className="t-faint" style={{ fontSize: 11, margin: 0 }}>
              {placeholderBrokers.length} broker{placeholderBrokers.length > 1 ? 's' : ''} registered but not yet available for live trading:
              {' '}<span style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}>{placeholderBrokers.map(b => displayName(b)).join(', ')}</span>.
              Check back for updates.
            </p>
          </div>
        </>
      )}

      {/* TradingView webhook */}
      <div className="t-panel" style={{ marginBottom: 20 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">
            <span style={{ marginRight: 6 }}>TV</span>
            TradingView Webhook Integration
          </h3>
        </div>
        <div className="t-panel-body">
          <p className="t-faint" style={{ fontSize: 12, margin: '0 0 8px' }}>
            Connect TradingView strategies via webhook. Configure alerts to POST to the endpoint below.
          </p>
          <div style={{
            background: 'rgba(0,0,0,0.2)', borderRadius: 6, padding: 10,
            fontFamily: 'var(--font-mono)', fontSize: 11, wordBreak: 'break-all', marginBottom: 8,
          }}>
            <span style={{ color: 'var(--cyan)' }}>POST</span>{' '}
            <span style={{ color: 'var(--text)' }}>
              {process.env.NEXT_PUBLIC_API_URL || 'https://api.ai.trademetrix.tech/api/v1'}/tradingview/webhook
            </span>
          </div>
          <div className="t-grid-2" style={{ gap: 8, fontSize: 11, marginBottom: 8 }}>
            <div>
              <p className="t-label" style={{ margin: '0 0 2px' }}>Request Format</p>
              <pre style={{
                margin: 0, fontSize: 10, color: 'var(--text-sub)',
                background: 'rgba(0,0,0,0.15)', padding: 8, borderRadius: 4, lineHeight: 1.5,
              }}>
{`{
  "symbol": "NIFTY",
  "action": "BUY",
  "quantity": 65,
  "price": 0,
  "exchange": "NSE",
  "order_type": "MARKET",
  "product": "INTRADAY",
  "paper": true
}`}
              </pre>
            </div>
            <div>
              <p className="t-label" style={{ margin: '0 0 2px' }}>Pine Script Alert</p>
              <pre style={{
                margin: 0, fontSize: 10, color: 'var(--text-sub)',
                background: 'rgba(0,0,0,0.15)', padding: 8, borderRadius: 4, lineHeight: 1.5,
              }}>
{`// Alert → Webhook URL
// Message:
{"symbol":"{{ticker}}",
 "action":"{{strategy.order.action}}",
 "quantity":{{strategy.order.contracts}},
 "paper":true}`}
              </pre>
            </div>
          </div>
          <p className="t-sub" style={{ fontSize: 10, margin: 0 }}>
            Set <code style={{ color: 'var(--cyan)' }}>paper: false</code> for live execution. Optionally set{' '}
            <code style={{ color: 'var(--cyan)' }}>TRADINGVIEW_WEBHOOK_SECRET</code> env for HMAC verification.
          </p>
        </div>
      </div>

      {/* Credential form dialog */}
      {showForm && (
        <Dialog onClose={closeForm} title={`Connect ${displayName(form.broker)}`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 4 }}>
            <p style={{ margin: 0, fontSize: 13, opacity: 0.85, lineHeight: 1.5 }}>
              Enter your <b>{displayName(form.broker)}</b> API credentials. We encrypt and store only the access token — never your password or PIN.
            </p>

            {metadataMap[form.broker]?.fields.map((field: BrokerFieldMeta) => {
              if (field.key === 'client_code') {
                return (
                  <div key={field.key} style={{ marginBottom: 12 }}>
                    <label className="t-label">{field.label}</label>
                    <input
                      className="t-input"
                      value={form.client_code}
                      onChange={e => { form.client_code = e.target.value }}
                      placeholder={field.placeholder || `Your ${displayName(form.broker)} ${field.label}`}
                    />
                  </div>
                )
              }
              if (field.key === 'client_id' || field.key === 'api_key') {
                return (
                  <div key={field.key} style={{ marginBottom: 12 }}>
                    <label className="t-label">{field.label}</label>
                    <input
                      className="t-input"
                      value={field.key === 'client_id' ? form.client_id : form.api_key}
                      onChange={e => {
                        if (field.key === 'client_id') form.client_id = e.target.value
                        else form.api_key = e.target.value
                      }}
                      placeholder={field.placeholder || `Your ${displayName(form.broker)} ${field.label}`}
                    />
                  </div>
                )
              }
              if (field.key === 'secret_key') {
                return (
                  <div key={field.key} style={{ marginBottom: 12 }}>
                    <label className="t-label">{field.label}</label>
                    <input
                      className="t-input"
                      type="password"
                      value={form.secret_key}
                      onChange={e => { form.secret_key = e.target.value }}
                      placeholder={field.placeholder || `Your ${displayName(form.broker)} ${field.label}`}
                    />
                  </div>
                )
              }
              return null
            })}

            {(metadataMap[form.broker]?.additional_params_fields || []).map((field: BrokerFieldMeta) => (
              <div key={field.key} style={{ marginBottom: 12 }}>
                <label className="t-label">{field.label}</label>
                <input
                  className="t-input"
                  type={field.type === 'password' ? 'password' : 'text'}
                  value={form.totp_secret}
                  onChange={e => { form.totp_secret = e.target.value }}
                  placeholder={field.placeholder}
                />
              </div>
            ))}

            {form.broker === 'fyers' && (
              <div style={{ marginBottom: 12 }}>
                <label className="t-label">App ID (Client ID)</label>
                <input
                  className="t-input"
                  value={form.client_id}
                  onChange={e => { form.client_id = e.target.value }}
                  placeholder="Your Fyers App ID"
                />
              </div>
            )}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
              <button className="t-btn t-btn-ghost" onClick={closeForm} style={{ width: 'auto', marginTop: 0 }}>
                Cancel
              </button>
              <button
                className="t-btn t-btn-primary"
                onClick={handleSave}
                disabled={saving}
                style={{ width: 'auto', marginTop: 0, minWidth: 120 }}
              >
                {saving ? 'Saving…' : 'Connect'}
              </button>
            </div>
          </div>
        </Dialog>
      )}
    </div>
  )
}
