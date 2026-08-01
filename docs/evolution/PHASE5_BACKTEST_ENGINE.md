# Phase 5 — Institutional Backtest Engine (Design Document)

Date: 2026-08-01
Status: Approved — implementation begins after this doc

---

## 1. Objective

Complete the Build → Backtest → Optimize → Deploy loop entirely inside TradeMetrix:

- Build: Strategy Builder (done, Phase 4.3)
- **Backtest: this phase — institutional-grade backtesting for Indian markets**
- Optimize: parameter optimization, walk-forward, Monte Carlo, sensitivity
- Deploy: one-click Paper deployment from the validated strategy

Hard constraint (per phase spec): **reuse** Strategy Builder, Execution Engine, OMS, and Risk Engine. No duplicate logic. Regression suite must stay green after every sub-phase.

## 2. Reuse Inventory (what already exists)

| Asset | File | Reuse |
|---|---|---|
| V2 backtest pipeline | `apps/api/backtest/manager.py` — `BacktestManager.run()`, pause/resume/stop, `list_runs`/`get_run` | Core runner; extended, not replaced |
| Replay engine | `apps/api/backtest/replay_engine.py` — speeds 1x/2x/5x/10x/100x/MAX, pause/resume/seek | Reuse as-is for replay mode |
| Performance analytics | `apps/api/backtest/performance.py` — win rate, PF, gross P/L, drawdown, Sharpe/Sortino/Calmar, monthly/daily returns, streaks | Extended with institutional metrics (§5) |
| Data loader | `apps/api/backtest/data_loader.py` — CSV/JSON/parquet + `historical_engine` | Extended with durable candle store + corporate actions + continuous futures (§4) |
| Historical fetch | `apps/api/market/historical.py` — Fyers (`brokers/fyers_adapter.py:get_historical`) + Yahoo fallback | Reuse as-is |
| Fill simulation | `apps/api/paper/fill_engine.py` — slippage, partial fills, charges on `PaperFill` | Charge formula reused in the backtest fill engine (§5) |
| ExecutionManager | `apps/api/execution/manager.py` — `_adapters` dict keyed `{user_id}:{broker}` | Backtest runs reuse `ExecutionManager.place_order` with a **BacktestBroker adapter** (same interface as PaperBroker) — zero OMS changes |
| Risk engine | `apps/api/risk/riskguard.py` `RiskGuard.check_order`; `risk/manager.py` `RiskManager.evaluate(dry_run=True)` | Per-trade validation in backtest when `risk_enabled` |
| Charts | `lightweight-charts` (apps/web/components/chart.tsx), SVG equity curve | Replay + markers (entry/exit/SL/TP) via lightweight-charts markers API |
| Web client | `apps/web/lib/api.ts` `api.backtest.*`, `apps/web/app/backtest/page.tsx` | Rewritten against new API surface |
| Builder compiler | `builder/compiler.py` `compile_dsl` | Backtest of **builder graph strategies** (§8) |

## 3. Architecture

```
┌───────────────────────────── Web (apps/web/app/backtest) ─────────────────────────────┐
│  Run form │ Replay viewer │ Metrics dashboard │ Charts │ Optimization │ Exports │      │
└──────────────────────────────────────┬─────────────────────────────────────────────────┘
                                       │ REST
┌──────────────────────────────────────▼─────────────────────────────────────────────────┐
│                       routes/v1_backtest.py (extended)                                  │
│  run-v3 │ status/pause/resume/seek │ optimize │ walk-forward │ monte-carlo │ sensitivity │
│  exports (csv/json/pdf) │ compare │ benchmark │ deploy-to-paper                         │
└──────────────────────────────────────┬─────────────────────────────────────────────────┘
┌──────────────────────────────────────▼─────────────────────────────────────────────────┐
│                       backtest/ package (all new modules here)                          │
│  costs.py (Indian charges model)     execution.py (BacktestBroker fill engine)          │
│  historical.py (durable candle store, continuous futures, corporate actions)            │
│  performance.py (extended)           optimizer.py (grid/WF/MC/sensitivity)              │
│  exports.py (CSV/JSON/PDF)           comparison.py (strategy vs benchmark)              │
│  manager.py (run-v3: builder + builtin strategies)                                       │
└──────────────┬───────────────────────────────┬──────────────────────────────────────────┘
               │                               │
   Reuse: ExecutionManager (adapters)   Reuse: RiskGuard/RiskManager (dry-run)
   Reuse: historical_engine / Fyers     Reuse: compile_dsl (graph strategies)
   Reuse: PortfolioManager (PnL)        Reuse: builder_manager (strategy source)
```

