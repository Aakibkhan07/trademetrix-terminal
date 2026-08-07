'use client'

/**
 * Trader-language strategy lifecycle labels.
 *
 * Maps backend builder statuses (DRAFT / VALIDATED / READY / PUBLISHED / PAPER /
 * LIVE / STOPPED / ARCHIVED) to the words a trader understands, plus runtime mode
 * (paper | live) to "Paper Running" / "Live Running". Pure UI mapping — backend
 * statuses are never changed.
 *
 * Keyboard-shortcut note: `data-kb` attributes are reserved for a future
 * shortcuts layer; no handlers are wired in this sprint.
 */

export type TraderStatus = 'draft' | 'backtested' | 'ready' | 'paper-running' | 'live-running' | 'paused' | 'stopped' | 'archived'

export interface TraderStatusMeta {
  label: string
  hint: string
  variant: 'violet' | 'cyan' | 'green' | 'amber' | 'red' | 'sub' | 'yellow'
}

const META: Record<TraderStatus, TraderStatusMeta> = {
  draft: { label: 'Draft', hint: 'Not yet backtested', variant: 'violet' },
  backtested: { label: 'Backtested', hint: 'Validated, ready to run on paper', variant: 'cyan' },
  ready: { label: 'Ready', hint: 'Cleared for deployment', variant: 'green' },
  'paper-running': { label: 'Paper Running', hint: 'Running on the paper account', variant: 'cyan' },
  'live-running': { label: 'Live Running', hint: 'Running on your live account', variant: 'green' },
  paused: { label: 'Paused', hint: 'Halted — no new trades until resumed', variant: 'amber' },
  stopped: { label: 'Stopped', hint: 'Stopped — positions remain until closed', variant: 'yellow' },
  archived: { label: 'Archived', hint: 'Hidden from the active list', variant: 'sub' },
}

export function traderStatusFor(status?: string | null, mode?: string | null): TraderStatus {
  const s = (status || '').toUpperCase()
  const m = (mode || '').toLowerCase()
  if (s === 'ARCHIVED') return 'archived'
  if (s === 'LIVE' || m === 'live') return 'live-running'
  if (s === 'PAPER' || m === 'paper') return 'paper-running'
  if (s === 'STOPPED' || s === 'STOPPING') return 'stopped'
  if (s === 'PAUSED') return 'paused'
  if (s === 'VALIDATED') return 'backtested'
  if (s === 'READY' || s === 'PUBLISHED') return 'ready'
  return 'draft'
}

export function traderStatusMeta(status?: string | null, mode?: string | null): TraderStatusMeta {
  return META[traderStatusFor(status, mode)]
}

export function traderStatusLabel(status?: string | null, mode?: string | null): string {
  return traderStatusMeta(status, mode).label
}
