'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { api, ApiError } from '@/lib/api'
import { useToast } from '@/lib/use-toast'
import { EmptyState } from '@/components/empty-state'
import { ErrorMessage } from '@/components/error-message'
import { SkeletonCard, SkeletonTable } from '@/components/skeleton'

/* ═══════════════════════════════════════
   Types
   ═══════════════════════════════════════ */

type ViewMode = 'list' | 'create' | 'edit'

interface Strategy {
  id: string
  user_id: string
  name: string
  status: 'draft' | 'active' | 'paused'
  strategy_type: 'intraday' | 'positional'
  index_symbol: string
  underlying_from: 'cash' | 'futures'
  entry_time: string
  exit_time: string
  days_of_week: number[]
  overall_sl_type: string | null
  overall_sl_value: number | null
  overall_target_type: string | null
  overall_target_value: number | null
  legs: StrategyLeg[]
  created_at?: string
  updated_at?: string
}

interface StrategyLeg {
  id?: string
  strategy_id?: string
  leg_order: number
  segment: 'options' | 'futures'
  position: 'buy' | 'sell'
  option_type: 'CE' | 'PE' | null
  lots: number
  expiry: 'weekly' | 'next_weekly' | 'monthly'
  strike_criteria: 'atm_offset' | 'premium_closest' | 'premium_range' | 'delta'
  strike_value: number
  leg_sl_type: string | null
  leg_sl_value: number | null
  leg_target_type: string | null
  leg_target_value: number | null
  trailing_sl_type: string | null
  trailing_sl_value: number | null
  trailing_activation: number | null
  reentry_mode: 'RE_ASAP' | 'RE_COST' | null
  max_reentries: number
}

interface OptionChain {
  symbol: string
  spot_price: number
  expiry: string
  strikes: Strike[]
  is_simulated?: boolean
}

interface Strike {
  strike: number
  CE: { ltp: number; delta: number }
  PE: { ltp: number; delta: number }
}

interface FormErrors {
  [key: string]: string
}

/* ═══════════════════════════════════════
   Constants
   ═══════════════════════════════════════ */

const INDEX_SYMBOLS = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX']
const EXPIRY_OPTIONS: { value: string; label: string }[] = [
  { value: 'weekly', label: 'Weekly' },
  { value: 'next_weekly', label: 'Next Weekly' },
  { value: 'monthly', label: 'Monthly' },
]
const STRIKE_CRITERIA_OPTIONS: { value: string; label: string }[] = [
  { value: 'atm_offset', label: 'ATM Offset' },
  { value: 'premium_closest', label: 'Premium Closest' },
  { value: 'premium_range', label: 'Premium Range' },
  { value: 'delta', label: 'Delta' },
]
const SL_TARGET_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'None' },
  { value: 'percent', label: '%' },
  { value: 'points', label: 'Points' },
  { value: 'premium', label: 'Premium' },
]
const STATUS_CHIP: Record<string, string> = {
  draft: 't-badge-sub',
  active: 't-badge-green',
  paused: 't-badge-amber',
}
const STATUS_LABEL: Record<string, string> = {
  draft: 'DRAFT',
  active: 'ACTIVE-PAPER',
  paused: 'PAUSED',
}
const MAX_LOTS = 10
const MAX_LEGS = 6
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

let _legId = 0
function newLegId() { return `leg_${++_legId}_${Date.now()}` }

function freshLeg(leg_order: number): StrategyLeg {
  return {
    id: newLegId(),
    leg_order,
    segment: 'options',
    position: 'buy',
    option_type: 'CE',
    lots: 1,
    expiry: 'weekly',
    strike_criteria: 'atm_offset',
    strike_value: 0,
    leg_sl_type: null,
    leg_sl_value: null,
    leg_target_type: null,
    leg_target_value: null,
    trailing_sl_type: null,
    trailing_sl_value: null,
    trailing_activation: null,
    reentry_mode: null,
    max_reentries: 3,
  }
}

interface BuilderForm {
  name: string
  strategy_type: 'intraday' | 'positional'
  index_symbol: string
  underlying_from: 'cash' | 'futures'
  entry_time: string
  exit_time: string
  days_of_week: number[]
  overall_sl_type: string | null
  overall_sl_value: number | null
  overall_target_type: string | null
  overall_target_value: number | null
}

const DEFAULT_FORM: BuilderForm = {
  name: '',
  strategy_type: 'intraday',
  index_symbol: 'NIFTY',
  underlying_from: 'cash',
  entry_time: '09:15',
  exit_time: '15:15',
  days_of_week: [1, 2, 3, 4, 5],
  overall_sl_type: null,
  overall_sl_value: null,
  overall_target_type: null,
  overall_target_value: null,
}

/* ═══════════════════════════════════════
   Helpers
   ═══════════════════════════════════════ */

function fmtNum(n: number) { return n.toLocaleString('en-IN', { maximumFractionDigits: 2 }) }

/* ═══════════════════════════════════════
   ConfirmDialog
   ═══════════════════════════════════════ */

