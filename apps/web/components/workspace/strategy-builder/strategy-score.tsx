'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

interface ScoreShape {
  overall: number
  quality: number
  risk: number
  complexity: number
  readability: number
  readiness: number
  grade: string
  breakdown?: { metric: string; label?: string; value: number; detail?: string }[]
}

function gradeColor(grade: string): string {
  if (grade === 'A' || grade === 'A+') return 'var(--green)'
  if (grade === 'B' || grade === 'B+') return 'var(--cyan)'
  if (grade === 'C' || grade === 'C+') return 'var(--yellow)'
  return 'var(--red)'
}

function Bar({ label, value, invert, grade }: { label: string; value: number; invert?: boolean; grade?: string }) {
  const pct = Math.max(0, Math.min(100, value))
  const color = grade ? gradeColor(grade)
    : invert ? (pct > 60 ? 'var(--red)' : pct > 30 ? 'var(--yellow)' : 'var(--green)')
    : (pct >= 70 ? 'var(--green)' : pct >= 40 ? 'var(--yellow)' : 'var(--red)')
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 2 }}>
        <span className="t-faint">{label}</span>
        <span style={{ color, fontWeight: 700 }}>{Math.round(pct)}</span>
      </div>
      <div style={{ height: 4, borderRadius: 2, background: 'var(--bg-tertiary)', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2 }} />
      </div>
    </div>
  )
}

export default function StrategyScore({ strategyId, onScore }: { strategyId: string; onScore?: (s: ScoreShape) => void }) {
  const [score, setScore] = useState<ScoreShape | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.builder.score(strategyId)
      .then(d => {
        const s = (d as { score?: ScoreShape }).score
        if (s) { setScore(s); onScore?.(s) }
        setError('')
      })
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load score'))
  }, [strategyId, onScore])

  if (error) return <p style={{ fontSize: 10, color: 'var(--red)' }}>{error}</p>
  if (!score) return <p className="t-faint" style={{ fontSize: 10 }}>Loading score…</p>

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
      <div style={{ width: 44, height: 44, borderRadius: '50%', border: `3px solid ${gradeColor(score.grade)}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <span style={{ fontSize: 16, fontWeight: 800, color: gradeColor(score.grade) }}>{score.grade}</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5, flex: 1 }}>
        <Bar label="Quality" value={score.quality} />
        <Bar label="Readiness" value={score.readiness} />
        <Bar label="Risk (lower better)" value={score.risk} invert />
        <Bar label="Complexity (lower better)" value={score.complexity} invert />
        <Bar label="Readability" value={score.readability} />
      </div>
    </div>
  )
}