Backtest runs use a **fake user id** `backtest:{run_id}` (existing pattern) so all existing
OMS/Risk/Portfolio code paths work untouched. The `BacktestBroker` adapter is registered in
`ExecutionManager._adapters["backtest:{run_id}:paper"]` exactly like PaperBroker today.

## 4. Historical Data Module

### 4.1 Durable candle store (Supabase table `candles`)
Current state: candles fetched on demand from Fyers/Yahoo, cached in-memory only (30s–1h TTL).
Gap: no persistence → no institutional history, no long-range backtests, no OI history.

Migration `supabase/migrations/20250801_01200_backtest_persistence.sql`:
```sql
create table if not exists candles (
  id text primary key,               -- {exchange}:{symbol}:{interval}:{ts_iso}
  symbol text not null,
  exchange text not null,
  interval text not null,            -- 1m 5m 15m 30m 1h 1d
  ts timestamptz not null,
  open double precision, high double precision,
  low double precision, close double precision,
  volume bigint default 0,
  oi bigint default 0,
  source text default 'fyers',
  unique (symbol, exchange, interval, ts)
);
create index if not exists idx_candles_lookup on candles (symbol, exchange, interval, ts);

create table if not exists corporate_actions (
  id text primary key,
  symbol text not null,
  ex_date date not null,
  action text not null,              -- SPLIT | BONUS | DIVIDEND
  ratio text,                        -- e.g. "1:2" for splits, "1:1" bonus
  dividend_amount numeric default 0,
  record_date date
);

create table if not exists backtest_runs (
  id text primary key,
  user_id text,
  strategy_type text,
  strategy_id text,
  symbol text, interval text, days int,
  config jsonb,
  summary jsonb,
  trades jsonb,
  equity_curve jsonb,
  created_at timestamptz default now(),
  source text default 'web'
);
```

### 4.2 Data fetch pipeline (`backtest/historical.py`)
1. `BacktestHistoricalData.load(symbol, interval, start, end, source)`:
   - Hit Supabase `candles` first (range query) — durable cache.
   - Fill gaps from `historical_engine` (Fyers → Yahoo fallback) in day-chunks (Fyers limit ~1000 bars/req).
   - Upsert fetched bars (best-effort try/except, like the builder write-through pattern).
   - Return sorted `list[dict]` (existing shape: open/high/low/close/volume/oi/timestamp).
2. **Continuous futures**: symbol suffix `-CONT` (e.g. `NIFTY-CONT`). Fetch current + N prior
   months' FUT candles from symbol_master (type FUT), compute total return index:
   - Roll on the last trading day of the contract month (back-adjusted: when rolling, adjust
     prior series prices by the roll ratio `close_old/close_new` — proportional back-adjust).
   - Output a single continuous series with `adj_factor` annotation.
3. **Corporate actions**: `BacktestExecution.apply_corporate_actions(candles, symbol)` — look up
   `corporate_actions` for the symbol; price-adjust candles before the ex-date by split/bonus
   ratio; dividend = cash adjustment on cashflow. Data entry via admin endpoint + CSV import
   (NSE corporate action files). If table empty → pass-through (fail-open, logged).
