'use client'

import { useEffect, useMemo, useState, useCallback } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { useUIStore } from '@/lib/stores/ui-store'
import { useLiveConnection } from '@/components/live/use-live-connection'
import { useLiveData } from '@/components/live/use-live-data'
import { MarketOverview } from '@/components/live/market-overview'
import { PositionsPanel } from '@/components/live/positions-panel'
import { OrdersPanel } from '@/components/live/orders-panel'
import { LiveSignals } from '@/components/live/live-signals'
import { TradingControls } from '@/components/live/trading-controls'
import { WidgetFrame } from '@/components/live/widget-frame'
import { KpiCard } from '@/components/ui/kpi-card'
import { Dot } from '@/components/ui/badge'
import Chart from '@/components/chart'
import Logo from '@/components/logo'
import { fmtInr, type LivePosition } from '@/components/live/types'

type PrimaryTab = 'positions' | 'orders' | 'portfolio'

export default function LivePage() {
  const { user, isAdmin, loading: authLoading } = useAuth()
  const conn = useLiveConnection()
  const [primaryTab, setPrimaryTab] = useState<PrimaryTab>('positions')
  const [activeSymbol, setActiveSymbol] = useState('NSE:NIFTY50-INDEX')
  const [activeName, setActiveName] = useState('NIFTY 50')

  const engine = useLiveData<{ positions: LivePosition[] }>(
    useCallback(async () => (await api.engine.positions()) as { positions: LivePosition[] }, []),
    { intervalMs: 15_000, enabled: !conn.isOffline },
  )

  const positionSymbols = useMemo(
    () => [...new Set((engine.data?.positions || []).filter(p => p.quantity !== 0).map(p => p.symbol).filter(Boolean))],
    [engine.data],
  )
  const symbolOptions = useMemo(() => {
    const options = [
      { symbol: 'NSE:NIFTY50-INDEX', name: 'NIFTY 50' },
      { symbol: 'NSE:NIFTYBANK-INDEX', name: 'BANK NIFTY' },
    ]
    for (const s of positionSymbols) {
      if (!options.some(o => o.symbol === s)) options.push({ symbol: s, name: s.split(':').pop() || s })
    }
    return options
  }, [positionSymbols])

  useEffect(() => {
    if (!symbolOptions.some(o => o.symbol === activeSymbol)) {
      setActiveSymbol(symbolOptions[0].symbol)
      setActiveName(symbolOptions[0].name)
    }
  }, [symbolOptions, activeSymbol])

  if (!authLoading && !user) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="t-panel" style={{ maxWidth: 360, textAlign: 'center' }}>
          <h3 className="t-panel-title" style={{ marginBottom: 8 }}>Sign in required</h3>
          <p className="t-faint" style={{ fontSize: 12, marginBottom: 16 }}>Your live dashboard is waiting — sign in to see positions, orders, signals and trading controls.</p>
          <Link href="/auth" className="t-btn t-btn-primary" style={{ textDecoration: 'none' }}>Sign In</Link>
        </div>
      </div>
    )
  }

  const tradeActive = () => {
    useUIStore.getState().openQuickOrder(activeSymbol, activeName)
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header style={{
        height: 56, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 24px', borderBottom: '1px solid var(--border)', flexShrink: 0,
      }}>
        <Link href="/live" style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none', fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700 }}>
          <Logo size={22} />
          <span style={{ background: 'var(--gradient-primary)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>TradeMetrix</span>
          <span className="t-badge t-badge-cyan" style={{ fontSize: 9, marginLeft: 4 }}>LIVE</span>
        </Link>
        <nav style={{ display: 'flex', gap: 14, alignItems: 'center', fontSize: 12, fontWeight: 600 }}>
          <Chip label="Market" ok={conn.isMarketOpen} text={conn.isMarketOpen ? 'OPEN' : 'CLOSED'} />
          <Chip label="Stream" ok={conn.sseConnected} text={conn.sseConnected ? 'live' : 'reconnecting'} />
          <Chip label="Online" ok={!conn.isOffline} text={conn.isOffline ? 'offline' : 'online'} />
          <Link href="/workspace" style={{ color: 'var(--text-sub)', textDecoration: 'none' }}>Workspace</Link>
          <span className="t-faint" style={{ fontSize: 11 }}>{user?.full_name || user?.email || ''}</span>
        </nav>
      </header>

      <div style={{ flex: 1, maxWidth: 1480, width: '100%', margin: '0 auto', padding: '16px 24px 40px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0, letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: conn.sseConnected ? 'var(--green)' : 'var(--amber)', boxShadow: conn.sseConnected ? '0 0 8px var(--green)' : 'none', display: 'inline-block' }} />
              Live
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, background: conn.isMarketOpen ? 'rgba(52,211,153,.12)' : 'rgba(251,191,36,.12)', border: `1px solid ${conn.isMarketOpen ? 'rgba(52,211,153,.2)' : 'rgba(251,191,36,.2)'}`, color: conn.isMarketOpen ? 'var(--green)' : 'var(--amber)' }}>{conn.isMarketOpen ? 'MARKET OPEN' : 'MARKET CLOSED'}</span>
            </h1>
            <div className="t-faint" style={{ fontSize: 12, marginTop: 4 }}>
              Institutional cockpit — positions, orders, signals and risk in one view · <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-sub)' }}>{new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })} IST</span>
            </div>
          </div>
          <div className="t-faint" style={{ fontSize: 11, display: 'flex', gap: 12, alignItems: 'center' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span className={`t-dot ${conn.sseConnected ? 't-dot-green t-dot-pulse' : 't-dot-amber'}`} /> Stream {conn.sseConnected ? 'live' : 'reconnecting'}</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span className={`t-dot ${!conn.isOffline ? 't-dot-green' : 't-dot-red'}`} /> {conn.isOffline ? 'offline' : 'online'}</span>
          </div>
        </div>

        <MarketOverview market={conn.market} marketLoading={conn.marketLoading} isOffline={conn.isOffline} />

        <div className="t-live-grid" style={{ display: 'grid', gridTemplateColumns: '300px minmax(0, 1fr) 320px', gap: 10, alignItems: 'start' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minHeight: 0 }}>
            <div className="t-seg" style={{ gap: 0 }}>
              {(['positions', 'orders', 'portfolio'] as PrimaryTab[]).map(t => (
                <button
                  key={t}
                  type="button"
                  className={`t-seg-btn ${primaryTab === t ? 'active' : ''}`}
                  onClick={() => setPrimaryTab(t)}
                  style={{ fontSize: 11, textTransform: 'capitalize' }}
                >
                  {t}
                </button>
              ))}
            </div>
            {primaryTab === 'positions' && <PositionsPanel offline={conn.isOffline} marketClosed={!conn.isMarketOpen} />}
            {primaryTab === 'orders' && <OrdersPanel offline={conn.isOffline} marketClosed={!conn.isMarketOpen} />}
            {primaryTab === 'portfolio' && <PortfolioSummary offline={conn.isOffline} />}
          </div>

          <div style={{ minHeight: 0 }}>
            <div className="t-panel" style={{ padding: 12, marginBottom: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                {symbolOptions.map(o => (
                  <button
                    key={o.symbol}
                    type="button"
                    className={`t-chip ${activeSymbol === o.symbol ? 'active' : ''}`}
                    onClick={() => { setActiveSymbol(o.symbol); setActiveName(o.name) }}
                    style={{ fontSize: 10 }}
                  >
                    {o.name}
                  </button>
                ))}
                <button type="button" className="t-btn t-btn-sm t-btn-primary" style={{ fontSize: 11, marginLeft: 'auto' }} onClick={tradeActive}>
                  Quick Trade
                </button>
              </div>
              <div className="t-faint" style={{ fontSize: 10, marginTop: 6 }}>{activeSymbol}</div>
            </div>
            <Chart symbol={activeSymbol.replace(/^NSE:/, '')} height={420} />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minHeight: 0 }}>
            <TradingControls offline={conn.isOffline} isAdmin={isAdmin} marketClosed={!conn.isMarketOpen} />
            <LiveSignals conn={{ online: !conn.isOffline, sseConnected: conn.sseConnected, subscribe: conn.subscribe }} />
          </div>
        </div>
      </div>
    </div>
  )
}

function Chip({ label, ok, text }: { label: string; ok: boolean; text: string }) {
  return (
    <span className="t-badge" style={{ fontSize: 10, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <Dot variant={ok ? 'green' : 'amber'} pulse={ok} />
      <span className="t-faint" style={{ fontWeight: 500 }}>{label}</span>
      {text}
    </span>
  )
}

interface PaperAccount {
  current_equity: number
  realised_pnl: number
  unrealised_pnl: number
  daily_pnl: number
  drawdown_pct: number
  broker: string
}

/** Portfolio snapshot tab — paper account + live broker funds (read-only, existing endpoints). */
function PortfolioSummary({ offline }: { offline: boolean }) {
  const paper = useLiveData<PaperAccount>(
    useCallback(async () => (await api.paper.account()) as PaperAccount, []),
    { intervalMs: 10_000, enabled: !offline },
  )
  const funds = useLiveData<{ funds: { total_margin: number; used_margin: number; available_margin: number } }>(
    useCallback(async () => (await api.engine.funds()) as { funds: { total_margin: number; used_margin: number; available_margin: number } }, []),
    { intervalMs: 10_000, enabled: !offline },
  )

  const f = funds.data?.funds
  const p = paper.data

  return (
    <WidgetFrame
      title="Portfolio"
      offline={offline}
      loading={paper.loading || funds.loading}
      error={paper.error || funds.error}
      empty={!p && !f}
      emptyMessage="No account data yet"
    >
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <KpiCard variant="stat" label="Paper Equity" value={fmtInr(p?.current_equity)} color="var(--green)" />
        <KpiCard variant="stat" label="Paper P&L (realised)" value={fmtInr(p?.realised_pnl)} color={p && p.realised_pnl < 0 ? 'var(--red)' : 'var(--green)'} />
        <KpiCard variant="stat" label="Paper Unrealised" value={fmtInr(p?.unrealised_pnl)} color={p && p.unrealised_pnl < 0 ? 'var(--red)' : 'var(--green)'} />
        <KpiCard variant="stat" label="Drawdown" value={p ? `${p.drawdown_pct.toFixed(2)}%` : '—'} color="var(--amber)" />
        <KpiCard variant="stat" label="Broker Margin" value={fmtInr(f?.available_margin)} color="var(--cyan)" />
        <KpiCard variant="stat" label="Margin Used" value={fmtInr(f?.used_margin)} color="var(--violet)" />
      </div>
    </WidgetFrame>
  )
}