function ConfirmDialog({
  title, message, confirmLabel, confirmClass, onConfirm, onCancel, loading,
}: {
  title: string; message: string; confirmLabel?: string; confirmClass?: string
  onConfirm: () => void; onCancel: () => void; loading?: boolean
}) {
  return (
    <div className="t-modal-overlay" onClick={onCancel}>
      <div className="t-modal" onClick={e => e.stopPropagation()}
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-hi)', borderRadius: 'var(--radius-lg)', padding: 20, maxWidth: 420, width: '90%', boxShadow: '0 8px 40px rgba(0,0,0,0.5)' }}>
        <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 700, margin: '0 0 12px' }}>{title}</h3>
        <p style={{ fontSize: 12, color: 'var(--text-sub)', margin: '0 0 20px', lineHeight: 1.5 }}>{message}</p>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button className="t-btn" onClick={onCancel} disabled={loading}>Cancel</button>
          <button className={confirmClass || 't-btn t-btn-danger'} onClick={onConfirm} disabled={loading}>
            {loading ? 'Processing...' : confirmLabel || 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════
   StepperInput
   ═══════════════════════════════════════ */

function StepperInput({
  value, onChange, min = 1, max = MAX_LOTS, step = 1, disabled, compact,
}: {
  value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number
  disabled?: boolean; compact?: boolean
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
      <button className="t-btn t-btn-xs" style={{ borderRadius: 'var(--radius-sm) 0 0 var(--radius-sm)', height: compact ? 22 : 26, padding: '0 6px' }}
        onClick={() => onChange(Math.max(min, value - step))} disabled={disabled || value <= min}>-</button>
      <input type="number" value={value}
        onChange={e => { const v = parseInt(e.target.value) || min; onChange(Math.min(max, Math.max(min, v))) }}
        style={{ width: compact ? 28 : 36, textAlign: 'center', height: compact ? 22 : 26, padding: 0, border: '1px solid var(--border)', borderLeft: 'none', borderRight: 'none', background: 'var(--bg-tertiary)', color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: compact ? 10 : 11, outline: 'none' }}
        disabled={disabled} min={min} max={max} />
      <button className="t-btn t-btn-xs" style={{ borderRadius: '0 var(--radius-sm) var(--radius-sm) 0', height: compact ? 22 : 26, padding: '0 6px' }}
        onClick={() => onChange(Math.min(max, value + step))} disabled={disabled || value >= max}>+</button>
    </div>
  )
}

/* ═══════════════════════════════════════
   LegCard
   ═══════════════════════════════════════ */

function LegCard({
  leg, index, onChange, onDelete, onDuplicate, errors, disabled,
}: {
  leg: StrategyLeg; index: number; onChange: (l: StrategyLeg) => void
  onDelete: () => void; onDuplicate: () => void
  errors: FormErrors; disabled?: boolean
}) {
  const seg = (v: string) => onChange({ ...leg, segment: v as 'options' | 'futures' })
  const pos = (v: string) => onChange({ ...leg, position: v as 'buy' | 'sell' })
  const opt = (v: string) => onChange({ ...leg, option_type: v as 'CE' | 'PE' | null })
  const exp = (v: string) => onChange({ ...leg, expiry: v as 'weekly' | 'next_weekly' | 'monthly' })
  const sc = (v: string) => onChange({ ...leg, strike_criteria: v as 'atm_offset' | 'premium_closest' | 'premium_range' | 'delta' })

  const isOpt = leg.segment === 'options'
  const isRange = leg.strike_criteria === 'premium_range'
  const err = (k: string) => errors[`leg_${index}_${k}`]

  return (
    <div className="t-panel" style={{ borderLeft: `3px solid ${leg.position === 'buy' ? 'var(--green)' : 'var(--red)'}`, position: 'relative' }}>
      <div className="t-panel-header" style={{ padding: '6px 10px', minHeight: 28 }}>
        <span className="t-panel-title" style={{ fontSize: 12 }}>
          Leg {index + 1}
          <span style={{ fontSize: 9, color: leg.position === 'buy' ? 'var(--text-green)' : 'var(--text-red)', marginLeft: 4 }}>
            {leg.position.toUpperCase()}
          </span>
        </span>
        <div style={{ display: 'flex', gap: 4 }}>
          <button className="t-btn t-btn-xs t-btn-ghost" onClick={onDuplicate} disabled={disabled}
            title="Duplicate leg">+</button>
          <button className="t-btn t-btn-xs t-btn-danger" onClick={onDelete} disabled={disabled}
            title="Delete leg">&times;</button>
        </div>
      </div>

      <div className="t-panel-body" style={{ padding: '8px 10px' }}>
        <div className="t-builder-leg-grid">
          {/* Segment + Position row */}
          <div style={{ gridColumn: '1 / -1' }}>
            <label className="t-label">Segment</label>
            <div className="t-btn-group" style={{ width: '100%' }}>
              <button className={`t-btn t-btn-sm ${leg.segment === 'options' ? 'active' : ''}`}
                style={{ flex: 1, fontSize: 10 }}
                onClick={() => { seg('options'); if (leg.option_type === null) opt('CE') }}
                disabled={disabled}>Options</button>
              <button className={`t-btn t-btn-sm ${leg.segment === 'futures' ? 'active' : ''}`}
                style={{ flex: 1, fontSize: 10 }}
                onClick={() => { seg('futures'); opt(null as unknown as string) }}
                disabled={disabled}>Futures</button>
            </div>
            {err('segment') && <p className="t-builder-err">{err('segment')}</p>}
          </div>

          <div>
            <label className="t-label">Side</label>
            <div className="t-btn-group" style={{ width: '100%' }}>
              <button className={`t-btn t-btn-sm ${leg.position === 'buy' ? 'active' : ''}`}
                style={{ flex: 1, fontSize: 10, color: 'var(--text-green)' }}
                onClick={() => pos('buy')} disabled={disabled}>Buy</button>
              <button className={`t-btn t-btn-sm ${leg.position === 'sell' ? 'active' : ''}`}
                style={{ flex: 1, fontSize: 10, color: 'var(--text-red)' }}
                onClick={() => pos('sell')} disabled={disabled}>Sell</button>
            </div>
            {err('position') && <p className="t-builder-err">{err('position')}</p>}
          </div>

          <div>
            <label className="t-label">Lots</label>
            <StepperInput value={leg.lots} onChange={v => onChange({ ...leg, lots: v })} min={1} max={MAX_LOTS} compact disabled={disabled} />
            {err('lots') && <p className="t-builder-err">{err('lots')}</p>}
          </div>

          {isOpt && (
            <>
              <div>
                <label className="t-label">Type</label>
                <div className="t-btn-group" style={{ width: '100%' }}>
                  <button className={`t-btn t-btn-sm ${leg.option_type === 'CE' ? 'active' : ''}`}
                    style={{ flex: 1, fontSize: 10 }} onClick={() => opt('CE')} disabled={disabled}>CE</button>
                  <button className={`t-btn t-btn-sm ${leg.option_type === 'PE' ? 'active' : ''}`}
                    style={{ flex: 1, fontSize: 10 }} onClick={() => opt('PE')} disabled={disabled}>PE</button>
                </div>
                {err('option_type') && <p className="t-builder-err">{err('option_type')}</p>}
              </div>

              <div>
                <label className="t-label">Expiry</label>
                <select className="t-select" value={leg.expiry} onChange={e => exp(e.target.value)}
                  disabled={disabled} style={{ height: 26, fontSize: 10, padding: '2px 20px 2px 6px' }}>
                  {EXPIRY_OPTIONS.map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
                {err('expiry') && <p className="t-builder-err">{err('expiry')}</p>}
              </div>
            </>
          )}

          {!isOpt && (
            <div style={{ gridColumn: '1 / -1' }}>
              <label className="t-label" style={{ fontSize: 10, color: 'var(--text-faint)' }}>
                No option type for futures segment
              </label>
            </div>
          )}

          {/* Strike Criteria */}
          {isOpt && (
            <>
              <div style={{ gridColumn: '1 / -1' }}>
                <label className="t-label">Strike Criteria</label>
                <select className="t-select" value={leg.strike_criteria} onChange={e => sc(e.target.value)}
                  disabled={disabled} style={{ height: 26, fontSize: 10, padding: '2px 20px 2px 6px' }}>
                  {STRIKE_CRITERIA_OPTIONS.map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
                {err('strike_criteria') && <p className="t-builder-err">{err('strike_criteria')}</p>}
              </div>

              <div style={{ gridColumn: '1 / -1' }}>
                {leg.strike_criteria === 'atm_offset' && (
                  <div>
                    <label className="t-label">ATM Offset (steps)</label>
                    <StepperInput value={leg.strike_value} onChange={v => onChange({ ...leg, strike_value: v })}
                      min={-10} max={10} compact={false} disabled={disabled} />
                    {err('strike_value') && <p className="t-builder-err">{err('strike_value')}</p>}
                  </div>
                )}
                {leg.strike_criteria === 'premium_closest' && (
                  <div>
                    <label className="t-label">Target Premium (&fnof;)</label>
                    <input className="t-input" type="number" value={leg.strike_value || ''}
                      onChange={e => onChange({ ...leg, strike_value: parseFloat(e.target.value) || 0 })}
                      placeholder="e.g. 150" disabled={disabled}
                      style={{ height: 26, fontSize: 10, padding: '2px 6px' }} />
                    {err('strike_value') && <p className="t-builder-err">{err('strike_value')}</p>}
                  </div>
                )}
                {leg.strike_criteria === 'premium_range' && (
                  <div>
                    <label className="t-label">Min-Max Premium (&fnof;)</label>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      <input className="t-input" type="number" value={leg.strike_value || ''}
                        onChange={e => onChange({ ...leg, strike_value: parseFloat(e.target.value) || 0 })}
                        placeholder="Min" disabled={disabled}
                        style={{ height: 26, fontSize: 10, padding: '2px 6px', flex: 1 }} />
                      <span style={{ color: 'var(--text-faint)', fontSize: 10 }}>to</span>
                    </div>
                    {err('strike_value') && <p className="t-builder-err">{err('strike_value')}</p>}
                  </div>
                )}
                {leg.strike_criteria === 'delta' && (
                  <div>
                    <label className="t-label">Delta</label>
                    <input className="t-input" type="number" step="0.05" min="0" max="1"
                      value={leg.strike_value || ''}
                      onChange={e => onChange({ ...leg, strike_value: parseFloat(e.target.value) || 0 })}
                      placeholder="e.g. 0.5" disabled={disabled}
                      style={{ height: 26, fontSize: 10, padding: '2px 6px' }} />
                    {err('strike_value') && <p className="t-builder-err">{err('strike_value')}</p>}
                  </div>
                )}
              </div>
            </>
          )}

          {/* SL / Target */}
          <div>
            <label className="t-label">SL Type</label>
            <select className="t-select" value={leg.leg_sl_type || ''}
              onChange={e => onChange({ ...leg, leg_sl_type: e.target.value || null, leg_sl_value: e.target.value ? leg.leg_sl_value : null })}
              disabled={disabled}
              style={{ height: 26, fontSize: 10, padding: '2px 20px 2px 6px' }}>
              {SL_TARGET_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="t-label">SL Value</label>
            <input className="t-input" type="number" value={leg.leg_sl_value ?? ''}
              onChange={e => onChange({ ...leg, leg_sl_value: parseFloat(e.target.value) || null })}
              disabled={disabled || !leg.leg_sl_type}
              style={{ height: 26, fontSize: 10, padding: '2px 6px' }} />
          </div>
          <div>
            <label className="t-label">Target Type</label>
            <select className="t-select" value={leg.leg_target_type || ''}
              onChange={e => onChange({ ...leg, leg_target_type: e.target.value || null, leg_target_value: e.target.value ? leg.leg_target_value : null })}
              disabled={disabled}
              style={{ height: 26, fontSize: 10, padding: '2px 20px 2px 6px' }}>
              {SL_TARGET_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="t-label">Target Value</label>
            <input className="t-input" type="number" value={leg.leg_target_value ?? ''}
              onChange={e => onChange({ ...leg, leg_target_value: parseFloat(e.target.value) || null })}
              disabled={disabled || !leg.leg_target_type}
              style={{ height: 26, fontSize: 10, padding: '2px 6px' }} />
          </div>

          {/* ── Trailing SL ── */}
          <div style={{ gridColumn: '1 / -1', borderTop: '1px solid var(--border)', paddingTop: 6, marginTop: 4 }}>
            <label className="t-label" style={{ fontSize: 10, color: 'var(--cyan)', marginBottom: 4, display: 'block' }}>
              Trailing SL
            </label>
            <div className="t-builder-leg-grid">
              <div>
                <label className="t-label">Type</label>
                <select className="t-select" value={leg.trailing_sl_type || ''}
                  onChange={e => onChange({ ...leg, trailing_sl_type: e.target.value || null, trailing_sl_value: e.target.value ? leg.trailing_sl_value : null })}
                  disabled={disabled}
                  style={{ height: 26, fontSize: 10, padding: '2px 20px 2px 6px' }}>
                  {SL_TARGET_OPTIONS.map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="t-label">Trail By</label>
                <input className="t-input" type="number" value={leg.trailing_sl_value ?? ''}
                  onChange={e => onChange({ ...leg, trailing_sl_value: parseFloat(e.target.value) || null })}
                  disabled={disabled || !leg.trailing_sl_type}
                  style={{ height: 26, fontSize: 10, padding: '2px 6px' }} />
              </div>
              <div>
                <label className="t-label">Activation (%)</label>
                <input className="t-input" type="number" value={leg.trailing_activation ?? ''}
                  onChange={e => onChange({ ...leg, trailing_activation: parseFloat(e.target.value) || null })}
                  disabled={disabled || !leg.trailing_sl_type}
                  style={{ height: 26, fontSize: 10, padding: '2px 6px' }}
                  placeholder="e.g. 1.5" />
              </div>
            </div>
          </div>

          {/* ── Re-entry ── */}
          <div style={{ gridColumn: '1 / -1', borderTop: '1px solid var(--border)', paddingTop: 6, marginTop: 4 }}>
            <label className="t-label" style={{ fontSize: 10, color: 'var(--amber)', marginBottom: 4, display: 'block' }}>
              Re-entry
            </label>
            <div className="t-builder-leg-grid">
              <div>
                <label className="t-label">Mode</label>
                <select className="t-select" value={leg.reentry_mode || ''}
                  onChange={e => onChange({ ...leg, reentry_mode: (e.target.value || null) as StrategyLeg['reentry_mode'] })}
                  disabled={disabled}
                  style={{ height: 26, fontSize: 10, padding: '2px 20px 2px 6px' }}>
                  <option value="">None</option>
                  <option value="RE_ASAP">ASAP</option>
                  <option value="RE_COST">Cost-Based</option>
                </select>
              </div>
              <div>
                <label className="t-label">Max Re-entries</label>
                <select className="t-select" value={leg.max_reentries}
                  onChange={e => onChange({ ...leg, max_reentries: parseInt(e.target.value) || 3 })}
                  disabled={disabled || !leg.reentry_mode}
                  style={{ height: 26, fontSize: 10, padding: '2px 20px 2px 6px' }}>
                  {[1, 2, 3].map(n => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════
   PayoffPreview
   ═══════════════════════════════════════ */

function PayoffPreview({
  legs, spotPrice, indexSymbol, isSimulated,
}: {
  legs: StrategyLeg[]; spotPrice: number | null; indexSymbol: string; isSimulated?: boolean
}) {
  if (!spotPrice) {
    return (
      <div className="t-panel" style={{ padding: 24, textAlign: 'center' }}>
        <p style={{ fontSize: 11, color: 'var(--text-faint)' }}>Preview unavailable</p>
        <p style={{ fontSize: 10, color: 'var(--text-sub)', marginTop: 4 }}>Market data not available for {indexSymbol}</p>
      </div>
    )
  }

  if (legs.length === 0) {
    return null
  }

  const strikeRange = 0.15
  const minPrice = Math.round(spotPrice * (1 - strikeRange))
  const maxPrice = Math.round(spotPrice * (1 + strikeRange))
  const step = Math.max(1, Math.round((maxPrice - minPrice) / 60))
  const points: number[] = []

  for (let p = minPrice; p <= maxPrice; p += step) {
    let total = 0
    for (const leg of legs) {
      if (leg.segment === 'futures') {
        const multiplier = leg.position === 'buy' ? 1 : -1
        total += multiplier * (p - spotPrice) * leg.lots
      } else if (leg.option_type) {
        const intrinsic = leg.option_type === 'CE'
          ? Math.max(0, p - spotPrice)
          : Math.max(0, spotPrice - p)
        const multiplier = leg.position === 'buy' ? 1 : -1
        total += multiplier * intrinsic * leg.lots
      }
    }
    points.push(total)
  }

  const maxP = Math.max(...points, 1)
  const minP = Math.min(...points, -1)
  const range = maxP - minP || 1
  const width = 340
  const height = 140
  const pad = { top: 16, right: 12, bottom: 20, left: 44 }
  const chartW = width - pad.left - pad.right
  const chartH = height - pad.top - pad.bottom

  const xPos = (i: number) => pad.left + (i / (points.length - 1)) * chartW
  const yPos = (v: number) => pad.top + chartH - ((v - minP) / range) * chartH

  const d = points.map((v, i) => `${i === 0 ? 'M' : 'L'}${xPos(i)},${yPos(v)}`).join(' ')

  const yTicks = 5
  const yStep = range / yTicks
  const zeroY = yPos(0)

  return (
    <div className="t-panel" style={{ position: 'relative' }}>
      <div className="t-panel-header" style={{ padding: '6px 10px', minHeight: 28 }}>
        <span className="t-panel-title" style={{ fontSize: 12 }}>Payoff Preview</span>
        {isSimulated && (
          <span className="t-badge t-badge-amber" style={{ fontSize: 9 }}>SIMULATED DATA</span>
        )}
      </div>
      <div className="t-panel-body" style={{ padding: '4px', overflow: 'hidden' }}>
        <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', maxHeight: 160, display: 'block' }}>
          {/* Gridlines and Y labels */}
          {Array.from({ length: yTicks + 1 }).map((_, i) => {
            const val = minP + i * yStep
            const y = yPos(val)
            return (
              <g key={i}>
                <line x1={pad.left} y1={y} x2={width - pad.right} y2={y} stroke="var(--border)" strokeWidth={0.5} />
                <text x={pad.left - 4} y={y + 3} textAnchor="end" fill="var(--text-faint)" fontSize={8}
                  fontFamily="var(--font-mono)">
                  {fmtNum(val)}
                </text>
              </g>
            )
          })}
          {/* Zero line */}
          <line x1={pad.left} y1={zeroY} x2={width - pad.right} y2={zeroY} stroke="var(--text-sub)" strokeWidth={0.5} strokeDasharray="3 3" />
          {/* Payoff line */}
          <path d={d} fill="none" stroke="var(--violet)" strokeWidth={1.5} />
          {/* Fill area */}
          <path d={`${d} L${xPos(points.length - 1)},${zeroY} L${xPos(0)},${zeroY} Z`}
            fill="url(#payoffGradient)" opacity={0.15} />
          <defs>
            <linearGradient id="payoffGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--violet)" stopOpacity={0.4} />
              <stop offset="100%" stopColor="var(--violet)" stopOpacity={0} />
            </linearGradient>
          </defs>
          {/* Spot marker */}
          <line x1={xPos(Math.round((spotPrice - minPrice) / step))} y1={pad.top}
            x2={xPos(Math.round((spotPrice - minPrice) / step))} y2={height - pad.bottom}
            stroke="var(--cyan)" strokeWidth={0.5} strokeDasharray="2 2" opacity={0.5} />
        </svg>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════
   StrategyList
   ═══════════════════════════════════════ */

function StrategyList({
  strategies, loading, error, onRetry, onEdit, onDelete, onDeploy, deploying,
  fetchActivity, activeStrategyId, activityLoading, strategyActivity,
}: {
  strategies: Strategy[]; loading: boolean; error: string | null
  onRetry: () => void; onEdit: (s: Strategy) => void
  onDelete: (s: Strategy) => void; onDeploy: (s: Strategy) => void
  deploying: string | null
  fetchActivity: (id: string) => void; activeStrategyId: string | null
  activityLoading: boolean; strategyActivity: Record<string, { created_at: string; event: string; details: string }[]>
}) {
  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}
      </div>
    )
  }

  if (error) {
    return <ErrorMessage message={error} onRetry={onRetry} />
  }

  if (strategies.length === 0) {
    return (
      <div className="t-panel" style={{ padding: 40, textAlign: 'center' }}>
        <p style={{ color: 'var(--text-faint)', fontSize: 13 }}>No strategies yet &mdash; create your first</p>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {strategies.map(s => {
        const legCount = s.legs?.length || 0
        return (
          <div key={s.id} className="t-panel" style={{ padding: '10px 12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{s.name}</span>
                  <span className={STATUS_CHIP[s.status] || 't-badge-sub'} style={{ fontSize: 9 }}>
                    {STATUS_LABEL[s.status] || s.status.toUpperCase()}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 12, fontSize: 10, color: 'var(--text-sub)' }}>
                  <span>{s.index_symbol}</span>
                  <span>{s.strategy_type}</span>
                  <span>{legCount} leg{legCount !== 1 ? 's' : ''}</span>
                  <span>{s.entry_time}&ndash;{s.exit_time}</span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                <button className="t-btn t-btn-xs t-btn-success"
                  onClick={() => onDeploy(s)} disabled={deploying === s.id}
                  title="Deploy (Paper)">
                  {deploying === s.id ? '...' : 'Paper'}
                </button>
                <button className="t-btn t-btn-xs"
                  title="LIVE coming soon" disabled style={{ opacity: 0.35, cursor: 'default' }}>
                  LIVE
                </button>
                <button className="t-btn t-btn-xs" onClick={() => fetchActivity(s.id)}>
                  {activeStrategyId === s.id ? '▲ Activity' : 'Activity'}
                </button>
                <button className="t-btn t-btn-xs" onClick={() => onEdit(s)}>Edit</button>
                <button className="t-btn t-btn-xs t-btn-danger" onClick={() => onDelete(s)}>&times;</button>
              </div>
            </div>
            {activeStrategyId === s.id && (
              <div style={{ marginTop: 8, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
                <p style={{ fontSize: 10, color: 'var(--text-sub)', marginBottom: 4 }}>Activity Feed</p>
                {activityLoading ? (
                  <p style={{ fontSize: 10, color: 'var(--text-faint)' }}>Loading...</p>
                ) : strategyActivity[s.id]?.length ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 200, overflowY: 'auto' }}>
                    {strategyActivity[s.id].map((e, i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-sub)', padding: '2px 0', borderBottom: '1px solid var(--border)' }}>
                        <span>{e.event.replace(/_/g, ' ')}</span>
                        <span style={{ color: 'var(--text-faint)', fontSize: 9 }}>{new Date(e.created_at).toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p style={{ fontSize: 10, color: 'var(--text-faint)' }}>No activity yet</p>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/* ═══════════════════════════════════════
   Validation
   ═══════════════════════════════════════ */

function validateForm(form: BuilderForm, legs: StrategyLeg[], editingId?: string): FormErrors {
  const e: FormErrors = {}

  if (!form.name.trim()) e.name = 'Name is required'
  else if (form.name.length > 100) e.name = 'Name too long (max 100)'

  if (!form.entry_time) e.entry_time = 'Entry time required'
  if (!form.exit_time) e.exit_time = 'Exit time required'

  if (form.entry_time && form.exit_time && form.entry_time >= form.exit_time) {
    e.exit_time = 'Exit must be after entry'
  }

  const marketOpen = '09:15'
  if (form.entry_time && form.entry_time < marketOpen) {
    e.entry_time = 'Entry cannot be before market open (09:15)'
  }

  if (legs.length === 0) e._legs = 'At least one leg required'
  if (legs.length > MAX_LEGS) e._legs = `Max ${MAX_LEGS} legs allowed`

  legs.forEach((leg, i) => {
    const p = `leg_${i}_`

    if (leg.lots < 1) e[p + 'lots'] = 'Min 1 lot'
    if (leg.lots > MAX_LOTS) e[p + 'lots'] = `Max ${MAX_LOTS} lots`

    if (leg.segment === 'options' && !leg.option_type) {
      e[p + 'option_type'] = 'CE or PE required for options'
    }
    if (leg.segment === 'futures' && leg.option_type) {
      e[p + 'option_type'] = 'Futures cannot have option type'
    }

    if (leg.strike_criteria === 'atm_offset' && (leg.strike_value < -10 || leg.strike_value > 10)) {
      e[p + 'strike_value'] = 'ATM offset must be -10 to +10'
    }

    if (leg.strike_criteria === 'delta' && (leg.strike_value < 0 || leg.strike_value > 1)) {
      e[p + 'strike_value'] = 'Delta must be 0 to 1'
    }
  })

  return e
}

/* ═══════════════════════════════════════
   Main Page Component
   ═══════════════════════════════════════ */

export default function BuilderPage() {
  const { toast } = useToast()

  /* ── View state ── */
  const [view, setView] = useState<ViewMode>('list')
  const [editingId, setEditingId] = useState<string | null>(null)

  /* ── List state ── */
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)
  const [deploying, setDeploying] = useState<string | null>(null)

  /* ── Activity state ── */
  const [activeStrategyId, setActiveStrategyId] = useState<string | null>(null)
  const [strategyActivity, setStrategyActivity] = useState<Record<string, { created_at: string; event: string; details: string }[]>>({})
  const [activityLoading, setActivityLoading] = useState(false)

  /* ── Editor state ── */
  const [form, setForm] = useState(DEFAULT_FORM)
  const [legs, setLegs] = useState<StrategyLeg[]>([freshLeg(1)])
  const [errors, setErrors] = useState<FormErrors>({})
  const [saving, setSaving] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  const [touched, setTouched] = useState(false)

  /* ── Payoff state ── */
  const [optionChain, setOptionChain] = useState<OptionChain | null>(null)
  const [chainLoading, setChainLoading] = useState(false)

  /* ── Margin estimate state ── */
  const [marginEstimate, setMarginEstimate] = useState<{
    total_margin: number; span_margin: number; exposure_margin: number
    supported: boolean; broker: string; error?: string
  } | null>(null)
  const [marginLoading, setMarginLoading] = useState(false)

  /* ── Confirm dialog state ── */
  const [confirm, setConfirm] = useState<{
    title: string; message: string; confirmLabel?: string; confirmClass?: string
    onConfirm: () => void
  } | null>(null)

  /* ── Load strategies ── */
  const loadStrategies = useCallback(async () => {
    setListLoading(true)
    setListError(null)
    try {
      const res = await api.userStrategies.list() as { strategies: Strategy[] }
      setStrategies(res.strategies || [])
    } catch (err) {
      setListError(err instanceof ApiError ? err.message : 'Failed to load strategies')
    } finally {
      setListLoading(false)
    }
  }, [])

  useEffect(() => { loadStrategies() }, [loadStrategies])

  /* ── Load option chain for payoff ── */
  useEffect(() => {
    if (view === 'list') return
    setChainLoading(true)
    api.get<OptionChain>(`/marketdata/option-chain?symbol=${form.index_symbol}`)
      .then(res => setOptionChain(res))
      .catch(() => setOptionChain(null))
      .finally(() => setChainLoading(false))
  }, [view, form.index_symbol])

  /* ── Start create ── */
  const startCreate = () => {
    setEditingId(null)
    setForm(DEFAULT_FORM)
    _legId = 0
    setLegs([freshLeg(1)])
    setErrors({})
    setServerError(null)
    setTouched(false)
    setView('create')
  }

  /* ── Start edit ── */
  const startEdit = (s: Strategy) => {
    setEditingId(s.id)
    setForm({
      name: s.name,
      strategy_type: s.strategy_type,
      index_symbol: s.index_symbol,
      underlying_from: s.underlying_from,
      entry_time: s.entry_time,
      exit_time: s.exit_time,
      days_of_week: s.days_of_week,
      overall_sl_type: s.overall_sl_type,
      overall_sl_value: s.overall_sl_value,
      overall_target_type: s.overall_target_type,
      overall_target_value: s.overall_target_value,
    })
    _legId = 0
    setLegs(s.legs.map(l => ({ ...l, id: newLegId() })))
    setErrors({})
    setServerError(null)
    setTouched(false)
    setView('edit')
  }

  /* ── Save (create or update) ── */
  const saveStrategy = async () => {
    setTouched(true)
    const v = validateForm(form, legs, editingId || undefined)
    setErrors(v)
    if (Object.keys(v).length > 0) return

    setSaving(true)
    setServerError(null)
    try {
      const payload = {
        name: form.name.trim(),
        strategy_type: form.strategy_type,
        index_symbol: form.index_symbol,
        underlying_from: form.underlying_from,
        entry_time: form.entry_time,
        exit_time: form.exit_time,
        days_of_week: form.days_of_week,
        overall_sl_type: form.overall_sl_type,
        overall_sl_value: form.overall_sl_value,
        overall_target_type: form.overall_target_type,
        overall_target_value: form.overall_target_value,
        legs: legs.map(l => ({
          leg_order: l.leg_order,
          segment: l.segment,
          position: l.position,
          option_type: l.option_type,
          lots: l.lots,
          expiry: l.expiry,
          strike_criteria: l.strike_criteria,
          strike_value: l.strike_value,
          leg_sl_type: l.leg_sl_type,
          leg_sl_value: l.leg_sl_value,
          leg_target_type: l.leg_target_type,
          leg_target_value: l.leg_target_value,
          trailing_sl_type: l.trailing_sl_type,
          trailing_sl_value: l.trailing_sl_value,
          trailing_activation: l.trailing_activation,
        })),
      }

      if (editingId) {
        await api.userStrategies.update(editingId, payload)
        toast('success', 'Strategy updated')
      } else {
        await api.userStrategies.create(payload)
        toast('success', 'Strategy created')
      }
      setView('list')
      loadStrategies()
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to save strategy'
      setServerError(msg)
    } finally {
      setSaving(false)
    }
  }

  /* ── Delete ── */
  const promptDelete = (s: Strategy) => {
    setConfirm({
      title: 'Delete Strategy',
      message: `Are you sure you want to delete "${s.name}"? This cannot be undone.`,
      confirmLabel: 'Delete',
      onConfirm: async () => {
        try {
          await api.userStrategies.delete(s.id)
          toast('success', 'Strategy deleted')
          loadStrategies()
        } catch (err) {
          toast('error', err instanceof ApiError ? err.message : 'Failed to delete')
        }
        setConfirm(null)
      },
    })
  }

  /* ── Activity ── */
  const fetchActivity = async (strategyId: string) => {
    if (activeStrategyId === strategyId) {
      setActiveStrategyId(null)
      return
    }
    setActiveStrategyId(strategyId)
    if (strategyActivity[strategyId]) return
    setActivityLoading(true)
    try {
      const res = await api.userStrategies.activity(strategyId) as { activity: { created_at: string; event: string; details: string }[] }
      setStrategyActivity(prev => ({ ...prev, [strategyId]: res.activity }))
    } catch { }
    setActivityLoading(false)
  }

  /* ── Deploy ── */
  const deployStrategy = async (s: Strategy) => {
    setDeploying(s.id)
    try {
      await api.userStrategies.deploy(s.id, 'PAPER') as { strategy_id: string; results: unknown[]; is_simulated?: boolean }
      toast('success', 'Deployed to PAPER')
      loadStrategies()
    } catch (err) {
      toast('error', err instanceof ApiError ? err.message : 'Deploy failed')
    } finally {
      setDeploying(null)
    }
  }

  /* ── Margin estimate ── */
  const fetchMarginEstimate = async () => {
    setMarginLoading(true)
    setMarginEstimate(null)
    try {
      const payload = {
        index_symbol: form.index_symbol,
        legs: legs.map(l => ({
          segment: l.segment,
          position: l.position,
          lots: l.lots,
          option_type: l.segment === 'options' ? l.option_type : null,
          expiry: l.expiry,
          strike_criteria: l.strike_criteria,
          strike_value: l.strike_value,
        })),
      }
      const res = await api.marginEstimate(payload) as {
        supported: boolean; broker: string; total_margin: number
        span_margin: number; exposure_margin: number; error?: string
      }
      setMarginEstimate(res)
    } catch {
      setMarginEstimate({ supported: false, broker: '', total_margin: 0, span_margin: 0, exposure_margin: 0, error: 'Failed to fetch estimate' })
    } finally {
      setMarginLoading(false)
    }
  }

  /* ── Leg helpers ── */
  const addLeg = () => {
    if (legs.length >= MAX_LEGS) return
    setLegs([...legs, freshLeg(legs.length + 1)])
  }

  const updateLeg = (i: number, leg: StrategyLeg) => {
    const next = [...legs]
    next[i] = leg
    setLegs(next)
  }

  const deleteLeg = (i: number) => {
    if (legs.length <= 1) return
    const next = legs.filter((_, idx) => idx !== i).map((l, idx) => ({ ...l, leg_order: idx + 1 }))
    setLegs(next)
  }

  const duplicateLeg = (i: number) => {
    if (legs.length >= MAX_LEGS) return
    const src = legs[i]
    const dup = { ...src, id: newLegId(), leg_order: legs.length + 1 }
    setLegs([...legs, dup])
  }

  /* ── Save & Back ── */
  const handleBack = () => {
    if (touched) {
      const dirty = form.name.trim() || legs.length > 1 || legs[0]?.lots !== 1
      if (dirty) {
        setConfirm({
          title: 'Discard changes?',
          message: 'You have unsaved changes. Are you sure you want to go back?',
          confirmLabel: 'Discard',
          confirmClass: 't-btn t-btn-danger',
          onConfirm: () => { setConfirm(null); setView('list') },
        })
        return
      }
    }
    setView('list')
  }

  const isFormValid = Object.keys(validateForm(form, legs, editingId || undefined)).length === 0

  /* ═══════════════════════════════════════
     Render
     ═══════════════════════════════════════ */

  /* ── List View ── */
  if (view === 'list') {
    return (
      <>
        <div className="t-page-header">
          <h1 className="t-page-title">Strategy Builder</h1>
          <button className="t-btn t-btn-primary" onClick={startCreate}>+ New Strategy</button>
        </div>

        <StrategyList
          strategies={strategies}
          loading={listLoading}
          error={listError}
          onRetry={loadStrategies}
          onEdit={startEdit}
          onDelete={promptDelete}
          onDeploy={deployStrategy}
          deploying={deploying}
          fetchActivity={fetchActivity}
          activeStrategyId={activeStrategyId}
          activityLoading={activityLoading}
          strategyActivity={strategyActivity}
        />

        {confirm && (
          <ConfirmDialog
            title={confirm.title}
            message={confirm.message}
            confirmLabel={confirm.confirmLabel}
            confirmClass={confirm.confirmClass}
            onConfirm={confirm.onConfirm}
            onCancel={() => setConfirm(null)}
          />
        )}
      </>
    )
  }

  /* ── Editor View ── */
  return (
    <>
      <div className="t-page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button className="t-btn t-btn-ghost" onClick={handleBack}
            style={{ fontSize: 16, padding: '2px 6px', lineHeight: 1 }}>&larr;</button>
          <h1 className="t-page-title" style={{ fontSize: 16 }}>
            {editingId ? 'Edit Strategy' : 'New Strategy'}
          </h1>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className="t-btn" onClick={handleBack} disabled={saving}>Cancel</button>
          <button className="t-btn t-btn-primary" onClick={saveStrategy} disabled={saving || !isFormValid}>
            {saving ? 'Saving...' : editingId ? 'Update' : 'Save'}
          </button>
        </div>
      </div>

      {serverError && (
        <div className="alert alert-error" style={{ fontSize: 11, padding: '6px 10px' }}>
          {serverError}
        </div>
      )}

      <div className="t-builder-layout">
        {/* ── Left: Settings ── */}
        <div className="t-builder-settings">
          <div className="t-panel">
            <div className="t-panel-header"><span className="t-panel-title" style={{ fontSize: 12 }}>Strategy Settings</span></div>
            <div className="t-panel-body" style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {/* Name */}
              <div>
                <label className="t-label">Name</label>
                <input className="t-input" type="text" value={form.name}
                  onChange={e => { setForm({ ...form, name: e.target.value }); setTouched(true) }}
                  placeholder="My Strategy" style={{ height: 28, fontSize: 11 }} />
                {touched && errors.name && <p className="t-builder-err">{errors.name}</p>}
              </div>

              {/* Strategy Type */}
              <div>
                <label className="t-label">Type</label>
                <div className="t-btn-group" style={{ width: '100%' }}>
                  <button className={`t-btn t-btn-sm ${form.strategy_type === 'intraday' ? 'active' : ''}`}
                    style={{ flex: 1, fontSize: 10, textTransform: 'uppercase' }}
                    onClick={() => setForm({ ...form, strategy_type: 'intraday' })}>Intraday</button>
                  <button className={`t-btn t-btn-sm ${form.strategy_type === 'positional' ? 'active' : ''}`}
                    style={{ flex: 1, fontSize: 10, textTransform: 'uppercase' }}
                    onClick={() => setForm({ ...form, strategy_type: 'positional' })}>Positional</button>
                </div>
              </div>

              {/* Index Symbol */}
              <div>
                <label className="t-label">Index</label>
                <select className="t-select" value={form.index_symbol}
                  onChange={e => setForm({ ...form, index_symbol: e.target.value })}
                  style={{ height: 28, fontSize: 11, padding: '4px 24px 4px 8px' }}>
                  {INDEX_SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>

              {/* Underlying */}
              <div>
                <label className="t-label">Underlying</label>
                <div className="t-btn-group" style={{ width: '100%' }}>
                  <button className={`t-btn t-btn-sm ${form.underlying_from === 'cash' ? 'active' : ''}`}
                    style={{ flex: 1, fontSize: 10 }}
                    onClick={() => setForm({ ...form, underlying_from: 'cash' })}>Cash</button>
                  <button className={`t-btn t-btn-sm ${form.underlying_from === 'futures' ? 'active' : ''}`}
                    style={{ flex: 1, fontSize: 10 }}
                    onClick={() => setForm({ ...form, underlying_from: 'futures' })}>Futures</button>
                </div>
              </div>

              {/* Entry / Exit Time */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div>
                  <label className="t-label">Entry</label>
                  <input className="t-input" type="time" value={form.entry_time}
                    onChange={e => { setForm({ ...form, entry_time: e.target.value }); setTouched(true) }}
                    style={{ height: 28, fontSize: 11 }} />
                  {touched && errors.entry_time && <p className="t-builder-err">{errors.entry_time}</p>}
                </div>
                <div>
                  <label className="t-label">Exit</label>
                  <input className="t-input" type="time" value={form.exit_time}
                    onChange={e => { setForm({ ...form, exit_time: e.target.value }); setTouched(true) }}
                    style={{ height: 28, fontSize: 11 }} />
                  {touched && errors.exit_time && <p className="t-builder-err">{errors.exit_time}</p>}
                </div>
              </div>

              {/* Days of Week */}
              <div>
                <label className="t-label">Days</label>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                  {DAYS.map((d, i) => {
                    const active = form.days_of_week.includes(i + 1)
                    return (
                      <button key={d} className={`t-chip ${active ? 'active' : ''}`}
                        style={{ fontSize: 10, padding: '2px 8px', height: 24 }}
                        onClick={() => {
                          const next = active
                            ? form.days_of_week.filter(x => x !== i + 1)
                            : [...form.days_of_week, i + 1].sort()
                          setForm({ ...form, days_of_week: next.length ? next : [i + 1] })
                        }}>
                        {d}
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* Overall SL / Target */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div>
                  <label className="t-label">Overall SL</label>
                  <select className="t-select" value={form.overall_sl_type || ''}
                    onChange={e => setForm({ ...form, overall_sl_type: e.target.value || null, overall_sl_value: e.target.value ? form.overall_sl_value : null })}
                    style={{ height: 26, fontSize: 10, padding: '2px 20px 2px 6px' }}>
                    {SL_TARGET_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="t-label">&nbsp;</label>
                  <input className="t-input" type="number" value={form.overall_sl_value ?? ''}
                    onChange={e => setForm({ ...form, overall_sl_value: parseFloat(e.target.value) || null })}
                    disabled={!form.overall_sl_type}
                    style={{ height: 26, fontSize: 10, padding: '2px 6px' }} />
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div>
                  <label className="t-label">Overall Target</label>
                  <select className="t-select" value={form.overall_target_type || ''}
                    onChange={e => setForm({ ...form, overall_target_type: e.target.value || null, overall_target_value: e.target.value ? form.overall_target_value : null })}
                    style={{ height: 26, fontSize: 10, padding: '2px 20px 2px 6px' }}>
                    {SL_TARGET_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="t-label">&nbsp;</label>
                  <input className="t-input" type="number" value={form.overall_target_value ?? ''}
                    onChange={e => setForm({ ...form, overall_target_value: parseFloat(e.target.value) || null })}
                    disabled={!form.overall_target_type}
                    style={{ height: 26, fontSize: 10, padding: '2px 6px' }} />
                </div>
              </div>
            </div>
          </div>

          {/* Payoff Preview */}
          <PayoffPreview
            legs={legs}
            spotPrice={optionChain?.spot_price ?? null}
            indexSymbol={form.index_symbol}
            isSimulated={optionChain?.is_simulated}
          />

          {/* Margin Estimate */}
          <div className="t-panel">
            <div className="t-panel-header">
              <span className="t-panel-title" style={{ fontSize: 12 }}>Margin Estimate</span>
            </div>
            <div className="t-panel-body" style={{ padding: '8px 10px' }}>
              <button className="t-btn t-btn-sm t-btn-primary" onClick={fetchMarginEstimate}
                disabled={marginLoading || legs.length === 0}
                style={{ width: '100%', marginBottom: marginEstimate ? 8 : 0 }}>
                {marginLoading ? 'Estimating...' : 'Estimate'}
              </button>
              {marginEstimate && (
                <div style={{ fontSize: 11, lineHeight: 1.6 }}>
                  {marginEstimate.supported ? (
                    <>
                      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderTop: '1px solid var(--border)' }}>
                        <span style={{ color: 'var(--text-sub)' }}>Total Margin</span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--cyan)' }}>
                          &fnof; {marginEstimate.total_margin.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
                        <span style={{ color: 'var(--text-sub)' }}>SPAN</span>
                        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
                          &fnof; {marginEstimate.span_margin.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
                        <span style={{ color: 'var(--text-sub)' }}>Exposure</span>
                        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
                          &fnof; {marginEstimate.exposure_margin.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                        </span>
                      </div>
                      <div style={{ fontSize: 9, color: 'var(--text-faint)', marginTop: 4 }}>
                        Via {marginEstimate.broker.toUpperCase()}
                      </div>
                    </>
                  ) : (
                    <p style={{ fontSize: 10, color: 'var(--text-faint)', margin: 0, textAlign: 'center' }}>
                      {marginEstimate.error || 'Margin estimate not available for this broker'}
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── Right: Leg Cards ── */}
        <div className="t-builder-legs">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)' }}>
              Legs ({legs.length}/{MAX_LEGS})
            </span>
            <button className="t-btn t-btn-sm t-btn-primary"
              onClick={addLeg} disabled={legs.length >= MAX_LEGS}>
              + Add Leg
            </button>
          </div>

          {touched && errors._legs && (
            <p className="t-builder-err" style={{ marginBottom: 8 }}>{errors._legs}</p>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {legs.map((leg, i) => (
              <LegCard
                key={leg.id}
                leg={leg}
                index={i}
                onChange={l => updateLeg(i, l)}
                onDelete={() => deleteLeg(i)}
                onDuplicate={() => duplicateLeg(i)}
                errors={touched ? errors : {}}
                disabled={saving}
              />
            ))}
          </div>
        </div>
      </div>

      {confirm && (
        <ConfirmDialog
          title={confirm.title}
          message={confirm.message}
          confirmLabel={confirm.confirmLabel}
          confirmClass={confirm.confirmClass}
          onConfirm={confirm.onConfirm}
          onCancel={() => setConfirm(null)}
        />
      )}
    </>
  )
}
