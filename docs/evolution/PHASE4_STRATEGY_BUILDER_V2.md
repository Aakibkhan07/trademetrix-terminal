# Phase 4 — Strategy Builder V2 (Design)

> Date: 2026-07-31 · Owner: TradeMetrix product · Status: Approved for phased implementation
> Product rule: no new features when an existing module can be extended · no duplicate UI/APIs · reuse components · integrate into the Trading Workspace · one ecosystem.

## 1. Scope & Grounding

### What already exists (reuse, do not duplicate)

| Asset | Where | Status |
|---|---|---|
| Graph-DSL strategy engine (blocks, compiler, runtime, publish/start/stop) | `apps/api/builder/*` + `engine/graph_strategy_runner.py` | Fully wired backend, **consumed by no page** |
| Block library (~110 blocks: indicator/SMC/ICT/time/risk/order/oi/greek) | `apps/api/builder/blocks.py` | Exposed via `/builder/blocks` |
| 10 DSL templates (ema_crossover, opening_range_breakout, vwap_mean_reversion, rsi_mean_reversion, bollinger_bandit, smc_order_block, macd_cross, scalping, ict_silver_bullet, expiry_hunter) | `apps/api/builder/templates.py` | Covers required template list (Breakout/Intraday map to the ORB/scalping/expiry templates + builtin classes) |
| NL → DSL generation | `POST /ai/build-strategy` (`apps/api/ai/strategy_builder.py`) | Beginner mode backend exists |
| Lifecycle endpoints | `/builder/strategies` CRUD + `validate/compile/preview/publish/archive/backtest/start/stop` | All present |
| Versioning | `/builder/strategies/{id}/versions` + `clone` + `rollback/{version}` + `import/export` | All present (in-memory only — see §5 risk) |
| Frontend `api.builder.*` client | `apps/web/lib/api.ts:507-532` | Present, unused by any page |
| Analytics lib for live preview | `components/workspace/indicator.ts` (ema/rsi/macd/adx/vwap/swings/aiSummary) | Workspace-grade, pure TS |
| Live feed + candles | `useMarketData()` + `api.marketdata.historical` | Present |
| Deployment UX patterns | `quick-order-drawer.tsx` (paper/live segmented, risk math), `/engine/start`, `/builder/.../start`, `/risk/live/enable` gate, `/engine/squareoff/config` | Present |
| Workspace shell + design system | `workspace/sidebar.tsx`, `top-bar.tsx`, `.t-*` primitives, `useUIStore` symbol context | Present |
| Strategy home | `/strategies` page (list + create modal), sidebar Automate → `/strategies`, action-bar 🤖 → `/strategies?symbol=` | Present |
| Legacy dead-end canvas | `app/strategies/builder/page.tsx` (frontend-only block layout persisted as `config`, never executed) | **Superseded by V2** |

### What V2 adds
1. The first real frontend over the DSL engine, inside the workspace ecosystem.
2. Beginner mode (plain-English guided builder) reusing `/ai/build-strategy`.
3. Advanced drag & drop canvas reusing the real `/builder/blocks` library.
4. Validation UX (client checks + `/validate` + live preview + NL summary, no new APIs).
5. Deployment wizard reusing the existing publish → start flow (paper/live gate, capital/risk/schedule).
6. Versioning UI over the existing versions/clone/rollback endpoints.
7. **Persistence fix** for the builder manager (currently in-memory → data loss on restart; see §5).

## 2. Key decisions

- **D1 — Route**: V2 supersedes the legacy dead-end canvas **at the same route** `/strategies/builder` (no duplicate UI; legacy page removed; git history retains it). The workspace action bar 🤖 Strategy and sidebar Automate launch it.
- **D2 — Engine untouched**: zero changes to `engine/*`, `oms/*`, `risk/*` execution paths, or broker adapters. All execution reuses `/builder/strategies/{id}/start` (graph runner) and the existing live gate.
- **D3 — Backend delta (minimal, non-engine)**: add Supabase persistence for builder DSL + versions (new `builder_strategies` + `builder_strategy_versions` tables, write-through in `builder/manager.py`). Required for production stability (mandate). No new endpoints; existing routes keep their shapes.
- **D4 — NL summary is client-side**: rule-based sentence generation from the DSL nodes (reuses `indicator.ts` vocabulary + `aiSummary` conventions). Deterministic, no LLM dependency in the critical path; the AI path is reserved for Beginner-mode NL→DSL generation (`/ai/build-strategy`).
- **D5 — Mode switch**: single page, two tabs — Beginner (guided) / Advanced (canvas). Beginner output is a DSL too; user can continue in Advanced at any time.
- **D6 — Live preview**: only needs candles + ticks + `indicator.ts`; computed client-side (no new preview API; `/builder/.../preview` also surfaces server-side signal state when available).

