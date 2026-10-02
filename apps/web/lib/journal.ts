/**
 * The response of `GET /ai/journal?lookback_days=N` — `ai/journal.py::analyze_trades`.
 *
 * Shared because two pages read this endpoint: the Trade Journal and the Daily Report. They were
 * each carrying their own copy of the interface, which is how the two drifted apart in the first
 * place — and how `/journal` ended up declaring a twelve-field `JournalData` that matched neither
 * this endpoint nor `/ai/journal/entries`.
 *
 * What this endpoint returns is deliberately narrow. `win_rate`, `sharpe_ratio`, `max_drawdown`,
 * `total_pnl`, `equity_curve` and `monthly_returns` are **not** here because nothing computes
 * them for live trading: those figures are backtest analytics, produced by `PerformanceAnalytics`
 * and served from `routes/v1_backtest.py`. There is no daily P&L series to derive them from
 * either — `/analytics/pnl?period=1d` returns a single float via `compute_daily_pnl_fifo`.
 *
 * So a tile reading `stats.win_rate` renders a dash, correctly. Adding those analytics means
 * computing them server-side from closed trades first.
 */

export interface JournalStats {
  /** Filled orders in the window. */
  total_trades?: number
  buy_trades?: number
  sell_trades?: number
  unique_symbols?: number
  /** Gross turnover — the summed value of those fills, not profit. */
  total_value?: number
  period_days?: number
}

export interface JournalResponse {
  /**
   * A plain sentence when the AI is not configured (`"AI journal not available. Configure
   * OPENROUTER_API_KEY."`), the model's parsed output when it is, and a short fallback on error.
   */
  analysis?: string | Record<string, unknown>
  stats?: JournalStats
}

/**
 * Renders `analysis` as text.
 *
 * It is a string on the configured and unconfigured paths but a parsed object when the model
 * answered, so both shapes reach the client and both have to display. Returns `null` when there is
 * nothing to show, so callers can skip the panel rather than render an empty one.
 */
export function journalNarrative(analysis: JournalResponse['analysis']): string | null {
  if (typeof analysis === 'string') return analysis.trim() || null
  if (analysis && typeof analysis === 'object') {
    const lines = Object.entries(analysis)
      .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
      .filter((l) => !l.endsWith(':'))
    return lines.join('\n') || null
  }
  return null
}