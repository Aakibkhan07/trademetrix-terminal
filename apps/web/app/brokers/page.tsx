'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { Dialog } from '@/components/ui/dialog'
import { api, type BrokerMeta } from '@/lib/api'
import { BrokerLogo } from '@/components/broker-logos'

interface BrokerCred {
  id: string
  broker: string
  is_active: boolean
  created_at: string
  token_status?: string
  token_expires_at?: string
}

interface MetadataMap {
  [key: string]: BrokerMeta
}

export default function BrokersPage() {
  const [credentials, setCredentials] = useState<BrokerCred[]>([])
  const [metadataMap, setMetadataMap] = useState<MetadataMap>({})
  const [availableBrokers, setAvailableBrokers] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [editBroker, setEditBroker] = useState('')
  const [selectedBroker, setSelectedBroker] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [clientCode, setClientCode] = useState('')
  const [secretKey, setSecretKey] = useState('')
  const [totpSecret, setTotpSecret] = useState('')
  const [msg, setMsg] = useState('')
  const [msgType, setMsgType] = useState<'success' | 'error'>('success')

  const msgTimer = useRef<ReturnType<typeof setTimeout>>()

  const showMsg = (text: string, type: 'success' | 'error' = 'success') => {
    setMsg(text)
    setMsgType(type)
    if (msgTimer.current) clearTimeout(msgTimer.current)
    msgTimer.current = setTimeout(() => { setMsg(''); msgTimer.current = undefined }, 12000)
  }

  const displayName = useCallback((broker: string) => {
    const meta = metadataMap[broker]
    return meta?.display_name || broker.charAt(0).toUpperCase() + broker.slice(1)
  }, [metadataMap])

  const load = useCallback(async () => {
    try {
      const [credData, brokerData, metaData] = await Promise.all([
        api.brokers.credentials(),
        api.brokers.list(),
        api.brokers.metadata(),
      ])
      const creds = (credData as { credentials: BrokerCred[] }).credentials || []
      setCredentials(creds)
      setAvailableBrokers((brokerData as { brokers: string[] }).brokers || [])
      const metaArr = (metaData as { brokers: BrokerMeta[] }).brokers || []
      const mm: MetadataMap = {}
      metaArr.forEach(m => { mm[m.broker] = m })
      setMetadataMap(mm)
    } catch (e) {
      console.error('Failed to load brokers:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    const fallback = setTimeout(() => { if (mountedRef.current) setLoading(false) }, 8000)
    load().finally(() => clearTimeout(fallback))
    return () => { mountedRef.current = false; clearTimeout(fallback) }
  }, [load])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const authCode = params.get('auth_code')
    let cancelled = false
    if (authCode) {
      api.brokers.fyersExchangeCode(authCode).then(() => {
        if (cancelled) return
        showMsg('Fyers authenticated successfully! Market feed will start shortly.')
        load()
      }).catch(() => {
        if (cancelled) return
        showMsg('Failed to exchange Fyers auth code. Try again.', 'error')
      })
    } else if (params.get('auth_success')) {
      showMsg('Fyers authenticated successfully! Market feed will start shortly.')
      load()
    } else if (params.get('auth_error')) {
      showMsg(`Fyers auth error: ${decodeURIComponent(params.get('auth_error')!)}`, 'error')
    }
    if (authCode || params.get('auth_success') || params.get('auth_error')) {
      const url = new URL(window.location.href)
      url.searchParams.delete('auth_code')
      url.searchParams.delete('state')
      url.searchParams.delete('auth_success')
      url.searchParams.delete('auth_error')
      window.history.replaceState({}, '', url.toString())
    }
    return () => { cancelled = true }
  }, [load])

  const openAdd = (broker?: string) => {
    setEditBroker('')
    setSelectedBroker(broker || '')
    setApiKey('')
    setClientCode('')
    setSecretKey('')
    setTotpSecret('')
    setShowAdd(true)
  }

  const openEdit = (broker: string) => {
    setEditBroker(broker)
    setSelectedBroker(broker)
    setApiKey('')
    setClientCode('')
    setSecretKey('')
    setTotpSecret('')
    setShowAdd(true)
  }

  const handleSave = async () => {
    try {
      const additional_params: Record<string, string> = {}
      if (totpSecret) additional_params.totp_secret = totpSecret
      if (clientCode) additional_params.client_code = clientCode
      await api.brokers.saveCredentials({ broker: selectedBroker, api_key: apiKey, secret_key: secretKey, additional_params: Object.keys(additional_params).length ? additional_params : undefined })
      setShowAdd(false)
      setEditBroker('')
      setSelectedBroker('')
      setApiKey('')
      setClientCode('')
      setSecretKey('')
      setTotpSecret('')
      if (metadataMap[selectedBroker]?.oauth_available) {
        const data = await api.brokers.fyersAuthUrl() as { auth_url: string }
        if (data.auth_url) {
          showMsg(`${displayName(selectedBroker)} saved! OAuth link opened in new tab.`)
          window.open(data.auth_url, '_blank')
        } else {
          showMsg(`${displayName(selectedBroker)} connected successfully`)
        }
      } else {
        showMsg(`${displayName(selectedBroker)} connected successfully`)
      }
      load()
    } catch (e: any) {
      showMsg(e?.message || 'Failed to save credentials', 'error')
    }
  }

  const handleReAuth = async (broker: string) => {
    try {
      const data = await api.brokers.reAuth(broker) as { auth_url?: string }
      if (data.auth_url) {
        window.open(data.auth_url, '_blank')
        showMsg(`${displayName(broker)} re-authentication link opened in new tab.`)
      } else {
        showMsg(`Re-authentication initiated for ${displayName(broker)}`, 'success')
      }
    } catch (e: any) {
      showMsg(e?.message || 'Re-authentication failed', 'error')
    }
  }

  const handleDelete = async (broker: string) => {
    try {
      await api.brokers.deleteCredentials(broker)
      showMsg(`${displayName(broker)} disconnected`)
      load()
    } catch {
      showMsg('Failed to disconnect broker', 'error')
    }
  }

  const connectedBrokers = credentials.map((c) => c.broker)
  const unconnected = availableBrokers.filter((b) => !connectedBrokers.includes(b))

  const metaForBroker = (broker: string) => {
    const m = metadataMap[broker]
    if (m) return m
    return null
  }

  const isOAuth = (broker: string) => metadataMap[broker]?.oauth_available ?? false

  const tokenBadge = (c: BrokerCred) => {
    if (!c.token_expires_at) return null
    const expiry = new Date(c.token_expires_at)
    const hoursLeft = (expiry.getTime() - Date.now()) / 3600000
    let cls = 't-badge-green'
    let label = `Token valid until ${expiry.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`
    if (hoursLeft <= 0) {
      cls = 't-badge-red'
      label = 'Token expired — re-auth required'
    } else if (hoursLeft <= 24) {
      cls = 't-badge-amber'
      label = `Token expires in ${hoursLeft < 1 ? Math.round(hoursLeft * 60) + 'm' : Math.round(hoursLeft) + 'h'} — re-auth recommended`
    }
    return (
      <span className={`t-badge ${cls}`} style={{ fontSize: 9, padding: '2px 8px', marginTop: 2 }}>
        {label}
      </span>
    )
  }

  const stats = {
    connected: credentials.length,
    available: availableBrokers.filter(b => !connectedBrokers.includes(b)).length,
    activeTokens: credentials.filter(c => c.token_expires_at && new Date(c.token_expires_at).getTime() > Date.now()).length,
  }
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, margin: 0, color: 'var(--text)', letterSpacing: '-0.02em' }}>Brokers</h1>
          <p className="t-faint" style={{ margin: '4px 0 0', fontSize: 12 }}>
            Institutional connectivity — <span style={{ color: 'var(--text)', fontWeight: 600 }}>{stats.connected} connected</span> · {stats.available} available · {stats.activeTokens} tokens live
          </p>
        </div>
        <button className="t-btn t-btn-primary" onClick={() => openAdd()} style={{ height: 34, padding: '0 16px', fontSize: 12 }}>
          + Connect Broker
        </button>
      </div>

      <div className="t-grid-3" style={{ marginBottom: 20 }}>
        <div className="t-panel" style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: 'rgba(52,211,153,.12)', border: '1px solid rgba(52,211,153,.2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--green)" strokeWidth="1.7"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Connected</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--text)' }}>{stats.connected}</div>
          </div>
          <span className="t-dot t-dot-green t-dot-pulse" style={{ marginLeft: 'auto' }} />
        </div>
        <div className="t-panel" style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: 'rgba(139,92,246,.12)', border: '1px solid rgba(139,92,246,.2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--violet)" strokeWidth="1.7"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a4 4 0 0 1 8 0v2"/></svg>
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Available</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--text)' }}>{stats.available}</div>
          </div>
        </div>
        <div className="t-panel" style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: stats.activeTokens ? 'rgba(34,211,238,.12)' : 'rgba(248,113,113,.12)', border: `1px solid ${stats.activeTokens ? 'rgba(34,211,238,.2)' : 'rgba(248,113,113,.2)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
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
          background: msgType === 'error' ? 'color-mix(in srgb, var(--red) 10%, transparent)' : 'color-mix(in srgb, var(--green) 10%, transparent)',
          border: `1px solid ${msgType === 'error' ? 'color-mix(in srgb, var(--red) 20%, transparent)' : 'color-mix(in srgb, var(--green) 20%, transparent)'}`,
          borderRadius: 8, padding: '10px 14px', marginBottom: 16
        }}>
          <p style={{ color: msgType === 'error' ? 'var(--red)' : 'var(--green)', fontSize: 13, margin: 0 }}>
            {msg}
          </p>
        </div>
      )}

      {showAdd && (
        <Dialog onClose={() => setShowAdd(false)} title={<div className="t-modal-title">{editBroker ? `Edit ${displayName(editBroker)}` : 'Connect Broker'}</div>}>
            {!editBroker && (
              <div style={{ marginBottom: 16 }}>
                <div className="t-grid-2" style={{ gap: 8 }}>
                  {unconnected.map((b) => (
                    <div
                      key={b}
                      onClick={() => setSelectedBroker(b)}
                      className={`t-chip${selectedBroker === b ? ' active' : ''}`}
                      style={{ textAlign: 'center', padding: '10px', cursor: 'pointer' }}
                    >
                      <div style={{
                        width: 32, height: 32, borderRadius: 8,
                        background: 'color-mix(in srgb, var(--violet) 12%, transparent)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        margin: '0 auto 6px', fontSize: 14, fontWeight: 700, color: 'var(--violet)'
                      }}>
                        {displayName(b)[0]}
                      </div>
                      <p style={{ margin: 0, fontSize: 11, fontWeight: 600 }}>{displayName(b)}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {(selectedBroker || editBroker) && (
              <div style={{ marginBottom: 16 }}>
                {(metaForBroker(selectedBroker || editBroker)?.fields || []).map(field => {
                  if (field.key === 'client_code') {
                    return (
                      <div key={field.key} style={{ marginBottom: 12 }}>
                        <label className="t-label">{field.label}</label>
                        <input className="t-input" value={clientCode} onChange={(e) => setClientCode(e.target.value)}
                          placeholder={field.placeholder || `Your ${displayName(selectedBroker || editBroker)} ${field.label}`} />
                      </div>
                    )
                  }
                  if (field.key === 'api_key') {
                    return (
                      <div key={field.key} style={{ marginBottom: 12 }}>
                        <label className="t-label">{field.label}</label>
                        <input className="t-input" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                          placeholder={field.placeholder || `Your ${displayName(selectedBroker || editBroker)} ${field.label}`} />
                      </div>
                    )
                  }
                  if (field.key === 'client_id') {
                    return (
                      <div key={field.key} style={{ marginBottom: 12 }}>
                        <label className="t-label">{field.label}</label>
                        <input className="t-input" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                          placeholder={field.placeholder || `Your ${displayName(selectedBroker || editBroker)} ${field.label}`} />
                      </div>
                    )
                  }
                  if (field.key === 'secret_key') {
                    return (
                      <div key={field.key} style={{ marginBottom: 12 }}>
                        <label className="t-label">{field.label}</label>
                        <input className="t-input" type="password" value={secretKey} onChange={(e) => setSecretKey(e.target.value)}
                          placeholder={field.placeholder || `Your ${displayName(selectedBroker || editBroker)} ${field.label}`} />
                      </div>
                    )
                  }
                  return null
                })}
                {(metaForBroker(selectedBroker || editBroker)?.additional_params_fields || []).map(field => (
                  <div key={field.key} style={{ marginBottom: 12 }}>
                    <label className="t-label">{field.label}</label>
                    <input className="t-input" type={field.type === 'password' ? 'password' : 'text'}
                      value={field.key === 'totp_secret' ? totpSecret : ''}
                      onChange={(e) => {
                        if (field.key === 'totp_secret') setTotpSecret(e.target.value)
                      }}
                      placeholder={field.placeholder} />
                  </div>
                ))}
              </div>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="t-btn t-btn-ghost" onClick={() => setShowAdd(false)}>Cancel</button>
              <button className="t-btn t-btn-primary" onClick={handleSave} disabled={!selectedBroker && !editBroker}>
                {editBroker ? 'Update' : 'Connect'}
              </button>
            </div>
        </Dialog>
      )}

      {loading ? (
        <p className="t-faint">Loading brokers...</p>
      ) : (
        <>
          {credentials.length > 0 && (
            <>
              <h2 className="t-panel-title" style={{ fontSize: 15, marginBottom: 12 }}>
                Connected Brokers ({credentials.length})
              </h2>
              <div className="t-grid-auto" style={{ marginBottom: 28 }}>
                {credentials.map((c) => (
                  <div key={c.id} className="t-panel" style={{ padding: 0 }}>
                    <div style={{ padding: 18, display: 'flex', alignItems: 'center', gap: 14 }}>
                      <BrokerLogo broker={c.broker} size={40} />
                      <div style={{ flex: 1 }}>
                        <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 14, margin: 0 }}>
                          {displayName(c.broker)}
                        </h3>
                        <p className="t-faint" style={{ margin: '2px 0 0', fontSize: 11 }}>
                          Connected {new Date(c.created_at).toLocaleDateString()}
                        </p>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
                        <span className={`t-badge ${c.is_active ? 't-badge-green' : 't-badge-violet'}`} style={{ fontSize: 9, padding: '2px 8px' }}>
                          {c.is_active ? 'Active' : 'Inactive'}
                        </span>
                        {tokenBadge(c)}
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button className="t-btn t-btn-sm t-btn-ghost" style={{ fontSize: 10, padding: '3px 8px' }} onClick={() => openEdit(c.broker)}>
                            Edit
                          </button>
                          {isOAuth(c.broker) && (
                            <button className="t-btn t-btn-sm t-btn-primary" style={{ fontSize: 10, padding: '3px 8px' }} onClick={() => handleReAuth(c.broker)}>
                              Re-auth
                            </button>
                          )}
                          <button className="t-btn t-btn-sm t-btn-danger" style={{ fontSize: 10, padding: '3px 8px' }} onClick={() => handleDelete(c.broker)}>
                            Disconnect
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

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
                fontFamily: 'var(--font-mono)', fontSize: 11, wordBreak: 'break-all', marginBottom: 8
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
                    background: 'rgba(0,0,0,0.15)', padding: 8, borderRadius: 4, lineHeight: 1.5
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
                    background: 'rgba(0,0,0,0.15)', padding: 8, borderRadius: 4, lineHeight: 1.5
                  }}>
{`// In Strategy settings:
// Alert → Webhook URL
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

          {availableBrokers.filter(b => !connectedBrokers.includes(b)).length > 0 && (
            <>
              <h2 className="t-panel-title" style={{ fontSize: 15, marginBottom: 12 }}>
                Available Brokers
              </h2>
              <div className="t-grid-auto">
                {availableBrokers.filter(b => !connectedBrokers.includes(b)).map((b) => (
                  <div key={b} className="t-panel" style={{
                    padding: 16, textAlign: 'center', cursor: 'pointer',
                  }} onClick={() => openAdd(b)}>
                    <div style={{
                      width: 40, height: 40, borderRadius: 10,
                      background: 'color-mix(in srgb, var(--green) 10%, transparent)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      margin: '0 auto 8px', fontSize: 18, fontWeight: 700,
                      color: 'var(--green)'
                    }}>
                      {displayName(b)[0]}
                    </div>
                    <p style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>{displayName(b)}</p>
                    <span className="t-badge t-badge-green" style={{ fontSize: 9, padding: '1px 6px', marginTop: 6 }}>
                      Connect
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
