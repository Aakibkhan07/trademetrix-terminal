'use client'
import { useApi } from '@/lib/use-api'
import { fmtMoney, fmtNum, NO_VALUE } from '@/lib/format'
import { journalNarrative, type JournalResponse } from '@/lib/journal'
import { API_BASE } from '@/lib/api'

/**
 * What `GET /ai/journal?lookback_days=1` actually answers — `ai/journal.py::analyze_trades`.
 *
 * This page used to declare a third shape that no endpoint returns:
 * `{ entries: [{ date, pnl, trades_count, win_rate }], total_pnl, total_trades, win_rate,
 * max_drawdown }`. Neither `/ai/journal` (`{ analysis, stats }`) nor `/ai/journal/entries`
 * (`{ entries }` of `journal_entries` rows, which carry `entry_type`/`content`/`tags`) matches
 * it, and `GET /reports/daily` — the endpoint named after this page — is a scaffold that says
 * so in its own body: *"Use /ai/journal?lookback_days=1 for real daily P&L"*.
 *
 * So four of the five tiles read `undefined`, and because the guard was `{data ? … : '—'}`
 * it checked the *envelope* rather than the *field*, which protected nothing. `max_drawdown`
 * then reached `.toFixed` on `undefined` and threw, putting the page into its error boundary:
 * "Something went wrong", twice over.
 *
 * `pnl`, `win_rate` and `max_drawdown` are not computed anywhere in the codebase. Rather than
 * keep tiles labelled with figures nothing produces, the tiles below are labelled with what the
 * response really carries, and the figures that do not exist are not shown at all. Adding them
 * later means adding them to `_compute_stats` first.
 */
export default function DailyReportPage() {
  const today = new Date().toISOString().slice(0, 10)
  const { data, loading } = useApi<JournalResponse>(`/ai/journal?lookback_days=1`)
  const stats = data?.stats ?? {}
  const analysisText = journalNarrative(data?.analysis)

  // Built from API_BASE rather than written out. The previous version hardcoded
  // `http://127.0.0.1:8000`, which answers on the VPS host only if port 8000 is published —
  // production compose does not publish it — and omitted `-X POST` on a POST endpoint, so the
  // documented cron returned 405 and the daily report never arrived.
  const cronUrl = `${API_BASE}/reports/daily/send`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 900, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 700, margin: 0, letterSpacing: '-0.02em' }}>Daily Report — {today}</h1>
          <p style={{ color: 'var(--text-sub)', fontSize: 14, margin: '4px 0 0' }}>Institutional 1-pager · P&L, trades, win, drawdown · auto-emailed 18:00 IST + Telegram</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="t-btn" onClick={() => window.print()}>Print / Save PDF</button>
          <button className="t-btn t-btn-primary" onClick={() => alert('Daily report will be auto-sent 18:00 IST via Email + Telegram when RESEND_API_KEY + TELEGRAM_BOT_TOKEN are set. Configure in VPS .env.')}>Enable Auto-Send</button>
        </div>
      </div>

      {loading ? <div className="t-panel" style={{ padding: 20, textAlign: 'center' }}><span className="t-faint">Loading…</span></div> : (
        <div className="t-grid-4">
          {/* Labelled with what `_compute_stats` actually returns. The previous labels —
              Net P&L Today, Win Rate, Max DD — named figures no endpoint computes, so three
              of the four tiles were promises nothing kept. */}
          <div className="t-panel" style={{ padding: '14px 16px' }}>
            <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Total Trades</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 24, fontWeight: 700, color: 'var(--text)', marginTop: 4 }}>{fmtNum(stats.total_trades, 0)}</div>
            <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 2 }}>
              {stats.total_trades ? `over ${stats.period_days ?? 1}d` : 'no trades in window'}
            </div>
          </div>
          <div className="t-panel" style={{ padding: '14px 16px' }}>
            <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Buys / Sells</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 24, fontWeight: 700, color: 'var(--text)', marginTop: 4 }}>
              {fmtNum(stats.buy_trades, 0)} / {fmtNum(stats.sell_trades, 0)}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 2 }}>order sides</div>
          </div>
          <div className="t-panel" style={{ padding: '14px 16px' }}>
            <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Symbols Traded</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 24, fontWeight: 700, color: 'var(--text)', marginTop: 4 }}>{fmtNum(stats.unique_symbols, 0)}</div>
            <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 2 }}>distinct instruments</div>
          </div>
          <div className="t-panel" style={{ padding: '14px 16px' }}>
            <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Traded Value</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 24, fontWeight: 700, color: 'var(--text)', marginTop: 4 }}>
              {stats.total_value === undefined || stats.total_value === null ? NO_VALUE : `₹${fmtMoney(stats.total_value)}`}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 2 }}>not P&amp;L — turnover</div>
          </div>
        </div>
      )}

      {/* The narrative is the one genuinely rich thing the endpoint returns, so it gets real
          estate instead of being buried. It reads as a plain sentence when the AI is not configured,
          which is itself worth showing rather than hiding. */}
      {analysisText && (
        <div className="t-panel" style={{ padding: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>Journal</div>
          <div style={{ fontSize: 14, color: 'var(--text-sub)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
            {analysisText}
          </div>
        </div>
      )}

      <div className="t-panel" style={{ padding: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>How it works</div>
        <ol style={{ margin: 0, paddingLeft: 18, fontSize: 14, color: 'var(--text-sub)', lineHeight: 1.7 }}>
          <li>Every trading day 18:00 IST the server aggregates each tenant&apos;s filled <code>orders</code> into <code>stats</code> — trade count, side split, symbols touched and turnover — which is what the tiles above show.</li>
          <li>Daily P&amp;L (FIFO), win rate and drawdown are <strong>not</strong> computed yet. Adding them means extending <code>_compute_stats</code> in <code>ai/journal.py</code>; they are deliberately absent here rather than shown as zero.</li>
          <li>PDF is rendered from this page (Print → Save as PDF) and also pushed via <code>RESEND_API_KEY</code> (email) + <code>TELEGRAM_BOT_TOKEN</code> (Telegram) when set.</li>
          <li>Audit trail is the `audit_log` table — each trade, kill-switch, broadcast is logged.</li>
        </ol>
        <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
          <a href="/journal" className="t-btn t-btn-sm" style={{ textDecoration: 'none' }}>Open Journal →</a>
          <a href="/live" className="t-btn t-btn-sm t-btn-primary" style={{ textDecoration: 'none' }}>Go Live</a>
        </div>
      </div>

      <div style={{ fontSize: 12, color: 'var(--text-faint)', textAlign: 'center' }}>Tip: Set <code>RESEND_API_KEY</code> + <code>TELEGRAM_BOT_TOKEN</code> in VPS <code>apps/api/.env</code> and add a cron <code>0 18 * * 1-5 curl -s -X POST {cronUrl} -H &quot;X-Cron-Secret: $CRON_SECRET&quot;</code> — scaffold ready, keys already in .env.</div>
    </div>
  )
}
