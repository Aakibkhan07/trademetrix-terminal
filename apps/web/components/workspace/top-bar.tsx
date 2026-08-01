'use client'

import { type ReactNode } from 'react'
import { useMarketData } from '@/lib/use-market-data'
import { useBrokerCredentials } from '@/lib/queries/misc'

interface TopBarProps {
  search?: ReactNode
  notifications?: ReactNode
}

export default function WorkspaceTopBar({ search, notifications }: TopBarProps) {
  const { connected, feedMode } = useMarketData()
  const { data: credsData } = useBrokerCredentials()

  const credentials = (credsData as { credentials?: { broker: string; is_active: boolean; token_status?: string }[] } | undefined)?.credentials || []

  const activeCred = credentials.find(c => c.is_active)
  const tokenOk = activeCred?.token_status === 'valid'

  return (
    <div style={{
      height: 52, flexShrink: 0, borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', gap: 18, padding: '0 16px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
        <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-red'}`} />
        <span className={connected ? 't-up' : 't-down'} style={{ fontWeight: 700 }}>{connected ? 'LIVE' : 'OFFLINE'}</span>
        {feedMode === 'simulator' && <span className="t-badge t-badge-amber">SIM</span>}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
        <span className="t-faint">BROKER</span>
        {activeCred ? (
          <>
            <span style={{ fontWeight: 700, textTransform: 'capitalize' }}>{activeCred.broker}</span>
            <span className={`t-chip ${tokenOk ? '' : 't-chip-warn'}`} style={{ fontSize: 9 }}>
              {tokenOk ? 'TOKEN OK' : 'RE-AUTH NEEDED'}
            </span>
          </>
        ) : (
          <span className="t-faint">not connected</span>
        )}
      </div>

      {search && <div style={{ flex: 1, maxWidth: 360, marginLeft: 'auto' }}>{search}</div>}

      {notifications}
    </div>
  )
}