4. **Options**: OHLC+OI for options symbols already flow through `Candle` (`instrument_type`,
   `oi` field). Backtest supports option symbols directly (`NSE:NIFTY26AUG25000CE`); Greeks-free
   (uses actual historical premium series when available, Black-Scholes fallback only in the
   legacy `user_strategy_backtest` path — kept as-is).

### 4.3 Supported symbols
- Index / stock cash: `NIFTY`, `BANKNIFTY`, any symbol_master EQ.
- Continuous futures: `NIFTY-CONT` (§4.2.2).
- Options: full `NSE:` Fyers symbol (actual premium history from Fyers when available).

## 5. Execution Simulation (`backtest/execution.py` + `backtest/costs.py`)

### 5.1 BacktestBroker adapter (replaces PaperBroker for backtests)
New adapter implementing the same broker interface as `PaperBroker` so `ExecutionManager` is
untouched. Fill logic (`BacktestFillEngine`) resolves orders against the loaded candle series:

| Order type | Fill rule |
|---|---|
| MARKET | Fill at current candle close × (1 ∓ slippage_pct/100); BUY worse, SELL worse |
| LIMIT (price p) | Fill if candle low ≤ p (BUY) / high ≥ p (SELL); fill at p; else PENDING → carry to next candle |
| SL-M (trigger t) | BUY triggers when high ≥ t → fill at t (worse = t × (1+slippage)); SELL when low ≤ t |
| SL-L (trigger t, price p) | Trigger as SL-M, then limit p; if p not tradeable same candle → market at close |
| Partial fills | When enabled: random 10–90% qty fill per candle, remainder carries (probabilistic, seeded per run for reproducibility) |
| Latency | `latency_candles` config: signal executes N candles later at that candle's price (models delay); fills also delayed by `broker_delay_ms` when in replay (real-time) mode |
| Charges | `costs.py` (§5.2) applied per fill, accumulated to `total_fees` |

Position/equity accounting: reuse `PortfolioManager` (already used by manager.py snapshots) —
BacktestBroker writes fills into the paper orders flow? **No** — to keep speed (MAX mode) the
adapter keeps in-memory positions and publishes snapshots; PortfolioManager is bypassed in
MAX mode and used only in replay mode (existing behavior). Simplification: BacktestBroker
maintains its own positions (long/short qty, avg price) and computes realized PnL per exit +
unrealized at mark; manager.py snapshots read from the adapter (replacing `portfolio_manager`
calls in `_collect_snapshot`).

### 5.2 Indian cost model (`backtest/costs.py`) — NEW, nothing duplicates this today
`IndianCostModel.estimate(side, value, segment, order_type, qty)` returns dict:
`slippage, brokerage, exchange_tc, stt, stamp_duty, gst, sebi, total`.

| Segment | Brokerage | STT | Exchange TC | Stamp | GST | SEBI |
|---|---|---|---|---|---|---|
| Equity delivery | 0 (or flat ₹20) | 0.1% sell | NSE 0.00297% | 0.015% buy | 18% of (brokerage+TC) | ₹10/crore |
| Equity intraday | 0.03% min ₹20 (config) | 0.025% both | NSE 0.00297% | 0.003% buy | 18% | ₹10/crore |
| Futures | 0.03% min ₹20 | 0.0125% sell | NSE 0.00173% | 0.002% buy | 18% | ₹10/crore |
| Options | flat ₹20/order | 0.0625% (0.1% on premium) sell | NSE 0.03503% | 0.003% buy | 18% | ₹10/crore |

All rates configurable via `BacktestCostConfig` (defaults = current NSE/SEBI rates, documented).
`commission_pct` is a single override knob for brokerage (kept for back-compat with the legacy
`slippage_pct/brokerage_pct` request fields).

## 6. Performance Analytics (extended `backtest/performance.py`)

Existing: net/gross PnL, win rate, PF, Sharpe, Sortino, Calmar, drawdown (max + curve),
monthly/daily returns, streaks, avg hold (duration_minutes), equity curve, trade list.

