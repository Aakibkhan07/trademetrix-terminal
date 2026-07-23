'use client'

import { useState, useEffect } from 'react'

interface WhitelistIP {
  id: string
  ip_address: string
  label: string
  created_at: string
}

export function IPWhitelistTab() {
  const [ips, setIps] = useState<WhitelistIP[]>([])
  const [loading, setLoading] = useState(true)
  const [newIP, setNewIP] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [adding, setAdding] = useState(false)
  const [msg, setMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/v1/admin/ip-whitelist')
      const d = await r.json()
      setIps(d.ips || [])
    } catch {}
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const addIP = async () => {
    if (!newIP.trim()) return
    setAdding(true)
    setMsg(null)
    try {
      const r = await fetch('/api/v1/admin/ip-whitelist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip_address: newIP.trim(), label: newLabel.trim() }),
      })
      if (!r.ok) { const d = await r.json(); setMsg({ type: 'err', text: d.detail || 'Failed' }) }
      else { setNewIP(''); setNewLabel(''); load(); setMsg({ type: 'ok', text: 'IP added' }) }
    } catch { setMsg({ type: 'err', text: 'Failed' }) }
    setAdding(false)
  }

  const removeIP = async (id: string) => {
    try {
      const r = await fetch(`/api/v1/admin/ip-whitelist/${id}`, { method: 'DELETE' })
      if (!r.ok) setMsg({ type: 'err', text: 'Failed to remove' })
      else { load(); setMsg({ type: 'ok', text: 'IP removed' }) }
    } catch { setMsg({ type: 'err', text: 'Failed' }) }
  }

  const resetToAllowAll = async () => {
    if (!confirm('Remove all IPs and allow all? This disables IP restriction.')) return
    for (const ip of ips) await removeIP(ip.id)
    await addIP()
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <input className="t-input" value={newIP} onChange={e => setNewIP(e.target.value)}
          placeholder="IP address (e.g. 103.xx.xx.xx or 192.168.1.0/24)" style={{ fontSize: 11, flex: '1 1 260px', minWidth: 200 }} />
        <input className="t-input" value={newLabel} onChange={e => setNewLabel(e.target.value)}
          placeholder="Label (optional)" style={{ fontSize: 11, flex: '0 1 160px', minWidth: 120 }} />
        <button onClick={addIP} disabled={adding || !newIP.trim()}
          style={{
            padding: '5px 14px', fontSize: 11, fontWeight: 600, borderRadius: 4,
            background: newIP.trim() ? 'var(--violet)' : 'var(--bg)', color: newIP.trim() ? '#fff' : 'var(--text-faint)',
            border: 'none', cursor: adding ? 'wait' : newIP.trim() ? 'pointer' : 'not-allowed',
          }}>
          {adding ? 'Adding...' : 'Add IP'}
        </button>
        <button onClick={load} className="t-btn t-btn-sm" style={{ fontSize: 10 }}>Refresh</button>
      </div>

      {msg && (
        <div style={{
          padding: '6px 12px', marginBottom: 10, borderRadius: 4, fontSize: 10,
          background: msg.type === 'ok' ? 'color-mix(in srgb, var(--green) 10%, var(--bg))' : 'color-mix(in srgb, var(--red) 10%, var(--bg))',
          border: `1px solid color-mix(in srgb, ${msg.type === 'ok' ? 'var(--green)' : 'var(--red)'} 20%, transparent)`,
          color: msg.type === 'ok' ? 'var(--green)' : 'var(--red)',
        }}>{msg.text}</div>
      )}

      {loading && <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}><p style={{ fontSize: 12, color: 'var(--text-faint)' }}>Loading...</p></div>}
      {!loading && ips.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No IPs whitelisted. Everyone can access admin.</p>
        </div>
      )}

      {!loading && ips.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>IP ADDRESS</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>LABEL</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>ADDED</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {ips.map(ip => (
                <tr key={ip.id} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                  <td style={{ padding: '6px 8px', fontFamily: 'monospace', color: ip.ip_address === '*' ? 'var(--amber)' : 'var(--text)' }}>
                    {ip.ip_address}
                    {ip.ip_address === '*' && <span style={{ fontSize: 8, color: 'var(--text-faint)', marginLeft: 6 }}>(allow all)</span>}
                  </td>
                  <td style={{ padding: '6px 8px', fontSize: 9, color: 'var(--text-sub)' }}>{ip.label || '—'}</td>
                  <td style={{ padding: '6px 8px', fontSize: 9, color: 'var(--text-faint)' }}>
                    {ip.created_at ? new Date(ip.created_at).toLocaleString() : '—'}
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    <button onClick={() => removeIP(ip.id)}
                      style={{
                        padding: '2px 8px', fontSize: 8, borderRadius: 3, border: 'none', cursor: 'pointer',
                        background: 'color-mix(in srgb, var(--red) 12%, transparent)', color: 'var(--red)',
                      }}>
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
