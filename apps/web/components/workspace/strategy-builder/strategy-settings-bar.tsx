'use client'

import { DSLSettings, INDEX_SYMBOLS, INTERVALS, TRIGGERS } from './types'

interface Props {
  settings: DSLSettings
  onChange: (patch: Partial<DSLSettings>) => void
  disabled?: boolean
}

const LABELS: Record<string, string> = {
  symbol: 'Symbol',
  interval: 'Interval',
  trigger: 'Trigger',
  max_positions: 'Max positions',
}

function Select({ label, value, options, onChange }: {
  label: string
  value: string
  options: string[]
  onChange: (v: string) => void
}) {
  return (
    <label className="t-label" style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10, fontWeight: 700, color: 'var(--text-sub)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
      {LABELS[label] || label}
      <select className="t-select" value={value} onChange={e => onChange(e.target.value)} style={{ fontSize: 11, padding: '2px 6px' }}>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  )
}

export default function StrategySettingsBar({ settings, onChange, disabled }: Props) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10, padding: '6px 12px',
      background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)', flexShrink: 0, flexWrap: 'wrap',
    }}>
      <Select label="symbol" value={settings.symbol || 'NIFTY'} options={INDEX_SYMBOLS} onChange={v => onChange({ symbol: v })} />
      <Select label="interval" value={settings.interval || '15m'} options={INTERVALS} onChange={v => onChange({ interval: v })} />
      <Select label="trigger" value={settings.trigger || 'CANDLE_CLOSE'} options={TRIGGERS} onChange={v => onChange({ trigger: v })} />
      <Select
        label="max_positions"
        value={String(settings.max_positions ?? 1)}
        options={['1', '2', '3', '4', '5']}
        onChange={v => onChange({ max_positions: Number(v) })}
      />
      {disabled && <span className="t-chip t-chip-warn" style={{ fontSize: 9 }}>new draft — save to persist</span>}
    </div>
  )
}
