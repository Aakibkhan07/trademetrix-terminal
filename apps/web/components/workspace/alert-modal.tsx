'use client'

import { useState } from 'react'
import { api } from '@/lib/api'
import { useToast } from '@/lib/use-toast'

export interface AlertTarget { symbol: string; name: string }

interface AlertModalProps {
  item: AlertTarget
  onClose: () => void
}

export default function AlertModal({ item, onClose }: AlertModalProps) {
  const { toast } = useToast()
  const [price, setPrice] = useState(0)
  const [dir, setDir] = useState<'above' | 'below'>('above')
  const [busy, setBusy] = useState(false)

  const create = async () => {
    if (price <= 0) { toast('error', 'Enter a target price'); return }
    setBusy(true)
    try {
      await api.alerts.create({ symbol: item.symbol, condition: dir, target_price: price, note: item.name })
      toast('success', `Alert set ${item.name} ${dir === 'above' ? '>' : '<'} ₹${price}`)
      onClose()
    } catch {
      toast('error', 'Failed to create alert')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="t-modal-overlay" onClick={onClose}>
      <div className="t-modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 320 }}>
        <h3 className="t-modal-title">Price Alert · {item.name}</h3>
        <div className="t-row" style={{ gap: 8, marginBottom: 10 }}>
          <div className="t-col">
            <label className="t-label">Condition</label>
            <select className="t-select" value={dir} onChange={e => setDir(e.target.value as 'above' | 'below')}>
              <option value="above">Crosses above</option>
              <option value="below">Drops below</option>
            </select>
          </div>
          <div className="t-col">
            <label className="t-label">Target</label>
            <input className="t-input" type="number" step={0.05} value={price || ''}
              onChange={e => setPrice(Number(e.target.value))} placeholder="0.00" />
          </div>
        </div>
        <div className="t-row" style={{ gap: 6 }}>
          <button className="t-btn t-btn-primary" onClick={create} disabled={busy} style={{ flex: 1 }}>
            {busy ? 'Saving…' : 'Set Alert'}
          </button>
          <button className="t-btn t-btn-ghost" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  )
}
