'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { TemplateInfo } from './types'

interface Props {
  onUse: (template: string) => void
  onBlank: () => void
  onAI: () => void
}

export default function TemplateGallery({ onUse, onBlank, onAI }: Props) {
  const [templates, setTemplates] = useState<TemplateInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.builder.templates()
      .then(d => setTemplates((d as { templates?: TemplateInfo[] })?.templates || (d as TemplateInfo[] || [])))
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load templates'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span className="t-stat-label" style={{ fontSize: 10, fontWeight: 700 }}>START FROM TEMPLATE</span>
        <span className="t-faint" style={{ fontSize: 10 }}>10 battle-tested starting points</span>
      </div>
      {error && <span style={{ color: 'var(--text-red)', fontSize: 11 }}>{error}</span>}
      {loading ? (
        <span className="t-faint" style={{ fontSize: 11 }}>Loading templates…</span>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: 8 }}>
          {templates.map(t => (
            <button
              key={t.key}
              className="t-btn t-btn-ghost"
              onClick={() => onUse(t.key)}
              style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 3, textAlign: 'left', padding: 10, height: 'auto', fontSize: 11 }}
            >
              <span style={{ fontWeight: 700, color: 'var(--text)' }}>{t.name}</span>
              <span className="t-faint" style={{ fontSize: 9, lineHeight: 1.35 }}>{t.description}</span>
              <span className="t-chip" style={{ fontSize: 8, marginTop: 3 }}>{t.node_count} blocks</span>
            </button>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
        <button className="t-btn t-btn-sm" onClick={onBlank}>Blank canvas</button>
        <button className="t-btn t-btn-sm t-btn-primary" onClick={onAI}>✨ Describe in plain English</button>
      </div>
    </div>
  )
}
