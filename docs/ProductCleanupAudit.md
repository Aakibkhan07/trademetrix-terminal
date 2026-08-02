# Product Cleanup & Navigation Audit — Pre-Public-Beta (2026-08-02)

**Scope:** every page, route, and menu item in `apps/web` (37 routes + admin dashboard tabs + API surface).
**Method:** code inspection (LOC, data calls, inbound/outbound links), prod E2E evidence (v1.0.1 run), dead-code scans.
**Status:** AUDIT ONLY — no deletions. Cleanup requires approval; every deletion is a git commit (reversible); full regression after cleanup.
**Protected (never remove):** OMS, Risk Engine, Broker Layer, Strategy Engine, Backtest Engine, Workspace, Builder, Analyzer.

**Legend:** Working = renders/executes correctly · Used = has callers/links · Integrated = wired to data/API · Navigation = reachable from UI · Value = business/user impact (High/Med/Low)

---

## A. Page-by-Page Audit

### USER SURFACE

| # | Item (route) | Current State | Working? | Used? | Integrated? | Navigation? | Value | **Recommendation** |
|---|---|---|---|---|---|---|---|---|
| 1 | Home (`/portfolio`) | Portfolio shell: watchlist panel, P&L, broker status, quick trade | ✅ (E2E) | ✅ | ✅ | ✅ (nav + post-login) | High | **KEEP** |
| 2 | Trading Workspace (`/workspace`) | Trade + Analyze workspace, self-nav sidebar | ✅ (E2E) | ✅ | ✅ | ✅ | High | **KEEP** |
| 3 | Watchlist (nav → `/portfolio`) | No dedicated page; panel on Home + custom tab in Market Analyzer (`tm_watchlist_custom` shared) | ✅ | ✅ | ✅ | ✅ | Med | **KEEP** (see nav note §G — 3 items point at same page) |
| 4 | Portfolio (nav → `/portfolio`) | Same shell as Home | ✅ | ✅ | ✅ | ✅ | Med | **KEEP** (nav redundancy — see §G) |
| 5 | Market Analyzer (`/marketdata`) | Index/stock/custom tabs, search, live ticks, option chain ref | ✅ (E2E) | ✅ | ✅ | ✅ | High | **KEEP** |
| 6 | Strategy Builder (`/strategies/builder`) | DSL v2 graph builder, templates, validate/deploy, versions | ✅ (E2E) | ✅ | ✅ | ✅ | High | **KEEP** |
| 7 | Backtest (`/backtest`) | v2 engine: runs, compare, optimize, exports, deploy-to-paper | ✅ (E2E) | ✅ | ✅ | ✅ | High | **KEEP** |
| 8 | Orders (`/trade`) | Quick order + order book | ✅ (E2E) | ✅ | ✅ | ✅ | High | **KEEP** |
| 9 | Positions (`/positions`) | Positions + orders tables, P&L | ✅ (E2E) | ✅ | ✅ | ✅ | High | **KEEP** |
| 10 | Funds (`/brokers`) | Broker connect/OAuth, token status, re-auth | ✅ (E2E) | ✅ | ✅ | ✅ (nav label "Funds") | Med | **KEEP** (label mismatch: page = Brokers; funds surface lives in Terminal — see FIX) |
| 11 | Trade Journal (`/journal`) | Order notes + AI journal entries | ✅ | ✅ | ✅ | ✅ | Med | **KEEP** |
| 12 | Alerts (`/alerts`) | Price alert CRUD + notification prefs | ✅ | ✅ | ✅ | ✅ | Med | **KEEP** |
| 13 | Settings (`/settings`) | Account, brokers, password, upgrade CTA | ✅ | ✅ | ✅ | ✅ | Med | **KEEP** |
| 14 | Help (`/help`) | FAQ accordion | ✅ | ✅ | n/a (static) | ✅ | Med | **KEEP** |
| 15 | Marketplace (`/marketplace`) | Strategy marketplace → strategy detail | ✅ | ✅ | ✅ | ✅ | Med (business) | **KEEP** |
| 16 | AI Assistant (`/ai`) | Chat + build strategy; journal endpoint ERR_FAILED in E2E (pre-existing) | ✅ | ✅ | ⚠️ | ✅ | High | **KEEP** (fix `ai/journal` latency in FIX list) |
| 17 | Terminal (`/terminal`) | Real-time order ticket + execution + funds | ✅ (E2E) | ✅ | ✅ | ✅ | High | **KEEP** |
| 18 | Terminal Builder (`/terminal/builder`) | **Legacy duplicate builder** (legs-form, `userStrategies` CRUD) vs DSL v2 at `/strategies/builder` (1060 LOC, separate code path) | ✅ | ❌ (only via nav item we added) | ✅ | ✅ | Low | **HIDE** — keep code, remove from navigation (superseded) |
| 19 | Risk Control (`/risk`) | Kill switch, risk settings, live status | ✅ | ✅ | ✅ | ✅ | High | **KEEP** |
| 20 | Option Chain (`/terminal/option-chain`) | Chain browser (expiry, strikes) | ✅ | ✅ | ✅ | ✅ | Med | **KEEP** |
| 21 | Strategy Catalog (`/strategies/catalog`) | Searchable builtin catalog (`/strategies/list-builtin`) | ✅ | ✅ | ✅ | ✅ | Med | **KEEP** (overlaps `/strategies`; acceptable) |
| 22 | Analytics (`/analytics`) | **273 LOC, ZERO data calls** — static tables + "No engine runs yet" empty state | ⚠️ | ✅ (nav) | ❌ | ✅ | Med | **FIX** — wire to engine-run/P&L analytics or remove from nav until done |
| 23 | Copilot (`/copilot`) | 10-LOC redirect → `/ai`; zero inbound links; `api.copilot` client method dead | ⚠️ | ❌ | ❌ | ❌ | None | **REMOVE** — dead route (redirect page + unused client method) |
| 24 | Transparency (`/transparency`) | Order lifecycle from engine runs | ✅ | ✅ | ✅ | ✅ (popover) | Med | **KEEP** |
| 25 | Status (`/status`) | Static; **hardcoded incident history** ("July 3, 2026 Redis…"), no live checks | ⚠️ | ✅ (popover) | ❌ | ✅ | Med | **FIX** — wire to real monitoring or strip placeholder incidents |
| 26 | Changelog (`/changelog`) | Static, real release history | ✅ | ✅ | n/a | ✅ (popover) | Med | **KEEP** |
| 27 | Account (`/account`) | Account health check (brokers/strategies/orders/notifications) | ✅ | ✅ | ✅ | ✅ (popover) | Med | **KEEP** |
| 28 | Feedback (`/feedback`) | **Submit is fake** — `await new Promise(r => setTimeout(r,500))` + toast, NO API call; real submit only in `components/feedback-button.tsx` dialog | ❌ | ✅ (popover) | ❌ | ✅ | Med | **FIX** — wire to `/api/v1/feedback` or reuse the dialog component |

