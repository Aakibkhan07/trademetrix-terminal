'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import dynamic from 'next/dynamic'
import WorkspaceSidebar from '@/components/workspace/sidebar'
import WorkspaceTopBar from '@/components/workspace/top-bar'
import WatchlistPanel from '@/components/workspace/watchlist-panel'
import MarketPanel from '@/components/workspace/market-panel'
import ChartActionBar from '@/components/workspace/chart-action-bar'
import PositionCard from '@/components/workspace/position-card'
import OrderTimeline from '@/components/workspace/order-timeline'
import CommandPalette from '@/components/workspace/command-palette'
import NotificationsPopover from '@/components/workspace/notifications-popover'
import Chart from '@/components/chart'
import { useMarketData } from '@/lib/use-market-data'
import { useUIStore } from '@/lib/stores/ui-store'
import { usePositions, useOrders } from '@/lib/queries/orders'
import AlertModal from '@/components/workspace/alert-modal'

const AnalyzerPanel = dynamic(() => import('@/components/workspace/analyzer-panel'), {
  ssr: false,
  loading: () => <div className="t-faint" style={{ padding: 12, fontSize: 11 }}>Loading analyzer…</div>,
})
const OptionChainPanel = dynamic(() => import('@/components/workspace/option-chain-panel'), {
  ssr: false,
  loading: () => <div className="t-faint" style={{ padding: 12, fontSize: 11 }}>Loading chain…</div>,
})

export default function WorkspacePage() {
  const { ticks } = useMarketData()
  const { data: positionsData } = usePositions()
  const { data: ordersData } = useOrders()
  const store = useUIStore()
  const { wsPrefs, activeSymbol, activeName } = store
  const [analyze, setAnalyze] = useState<{ symbol: string; name: string } | null>(null)
  const [chainOpen, setChainOpen] = useState(false)
  const [alertItem, setAlertItem] = useState<{ symbol: string; name: string } | null>(null)

  useEffect(() => {
    store.restoreWsPrefs()
    const p = useUIStore.getState().wsPrefs
    setAnalyze(p.analyzeOpen ? { symbol: p.activeSymbol, name: p.activeName } : null)
    setChainOpen(p.chainOpen)
  }, [])

  const selectSymbol = useCallback((symbol: string, name: string) => {
    store.setActiveSymbol(symbol, name)
    store.pushRecent(symbol, name)
  }, [store])

  const openAnalyzer = useCallback((symbol: string, name: string) => {
    store.setActiveSymbol(symbol, name)
    store.setWsPrefs({ analyzeOpen: true, chainOpen: false })
    setAnalyze({ symbol, name })
    setChainOpen(false)
  }, [store])

  const closeAnalyzer = useCallback(() => {
    store.setWsPrefs({ analyzeOpen: false })
    setAnalyze(null)
  }, [store])

  const openChain = useCallback((symbol: string, name: string) => {
    store.setActiveSymbol(symbol, name)
    store.setWsPrefs({ analyzeOpen: false, chainOpen: true })
    setAnalyze(null)
    setChainOpen(true)
  }, [store])

  const onPaletteAlert = useCallback((symbol: string, name: string) => setAlertItem({ symbol, name }), [])

  const closeChain = useCallback(() => {
    store.setWsPrefs({ chainOpen: false })
    setChainOpen(false)
  }, [store])

  const positions = (positionsData as { positions?: any[] } | undefined)?.positions || []
  const orders = (ordersData as { orders?: any[] } | undefined)?.orders || []

  const position = useMemo(() => {
    const short = activeSymbol.split(':').pop()
    return positions.find(p => p.symbol === activeSymbol || p.symbol === short) || null
  }, [positions, activeSymbol])

  const holdingStart = useMemo(() => {
    const short = activeSymbol.split(':').pop()
    const fills = orders
      .filter(o => o.status === 'FILLED' && (o.symbol === activeSymbol || o.symbol === short) && o.filled_quantity > 0)
      .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    return fills.length ? new Date(fills[0].created_at).getTime() : undefined
  }, [orders, activeSymbol])

  const bottomTab = wsPrefs.bottomTab
  const [chartH, setChartH] = useState(430)

  useEffect(() => {
    const update = () => setChartH(Math.max(280, window.innerHeight - 370))
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100%', overflow: 'hidden', background: 'var(--bg)' }}>
      <WorkspaceSidebar />
      <div style={{ width: 238, flexShrink: 0, borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <WatchlistPanel activeSymbol={activeSymbol} onSelectSymbol={selectSymbol} onAnalyze={openAnalyzer} />
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <WorkspaceTopBar
          search={<CommandPalette onOpenAlert={onPaletteAlert} />}
          notifications={<NotificationsPopover />}
        />
        <ChartActionBar onAnalyze={openAnalyzer} onOpenChain={openChain} />
        <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ flex: 1, minHeight: 0, padding: 10, paddingBottom: 4 }}>
              <div style={{ width: '100%', height: '100%', minHeight: 0, overflow: 'hidden', position: 'relative' }}>
                <Chart
                  key={activeSymbol}
                  symbol={activeSymbol}
                  height={chartH}
                  interval={wsPrefs.chartInterval as '5m' | '15m' | '1h' | '1d'}
                  onIntervalChange={i => store.setWsPrefs({ chartInterval: i })}
                />
              </div>
            </div>
            <div style={{ borderTop: '1px solid var(--border)' }}>
              <div className="t-tabs" style={{ margin: 8, width: 'fit-content' }}>
                <button className={`t-tab ${bottomTab === 'position' ? 'active' : ''}`} onClick={() => store.setWsPrefs({ bottomTab: 'position' })}>Position</button>
                <button className={`t-tab ${bottomTab === 'orders' ? 'active' : ''}`} onClick={() => store.setWsPrefs({ bottomTab: 'orders' })}>Orders</button>
              </div>
              <div style={{ padding: '0 10px 12px', maxHeight: 190, overflowY: 'auto' }}>
                {bottomTab === 'position' && (
                  position
                    ? <PositionCard position={position} tick={ticks[activeSymbol]} holdingStart={holdingStart}
                        onModify={(sym, nm, side, qty) => store.openQuickOrder(sym, nm, side, qty)} />
                    : <span className="t-faint" style={{ fontSize: 11 }}>No open position for {activeName || activeSymbol}. Use BUY/SELL above to open one.</span>
                )}
                {bottomTab === 'orders' && <OrderTimeline symbol={activeSymbol} />}
              </div>
            </div>
          </div>
          {(analyze || chainOpen) && (
            <div style={{ width: 340, flexShrink: 0, borderLeft: '1px solid var(--border)', minHeight: 0, animation: 't-fade-in .18s ease' }}>
              {analyze
                ? <AnalyzerPanel symbol={analyze.symbol} name={analyze.name} onClose={closeAnalyzer} />
                : chainOpen
                  ? <OptionChainPanel symbol={activeSymbol} name={activeName} onClose={closeChain} />
                  : null}
            </div>
          )}
        </div>
      </div>
      <div style={{ width: 268, flexShrink: 0, borderLeft: '1px solid var(--border)', padding: 10, minHeight: 0 }}>
        <MarketPanel activeSymbol={activeSymbol} activeName={activeName} ticks={ticks} onAnalyze={openAnalyzer} />
      </div>

      {alertItem && <AlertModal item={alertItem} onClose={() => setAlertItem(null)} />}
    </div>
  )
}
