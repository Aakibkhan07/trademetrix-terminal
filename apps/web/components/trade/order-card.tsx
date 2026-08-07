'use client'

import { MONEYNESS_OPTIONS, marginLeg } from '@/lib/options-contracts'
import type { IndexKey, Moneyness } from '@/lib/options-contracts'
import type { ChainData } from './types'

export interface OrderForm {
  index: IndexKey
  moneyness: Moneyness
  customStrike: number | null
  optionType: 'CE' | 'PE'
  expiry: string
  lots: number
  orderType: 'MARKET' | 'LIMIT'
  limitPrice: number
}

/**
 * Order card — every decision is a click, never a typed symbol/strike/qty.
 * Shows live SPAN margin from the existing /margin-estimate API and a final
 * contract preview before BUY / SELL. Paper is the default; Live is one
 * deliberate toggle away (reuse of the strategy deploy contract).
 */
export function OrderCard({ form, onChange, chain, spot, ltp, lotSize, margin, marginLoading, mode, onMode, onPlace }: {
  form: OrderForm
  onChange: (next: Partial<OrderForm>) => void
  chain: ChainData | null
  spot: number | null
  ltp: number | null
  lotSize: number
  margin: { span: number; exposure: number; total: number } | null
  marginLoading: boolean
  mode: 'paper' | 'live'
  onMode: (m: 'paper' | 'live') => void
  onPlace: (side: 'BUY' | 'SELL') => void
}) {
  const expiries = chain?.expiries ?? []
  const weekly = expiries[0] ?? '—'
  const monthly = expiries[expiries.length - 1] ?? '—'

  return (
    <div className="t-panel">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderBottom: '1px solid color-mix(in srgb, var(--text-inverse) 6%, transparent)' }}>
        <span className="t-faint" style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em' }}>ORDER</span>
        <span style={{ flex: 1 }} />
        <div className="t-chip-group">
          <button type="button" data-kb="mode-paper" className={`t-chip ${mode === 'paper' ? 'active' : ''}`} style={{ fontSize: 10 }} onClick={() => onMode('paper')}>PAPER</button>
          <button type="button" data-kb="mode-live" className={`t-chip ${mode === 'live' ? 'active' : ''}`} style={{ fontSize: 10, color: mode === 'live' ? 'var(--red)' : undefined }} onClick={() => onMode('live')}>LIVE</button>
        </div>
      </div>

      <div style={{ padding: '10px 12px', display: 'grid', gap: 10 }}>
        {/* Expiry */}
        <div style={{ display: 'grid', gap: 4 }}>
          <span className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.06em' }}>EXPIRY</span>
          <div className="t-chip-group">
            <button type="button" data-kb="expiry-weekly" className={`t-chip ${form.expiry === weekly ? 'active' : ''}`} style={{ fontSize: 10 }} onClick={() => onChange({ expiry: weekly })}>
              Weekly {weekly}
            </button>
            <button type="button" data-kb="expiry-monthly" className={`t-chip ${form.expiry === monthly ? 'active' : ''}`} style={{ fontSize: 10 }} onClick={() => onChange({ expiry: monthly })}>
              Monthly {monthly}
            </button>
          </div>
        </div>

        {/* Contract side */}
        <div style={{ display: 'grid', gap: 4 }}>
          <span className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.06em' }}>CONTRACT OF</span>
          <div className="t-chip-group">
            <button type="button" data-kb="oc-ce" className={`t-chip ${form.optionType === 'CE' ? 'active' : ''}`} style={{ fontSize: 10, color: form.optionType === 'CE' ? 'var(--violet)' : undefined }} onClick={() => onChange({ optionType: 'CE' })}>CE</button>
            <button type="button" data-kb="oc-pe" className={`t-chip ${form.optionType === 'PE' ? 'active' : ''}`} style={{ fontSize: 10, color: form.optionType === 'PE' ? 'var(--red)' : undefined }} onClick={() => onChange({ optionType: 'PE' })}>PE</button>
          </div>
        </div>

        {/* Moneyness */}
        <div style={{ display: 'grid', gap: 4 }}>
          <span className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.06em' }}>MONEYNESS</span>
          <div className="t-chip-group">
            {MONEYNESS_OPTIONS.map(o => (
              <button key={o.key} type="button" data-kb={`mn-${o.key}`} className={`t-chip ${form.moneyness === o.key ? 'active' : ''}`} style={{ fontSize: 10 }} onClick={() => onChange({ moneyness: o.key, customStrike: null })}>
                {o.label}
              </button>
            ))}
            {form.moneyness === 'CUSTOM' && (
              <input
                inputMode="numeric"
                placeholder="Custom strike"
                value={form.customStrike ?? ''}
                onChange={e => onChange({ customStrike: Number(e.target.value) || null })}
                style={{ width: 90, fontSize: 10, padding: '2px 6px', background: 'var(--bg)', border: '1px solid color-mix(in srgb, var(--text-inverse) 15%, transparent)', borderRadius: 6, color: 'var(--text)' }}
              />
            )}
          </div>
        </div>

        {/* Lots */}
        <div style={{ display: 'grid', gap: 4 }}>
          <span className="t-faint" style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.06em' }}>
            QUANTITY · {form.lots} × {lotSize} = <b style={{ color: 'var(--text)' }}>{form.lots * lotSize}</b>
          </span>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <button type="button" className="t-btn t-btn-sm" onClick={() => onChange({ lots: Math.max(1, form.lots - 1) })}>−</button>
            <div style={{ fontSize: 16, fontWeight: 800, minWidth: 56, textAlign: 'center', fontFamily: 'var(--font-mono)' }}>{form.lots}</div>
            <button type="button" className="t-btn t-btn-sm" onClick={() => onChange({ lots: Math.min(50, form.lots + 1) })}>+</button>
            <span style={{ flex: 1 }} />
            {form.orderType === 'LIMIT' && (
              <input
                type="number"
                step="0.05"
                value={form.limitPrice || ''}
                onChange={e => onChange({ limitPrice: Number(e.target.value) || 0 })}
                placeholder={`Limit @ ${ltp?.toFixed(2) ?? '—'}`}
                style={{ width: 110, fontSize: 11, padding: '3px 8px', background: 'var(--bg)', border: '1px solid color-mix(in srgb, var(--text-inverse) 15%, transparent)', borderRadius: 6, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}
              />
            )}
          </div>
          <div className="t-chip-group">
            <button type="button" data-kb="otype-market" className={`t-chip ${form.orderType === 'MARKET' ? 'active' : ''}`} style={{ fontSize: 10 }} onClick={() => onChange({ orderType: 'MARKET' })}>MARKET</button>
            <button type="button" data-kb="otype-limit" className={`t-chip ${form.orderType === 'LIMIT' ? 'active' : ''}`} style={{ fontSize: 10 }} onClick={() => onChange({ orderType: 'LIMIT' })}>LIMIT</button>
            <span className="t-faint" style={{ fontSize: 9, marginLeft: 6 }}>LTP <b style={{ color: 'var(--text)' }}>{ltp !== null && ltp > 0 ? ltp.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—'}</b></span>
          </div>
        </div>

        {/* Margin */}
        <div style={{ display: 'grid', gap: 2, padding: '8px 10px', background: 'color-mix(in srgb, var(--text-inverse) 3%, transparent)', borderRadius: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
            <span className="t-faint">SPAN</span>
            <span style={{ fontFamily: 'var(--font-mono)' }}>{marginLoading ? '…' : margin ? '₹' + margin.span.toLocaleString('en-IN') : '—'}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
            <span className="t-faint">EXPOSURE</span>
            <span style={{ fontFamily: 'var(--font-mono)' }}>{marginLoading ? '…' : margin ? '₹' + margin.exposure.toLocaleString('en-IN') : '—'}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 700, paddingTop: 4, borderTop: '1px solid color-mix(in srgb, var(--text-inverse) 8%, transparent)' }}>
            <span className="t-faint">TOTAL</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--violet)' }}>{marginLoading ? '…' : margin ? '₹' + margin.total.toLocaleString('en-IN') : '—'}</span>
          </div>
        </div>

        {/* Preview */}
        <div style={{ fontSize: 10, color: 'var(--text-faint)', lineHeight: 1.6 }}>
          {form.index} <b style={{ color: 'var(--text)' }}>{form.expiry}</b> · {form.moneyness === 'CUSTOM' && form.customStrike ? form.customStrike : MONEYNESS_OPTIONS.find(m => m.key === form.moneyness)?.label} ·{' '}
          <b style={{ color: form.optionType === 'CE' ? 'var(--violet)' : 'var(--red)' }}>{form.optionType === 'CE' ? 'CE' : 'PE'}</b> · {form.lots} lot × {lotSize}
        </div>

        {/* Actions */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <button type="button" data-kb="buy" className="t-btn" style={{ background: 'var(--green)', color: '#052a14', fontWeight: 800 }} onClick={() => onPlace('BUY')}>
            BUY {form.optionType}
          </button>
          <button type="button" data-kb="sell" className="t-btn" style={{ background: 'var(--red)', color: '#fff', fontWeight: 800 }} onClick={() => onPlace('SELL')}>
            SELL {form.optionType}
          </button>
        </div>
        {mode === 'live' && (
          <div className="t-faint" style={{ fontSize: 9, textAlign: 'center' }}>
            LIVE orders go to the broker. Double-check the preview above.
          </div>
        )}
      </div>
    </div>
  )
}