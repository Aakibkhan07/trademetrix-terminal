'use client'

import { useState } from 'react'
import type { ChainRow } from './types'

export interface ChainMetrics {
  pcr: number | null
  maxPain: number | null
}

function fmtInt(n: number) {
  return n >= 100000 ? (n / 100000).toFixed(1) + 'L' : n >= 1000 ? (n / 1000).toFixed(1) + 'K' : String(n)
}

/**
 * Simplified-by-default option chain. Advanced analytics (IV / OI / Vol / PCR /
 * Max Pain) live in the collapsed section. Clicking a strike only HIGHLIGHTS it;
 * the side (CE/PE) is selected separately via the per-row buttons. No action on a
 * row ever places or pre-selects BUY/SELL.
 */
export function ChainPanel({ rows, metrics, spot, selectedStrike, selectedSide, onSelectStrike, onSelectSide, notionalLots }: {
  rows: ChainRow[]
  metrics: ChainMetrics
  spot: number | null
  selectedStrike: number | null
  selectedSide: 'CE' | 'PE' | null
  onSelectStrike: (strike: number) => void
  onSelectSide: (strike: number, side: 'CE' | 'PE') => void
  notionalLots: number
}) {
  const [advanced, setAdvanced] = useState(false)
  const atm = spot !== null && rows.length ? rows.reduce((a, b) => Math.abs(a.strike - spot) < Math.abs(b.strike - spot) ? a : b, rows[0]) : null
  const atmStrike = atm?.strike ?? null

  return (
    <div className="t-panel" style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderBottom: '1px solid color-mix(in srgb, var(--text-inverse) 6%, transparent)' }}>
        <span className="t-faint" style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em' }}>OPTION CHAIN</span>
        {spot !== null && atmStrike !== null && (
          <span className="t-faint" style={{ fontSize: 10 }}>
            ATM <b style={{ color: 'var(--text)' }}>{atmStrike.toLocaleString('en-IN')}</b>
            {spot !== null && <>&nbsp;· SPOT <b style={{ color: 'var(--text)' }}>{spot.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</b></>}
          </span>
        )}
        <span style={{ flex: 1 }} />
        <button type="button" className="t-chip" style={{ fontSize: 10 }} onClick={() => setAdvanced(v => !v)} data-kb="chain-advanced">
          {advanced ? 'Hide' : 'Show'} {advanced ? '▲' : '▼'} Advanced
        </button>
      </div>

      {advanced && metrics.pcr !== null && (
        <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', padding: '8px 12px', borderBottom: '1px solid color-mix(in srgb, var(--text-inverse) 6%, transparent)' }}>
          <div>
            <div className="t-faint" style={{ fontSize: 9 }}>PCR</div>
            <div style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{metrics.pcr.toFixed(2)}</div>
          </div>
          {metrics.maxPain !== null && (
            <div>
              <div className="t-faint" style={{ fontSize: 9 }}>Max Pain</div>
              <div style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{metrics.maxPain.toLocaleString('en-IN')}</div>
            </div>
          )}
          <div className="t-faint" style={{ alignSelf: 'center', fontSize: 9 }}>
            IV · OI · Volume shown per side below
          </div>
        </div>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table className="t-table" style={{ fontSize: 10, width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ fontSize: 9, color: 'var(--text-faint)' }}>
              <th style={{ textAlign: 'right', padding: '4px 6px' }}>CE {advanced ? 'IV' : 'LTP'}</th>
              {advanced && <th style={{ textAlign: 'right', padding: '4px 6px' }}>OI</th>}
              {advanced && <th style={{ textAlign: 'right', padding: '4px 6px' }}>Vol</th>}
              <th style={{ textAlign: 'center', padding: '4px 6px' }}>STRIKE</th>
              {advanced && <th style={{ textAlign: 'left', padding: '4px 6px' }}>Vol</th>}
              {advanced && <th style={{ textAlign: 'left', padding: '4px 6px' }}>OI</th>}
              <th style={{ textAlign: 'left', padding: '4px 6px' }}>PE {advanced ? 'IV' : 'LTP'}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const isSelStrike = selectedStrike === r.strike
              const isAtm = atmStrike === r.strike
              return (
                <tr key={r.strike}
                  onClick={() => onSelectStrike(r.strike)}
                  style={{
                    cursor: 'pointer',
                    background: isAtm ? 'color-mix(in srgb, var(--violet) 7%, transparent)' : undefined,
                    outline: isSelStrike ? '2px solid var(--violet)' : undefined,
                    outlineOffset: -1,
                  }}
                >
                  <td colSpan={advanced ? 3 : 1} style={{ padding: 0 }}>
                    <div style={{ display: 'flex', width: '100%', gap: 4, alignItems: 'center', justifyContent: 'flex-end' }}>
                      <button
                        type="button"
                        data-kb={`ce-${r.strike}`}
                        className={`t-btn t-btn-sm ${selectedStrike === r.strike && selectedSide === 'CE' ? 't-btn-primary' : 't-btn-ghost'}`}
                        style={{ flex: 0, padding: '2px 6px', fontSize: 10, minWidth: 0 }}
                        onClick={e => { e.stopPropagation(); onSelectSide(r.strike, 'CE') }}
                      >
                        {r.call.ltp > 0 ? r.call.ltp.toLocaleString('en-IN', { maximumFractionDigits: 1 }) : '—'}
                        {advanced && <span className="t-faint" style={{ fontSize: 8, marginLeft: 3 }}>{r.call.iv > 0 ? r.call.iv.toFixed(0) + '%' : ''}</span>}
                      </button>
                    </div>
                  </td>
                  {advanced && <td style={{ textAlign: 'right', padding: '2px 4px', color: r.call.oi > 0 ? 'var(--text)' : 'var(--text-faint)' }}>{r.call.oi > 0 ? fmtInt(r.call.oi) : '—'}</td>}
                  {advanced && <td style={{ textAlign: 'right', padding: '2px 4px' }}>{r.call.volume > 0 ? fmtInt(r.call.volume) : '—'}</td>}
                  <td style={{ textAlign: 'center', fontWeight: 700, padding: '4px 6px', fontFamily: 'var(--font-mono)', background: isSelStrike ? 'color-mix(in srgb, var(--violet) 12%, transparent)' : undefined }}>
                    {r.strike.toLocaleString('en-IN')}
                  </td>
                  {advanced && <td style={{ textAlign: 'left', padding: '2px 4px' }}>{r.put.volume > 0 ? fmtInt(r.put.volume) : '—'}</td>}
                  {advanced && <td style={{ textAlign: 'left', padding: '2px 4px' }}>{r.put.oi > 0 ? fmtInt(r.put.oi) : '—'}</td>}
                  <td style={{ padding: 0 }}>
                    <div style={{ display: 'flex', width: '100%', gap: 4, alignItems: 'center' }}>
                      <button
                        type="button"
                        data-kb={`pe-${r.strike}`}
                        className={`t-btn t-btn-sm ${selectedStrike === r.strike && selectedSide === 'PE' ? 't-btn-danger' : 't-btn-ghost'}`}
                        style={{ padding: '2px 6px', fontSize: 10, minWidth: 0 }}
                        onClick={e => { e.stopPropagation(); onSelectSide(r.strike, 'PE') }}
                      >
                        {advanced && <span className="t-faint" style={{ fontSize: 8, marginRight: 3 }}>{r.put.iv > 0 ? r.put.iv.toFixed(0) + '%' : ''}</span>}
                        {r.put.ltp > 0 ? r.put.ltp.toLocaleString('en-IN', { maximumFractionDigits: 1 }) : '—'}
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {notionalLots > 0 && selectedStrike !== null && (
        <div style={{ padding: '6px 12px', borderTop: '1px solid color-mix(in srgb, var(--text-inverse) 6%, transparent)', fontSize: 10, color: 'var(--text-faint)' }}>
          Selected <b style={{ color: 'var(--text)' }}>{selectedStrike.toLocaleString('en-IN')}</b> — quantity uses the order panel lots. Clicking a row never places an order.
        </div>
      )}
    </div>
  )
}