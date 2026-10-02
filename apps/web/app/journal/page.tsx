'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useApi } from '@/lib/use-api'
import { fmtMoney, fmtNum, NO_VALUE } from '@/lib/format'
import { journalNarrative, type JournalResponse } from '@/lib/journal'

/**
 * Trade Journal.
 *
 * ## What this page used to claim, and why that was fiction
 *
 * It declared three response shapes and none of them existed. Every one was invented:
 *
 *   JournalData  { entries, total_pnl, win_rate, sharpe_ratio, max_drawdown,
 *                  total_trades, avg_win, avg_loss, largest_win, largest_loss,
 *                  monthly_returns, equity_curve }              — 12 fields
 *   Trade        { id, symbol, side, quantity, price, pnl,
 *                  status, timestamp, strategy }                 — 9 fields
 *   JournalEntry { date, pnl, trades_count, win_rate }           — unused
 *
 * `JournalData` is recognisably a **backtest result** payload — those exact field names are
 * what `PerformanceAnalytics` produces and what `routes/v1_backtest.py` serves. They were
 * applied to a page reading a live journal endpoint. `win_rate`, `sharpe_ratio`,
 * `max_drawdown_pct`, `equity_curve` and `monthly_returns` are computed for **backtests only**;
 * there is no live-trading equivalent anywhere in the codebase, and `/analytics/pnl` returns a
 * single float (today's P&L via `compute_daily_pnl_fifo`), not a series to build a curve from.
 *
 * `GET /ai/journal` actually answers `{ analysis, stats }`, where `stats` carries
 * `total_trades`, `buy_trades`, `sell_trades`, `unique_symbols`, `total_value`, `period_days` —
 * and even `total_trades` is nested one level down, so the old `journalData.total_trades` read
 * `undefined`.
 *
 * The consequence was not a crash, which is why it survived. `hasData` was
 * `journalData.total_trades > 0 || journalData.entries?.length > 0` — both `undefined`, both
 * falsy — so **the entire KPI section, equity curve and monthly-returns panel never rendered,
 * for any user, ever.** The page showed its "No trading data yet" empty state permanently while
 * looking perfectly healthy.
 *
 * The trade table was worse, because it *was* reachable. It renders when
 * `filteredTrades.length > 0`, and it was fed `/ai/journal/entries` — rows of `journal_entries`,
 * whose columns are `id, user_id, entry_type, content, tags, trade_ids, created_at`. Only `id`
 * is in the declared `Trade` shape. So `fmt(t.price)` received `undefined` and threw. Verified:
 * inserting **one** journal entry put `/journal` into its error boundary with
 * `Cannot read properties of undefined (reading 'toLocaleString')`. A user's first journal
 * entry took the page down. It stayed hidden from the route crawler only because it needs the
 * data to be present, and the test user had none.
 *
 * ## What it shows now
 *
 * Only things that exist:
 *   - the four figures `_compute_stats` really produces
 *   - the AI narrative, which is the one genuinely rich thing the endpoint returns
 *   - executed trade history from `/engine/orders`, whose rows carry real `symbol`, `side`,
 *     `quantity`, `average_price`, `status` and timestamps — so the side filter and the symbol
 *     search work for the first time
 *   - journal entries, with their real columns
 *
 * The per-trade performance analytics (win rate, Sharpe, drawdown, equity curve, monthly
 * returns, gross profit/loss) are gone rather than rendered as zero. Adding them means
 * computing them server-side from closed trades first — a feature, not a rendering fix.
 */

/** A row of the `orders` audit table, as `/engine/orders` returns it. */
interface EngineOrder {
  id: string
  symbol?: string
  side?: string
  order_type?: string
  status?: string
  quantity?: number
  filled_quantity?: number
  price?: number
  average_price?: number
  broker?: string
  is_paper?: boolean
  latency_ms?: number
  slippage?: number
  filled_at?: string | null
  created_at?: string
}

/** A row of `journal_entries`, as `/ai/journal/entries` returns it. */
interface JournalEntryRow {
  id: string
  entry_type?: string
  content?: string
  tags?: string[] | null
  trade_ids?: string[] | null
  created_at?: string
}

