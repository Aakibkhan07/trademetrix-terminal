# TradeMetrix Web — Browser Smoke Report (Auto Trading v1.0)

- **Date**: 2026-08-04
- **Tooling**: Playwright (Python), headless Chromium 1223 on the prod VPS
- **Auth**: minted `tm_session` HS token (API `create_access_token`) + native CSRF handshake
- **Target**: `https://ai.trademetrix.tech` / `https://api.ai.trademetrix.tech/api/v1`

## Result

| Metric | Value |
|---|---|
| Functional checks | **38 / 38 PASS** |
| Page errors (uncaught exceptions) | **0** |
| Hydration warnings | **0** |
| React warnings | **0** |
| Route load failures | 0 (all 18 routes served) |
| Verdict | **PASS** (with documented pre-existing console noise below) |

## Route sweep (18 pages, HTTP 200 + rendered DOM)

`/` `/auth` `/dashboard` `/strategies` `/strategies/builder` `/paper` `/portfolio`
`/positions` `/marketdata` `/terminal` `/terminal/option-chain` `/workspace`
`/backtest` `/risk` `/funds` `/settings` `/transparency` `/status`

## API integrations (through the browser, app-native cookies/CSRF)

| Endpoint | Result |
|---|---|
| `GET /builder/dashboard` | 200 |
| `GET /runtime/health` | 200 |
| `GET /runtime/strategies` | 200 |
| `GET /runtime/accounts` | 200 |
| `GET /user-strategies/` | 200 |
| `GET /paper/status` | 200 |
| `GET /paper/account` | 200 |
| `GET /paper/positions` | 200 |
| `GET /paper/portfolio` | 200 |

## Auto Trading lifecycle (fail-closed, paper only)

| Step | Result |
|---|---|
| `POST /builder/strategies` (create) | 200 |
| `POST /runtime/deploy` mode=paper, is_paper=true | 200 → `started` |
| `GET /runtime/{id}/status` | 200, `mode=paper`, `confirmed=true` |
| `POST /runtime/{id}/pause` / `/resume` | 200 / 200 |
| `POST /runtime/{id}/reconcile` | 200, `position_consistency` check present |
| `POST /runtime/deploy` mode=live **without confirm_live** | **409** (guard holds) |
| `POST /runtime/emergency` | 200 |
| `POST /runtime/emergency/release` | 200 |
| `POST /runtime/{id}/stop` | 200 |

## Confirmation Wizard (client + server gating)

- Wizard opens on ready strategy, renders Paper/Live segmented toggle, symbol/interval,
  broker select (Fyers/Angel One/Zerodha), capital, risk grid, trading days, times
- Switching to **Live** shows `Select broker…` requirement; `Deploy Live` stays **disabled**
- Selecting broker renders the explicit confirmation checkbox:
  > "I confirm this deploys real money on FYERS. Live orders are executed through the
  > broker with risk checks and can only be stopped via the Kill Switch / Emergency Stop."
- `Deploy Live` **disabled** before tick → **enabled** after tick (client gate)
- Server gate independently verified: live deploy without `confirm_live` → **409**

## UI smoke (strategies dashboard)

- `Execution Dashboard` panel renders with health badge, mode badge (PAPER), candles /
  signals / orders / filled / rejected / errors / PnL columns
- **Emergency Stop (all)** and **Release Emergency Stop** buttons present and functional
- Per-row Emergency button + Open link present

## Console / network analysis

- **0** page errors, **0** hydration mismatches, **0** React warnings on all pages
- Console errors are exclusively:
  - `/engine/positions|funds` CORS blocks — **pre-existing** (expired Fyers token →
    circuit breaker → 500 without CORS header; tracked since 2026-08-01, pending re-auth)
  - `analytics/track-batch` 429s — test-induced rate-limit exhaustion from repeated runs
  - `events/stream` close on `/status` — intentional EventSource probe lifecycle

## Artifacts (`/root/.web-verify/v1/`)

- `browser_smoke.json` — full structured report
- `hydration_check.json` — console/page error capture across key pages
- `strategies_dashboard.png`, `builder_wizard.png`, `builder_state.png`,
  `wizard_live_confirm.png`, `smoke-final.png` — screenshots