## 3. UX Wireframes

### W1 — Strategies home (`/strategies`, extended)
```
┌──────────────────────────────────────────────────────────────────┐
│ Strategies                [+ New Strategy ▾]  [Templates]        │
│  ┌──────────────────────┐ ┌ Beginner (guided)                    │
│  │ MY BUILDER STRATEGIES│ └ Advanced (canvas)                    │
│  │  EMA Cross 15m  ●RUNNING PAPER   ▶ ⚙ ⧉ ⎘ 🗑                  │
│  │  SMC Order Block    DRAFT         ▶ ⚙ ⧉ ⎘ 🗑                  │
│  └──────────────────────┘                                         │
│  LEGACY (builtin)  …existing rows unchanged…                     │
└──────────────────────────────────────────────────────────────────┘
```
- New "MY BUILDER STRATEGIES" section on the existing page listing `/builder/strategies`
- Status chips DRAFT / PUBLISHED / RUNNING (from `strategy_runs` + `strategy_health`)
- Row actions: ▶ Deploy · ⚙ Edit (→ builder) · ⧉ Clone · ⎘ Versions · 🗑 Delete
- "Templates" opens the template gallery (W2)

### W2 — Template gallery (part of builder start)
```
┌──────────────────────────────────────────────────────┐
│  START FROM TEMPLATE            [Blank canvas] [AI ✨]│
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐         │
│  │EMA Cross│ │ ORB    │ │ VWAP   │ │ SMC OB │         │
│  │15m NIFTY│ │9:15-9:30││mean-rev│ │order blk│        │
│  ├────────┤ ├────────┤ ├────────┤ ├────────┤         │
│  │Scalping│ │MACD    │ │ICT SB  │ │RSI mean│         │
│  └────────┘ └────────┘ └────────┘ └────────┘         │
│  [Use → loads DSL into canvas]                       │
└──────────────────────────────────────────────────────┘
```

### W3 — Beginner mode
```
┌─────────────────────────────────────────────────────────────────┐
│ ⭐ New Strategy · Beginner                    [Advanced mode ▸] │
│  DESCRIBE IN PLAIN ENGLISH (pre-filled symbol from workspace)   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Buy NIFTY when EMA 9 crosses above EMA 21, exit at +1%    │  │
│  │ target with 0.5% SL, only 09:30–14:30 on weekdays         │  │
│  └───────────────────────────────────────────────────────────┘  │
│  [✨ Generate strategy]                                         │
│  ┌────────────────────────────────────┐ ┌────────────────────┐  │
│  │ YOUR PLAN (NL summary)             │ │ SETTINGS           │  │
│  │ 1. Buy when EMA9 crosses above     │ │ Symbol    NIFTY ▾  │  │
│  │    EMA21 on the 5m chart           │ │ Interval  5m ▾     │  │
│  │ 2. Target +1% · Stop −0.5%         │ │ Trigger   CANDLE ▾ │  │
│  │ 3. Only 09:30–14:30, Mon–Fri       │ │ Positions 1        │  │
│  │    ✓ Valid · 6 nodes · 5 edges     │ │ [Validate] ✓       │  │
│  └────────────────────────────────────┘ └────────────────────┘  │
│  [💾 Save draft]  [Continue in Advanced ▸]  [▶ Publish & Deploy]│
└─────────────────────────────────────────────────────────────────┘
```

