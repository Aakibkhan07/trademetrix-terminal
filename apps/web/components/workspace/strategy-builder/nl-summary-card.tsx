'use client'

import { ValidationIssue } from './types'

interface Props {
  lines: string[]
  valid: boolean
  issues: string[]
  serverIssues?: ValidationIssue[]
}

export default function NLSummaryCard({ lines, valid, issues, serverIssues }: Props) {
  return (
    <div style={{
      padding: 10, borderRadius: 'var(--radius-md)', border: '1px solid var(--border-hi)',
      background: 'var(--panel)', flexShrink: 0, maxHeight: 150, overflowY: 'auto',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span className="t-stat-label" style={{ fontSize: 9, fontWeight: 700 }}>YOUR STRATEGY — PLAIN ENGLISH</span>
        <span className={`t-badge ${valid ? 't-badge-green' : 't-badge-red'}`} style={{ fontSize: 9 }}>
          {valid ? '✓ VALID' : 'NEEDS ATTENTION'}
        </span>
      </div>
      {lines.map((l, i) => (
        <div key={i} style={{ fontSize: 11, color: 'var(--text-sub)', lineHeight: 1.5 }}>{l}</div>
      ))}
      {issues.map((iss, i) => (
        <div key={`i-${i}`} style={{ fontSize: 11, color: 'var(--text-red)', lineHeight: 1.4 }}>⚠ {iss}</div>
      ))}
      {(serverIssues || []).filter(iss => iss.severity === 'error').map((iss, i) => (
        <div key={`s-${i}`} style={{ fontSize: 11, color: 'var(--text-red)', lineHeight: 1.4 }}>⚠ {iss.message}</div>
      ))}
    </div>
  )
}
