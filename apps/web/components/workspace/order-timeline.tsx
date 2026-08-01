'use client'

import { useMemo } from 'react'
import { useOrders } from '@/lib/queries/orders'

const STAGES = ['Requested', 'Validated', 'Sent', 'Accepted', 'Filled', 'Completed'] as const

function stageOf(status: string): { index: number; rejected?: string } {
  switch (status) {
    case 'QUEUED': return { index: 0 }
    case 'VALIDATED': return { index: 1 }
    case 'SENT': return { index: 2 }
    case 'PENDING': return { index: 3 }
    case 'PARTIAL': return { index: 4 }
    case 'FILLED': return { index: 5 }
    case 'REJECTED': return { index: -1, rejected: 'REJECTED' }
    case 'CANCELLED': return { index: -1, rejected: 'CANCELLED' }
    case 'EXPIRED': return { index: -1, rejected: 'EXPIRED' }
    default: return { index: 0 }
  }
}

function short(s: string) { return s.split(':').pop() || s }

export default function OrderTimeline({ symbol }: { symbol: string }) {
  const { data, isLoading } = useOrders()
  const orders = ((data as { orders?: any[] } | undefined)?.orders || []) as any[]

  const list = useMemo(() => {
    const mine = orders.filter(o => o.symbol === symbol || o.symbol?.endsWith(symbol.split(':').pop()))
    const src = mine.length ? mine : orders
    return [...src].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).slice(0, 8)
  }, [orders, symbol])

  if (isLoading) return <span className="t-faint" style={{ fontSize: 11 }}>Loading orders…</span>
  if (!list.length) return <span className="t-faint" style={{ fontSize: 11 }}>No orders yet — place one from the action bar above.</span>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {list.map(o => {
        const st = stageOf(o.status)
        const reason = o.reason || o.message || o.reject_reason
        return (
          <div key={o.id} className="t-panel" style={{ padding: '9px 12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7, fontSize: 11 }}>
              <span className={`t-num ${o.side === 'BUY' ? 't-up' : 't-down'}`} style={{ fontWeight: 800 }}>{o.side}</span>
              <span style={{ fontWeight: 700 }}>{short(o.symbol)}</span>
              <span className="t-faint">{o.quantity} qty{o.average_price ? ` @ ${o.average_price}` : ''}</span>
              {o.is_paper && <span className="t-badge t-badge-cyan" style={{ fontSize: 8 }}>PAPER</span>}
              <span className="t-faint" style={{ fontSize: 9, marginLeft: 'auto' }}>
                {new Date(o.created_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
            {st.rejected ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="t-badge t-badge-red" style={{ fontSize: 9 }}>{st.rejected}</span>
                <span className="t-faint" style={{ fontSize: 10 }}>{reason || 'No reason provided'}</span>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
                {STAGES.map((label, i) => {
                  const done = i < st.index
                  const current = i === st.index
                  return (
                    <div key={label} style={{ display: 'flex', alignItems: 'center', flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 5, flex: 1, minWidth: 0 }}>
                        <span className="t-dot"
                          style={current
                            ? { background: 'var(--cyan)', boxShadow: '0 0 8px var(--cyan)', animation: 't-pulse 1.7s ease-in-out infinite' }
                            : done ? { background: 'var(--green)', boxShadow: '0 0 6px var(--green)' } : { background: 'var(--border-hi)' }} />
                        <span style={{
                          fontSize: 8, fontWeight: current ? 800 : 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                          color: current ? 'var(--text)' : done ? 'var(--text-sub)' : 'var(--text-faint)',
                        }}>{label}</span>
                      </div>
                      {i < STAGES.length - 1 && <div style={{ flex: 1, height: 1, background: done || current ? 'var(--green)' : 'var(--border)' }} />}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