### W4 — Advanced mode (canvas)
```
┌───────────────────────────────────────────────────────────────────────────┐
│ ⭐ Strategy Builder · Advanced               [◀ Beginner] [✓][✓ Validate] │
│  SETTINGS BAR: Symbol ▾ Interval ▾ Trigger ▾ MaxPos ▾   [▶ Deploy]        │
│┌ PALETTE ───────────┬─────────────── CANVAS ──────────────────────────────┐│
││ INDICATORS         │  [EMA 9]──────▶[cross_above]──▶[logic.and]──▶[buy]  ││
││  EMA · SMA · RSI   │  [EMA 21]──────▶[cross_above]──┘    ▲      │        │
││  MACD · ADX · ATR  │  [time.range 9:15–9:30]────────────────┘  [exit]    │
││  VWAP · Bollinger  │  [indicator.atr]──▶[risk.max_loss]                  │
││ SMC / ICT          │                                                    │
││  order_block · FVG │                                                    │
││  liquidity · MSS   │──────────────── LIVE PREVIEW ──────────────────────│
││ TIME · RISK        │  EMA9 24123.4 ↑ · EMA21 24118.7 · cross TRUE       │
││ ORDER · SOURCES    │  last 24145 (5m) · ATR 18.2 · risk ₹1,000 ≤ max    │
│└────────────────────┴────────────────────────────────────────────────────┘│
│  VALIDATION: ✓ valid · NL summary: "Buy NIFTY when EMA9 crosses above    │
│  EMA21 within 09:15–09:30, one position, max loss ₹1,000 per trade."     │
└───────────────────────────────────────────────────────────────────────────┘
```

### W5 — Deploy modal (reuses drawer patterns)
```
┌──────────────────────────────────────────┐
│  DEPLOY — EMA Cross 15m                  │
│  Broker      [fyers ▾  token ✓]          │
│  Mode        [ PAPER | LIVE ] (live gated│
│              by /risk/live/enable)       │
│  Capital     ₹100,000 (from /engine/funds)│
│  Risk/trade  [1] % → ₹1,000 · RR preview │
│  Schedule    Entry 09:30 · Exit 14:30    │
│              Days Mon–Fri · Square-off ✓ │
│  [🚀 Publish & Start]   (needs PUBLISHED)│
└──────────────────────────────────────────┘
```

### W6 — Versions drawer
```
┌──────────────────────────────────────────┐
│  VERSIONS — SMC Order Block  v3          │
│  v3 · today 14:02 · current              │
│  v2 · today 11:47   [View] [Rollback]    │
│  v1 · yesterday      [View] [Rollback]   │
│  [⧉ Clone as new] [💾 Save As…] [⇩ Export]│
└──────────────────────────────────────────┘
```

## 4. Component tree

```
components/workspace/strategy-builder/
├── strategy-builder.tsx        # top-level: Beginner|Advanced tabs, header actions, settings bar
│   ├── beginner-builder.tsx    # NL input + /ai/build-strategy + guided settings
│   │   └── nl-summary-card.tsx # generated plan + NL summary (DSL → sentences)
│   ├── advanced-builder.tsx    # palette + canvas + validate strip
│   │   ├── block-palette.tsx   # /builder/blocks grouped by category
│   │   ├── canvas.tsx          # HTML5 drag&drop nodes + port edges (no new deps)
│   │   │   ├── canvas-node.tsx # draggable node, param editor from ParamDef
│   │   │   └── canvas-edge.tsx # connection renderer
│   │   ├── live-preview.tsx    # historical candles + useMarketData ticks + indicator.ts
│   │   └── validate-strip.tsx  # client checks + /validate errors + NL summary
│   ├── template-gallery.tsx    # /builder/templates picker
│   ├── deploy-modal.tsx        # broker/mode/capital/risk/schedule → publish+start
│   └── versions-drawer.tsx     # versions/clone/rollback/export + Save As
```
Reused (no copies): `workspace/sidebar.tsx` shell style, `top-bar.tsx`, `indicator.ts`, `useMarketData`, `useUIStore` (symbol context + recents), `api.builder.*` + new `api.ai.buildStrategy`, `.t-*` primitives, paper/live segmented pattern from `quick-order-drawer.tsx`, `useRuns` for running-state chips, notifications via existing popover.

## 5. Production-stability delta (backend, non-engine)

**Problem:** `builder/manager.py` keeps DSL + versions in module-level dicts → every strategy vanishes on API restart.
**Fix (write-through, engine untouched):**
- New tables (SQL migration, Supabase):
  - `builder_strategies(id uuid pk, user_id, name, description, tags jsonb, settings jsonb, nodes jsonb, edges jsonb, status text, version_number int, parent_id uuid, created_at, updated_at)`
  - `builder_strategy_versions(id uuid pk, strategy_id fk, version int, data jsonb, saved_at)`
