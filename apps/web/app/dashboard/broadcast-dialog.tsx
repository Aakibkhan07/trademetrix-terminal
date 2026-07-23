'use client'

import { useState } from 'react'
import { api } from '@/lib/api'

interface BroadcastDialogProps {
  onClose: () => void
}

export function BroadcastDialog({ onClose }: BroadcastDialogProps) {
  const [title, setTitle] = useState('')
  const [message, setMessage] = useState('')
  const [type, setType] = useState<'email' | 'sms' | 'both'>('email')
  const [sendToAll, setSendToAll] = useState(true)
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<{ success: number; failed: number; total: number } | null>(null)
  const [error, setError] = useState('')

  const handleSend = async () => {
    if (!title.trim() || !message.trim()) return
    setSending(true)
    setError('')
    setResult(null)
    try {
      const res = await api.admin.broadcastNotify({ title, message, type, user_ids: sendToAll ? undefined : [] })
      setResult({ success: res.success, failed: res.failed, total: res.total })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to send')
    } finally {
      setSending(false)
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
    }} onClick={onClose}>
      <div className="t-panel" style={{
        width: 500, maxWidth: '90vw', maxHeight: '85vh', overflowY: 'auto',
        padding: 20,
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Broadcast Notification</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-sub)', cursor: 'pointer', fontSize: 16 }}>✕</button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label className="t-label" style={{ fontSize: 10, marginBottom: 4, display: 'block' }}>Title</label>
            <input className="t-input" value={title} onChange={e => setTitle(e.target.value)}
              placeholder="e.g. System Maintenance Tonight" style={{ width: '100%', fontSize: 12 }} />
          </div>

          <div>
            <label className="t-label" style={{ fontSize: 10, marginBottom: 4, display: 'block' }}>Message</label>
            <textarea className="t-input" value={message} onChange={e => setMessage(e.target.value)}
              placeholder="Type your message here..."
              rows={5} style={{ width: '100%', fontSize: 12, resize: 'vertical', fontFamily: 'inherit' }} />
            <div style={{ fontSize: 9, color: 'var(--text-faint)', marginTop: 2 }}>{message.length} chars</div>
          </div>

          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <div>
              <label className="t-label" style={{ fontSize: 10, marginBottom: 4, display: 'block' }}>Channel</label>
              <select className="t-input" value={type} onChange={e => setType(e.target.value as any)}
                style={{ fontSize: 11 }}>
                <option value="email">Email</option>
                <option value="sms">SMS</option>
                <option value="both">Email + SMS</option>
              </select>
            </div>
            <div>
              <label className="t-label" style={{ fontSize: 10, marginBottom: 4, display: 'block' }}>Recipients</label>
              <select className="t-input" value={sendToAll ? 'all' : 'selected'} onChange={e => setSendToAll(e.target.value === 'all')}
                style={{ fontSize: 11 }}>
                <option value="all">All users</option>
                <option value="selected">Selected users</option>
              </select>
            </div>
          </div>

          {error && (
            <div style={{ padding: 8, background: 'color-mix(in srgb, var(--red) 10%, transparent)', borderRadius: 6, fontSize: 11, color: 'var(--red)' }}>
              {error}
            </div>
          )}

          {result && (
            <div style={{
              padding: 12, borderRadius: 6, fontSize: 11,
              background: result.failed === 0
                ? 'color-mix(in srgb, var(--green) 10%, transparent)'
                : 'color-mix(in srgb, var(--amber) 10%, transparent)',
              color: result.failed === 0 ? 'var(--green)' : 'var(--amber)',
            }}>
              Sent to {result.success}/{result.total} users{result.failed > 0 ? ` (${result.failed} failed)` : ''}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
            <button className="t-btn t-btn-sm" onClick={onClose} style={{ fontSize: 10 }}>Cancel</button>
            <button className="t-btn t-btn-sm" onClick={handleSend} disabled={sending || !title.trim() || !message.trim()}
              style={{
                fontSize: 10,
                background: 'color-mix(in srgb, var(--violet) 15%, transparent)',
                border: '1px solid color-mix(in srgb, var(--violet) 20%, transparent)',
                color: 'var(--violet)',
              }}>
              {sending ? 'Sending...' : `Send to ${sendToAll ? 'All Users' : 'Selected'}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
