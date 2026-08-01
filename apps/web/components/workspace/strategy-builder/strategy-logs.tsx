'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'

interface LogEntry {
  id: string
  ts: string
  kind: string
  level: string
  message: string
  detail?: Record<string, unknown> | null
}

const KIND_COLOR: Record<string, string> = {
  lifecycle: 'var(--violet)',
  validation: 'var(--cyan)',
  signal: 'var(--green)',
  order: 'var(--cyan)',
  rejection: 'var(--red)',
  exit: 'var(--yellow)',
  error: 'var(--red)',
  decision: 'var(--green)',
}

export default function StrategyLogs({ strategyId }: { strategyId: string }) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.builder.logs(strategyId, 60)
      .then(d => { setLogs((d as { logs?: LogEntry[] }).logs || []); setError('') })
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load logs'))
  }, [strategyId])

  useEffect(() => {
    load()
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [load])

  if (error) return <p style={{ fontSize: 10, color: 'var(--red)' }}>{error}</p>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 220, overflowY: 'auto' }}>
      {logs.length === 0 && <p className="t-faint" style={{ fontSize: 10 }}>No activity yet.</p>}
      {logs.map(l => {
        const color = KIND_COLOR[l.kind] || 'var(--text-faint)'
        let ts = ''
        try { ts = new Date(l.ts).toLocaleTimeString() } catch { ts = '' }
        return (
          <div key={l.id} style={{ display: 'flex', gap: 8, fontSize: 10, alignItems: 'baseline' }}>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-faint)', flexShrink: 0 }}>{ts}</span>
            <span className="t-badge" style={{ fontSize: 8, background: 'transparent', border: `1px solid ${color}`, color, flexShrink: 0, padding: '0 4px' }}>
              {l.kind}
            </span>
            <span style={{ color: l.level === 'error' ? 'var(--red)' : l.level === 'warning' ? 'var(--yellow)' : 'var(--text)', flex: 1 }}>{l.message}</span>
          </div>
        )
      })}
    </div>
  )
}