- `BuilderManager` gains `_load(user_id)` (on first access / startup) and write-through on every mutation (`create/update/clone/rollback`). Route handlers unchanged.
- Existing `strategy_runs` + `strategy_health` already persist run state — unchanged.

## 6. API reuse plan (no new endpoints)

| V2 feature | Reused endpoint | New frontend client |
|---|---|---|
| Beginner NL→DSL | `POST /ai/build-strategy` | `api.ai.buildStrategy(prompt)` |
| Block library | `GET /builder/blocks`, `/blocks/categories` | `api.builder.blocks/categories` (exists) |
| Create/list/get/update/delete | `/builder/strategies` CRUD | exists |
| Validate / compile / preview | `POST /builder/strategies/{id}/validate|compile|preview` | exists |
| Publish (required before start) | `POST /builder/strategies/{id}/publish` | exists |
| Run lifecycle | `POST /builder/strategies/{id}/start` (`{symbol, interval}`), `/stop` | exists |
| Backtest | `POST /builder/strategies/{id}/backtest` | exists |
| Templates | `GET /builder/templates`, `/templates/{key}` | exists |
| Versioning | `/versions`, `/clone`, `/rollback/{v}`, `/import`, `/export` | exists |
| Live preview data | `api.marketdata.historical` + `useMarketData().ticks` + `indicator.ts` | exists |
| Broker/mode/capital | `/engine/funds`, `/brokers` list, `/risk/live/enable` gate, drawer paper/live pattern | exists |
| Schedule | `/engine/squareoff/config` + DSL time blocks | exists |
| Run status / notify | `useRuns()` + notifications popover | exists |
| NL summary (display) | client-side rule-based from DSL (no API) | new local util `dsl-summary.ts` |

**Backend changes total:** 1 migration + write-through in `builder/manager.py`. No new routes, no engine/OMS/risk/broker changes.

## 7. Implementation phases (regression gate after each)

| Phase | Scope | Regression gate (prod) |
|---|---|---|
| **4.1 Foundations** | Persistence fix (migration + manager write-through); `api.ai.buildStrategy`; workspace entry points (action bar 🤖 → builder with active symbol; sidebar Automate); route shell at `/strategies/builder` (workspace-styled, Beginner/Advanced tabs); template gallery; create-from-template; save draft; `dsl-summary.ts` NL summary card | /workspace action bar 0 errors; /strategies & /strategies/builder render 200; create+reload survives API restart (persistence proof); 0 page errors |
| **4.2 Advanced canvas** | palette from `/builder/blocks`; HTML5 drag&drop nodes; port wiring; `node-config.tsx` param editor from ParamDef; settings bar; save/load DSL | canvas renders blocks; create/edit/save round-trip; 0 errors |
| **4.3 Validation + live preview** | client-side checks (required params, dangling ports, no cycle); `/validate` errors in strip; live-preview component (historical + ticks + indicator.ts) | invalid strategy blocked at publish; preview shows real values for active symbol; 0 errors |
| **4.4 Deployment** | deploy modal (broker/mode/capital/risk/schedule); publish→start/stop; paper/live gate; running chip + notifications; backtest button | paper run starts/stops via existing runner; live gated; 0 errors |
| **4.5 Beginner mode + versioning** | NL→DSL flow wired end-to-end; versions drawer (clone/save-as/rollback/export); home page builder section; legacy canvas removal | full E2E: NL → generate → validate → publish → deploy → stop; clone/rollback round-trip; regressions /portfolio /marketdata /trade /portal /dashboard /workspace all 0 |

## 8. Risks & mitigations

- **In-memory builder manager** → §5 persistence fix, verified by restart test in 4.1 gate.
- **`require_feature("builder")` 403** → capability check surfaced in UI (upgrade prompt) — existing pattern.
- **Live mode safety** → reuses `/risk/live/enable` confirm gate + broker token status chip; paper default everywhere.
- **Canvas complexity** → HTML5 native DnD, no new dependency; port-edge model mirrors `GraphEdge` 1:1 so save/load is lossless.
- **AI NL generation quality** → generated DSL passes the same `/validate` gate as manual; user can always switch to Advanced to fix.
- **Synthetic historical data** (`/marketdata/historical` fallback) → preview labels data source (REAL/SIM) like the analyzer already does; `/market/historical` (real-only) used when available.
