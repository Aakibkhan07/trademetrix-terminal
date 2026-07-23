'use client'

import { useState, useEffect } from 'react'

interface BackupEntry {
  filename: string
  size_bytes: number
  created_at: string
  total_rows: number
  tables: Record<string, number>
  error?: string
}

export function BackupsTab() {
  const [backups, setBackups] = useState<BackupEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [restoring, setRestoring] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/v1/admin/backups')
      const d = await r.json()
      setBackups(d.backups || [])
    } catch { setMsg({ type: 'err', text: 'Failed to load backups' }) }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const runBackup = async () => {
    setRunning(true)
    setMsg(null)
    try {
      const r = await fetch('/api/v1/admin/backups/run', { method: 'POST' })
      const d = await r.json()
      if (!r.ok) setMsg({ type: 'err', text: d.detail || 'Backup failed' })
      else { setMsg({ type: 'ok', text: `Backup created: ${d.filename} (${d.total_rows} rows)` }); load() }
    } catch { setMsg({ type: 'err', text: 'Backup failed' }) }
    setRunning(false)
  }

  const restore = async (filename: string) => {
    if (!confirm(`Restore from ${filename}? This will overwrite existing data.`)) return
    setRestoring(filename)
    setMsg(null)
    try {
      const r = await fetch(`/api/v1/admin/backups/restore/${encodeURIComponent(filename)}`, { method: 'POST' })
      const d = await r.json()
      if (!r.ok) setMsg({ type: 'err', text: d.detail || 'Restore failed' })
      else setMsg({ type: 'ok', text: `Restored ${d.total_rows} rows from ${filename}` })
    } catch { setMsg({ type: 'err', text: 'Restore failed' }) }
    setRestoring(null)
  }

  const deleteBackup = async (filename: string) => {
    if (!confirm(`Delete ${filename}?`)) return
    try {
      const r = await fetch(`/api/v1/admin/backups/${encodeURIComponent(filename)}`, { method: 'DELETE' })
      if (!r.ok) setMsg({ type: 'err', text: 'Delete failed' })
      else { setMsg({ type: 'ok', text: `Deleted ${filename}` }); load() }
    } catch { setMsg({ type: 'err', text: 'Delete failed' }) }
  }

  const fmtSize = (bytes: number) =>
    bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <button onClick={runBackup} disabled={running}
          style={{
            padding: '6px 16px', fontSize: 11, fontWeight: 600, borderRadius: 5, cursor: running ? 'wait' : 'pointer',
            background: running ? 'var(--bg)' : 'var(--violet)', color: running ? 'var(--text-faint)' : '#fff',
            border: running ? '1px solid var(--border)' : 'none',
          }}>
          {running ? 'Running...' : 'Run Backup Now'}
        </button>
        <button onClick={load} className="t-btn t-btn-sm" style={{ fontSize: 10 }}>Refresh</button>
        <span style={{ fontSize: 10, color: 'var(--text-sub)' }}>{backups.length} backups</span>
      </div>

      {msg && (
        <div style={{
          padding: '8px 12px', marginBottom: 12, borderRadius: 5, fontSize: 11,
          background: msg.type === 'ok' ? 'color-mix(in srgb, var(--green) 10%, var(--bg))' : 'color-mix(in srgb, var(--red) 10%, var(--bg))',
          border: `1px solid color-mix(in srgb, ${msg.type === 'ok' ? 'var(--green)' : 'var(--red)'} 20%, transparent)`,
          color: msg.type === 'ok' ? 'var(--green)' : 'var(--red)',
        }}>{msg.text}</div>
      )}

      {loading && <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}><p style={{ fontSize: 12, color: 'var(--text-faint)' }}>Loading...</p></div>}
      {!loading && backups.length === 0 && (
        <div className="t-panel" style={{ padding: 16, textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-faint)' }}>No backups found. Run your first backup!</p>
        </div>
      )}

      {!loading && backups.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 12%, transparent)' }}>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>FILENAME</th>
                <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>SIZE</th>
                <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>ROWS</th>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>CREATED</th>
                <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, color: 'var(--text-sub)', fontSize: 8 }}>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {backups.map(b => (
                <tr key={b.filename} style={{ borderBottom: '1px solid color-mix(in srgb, var(--violet) 6%, transparent)' }}>
                  <td style={{ padding: '6px 8px', fontFamily: 'monospace', fontSize: 9, color: 'var(--text)' }}>{b.filename}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', fontSize: 9, color: 'var(--text-sub)' }}>{b.error ? '—' : fmtSize(b.size_bytes)}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', fontSize: 9, color: 'var(--text-sub)' }}>{b.error ? '—' : b.total_rows}</td>
                  <td style={{ padding: '6px 8px', fontSize: 9, color: 'var(--text-faint)' }}>
                    {b.created_at ? new Date(b.created_at).toLocaleString() : b.error || '—'}
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                      <button onClick={() => restore(b.filename)} disabled={restoring === b.filename || !!b.error}
                        style={{
                          padding: '2px 8px', fontSize: 8, borderRadius: 3, border: 'none', cursor: restoring === b.filename ? 'wait' : 'pointer',
                          background: b.error ? 'var(--bg)' : 'color-mix(in srgb, var(--amber) 12%, transparent)', color: b.error ? 'var(--text-faint)' : 'var(--amber)',
                        }}>
                        {restoring === b.filename ? '...' : 'Restore'}
                      </button>
                      <button onClick={() => deleteBackup(b.filename)} disabled={!!b.error}
                        style={{
                          padding: '2px 8px', fontSize: 8, borderRadius: 3, border: 'none', cursor: 'pointer',
                          background: b.error ? 'var(--bg)' : 'color-mix(in srgb, var(--red) 12%, transparent)', color: b.error ? 'var(--text-faint)' : 'var(--red)',
                        }}>
                        Delete
                      </button>
                    </div>
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
