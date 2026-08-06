'use client'

import { useCallback, useState } from 'react'
import { api } from '@/lib/api'
import { useLiveData } from './use-live-data'
import { WidgetFrame } from './widget-frame'
import { Table } from './table'
import { OrderStatusBadge } from '@/components/ui/badge'
import { fmtInr, fmtTime, type LiveOrder } from './types'

const CANCELABLE = ['OPEN', 'PENDING', 'PARTIALLY_FILLED']

/**
 * Live Orders widget — most recent engine orders (`/engine/orders`) with the
 * canonical status badges and cancel for still-open orders.
 */
export function OrdersPanel({ offline, marketClosed }: { offline: boolean; marketClosed: boolean }) {
  const { data, loading, error } = useLiveData<{ orders: LiveOrder[] }>(
    useCallback(async () => (await api.engine.orders()) as { orders: LiveOrder[] }, []),
    { enabled: !offline },
  )
  const [cancelling, setCancelling] = useState<string | null>(null)
  const orders = data?.orders || []

  const cancel = async (id?: string, brokerOrderId?: string) => {
    const target = id || brokerOrderId
    if (!target) return
    setCancelling(target)
    try {
      await api.engine.cancelOrder(target)
    } catch {
      // error surfaces on the next poll
    } finally {
      setCancelling(null)
    }
  }

  const executed = orders.filter(o => o.status === 'FILLED').length

  return (
    <WidgetFrame
      title="Orders"
      subtitle={`${executed} executed`}
      offline={offline}
      marketClosed={marketClosed}
      loading={loading}
      error={error}
      empty={orders.length === 0}
      emptyMessage="No orders today"
    >
      <Table head={['Time', 'Symbol', 'Side', 'Qty', 'Price', 'Status', '']}>
        {orders.slice(0, 25).map(o => (
          <tr key={o.id || o.broker_order_id}>
            <td style={{ whiteSpace: 'nowrap', color: 'var(--text-faint)', fontSize: 10 }}>{fmtTime(o.created_at)}</td>
            <td style={{ fontWeight: 600, fontSize: 12 }}>{o.symbol?.split(':').pop()}</td>
            <td style={{ color: o.side === 'BUY' ? 'var(--text-green)' : 'var(--text-red)', fontWeight: 600 }}>{o.side}</td>
            <td className="t-num">{o.filled_quantity || o.quantity}</td>
            <td className="t-num">{fmtInr(o.average_price || o.price || 0)}</td>
            <td><OrderStatusBadge status={o.status} style={{ fontSize: 8 }} /></td>
            <td>
              {CANCELABLE.includes(o.status) && (o.id || o.broker_order_id) && (
                <button
                  type="button"
                  className="t-btn t-btn-xs t-btn-ghost"
                  style={{ fontSize: 10, color: 'var(--text-red)' }}
                  onClick={() => cancel(o.id, o.broker_order_id)}
                  disabled={cancelling === (o.id || o.broker_order_id)}
                >
                  {cancelling === (o.id || o.broker_order_id) ? '…' : 'Cancel'}
                </button>
              )}
            </td>
          </tr>
        ))}
      </Table>
    </WidgetFrame>
  )
}