'use client'

import { useState } from 'react'
import { loadPresets, savePreset, deletePreset } from '@/lib/trader-presets'
import type { TraderPreset } from '@/lib/trader-presets'
import type { IndexKey, Moneyness } from '@/lib/options-contracts'

/** Saved presets: one click restores a full trade setup. LocalStorage only. */
export function PresetsBar({ current, onApply }: {
  current: { name: string; index: IndexKey; moneyness: Moneyness; customStrike: number | null; optionType: 'CE' | 'PE'; lots: number; orderType: 'MARKET' | 'LIMIT' }
  onApply: (p: TraderPreset) => void
}) {
  const [presets, setPresets] = useState<TraderPreset[]>(() => loadPresets())
  const [name, setName] = useState('')

  const save = () => {
    if (!name.trim()) return
    setPresets(savePreset({ ...current, name: name.trim() }))
    setName('')
  }

  return (
    <div className="t-panel" style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <span className="t-faint" style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em' }}>PRESETS</span>
      {presets.length === 0 && <span className="t-faint" style={{ fontSize: 10 }}>None yet — save one below</span>}
      {presets.map(p => (
        <button key={p.id} type="button" className="t-chip" style={{ fontSize: 10, display: 'flex', alignItems: 'center', gap: 4 }} onClick={() => onApply(p)}>
          {p.name}
          <span
            role="button"
            tabIndex={0}
            style={{ color: 'var(--text-faint)', cursor: 'pointer', paddingLeft: 4 }}
            onClick={e => { e.stopPropagation(); setPresets(deletePreset(p.id)) }}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); setPresets(deletePreset(p.id)) } }}
          >
            ✕
          </span>
        </button>
      ))}
      <span style={{ flex: 1 }} />
      <input
        value={name}
        onChange={e => setName(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') save() }}
        placeholder="Name this setup…"
        style={{ width: 130, fontSize: 10, padding: '3px 8px', background: 'var(--bg)', border: '1px solid color-mix(in srgb, var(--text-inverse) 15%, transparent)', borderRadius: 6, color: 'var(--text)' }}
      />
      <button type="button" className="t-btn t-btn-sm" onClick={save} disabled={!name.trim()}>Save setup</button>
    </div>
  )
}