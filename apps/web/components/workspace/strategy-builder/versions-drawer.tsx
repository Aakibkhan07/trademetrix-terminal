'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'

interface VersionEntry {
  version: number
  saved_at: string
  data?: Record<string, unknown>
}

interface CompareDiff {
  field: string
  kind: 'added' | 'removed' | 'changed'
  node_id?: string
  block_type?: string
  param?: string
  edge?: [string, string, string, string]
  from?: unknown
  to?: unknown
}

export default function VersionsDrawer({
  strategyId,
  onClose,
  onRestored,
}: {
  strategyId: string
  onClose: () => void
  onRestored: () => void
}) {
  const [versions, setVersions] = useState<VersionEntry[]>([])
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [fromV, setFromV] = useState<number | null>(null)
  const [toV, setToV] = useState<number | null>(null)
  const [diff, setDiff] = useState<CompareDiff[] | null>(null)
  const [diffSummary, setDiffSummary] = useState<{ added: number; removed: number; changed: number } | null>(null)

  const load = useCallback(() => {
    setBusy('Loading…')
    api.builder.versions(strategyId)
      .then(d => {
        const list = (d as { versions?: VersionEntry[] }).versions || []
        setVersions(list)
        if (list.length >= 2 && fromV === null) {
          setFromV(list[list.length - 2].version)
          setToV(list[list.length - 1].version)
        }
        setError('')
      })
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load versions'))
      .finally(() => setBusy(''))
  }, [strategyId, fromV])

  useEffect(() => { load() }, [load])

  const compare = useCallback(() => {
    if (fromV === null || toV === null || fromV === toV) return
    setBusy('Comparing…')
    api.builder.compare(strategyId, fromV, toV)
      .then(d => {
        setDiff((d as { changes?: CompareDiff[] }).changes || [])
        setDiffSummary((d as { summary?: { added: number; removed: number; changed: number } }).summary || null)
        setError('')
      })
      .catch(e => setError(e instanceof Error ? e.message : 'Compare failed'))
      .finally(() => setBusy(''))
  }, [strategyId, fromV, toV])

  const restore = useCallback(async (version: number) => {
    if (!confirm(`Restore version v${version}? Current state is saved as a new version.`)) return
    setBusy(`Restoring v${version}…`)
    try {
      await api.builder.rollback(strategyId, version)
      setError('')
      onRestored()
      setVersions([])
      setDiff(null)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Restore failed')
    } finally {
      setBusy('')
    }
  }, [strategyId, onRestored, load])

  const fmt = (ts: string) => {
    try { return new Date(ts).toLocaleString() } catch { return ts }
  }

  const val = (v: unknown) => {
    if (typeof v === 'string' && v.length > 28) return v.slice(0, 28) + '…'
    return String(v ?? '—')
  }

  return (
    <div className="t-modal-overlay" onClick={onClose}>
      <div className="t-modal" style={{ maxWidth: 620, padding: 0 }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>Versions & History</span>
          <button className="t-btn t-btn-sm" onClick={onClose}>✕</button>
        </div>

        <div style={{ padding: 14, maxHeight: '60vh', overflowY: 'auto' }}>
          {busy && <p className="t-faint" style={{ fontSize: 11 }}>{busy}</p>}
          {error && <p style={{ margin: '0 0 10px', fontSize: 11, color: 'var(--red)' }}>{error}</p>}

          {versions.length === 0 && !busy && (
            <p className="t-faint" style={{ fontSize: 12 }}>No versions yet — versions are snapshotted on every save.</p>
          )}

          {versions.length > 0 && (
            <>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
                <select className="t-select" value={fromV ?? ''} onChange={e => setFromV(Number(e.target.value))} style={{ fontSize: 11 }}>
                  {versions.slice(0, -1).map(v => <option key={v.version} value={v.version}>v{v.version} → {fmt(v.saved_at)}</option>)}
                </select>
                <span className="t-faint" style={{ fontSize: 11 }}>vs</span>
                <select className="t-select" value={toV ?? ''} onChange={e => setToV(Number(e.target.value))} style={{ fontSize: 11 }}>
                  {versions.map(v => <option key={v.version} value={v.version}>v{v.version} → {fmt(v.saved_at)}</option>)}
                </select>
                <button className="t-btn t-btn-sm" onClick={compare} disabled={fromV === null || toV === null || fromV === toV}>Compare</button>
              </div>

              {diffSummary && (
                <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
                  <span className="t-badge t-badge-green" style={{ fontSize: 9 }}>+{diffSummary.added} added</span>
                  <span className="t-badge t-badge-sub" style={{ fontSize: 9 }}>−{diffSummary.removed} removed</span>
                  <span className="t-badge t-badge-cyan" style={{ fontSize: 9 }}>~{diffSummary.changed} changed</span>
                </div>
              )}

              {diff && diff.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 14 }}>
                  {diff.map((c, i) => (
                    <div key={i} style={{
                      fontSize: 11, padding: '5px 8px', borderRadius: 6, fontFamily: 'var(--font-mono)',
                      background: c.kind === 'added' ? 'color-mix(in srgb, var(--green) 8%, transparent)'
                        : c.kind === 'removed' ? 'color-mix(in srgb, var(--red) 8%, transparent)'
                        : 'color-mix(in srgb, var(--cyan) 8%, transparent)',
                      border: `1px solid color-mix(in srgb, ${c.kind === 'added' ? 'var(--green)' : c.kind === 'removed' ? 'var(--red)' : 'var(--cyan)'} 20%, transparent)`,
                      color: c.kind === 'added' ? 'var(--green)' : c.kind === 'removed' ? 'var(--red)' : 'var(--cyan)',
                    }}>
                      {c.kind === 'added' && `+ added ${c.block_type || c.field}${c.node_id ? ` (${c.node_id.slice(0, 6)})` : ''}${c.edge ? ` edge ${c.edge.join(' → ')}` : ''}`}
                      {c.kind === 'removed' && `− removed ${c.block_type || c.field}${c.node_id ? ` (${c.node_id.slice(0, 6)})` : ''}${c.edge ? ` edge ${c.edge.join(' → ')}` : ''}`}
                      {c.kind === 'changed' && `~ ${c.field}${c.param ? `: ${c.param}` : ''}${c.node_id ? ` (${c.block_type} ${c.node_id.slice(0, 6)})` : ''} ${val(c.from)} → ${val(c.to)}`}
                    </div>
                  ))}
                </div>
              )}

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {[...versions].reverse().map(v => (
                  <div key={v.version} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 6, background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
                    <span className="t-badge t-badge-cyan" style={{ fontSize: 9 }}>v{v.version}</span>
                    <span className="t-faint" style={{ fontSize: 10, flex: 1 }}>{fmt(v.saved_at)}</span>
                    <button className="t-btn t-btn-sm" onClick={() => restore(v.version)} style={{ fontSize: 10 }}>Restore</button>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
