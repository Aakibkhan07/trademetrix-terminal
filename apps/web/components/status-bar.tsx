'use client'

import { useEffect, useState } from 'react'
import { useMarketData } from '@/lib/use-market-data'

export default function StatusBar() {
  const { connected, feedMode } = useMarketData()
  const [time, setTime] = useState('')

  useEffect(() => {
    const update = () => setTime(new Date().toLocaleTimeString())
    update()
    const id = setInterval(update, 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="t-statusbar">
      <div className="t-statusbar-left">
        <span className="t-status-item">
          <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-red'}`} />
          {connected ? 'CONNECTED' : 'DISCONNECTED'}
        </span>
        <span className="t-status-item">
          FEED: {feedMode === 'idle' ? 'NONE' : feedMode.toUpperCase()}
        </span>
        <span className="t-status-item">
          SYS: OK
        </span>
        <span className="t-status-item" style={{ fontFamily: 'var(--font-mono)', fontSize: 9 }}>
          v{process.env.NEXT_PUBLIC_APP_VERSION || '0.0.0'}
        </span>
      </div>
      <div className="t-statusbar-right">
        <span>{time} UTC</span>
      </div>
    </div>
  )
}