### PUBLIC / BUSINESS PAGES

| # | Item (route) | Current State | Working? | Used? | Integrated? | Navigation? | Value | **Recommendation** |
|---|---|---|---|---|---|---|---|---|
| 29 | Landing (`/`) | Marketing page; links only `/portfolio` + `/auth` — **no pricing/status/legal links** | ✅ | ✅ | n/a | ✅ | High | **FIX** — add Pricing/Status/Legal footer links for public beta (keep page) |
| 30 | Auth (`/auth`) | Password + OTP flows, CSRF | ✅ (E2E) | ✅ | ✅ | ✅ | High | **KEEP** |
| 31 | Onboarding (`/onboarding`) | Post-signup broker connect wizard | ✅ | ✅ | ✅ | ✅ (post-auth) | High | **KEEP** |
| 32 | Pricing (`/pricing`) | Plans + subscription create (Razorpay link) | ✅ | ✅ | ✅ | ⚠️ (only via settings/account/upgrade CTAs) | High (business) | **KEEP** (add to landing — see #29) |
| 33 | Client Portal (`/portal`) | Standalone: positions/orders/funds/strategies for clients | ✅ | ✅ | ✅ | ✅ (portfolio header) | High (business) | **KEEP** |
| 34 | Legal (`/legal/*`) | Terms/privacy/risk/refund/disclaimer | ✅ | ✅ | n/a | ⚠️ (portal footer only) | High (compliance) | **KEEP** (link from landing — see #29) |

### ADMIN / INTERNAL SURFACE (already isolated from users; keep admin-only)

| # | Item (route) | Current State | Working? | Used? | Integrated? | Navigation? | Value | **Recommendation** |
|---|---|---|---|---|---|---|---|---|
| 35 | Dashboard (`/dashboard` + 19 tabs) | Admin ops console: trade router, users, brokers, P&L, perf, referrals, webhooks, backups, scheduled, risk, activity, audit, IP whitelist, buyer strat, user algos… | ✅ | ✅ | ✅ | ✅ (admin nav) | Ops | **HIDE** — internal dev/ops tool; keep in admin nav, never user-facing |
| 36 | Admin Admins (`/admin/admins`) | Admin management | ✅ | ✅ | ✅ | ✅ (admin nav) | Ops | **HIDE** |
| 37 | Beta Dashboard (`/admin/beta`) | Analytics: DAU/funnel/retention/features/sessions/crashes/feedback | ✅ (smoke) | ✅ | ✅ | ✅ (admin nav) | Ops | **HIDE** (operator tool) |
| 38 | Admin Broadcast (`/admin/broadcast`) | Announcement broadcast | ✅ | ✅ | ✅ | ✅ (admin nav) | Ops | **HIDE** |
| 39 | Dashboard tabs ×19 | See §A35 | ✅ | ✅ | ✅ | ✅ (admin) | Ops | **HIDE** |

### CODE / DEAD SURFACE

| # | Item | Evidence | **Recommendation** |
|---|---|---|---|
| 40 | `components/equity-curve.tsx` | Zero imports anywhere (verified grep) | **REMOVE** |
| 41 | `api.copilot` client method (lib/api.ts) | Defined, never called | **REMOVE** (with #23) |
| 42 | `components/header.tsx` | Already deleted (Phase 6) — confirm no residue | n/a (done) |

---

## B. KEEP LIST (29)

Home, Trading Workspace, Watchlist, Portfolio, Market Analyzer, Strategy Builder, Backtest, Orders, Positions, Funds/Brokers, Trade Journal, Alerts, Settings, Help, Marketplace, AI Assistant, Terminal, Option Chain, Risk Control, Strategy Catalog, Strategies (+ `[key]` detail + Multi-Leg), Transparency, Changelog, Account, Auth, Onboarding, Pricing, Client Portal, Legal.

## C. FIX LIST (5)

1. **Analytics** (`/analytics`) — no data source; wire engine-run/P&L data or hide from nav
2. **Feedback page** (`/feedback`) — fake submit (500 ms sleep + toast); wire to `/api/v1/feedback` or reuse `feedback-button` dialog
3. **Status** (`/status`) — hardcoded placeholder incidents; wire to real monitoring or strip fake history
4. **Landing** (`/`) — missing Pricing/Status/Legal links for public beta
5. **Funds nav label** — nav item "Funds" → `/brokers` page is broker management; either rename label to "Brokers & Funds" or surface actual funds (API exists: `/api/v1/funds`)
   *(+ minor: `ai/journal` endpoint latency seen in E2E; watchlist/Home/Portfolio = 3 nav items → 1 page — consider consolidating)*

## D. HIDE LIST (3)

1. **Terminal Builder** (`/terminal/builder`) — legacy duplicate builder; remove from user nav, keep route/code
2. **Dashboard + 19 admin tabs** (`/dashboard*`) — internal ops console; admin-only (already)
3. **Admin pages** (`/admin/admins`, `/admin/beta`, `/admin/broadcast`) — operator tools; admin-only (already)

## E. REMOVE LIST (3)

1. **Copilot** (`/copilot` page + `api.copilot` method) — dead route, zero links, redirect to `/ai`
2. **`components/equity-curve.tsx`** — zero imports
3. *(Nothing else — all remaining routes/APIs have live callers)*

## F. Final Recommended Navigation

**USER SIDEBAR** (after HIDE/FIX):
- **Home**: Home, Watchlist, Portfolio (keep 3 entries → same shell; consolidate to 1 when a dedicated Watchlist module ships)
- **Trade**: Trading Workspace, Orders, Positions, Funds (renamed "Brokers & Funds")
- **Build & Analyze**: Market Analyzer, Strategy Builder, Backtest, Analytics *(keep only after FIX-1)*, Trade Journal
- **Manage**: Alerts, Risk Control, Settings, Help
- **Platform**: Terminal, Option Chain, Strategies, Marketplace, AI Assistant
- *(Removed: Terminal Builder)*
- **Profile popover**: Settings, Account, Feedback *(after FIX-2)*, Changelog, Transparency, Status *(after FIX-3)*

**ADMIN SIDEBAR** (unchanged): user sections + Trading/Control Center/Operations/Beta/Security (Dashboard tabs, Admins, Beta Dashboard, Broadcast).

**PUBLIC**: Landing + Pricing + Status + Legal links (FIX-4).

## G. Notes

- No backend/API changes required for any FIX/HIDE/REMOVE item (except Feedback page wiring, which uses the existing `/api/v1/feedback` endpoint).
- All deletions reversible via git (commit-per-removal). Full regression (API pytest + web tsc/build + prod smoke) after cleanup.
- Protected engines untouched: OMS, Risk, Broker layer, Strategy Engine, Backtest Engine, Workspace, Builder, Analyzer.