function downloadCSV(rows: string[][], filename: string) {
  const blob = new Blob([rows.map((r) => r.join(',')).join('\n')], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function timeLabel(iso?: string | null): string {
  if (!iso) return NO_VALUE
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return NO_VALUE
  return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export default function JournalPage() {
  const { data, loading, error } = useApi<JournalResponse>('/ai/journal?lookback_days=30')
  const stats = data?.stats ?? {}

  const analysisText = journalNarrative(data?.analysis)

  const [orders, setOrders] = useState<EngineOrder[]>([])
  const [ordersLoading, setOrdersLoading] = useState(true)
  const [ordersError, setOrdersError] = useState('')
  const [entries, setEntries] = useState<JournalEntryRow[]>([])
  const [sideFilter, setSideFilter] = useState<'ALL' | 'BUY' | 'SELL'>('ALL')
  const [searchFilter, setSearchFilter] = useState('')

  useEffect(() => {
    // `GET /engine/orders` answers `{ orders: [...] }`, so this has to be unwrapped. Handing the
    // envelope straight to `.filter` is the same mistake `/forward-test` made.
    api.engine
      .orders()
      .then((res) => {
        const rows = (res as { orders?: EngineOrder[] } | EngineOrder[])
        setOrders(Array.isArray(rows) ? rows : Array.isArray(rows?.orders) ? rows.orders : [])
      })
      .catch((e) => setOrdersError(e?.message || 'Failed to load orders'))
      .finally(() => setOrdersLoading(false))

    api.ai
      .journalEntries()
      .then((res) => {
        const rows = (res as { entries?: JournalEntryRow[] } | JournalEntryRow[])
        setEntries(Array.isArray(rows) ? rows : Array.isArray(rows?.entries) ? rows.entries : [])
      })
      .catch(() => setEntries([]))
  }, [])

  // Only executed trades belong in a journal. `filled_quantity` is the honest test rather than
  // `status === 'FILLED'`, because a partially-filled order is also real executed quantity.
  const executed = orders.filter((o) => (o.filled_quantity ?? 0) > 0)

  const filtered = executed.filter((o) => {
    // These now work: the previous filter compared against `undefined` for both values, so
    // selecting Buy or Sell always produced an empty table.
    if (sideFilter !== 'ALL' && o.side !== sideFilter) return false
    if (searchFilter && !(o.symbol ?? '').toLowerCase().includes(searchFilter.toLowerCase())) return false
    return true
  })

  const hasData = (stats.total_trades ?? 0) > 0 || executed.length > 0 || entries.length > 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="t-page-header">
        <div>
          <h1 className="t-page-title">Trade Journal</h1>
          <p className="t-page-subtitle">
            Executed trades, your own notes, and the AI read on the window
          </p>
        </div>
      </div>

      {loading && (
        <div className="t-panel" style={{ padding: 20, textAlign: 'center' }}>
          <span className="t-faint">Loading journal…</span>
        </div>
      )}

      {error && !loading && (
        <div className="t-panel" style={{ padding: 20, borderLeft: '3px solid var(--red)' }}>
          <span className="t-down">{error?.message || 'Failed to load journal data'}</span>
        </div>
      )}

      {!hasData && !loading && !error && (
        <div className="t-panel" style={{ padding: 24, textAlign: 'center' }}>
          <div style={{ fontSize: 29, marginBottom: 8 }}>T</div>
          <h3 style={{ fontSize: 19, marginBottom: 4 }}>No trading data yet</h3>
          <p className="t-faint" style={{ fontSize: 14, margin: 0 }}>
            Place a trade, or write a journal entry, and both show up here.
          </p>
        </div>
      )}

      {hasData && (
        <>
          {/* Labelled with what `_compute_stats` returns. Total P&L, win rate, Sharpe and max
              drawdown are not here: nothing computes them for live trading. */}
          <div className="t-grid-4">
            <div className="t-panel" style={{ padding: '12px 16px' }}>
              <span className="t-stat-label">Trades in window</span>
              <p className="t-stat-value">{fmtNum(stats.total_trades, 0)}</p>
              <div className="t-faint" style={{ fontSize: 12, marginTop: 2 }}>
                {stats.period_days ? `last ${stats.period_days}d` : ''}
              </div>
            </div>
            <div className="t-panel" style={{ padding: '12px 16px' }}>
              <span className="t-stat-label">Buys / Sells</span>
              <p className="t-stat-value">
                {fmtNum(stats.buy_trades, 0)} / {fmtNum(stats.sell_trades, 0)}
              </p>
              <div className="t-faint" style={{ fontSize: 12, marginTop: 2 }}>order sides</div>
            </div>
            <div className="t-panel" style={{ padding: '12px 16px' }}>
              <span className="t-stat-label">Symbols traded</span>
              <p className="t-stat-value">{fmtNum(stats.unique_symbols, 0)}</p>
              <div className="t-faint" style={{ fontSize: 12, marginTop: 2 }}>distinct</div>
            </div>
            <div className="t-panel" style={{ padding: '12px 16px' }}>
              <span className="t-stat-label">Traded value</span>
              <p className="t-stat-value">
                {stats.total_value == null ? NO_VALUE : `₹${fmtMoney(stats.total_value)}`}
              </p>
              <div className="t-faint" style={{ fontSize: 12, marginTop: 2 }}>turnover, not P&amp;L</div>
            </div>
          </div>

          {analysisText && (
            <div className="t-panel" style={{ padding: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>
                AI Journal
              </div>
              <div
                style={{
                  fontSize: 14,
                  color: 'var(--text-sub)',
                  lineHeight: 1.7,
                  whiteSpace: 'pre-wrap',
                }}
              >
                {analysisText}
              </div>
            </div>
          )}
        </>
      )}

      {/* Trade History — real executed orders. */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">Trade History</h3>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {filtered.length > 0 && (
              <button
                className="t-btn t-btn-xs t-btn-ghost"
                onClick={() => {
                  const header = ['Symbol', 'Side', 'Qty', 'Filled qty', 'Avg price', 'Status', 'Broker', 'Time']
                  const data = filtered.map((o) => [
                    o.symbol ?? '',
                    o.side ?? '',
                    String(o.quantity ?? ''),
                    String(o.filled_quantity ?? ''),
                    o.average_price != null ? String(o.average_price) : '',
                    o.status ?? '',
                    o.is_paper ? `${o.broker ?? ''} (paper)` : (o.broker ?? ''),
                    o.filled_at ?? o.created_at ?? '',
                  ])
                  downloadCSV([header, ...data], `trades-${new Date().toISOString().slice(0, 10)}.csv`)
                }}
              >
                Export CSV
              </button>
            )}
            <input
              className="t-input"
              placeholder="Filter symbol…"
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              style={{ width: 150, height: 24, fontSize: 13, padding: '2px 8px' }}
            />
            <select
              className="t-select"
              value={sideFilter}
              onChange={(e) => setSideFilter(e.target.value as 'ALL' | 'BUY' | 'SELL')}
              style={{ width: 86, height: 24, fontSize: 13, padding: '2px 8px' }}
            >
              <option value="ALL">All</option>
              <option value="BUY">Buy</option>
              <option value="SELL">Sell</option>
            </select>
            <span className="t-faint" style={{ fontSize: 13 }}>
              {filtered.length} of {executed.length} executed
            </span>
          </div>
        </div>

        {ordersLoading ? (
          <div className="t-panel-body">
            <span className="t-faint">Loading trades…</span>
          </div>
        ) : ordersError ? (
          <div className="t-panel-body">
            <span className="t-down">{ordersError}</span>
          </div>
        ) : filtered.length > 0 ? (
          <div className="t-table-wrap">
            <table className="t-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Qty</th>
                  <th>Filled</th>
                  <th>Avg price</th>
                  <th>Status</th>
                  <th>Broker</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((o) => (
                  <tr key={o.id}>
                    <td style={{ fontWeight: 600 }}>{o.symbol || NO_VALUE}</td>
                    <td className={o.side === 'BUY' ? 't-up' : o.side === 'SELL' ? 't-down' : ''}>
                      {o.side || NO_VALUE}
                    </td>
                    <td className="t-num">{fmtNum(o.quantity, 0)}</td>
                    <td className="t-num">{fmtNum(o.filled_quantity, 0)}</td>
                    <td className="t-num">
                      {o.average_price != null ? `₹${fmtMoney(o.average_price, 2)}` : NO_VALUE}
                    </td>
                    <td>
                      <span
                        className={`t-badge ${
                          o.status === 'FILLED'
                            ? 't-badge-green'
                            : o.status === 'REJECTED'
                              ? 't-badge-red'
                              : o.status === 'PENDING'
                                ? 't-badge-violet'
                                : 't-badge-cyan'
                        }`}
                      >
                        {o.status || NO_VALUE}
                      </span>
                    </td>
                    <td className="t-faint">
                      {o.broker ? `${o.broker}${o.is_paper ? ' · paper' : ''}` : NO_VALUE}
                    </td>
                    <td className="t-faint">{timeLabel(o.filled_at || o.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="t-panel-body">
            <span className="t-faint">
              {executed.length === 0
                ? 'No executed trades yet.'
                : 'No trades match those filters.'}
            </span>
          </div>
        )}
      </div>

      {/* Journal entries — real `journal_entries` rows. */}
      {entries.length > 0 && (
        <div className="t-panel" style={{ padding: 0 }}>
          <div className="t-panel-header">
            <h3 className="t-panel-title">Journal Entries</h3>
            <span className="t-faint">{entries.length} entries</span>
          </div>
          <div className="t-table-wrap">
            <table className="t-table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Entry</th>
                  <th>Tags</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id}>
                    <td className="t-faint">{e.entry_type || NO_VALUE}</td>
                    <td>{e.content || NO_VALUE}</td>
                    <td className="t-faint">
                      {Array.isArray(e.tags) && e.tags.length ? e.tags.join(', ') : NO_VALUE}
                    </td>
                    <td className="t-faint">{timeLabel(e.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}