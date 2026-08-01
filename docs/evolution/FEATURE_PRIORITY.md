# FEATURE_PRIORITY.md

Scored by user impact × effort × risk to production. Backend untouched in all phases.

| Priority | Feature | Phase | Why | Effort |
|---|---|---|---|---|
| P0 | Quick Order Drawer (3-click order) | 1 | Kite-parity entry surface; unblocks every later phase (all flows land here) | M |
| P0 | Drawer wiring into watchlist rows (BUY/SELL) | 1 | Same feature — the actual 3-click path | S |
| P0 | Margin preview + charges estimate in drawer | 1 | Required by mandate; existing margin API | S |
| P1 | Multi-watchlist + drag-drop hub | 2 | Watchlist becomes trading hub; biggest daily surface | M |
| P1 | Watchlist quick actions (Chart/Chain/Analyzer/Backtest/Alert) | 2 | Cross-module navigation without leaving screen | M |
| P1 | Analyzer in-portal (chart + indicators + chain + AI) | 3 | Consolidates analyzer.trademetrix.tech; mandates integration | L |
| P1 | Analyzer action bar (Trade/Backtest/Strategy/Portfolio) | 3 | Keeps user in one screen | S |
| P2 | Backtest report (Sharpe/Sortino/PF/DD/monthly/CSV) | 5 | Institutional-grade evidence; data already exists | M |
| P2 | Strategy Builder Beginner mode + NL preview | 4 | Lowers barrier; advanced canvas already exists | M |
| P2 | Portal Overview widget dashboard | 6 | Daily decision surface | M |
| P3 | TradingView Replay export (Phase 5 stretch) | 5 | Nice-to-have; heavy | L |
| P3 | Virtualization + react-query tuning | 7 | Performance hardening after features settle | M |
| P3 | AI market summary in analyzer | 3 | Reuses /ai; cheap win | S |

## Cut criteria
- Anything requiring backend changes → deferred unless it blocks a mandated flow
  (none currently; OMS auto-bracket already gives SL/Target on every trade).
- Anything that rewrites existing pages wholesale → out of scope by mandate.
- Admin panel: no user-facing features added there (RBAC separation).

## Phase gating
Ship P0 (Phase 1) first → regression → then P1 (Phases 2–3) → P2 (Phases 4–6) → P3.