Add (all unit-testable pure functions):
- **Expectancy** = mean(PnL per trade) and **Expectancy per R** = mean(PnL / entry_risk).
- **Average RR** = avg_win / avg_loss (and median).
- **Trade distribution**: by weekday, by month, by hour-of-day, by symbol (counts + PnL).
- **Benchmark comparison**: same-period NIFTY buy & hold (from candle series) → alpha, beta,
  excess return, benchmark max DD. Pure function `benchmark_stats(candles, equity_curve)`.
- **Monthly calendar**: `{year, month, day}` → return % (for the calendar heatmap).
- Trade timeline: reuse `trades[]` (entry/exit already timestamped).

## 7. Optimization (`backtest/optimizer.py`)

All four run **strategy runs against a shared candle series** in-process (MAX speed, no replay
delay, no Supabase writes except final result). Each variant returns summary metrics.

| Mode | Algorithm | Output |
|---|---|---|
| Parameter sweep | Grid/step over declared param ranges (nested loops, max 512 combos) | Sorted table (params → net PnL, PF, DD, Sharpe), best config |
| Walk-forward | Split series into N windows (default 6); optimize on first k−1 windows' params, validate on last window; walk one window forward | Per-window (train/valid) metrics + combined out-of-sample curve |
| Monte Carlo | From a completed run: bootstrap trade order (N=2000 paths) or resample equity returns | PnL distribution: mean, 5th/50th/95th pct, probability of profit, max-DD distribution |
| Sensitivity | One-factor-at-a-time around best/base params (±20% in 5 steps) | Table of Δmetric per param (tornado data) |

Design notes:
- Optimization runs reuse `BacktestManager` internals but a **dedicated fast runner**
  (`backtest/optimizer.py::_fast_run`) — same strategy eval, same fills, no replay/snapshot
  overhead (avoids duplicating signal logic; reuses `strategy.on_candle`).
- Async: route kicks off `asyncio.create_task`, returns `optimization_id`; status polled via
  `GET /backtests/optimize/{id}/status`. Progress = combos completed / total.
- Deterministic: seeded RNG per run_id (reproducible Monte Carlo + partial fills).

## 8. Builder Strategy Backtest (reuse Strategy Builder)

`POST /backtests/run-v3` accepts **either**:
- `strategy_type` (builtin) — existing path, or
- `strategy_id` (builder DSL) — **new**: compile via `builder/compiler.compile_dsl`, execute
  via the same graph evaluation used in `engine/graph_strategy_runner.py` (reuse
  `GraphStrategyExecutor`/`process_candle` logic) feeding BacktestBroker fills.

This is the critical "backtest what you built" path — same DSL that deploys to paper/live.

## 9. Validation & Deploy (`backtest` → `paper`)

- `POST /backtests/{run_id}/deploy-to-paper` — creates a builder strategy (if from builder) or
  starts a paper run with the backtested params → reuses `routes/v1_builder.py:/deploy`
  (mode=paper). One click from results → live paper run.
- `POST /backtests/compare` — run same symbol/interval over multiple strategies → table
  (net PnL, PF, DD, Sharpe, trade count per strategy).
- Benchmark comparison built into run-v3 response (`benchmark` block).

## 10. API Surface (all under `/api/v1/backtests`)

```
POST /run-v3                     # BacktestRunRequest: strategy_type|strategy_id, symbol,
                                 #   interval, start/end or days, capital, speed,
                                 #   cost config, fill config (slippage/latency/partials),
                                 #   benchmark_symbol (default NIFTY), risk_enabled
GET  /v2/status                  # (exists) progress
POST /v2/pause|resume|stop       # (exists)
POST /v2/seek                    # {index} → replay seek (new)
GET  /runs                       # persisted runs (from backtest_runs)
GET  /runs/{run_id}              # full result incl. benchmark, distributions, calendar
POST /optimize                   # grid sweep
POST /optimize/walk-forward
POST /optimize/monte-carlo       # {run_id, paths}
POST /optimize/sensitivity       # {run_id, base_params, deltas}
GET  /optimize/{id}/status
POST /compare                    # {strategies:[...], symbol, interval, days}
GET  /export/{run_id}?format=csv|json|pdf
POST /runs/{run_id}/deploy-to-paper
POST /benchmark                  # {symbol, interval, start, end} → index stats
ADMIN POST /corporate-actions    # ingest CSV/JSON
GET  /candles/{symbol}/{interval}?start=&end=  # durable store read
```

