'use client'

import { useState } from 'react'

const DEFAULT_PAYLOAD = `{
  "symbol": "NIFTY",
  "action": "BUY",
  "quantity": 65,
  "price": 0,
  "exchange": "NSE",
  "order_type": "MARKET",
  "product": "INTRADAY",
  "user_id": "",
  "strategy_id": "",
  "reason": "Webhook test from admin"
}`

export function WebhookTesterTab() {
  const [payload, setPayload] = useState(DEFAULT_PAYLOAD)
  const [result, setResult] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showInfo, setShowInfo] = useState(true)

  const sendWebhook = async () => {
    setSending(true)
    setError(null)
    setResult(null)
    try {
      let parsed: unknown
      try { parsed = JSON.parse(payload) } catch {
        setError('Invalid JSON payload')
        setSending(false)
        return
      }
      const res = await fetch('/api/v1/tradingview/webhook', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(parsed),
      })
      const text = await res.text()
      if (!res.ok) {
        setError(`HTTP ${res.status}: ${text}`)
      } else {
        try {
          setResult(JSON.stringify(JSON.parse(text), null, 2))
        } catch {
          setResult(text)
        }
      }
    } catch (e) {
      setError(String(e))
    }
    setSending(false)
  }

  return (
    <div>
      <div className="t-panel" style={{ marginBottom: 16, padding: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: showInfo ? 12 : 0 }}>
          <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>Webhook Endpoint</h3>
          <button onClick={() => setShowInfo(!showInfo)} style={{ fontSize: 10, color: 'var(--text-sub)', background: 'none', border: 'none', cursor: 'pointer' }}>
            {showInfo ? 'Hide' : 'Show'}
          </button>
        </div>
        {showInfo && (
          <div style={{ fontSize: 10, lineHeight: 1.6 }}>
            <p style={{ margin: 0 }}><strong>URL:</strong> <code style={{ background: 'color-mix(in srgb, var(--violet) 8%, transparent)', padding: '1px 6px', borderRadius: 3, fontSize: 10 }}>POST /api/v1/tradingview/webhook</code></p>
            <p style={{ margin: '4px 0' }}><strong>Header:</strong> <code style={{ background: 'color-mix(in srgb, var(--violet) 8%, transparent)', padding: '1px 6px', borderRadius: 3, fontSize: 10 }}>X-TradingView-Signature: &lt;your_sha256_hmac&gt;</code></p>
            <p style={{ margin: '4px 0 0', color: 'var(--amber)' }}>Leave <code>user_id</code> empty + set <code>strategy_id</code> to mirror-trade; or set <code>user_id</code> to target a specific user.</p>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 400px', minWidth: 300 }}>
          <label style={{ display: 'block', fontSize: 10, color: 'var(--text-sub)', marginBottom: 6 }}>Payload (JSON)</label>
          <textarea
            value={payload}
            onChange={e => setPayload(e.target.value)}
            style={{
              width: '100%', minHeight: 280, padding: 10, fontSize: 11, fontFamily: 'monospace',
              background: 'color-mix(in srgb, var(--bg) 80%, var(--violet))', color: 'var(--text)',
              border: '1px solid var(--border)', borderRadius: 6, resize: 'vertical',
            }}
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button onClick={sendWebhook} disabled={sending}
              className="t-btn" style={{ fontSize: 11, background: 'var(--violet)', color: '#fff', border: 'none', padding: '6px 18px', borderRadius: 5, cursor: sending ? 'wait' : 'pointer', opacity: sending ? 0.6 : 1 }}>
              {sending ? 'Sending...' : 'Send Test Webhook'}
            </button>
            <button onClick={() => setPayload(DEFAULT_PAYLOAD)}
              style={{ fontSize: 10, background: 'none', border: '1px solid var(--border)', borderRadius: 4, padding: '4px 12px', cursor: 'pointer', color: 'var(--text-sub)' }}>
              Reset
            </button>
          </div>
        </div>

        <div style={{ flex: '1 1 400px', minWidth: 300 }}>
          <label style={{ display: 'block', fontSize: 10, color: 'var(--text-sub)', marginBottom: 6 }}>Response</label>
          {error && (
            <div style={{
              width: '100%', minHeight: 280, padding: 10, fontSize: 11, fontFamily: 'monospace',
              background: 'color-mix(in srgb, var(--bg) 80%, var(--red))', color: 'var(--red)',
              border: '1px solid color-mix(in srgb, var(--red) 30%, transparent)', borderRadius: 6, whiteSpace: 'pre-wrap', overflow: 'auto',
            }}>
              {error}
            </div>
          )}
          {result && !error && (
            <div style={{
              width: '100%', minHeight: 280, padding: 10, fontSize: 11, fontFamily: 'monospace',
              background: 'color-mix(in srgb, var(--bg) 80%, var(--green))', color: 'var(--green)',
              border: '1px solid color-mix(in srgb, var(--green) 20%, transparent)', borderRadius: 6, whiteSpace: 'pre-wrap', overflow: 'auto',
            }}>
              {result}
            </div>
          )}
          {!result && !error && (
            <div style={{
              width: '100%', minHeight: 280, padding: 10, fontSize: 11, fontFamily: 'monospace',
              background: 'color-mix(in srgb, var(--bg) 90%, var(--violet))', color: 'var(--text-faint)',
              border: '1px solid var(--border)', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              Send a webhook to see the response here
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
