'use client'

import { useLiveFeed, type LiveFeedFilters } from './use-live-feed'
import { SignalCard } from './signal-card'
import { WidgetFrame } from './widget-frame'
import { EmptyState } from '@/components/ui/empty-state'

/**
 * Live Signals widget — right-rail, feed-to-workflow. Owns the SignalGenerated
 * SSE subscription (via `useLiveFeed`) and renders signal cards whose primary
 * actions (Trade / Analyze) plus overflow (Backtest / Deploy / Portfolio) wire
 * into the existing engines. While nothing is firing it stays useful by
 * listing the currently running runtime strategies.
 */
export function LiveSignals({ conn }: {
  conn: { online: boolean; sseConnected: boolean; subscribe: (type: string, cb: (e: any) => void) => () => void }
}) {
  const { filtered, signals, filters, setFilters, strategyIds, seeds } = useLiveFeed(conn.subscribe)

  return (
    <WidgetFrame
      title="Live Signals"
      subtitle={conn.sseConnected ? 'streaming' : 'reconnecting…'}
      offline={!conn.online}
      loading={false}
      error={null}
      empty={false}
    >
      <FiltersBar filters={filters} setFilters={setFilters} strategyIds={strategyIds} />

      {filtered.length === 0 ? (
        signals.length === 0 ? (
          <div>
            <EmptyState
              title={seeds.length > 0 ? 'Waiting for signal events…' : 'No signals yet'}
              description={
                seeds.length > 0
                  ? `${seeds.length} strateg${seeds.length === 1 ? 'y' : 'ies'} running — signals stream here in real time.`
                  : 'Deploy a strategy or run a backtest — its signals stream live here.'
              }
            />
            {seeds.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, padding: '0 4px 4px' }}>
                {seeds.slice(0, 8).map(s => (
                  <span key={s.strategy_id} className="t-badge t-badge-cyan" style={{ fontSize: 9 }}>
                    {s.symbol} · {s.mode}
                  </span>
                ))}
              </div>
            )}
          </div>
        ) : (
          <EmptyState title="No signals match your filters" style={{ padding: 24 }} />
        )
      ) : (
        filtered.map(s => <SignalCard key={s.signal_id} signal={s} />)
      )}
    </WidgetFrame>
  )
}

function FiltersBar({ filters, setFilters, strategyIds }: {
  filters: LiveFeedFilters
  setFilters: (f: LiveFeedFilters) => void
  strategyIds: string[]
}) {
  const seg = (key: 'mode' | 'side', opts: string[]) => (
    <div className="t-seg" style={{ gap: 0 }}>
      {opts.map(o => (
        <button
          key={o}
          type="button"
          className={`t-seg-btn ${filters[key] === o ? 'active' : ''}`}
          onClick={() => setFilters({ ...filters, [key]: o as never })}
          style={{ fontSize: 10 }}
        >
          {o === 'all' ? 'All' : o}
        </button>
      ))}
    </div>
  )

  return (
    <div style={{ display: 'grid', gap: 6, marginBottom: 8 }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        {seg('mode', ['all', 'paper', 'live'])}
        {seg('side', ['all', 'BUY', 'SELL', 'EXIT'])}
        <input
          value={filters.search}
          onChange={e => setFilters({ ...filters, search: e.target.value })}
          placeholder="Search…"
          style={{ flex: 1, minWidth: 90, fontSize: 11 }}
        />
      </div>
      {strategyIds.length > 0 && (
        <select value={filters.strategyId} onChange={e => setFilters({ ...filters, strategyId: e.target.value })} style={{ fontSize: 11 }}>
          <option value="">All strategies</option>
          {strategyIds.map(id => <option key={id} value={id}>{id}</option>)}
        </select>
      )}
    </div>
  )
}