## 11. Web UI (apps/web/app/backtest + components/backtest/)

- **Run form**: strategy source toggle (Builtin / My Strategies — lists `builder_manager`),
  symbol (cash/fut-cont/options), interval, date range, capital, speed, cost toggles
  (slippage %, brokerage, STT, charges, partial fills, latency).
- **Replay viewer**: lightweight-charts candle chart + entry/exit markers
  (`series.setMarkers` — green triangle entry, red triangle exit, dashed SL/TP lines),
  play/pause/seek slider/speed selector (reuses existing `/v2` endpoints).
- **Metrics dashboard**: KPI cards (net PnL, return %, win rate, PF, Sharpe, Sortino, Calmar,
  expectancy, avg RR, avg hold, max DD), equity curve + drawdown curve (two charts),
  monthly calendar heatmap (SVG grid), trade distribution (weekday/month/hour bars),
  trade timeline (list with entry/exit/SL/TP/reason).
- **Benchmark panel**: strategy equity vs NIFTY normalized, alpha/beta/outperformance.
- **Optimization tab**: parameter grid inputs → table; walk-forward results; Monte Carlo
  distribution histogram (SVG); sensitivity tornado (SVG).
- **Exports**: CSV (trades/equity), JSON (full result), PDF (summary report via backend).
- **Compare**: multi-strategy table.
- **Deploy to Paper** button on completed runs.

## 12. Sub-phases & Regression Gates

| # | Scope | Exit gate |
|---|---|---|
| 5.1 | Costs module (`costs.py`) + unit tests | pytest green; add costs tests |
| 5.2 | Durable candle store + historical loader + continuous futures + corporate actions | tests + local migration applied |
| 5.3 | BacktestBroker + fill engine (all order types, partials, slippage, latency) wired into manager | tests + full suite green |
| 5.4 | Performance extensions + benchmark + distributions | tests + full suite green |
| 5.5 | Optimizer (grid/WF/MC/sensitivity) + routes | tests + full suite green |
| 5.6 | run-v3 routes (builder strategies), compare, exports, deploy-to-paper, admin CA ingest | tests + full suite green |
| 5.7 | Web UI rewrite + build + typecheck | `tsc` + `next build` clean |
| 5.8 | Deploy to VPS + prod smoke + CHANGELOG + AGENTS.md | prod lifecycle verified |

Full `pytest tests/ -q` after EVERY sub-phase (current baseline: 494 passed, 1 xfailed).

## 13. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Fyers history depth/limits (~1yr, 1000 bars/req) | Durable candle store accumulates; chunked day-range fetch; Yahoo fallback; CSV/JSON import path for institutional data |
| Backtest realism (look-ahead bias) | Signals evaluated on closed candle only; fills at close/slippage; latency_n- candle option; no use of current candle high/low before close |
| ExecutionManager reuse in MAX mode too slow (validate/risk/audit per order) | BacktestBroker path short-circuits broker calls; risk check only when `risk_enabled`; no DB writes per order in MAX mode |
| Prod Supabase password blocked | Same write-through pattern as Phase 4.3: best-effort persist, in-memory fallback; migration ships ready |
| PDF generation dependency | `reportlab` added to requirements (pure-python wheel); verified in container before deploy |
| Regression breakage | Deterministic seeds; all new logic unit-tested; suite run after every sub-phase |
