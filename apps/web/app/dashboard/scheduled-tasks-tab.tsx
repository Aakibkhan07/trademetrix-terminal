'use client'

import { useState, useEffect } from 'react'

interface SquareoffConfig {
  user_id: string
  email: string
  full_name: string
  enabled: boolean
  time: string
  days: number[]
}

interface SchedulerSummary {
  scheduler_running: boolean
  active_squareoff_configs: number
  squareoff_configs: SquareoffConfig[]
}

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function ScheduledTasksTab() {
  const [data, setData] = useState<SchedulerSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  const [sqOffUser, setSqOffUser] = useState('')
  const [sqOffRunning, setSqOffRunning] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/v1/admin/scheduled-tasks')
      if (r.ok) setData(await r.json())
    } catch {}
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const runSquareoff = async () => {
    if (!sqOffUser) return
    setSqOffRunning(true)
    setMsg(null)
    try {
      const r = await fetch(`/api/v1/admin/squareoff/run/${sqOffUser}`, { method: 'POST' })
      const d = await r.json()
      setMsg({ type: r.ok ? 'ok' : 'err', text: r.ok ? `Square-off triggered for ${d.result?.message || d.user_id}` : d.detail || 'Failed' })
    } catch { setMsg({ type: 'err', text: 'Failed' }) }
    setSqOffRunning(false)
  }

  const daysStr = (days: number[]) => days.map(d => DAY_LABELS[d] || d).join(', ')

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <div className="t-panel" style={{ flex: '1 1 160px', padding: '10px 14px', minWidth: 120 }}>
          <p style={{ margin: 0, fontSize: 9, color: 'var(--text-faint)', textTransform: 'uppercase' }}>Scheduler</p>
          <p style={{ margin: '4px 0 0', fontSize: 14, fontWeight: 700, color: data?.scheduler_running ? 'var(--green)' : 'var(--red)' }}>
            {data?.scheduler_running ? 'Running' : 'Stopped'}
          </p>
        </div>
        <div className="t-panel" style={{ flex: '1 1 160px', padding: '10px 14px', minWidth: 120 }}>
          <p style={{ margin: 0, fontSize: 9, color: 'var(--text-faint)', textTransform: 'uppercase' }}>Active Square-Off</p>
          <p style={{ margin: '4px 0 0', fontSize: 14, fontWeight: 700 }}>{data?.active_squareoff_configs ?? '—'}</p>
        </div>
      </div>

      {msg && (
        <div style={{
          padding: '6px 12px', marginBottom: 10, borderRadius: 4, fontSize: 10,
          background: msg.type === 'ok' ? 'color-mix(in srgb, var(--green) 10%, var(--bg))' : 'color-mix(in srgb, var(--red) 10%, var(--bg))',
          border: `1px solid color-mix(in srgb, ${msg.type === 'ok' ? 'var(--green)' : 'var(--red)'} 20%, transparent)`,
          color: msg.type === 'ok' ? 'var(--green)' : 'var(--red)',
        }}>{msg.text}</div>
      )}

      <div className="t-panel" style={{ padding: 14, marginBottom: 16 }}>
        <h3 style={{ margin: '0 0 8px', fontSize: 13, fontWeight: 600 }}>Trigger Square-Off</h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input className="t-input" value={sqOffUser} onChange={e => setSqOffUser(e.target.value)}
            placeholder="User ID" style={{ fontSize: 11, flex: '1 1 280px', minWidth: 200 }} />
          <button onClick={runSquareoff} disabled={sqOffRunning || !sqOffUser}
            style={{
              padding: '5px 14px', fontSize: 11, fontWeight: 600, borderRadius: 4,
              background: sqOffUser ? 'var(--amber)' : 'var(--bg)', color: sqOffUser ? '#000' : 'var(--text-faint)',
              border: 'none', cursor: sqOffRunning ? 'wait' : sqOffUser ? 'pointer' : 'not-allowed',
            }}>
            {sqOffRunning ? 'Running...' : 'Run Square-Off'}
          </button>
        </div>
      </div>

      {loading && <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}><p style={{ fontSize: 12, color: 'var(--text-faint)' }}>Loading...</p></div>}
      {!loading && data?.squareoff_configs && data.squareoff_configs.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>USER</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>ENABLED</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>TIME</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>DAYS</th>
              </tr>
            </thead>
            <tbody>
              {data.squareoff_configs.map(c => (
                <tr key={c.user_id} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                  <td style={{ padding: '6px 8px' }}>
                    <div style={{ fontWeight: 600, color: 'var(--text)', fontSize: 10 }}>{c.full_name || '—'}</div>
                    <div style={{ fontSize: 8, color: 'var(--text-faint)', fontFamily: 'monospace' }}>{c.email}</div>
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: c.enabled ? 'var(--green)' : 'var(--text-faint)' }} />
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center', fontFamily: 'monospace', fontSize: 10 }}>{c.time}</td>
                  <td style={{ padding: '6px 8px', fontSize: 9, color: 'var(--text-sub)' }}>{daysStr(c.days)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
