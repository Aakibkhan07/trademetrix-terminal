'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useUIStore } from '@/lib/stores/ui-store'
import { Badge } from '@/components/ui/badge'
import { fmtInr, fmtNum, fmtTime, type LiveSignal } from './types'

const SIDE_COLOR: Record<string, string> = { BUY: 'var(--green)', SELL: 'var(--red)', EXIT: 'var(--amber)', REVERSE: 'var(--violet)', HOLD: 'var(--text-sub)' }
const SIDE_VARIANT: Record<string, 'green' | 'red' | 'amber' | 'violet' | 'sub'> = {
  BUY: 'green', SELL: 'red', EXIT: 'amber', REVERSE: 'violet', HOLD: 'sub',
}

/**
 * One live signal card. PRIMARY actions = Trade + Analyze; every other
 * workflow (Backtest / Deploy / Portfolio) sits behind the overflow "⋯" menu.
 */
export function SignalCard({ signal }: { signal: LiveSignal }) {
  const router = useRouter()
  const [menuOpen, setMenuOpen] = useState(false)

  const side = signal.side || 'HOLD'
  const color = SIDE_COLOR[side] || 'var(--text-sub)'

  const trade = () => {
    useUIStore.getState().openQuickOrder(signal.symbol, signal.strategy_name || signal.symbol, side as 'BUY' | 'SELL')
  }

  const menuAction = (href: string) => {
    setMenuOpen(false)
    router.push(href)
  }

  const confidence = signal.confidence ? Math.round(signal.confidence) : null

  return (
    <div className="t-panel" style={{ padding: 10, marginBottom: 8, position: 'relative' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <span style={{ color, fontWeight: 800, fontSize: 11, letterSpacing: '0.05em' }}>{side}</span>
        <Badge variant={signal.mode === 'live' ? 'red' : 'cyan'} style={{ fontSize: 8 }}>{signal.mode || 'paper'}</Badge>
        {signal.signal_version && signal.signal_version !== 1 && (
          <Badge variant="sub" style={{ fontSize: 8 }}>v{signal.signal_version}</Badge>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{fmtTime(signal.triggered_at)}</span>
      </div>

      <div style={{ fontWeight: 700, fontSize: 13 }}>{signal.symbol?.split(':').pop()}</div>
      <div style={{ fontSize: 10, color: 'var(--text-sub)', marginBottom: 6 }}>
        {signal.strategy_name || signal.strategy_id} <span className="t-faint">· {signal.exchange || 'NSE'}</span>
      </div>

      {signal.reason && <div style={{ fontSize: 11, color: 'var(--text-sub)', marginBottom: 6 }}>{signal.reason}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '2px 10px', fontSize: 10, marginBottom: 8 }}>
        <Metric label="Qty" value={String(signal.quantity ?? '—')} />
        <Metric label="Entry" value={fmtNum(signal.price)} />
        <Metric label="SL" value={fmtNum(signal.sl_price)} />
        <Metric label="Target" value={fmtNum(signal.target_price)} />
        {confidence !== null && <Metric label="Confidence" value={`${confidence}%`} />}
      </div>

      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <button type="button" className="t-btn t-btn-sm t-btn-primary" style={{ fontSize: 11, flex: 1 }} onClick={trade}>Trade</button>
        <button type="button" className="t-btn t-btn-sm" style={{ fontSize: 11, flex: 1 }} onClick={() => router.push(`/workspace?sym=${encodeURIComponent(signal.symbol)}`)}>Analyze</button>
        <div style={{ position: 'relative' }}>
          <button type="button" aria-label="More actions" className="t-btn t-btn-sm t-btn-ghost" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => setMenuOpen(o => !o)}>⋯</button>
          {menuOpen && (
            <>
              <div style={{ position: 'fixed', inset: 0, zIndex: 40 }} onClick={() => setMenuOpen(false)} />
              <div className="t-panel" style={{ position: 'absolute', right: 0, top: '100%', zIndex: 41, padding: 4, minWidth: 140, marginTop: 2 }}>
                <MenuItem onClick={() => menuAction(`/backtest?s=${encodeURIComponent(signal.symbol)}`)}>Backtest</MenuItem>
                <MenuItem onClick={() => menuAction('/strategies')}>Deploy</MenuItem>
                <MenuItem onClick={() => menuAction('/portfolio')}>Portfolio</MenuItem>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
      <span className="t-faint">{label}</span>
      <span className="t-num" style={{ fontWeight: 600 }}>{value}</span>
    </div>
  )
}

function MenuItem({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} style={{ display: 'block', width: '100%', textAlign: 'left', background: 'none', border: 'none', padding: '6px 8px', fontSize: 11, cursor: 'pointer', borderRadius: 4, color: 'var(--text-sub)' }}>
      {children}
    </button>
  )
}