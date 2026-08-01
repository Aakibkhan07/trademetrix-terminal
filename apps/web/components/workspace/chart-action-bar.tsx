'use client'

import { useState } from 'react'
import { useUIStore } from '@/lib/stores/ui-store'
import { useToast } from '@/lib/use-toast'
import AlertModal from './alert-modal'

interface ChartActionBarProps {
  onAnalyze: (symbol: string, name: string) => void
  onOpenChain: (symbol: string, name: string) => void
}

export default function ChartActionBar({ onAnalyze, onOpenChain }: ChartActionBarProps) {
  const activeSymbol = useUIStore(s => s.activeSymbol)
  const activeName = useUIStore(s => s.activeName)
  const openQuickOrder = useUIStore(s => s.openQuickOrder)
  const { toast } = useToast()
  const [alertOpen, setAlertOpen] = useState(false)

  const btn = (label: string, onClick: () => void, tone?: 'green' | 'red' | '') => (
    <button
      className="t-btn t-btn-sm"
      onClick={onClick}
      style={tone === 'green'
        ? { borderColor: 'rgba(52,211,153,.35)', color: 'var(--green)', fontWeight: 800 }
        : tone === 'red'
          ? { borderColor: 'hsla(0,91%,71%,.35)', color: 'var(--red)', fontWeight: 800 }
          : undefined}
    >
      {label}
    </button>
  )

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6, padding: '8px 10px',
      borderBottom: '1px solid var(--border)', flexWrap: 'wrap',
    }}>
      {btn('BUY', () => openQuickOrder(activeSymbol, activeName, 'BUY'), 'green')}
      {btn('SELL', () => openQuickOrder(activeSymbol, activeName, 'SELL'), 'red')}
      <span style={{ width: 1, height: 18, background: 'var(--border)' }} />
      {btn('🔬 Analyze', () => onAnalyze(activeSymbol, activeName))}
      {btn('☰ Option Chain', () => onOpenChain(activeSymbol, activeName))}
      {btn('🤖 Strategy', () => { window.location.assign(`/strategies/builder?symbol=${encodeURIComponent(activeSymbol)}`) })}
      {btn('📈 Backtest', () => { window.location.assign(`/backtest?symbol=${encodeURIComponent(activeSymbol)}`) })}
      {btn('🔔 Alert', () => setAlertOpen(true))}
      {btn('📓 Journal', () => { window.location.assign('/journal') })}
      <span className="t-faint" style={{ fontSize: 9, marginLeft: 'auto' }}>{activeName} · {activeSymbol}</span>

      {alertOpen && <AlertModal item={{ symbol: activeSymbol, name: activeName }} onClose={() => setAlertOpen(false)} />}
    </div>
  )
}
