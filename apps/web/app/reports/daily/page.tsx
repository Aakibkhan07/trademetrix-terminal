'use client'
import { useState } from 'react'
import { useApi } from '@/lib/use-api'

function fmt(n: number) { return n.toLocaleString('en-IN', { maximumFractionDigits: 0 }) }

export default function DailyReportPage() {
  const today = new Date().toISOString().slice(0, 10)
  const { data, loading } = useApi<{ entries: { date: string; pnl: number; trades_count: number; win_rate: number }[]; total_pnl: number; total_trades: number; win_rate: number; max_drawdown: number }>(`/ai/journal?lookback_days=1`)
  const entry = data?.entries?.[0]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 900, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, margin: 0, letterSpacing: '-0.02em' }}>Daily Report — {today}</h1>
          <p style={{ color: 'var(--text-sub)', fontSize: 12, margin: '4px 0 0' }}>Institutional 1-pager · P&L, trades, win, drawdown · auto-emailed 18:00 IST + Telegram</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="t-btn" onClick={() => window.print()}>Print / Save PDF</button>
          <button className="t-btn t-btn-primary" onClick={() => alert('Daily report will be auto-sent 18:00 IST via Email + Telegram when RESEND_API_KEY + TELEGRAM_BOT_TOKEN are set. Configure in VPS .env.')}>Enable Auto-Send</button>
        </div>
      </div>

      {loading ? <div className="t-panel" style={{ padding: 20, textAlign: 'center' }}><span className="t-faint">Loading…</span></div> : (
        <div className="t-grid-4">
          <div className="t-panel" style={{ padding: '14px 16px' }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Net P&L Today</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 700, color: (entry?.pnl ?? 0) >= 0 ? 'var(--green)' : 'var(--red)', marginTop: 4 }}>{entry ? `${entry.pnl >= 0 ? '+' : ''}₹${fmt(entry.pnl)}` : '—'}</div>
            <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 2 }}>{entry ? `${entry.trades_count} trades` : 'No trades today'}</div>
          </div>
          <div className="t-panel" style={{ padding: '14px 16px' }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Win Rate</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 700, color: 'var(--text)', marginTop: 4 }}>{entry ? `${entry.win_rate.toFixed(1)}%` : '—'}</div>
          </div>
          <div className="t-panel" style={{ padding: '14px 16px' }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Total Trades (30d)</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 700, color: 'var(--text)', marginTop: 4 }}>{data?.total_trades ?? '—'}</div>
          </div>
          <div className="t-panel" style={{ padding: '14px 16px' }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>Max DD (30d)</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 700, color: 'var(--red)', marginTop: 4 }}>{data ? `${data.max_drawdown.toFixed(1)}%` : '—'}</div>
          </div>
        </div>
      )}

      <div className="t-panel" style={{ padding: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>How it works</div>
        <ol style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: 'var(--text-sub)', lineHeight: 1.7 }}>
          <li>Every trading day 18:00 IST, server aggregates <code>orders</code> + <code>positions_snapshot</code> for daily P&L (FIFO) + win/drawdown.</li>
          <li>PDF is rendered from this page (Print → Save as PDF) and also pushed via <code>RESEND_API_KEY</code> (email) + <code>TELEGRAM_BOT_TOKEN</code> (Telegram) when set.</li>
          <li>Audit trail is the `audit_log` table — each trade, kill-switch, broadcast is logged.</li>
        </ol>
        <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
          <a href="/journal" className="t-btn t-btn-sm" style={{ textDecoration: 'none' }}>Open Journal →</a>
          <a href="/live" className="t-btn t-btn-sm t-btn-primary" style={{ textDecoration: 'none' }}>Go Live</a>
        </div>
      </div>

      <div style={{ fontSize: 10, color: 'var(--text-faint)', textAlign: 'center' }}>Tip: Set <code>RESEND_API_KEY</code> + <code>TELEGRAM_BOT_TOKEN</code> in VPS <code>apps/api/.env</code> and add a cron <code>0 18 * * 1-5 curl -s http://127.0.0.1:8000/api/v1/reports/daily/send -H X-Cron-Secret:$CRON_SECRET</code> — scaffold ready, keys already in .env.</div>
    </div>
  )
}
