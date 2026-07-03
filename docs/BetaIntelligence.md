# Beta Intelligence System

## Overview

The Beta Intelligence system provides session replay, product analytics, error tracking, user feedback, and release tracking — all without building new trading features. It reuses existing infrastructure (Supabase, Python FastAPI backend, Next.js) and adds minimal new code.

---

## 1. Session Replay — Microsoft Clarity

**How it works:**
- Clarity script is injected in `apps/web/app/layout.tsx` via `<ClarityScript />` component (in `apps/web/components/clarity.tsx`)
- Loads only when `NEXT_PUBLIC_CLARITY_PROJECT_ID` environment variable is set
- Records anonymous user sessions including rage clicks, dead clicks, and scroll heatmaps
- CSP in `next.config.js` updated to allow `clarity.ms` domains in `connect-src`, `script-src`, and `img-src`

**Configuration:**
```
NEXT_PUBLIC_CLARITY_PROJECT_ID=your_project_id
```

**Files:**
- `apps/web/components/clarity.tsx` — Clarity script injection
- `apps/web/app/layout.tsx` — Script loading
- `apps/web/next.config.js` — CSP updated for Clarity domains

---

## 2. Product Analytics

### Client-side Tracking

A lightweight analytics module (`apps/web/lib/analytics.ts`) tracks user events:

| Event | Trigger | Properties |
|-------|---------|------------|
| `signup_started` | User opens signup form | — |
| `signup_completed` | Account created | `user_id` |
| `otp_success` | OTP verified | `method` |
| `otp_failure` | OTP failed | `error` |
| `broker_connected` | Broker linked | `broker_type` |
| `first_paper_trade` | First paper order placed | — |
| `first_backtest` | First backtest run | — |
| `first_strategy` | First strategy assigned | `strategy_key` |
| `first_runtime` | First runtime started | — |
| `first_live_trade` | First live order placed | — |

Events are sent via `navigator.sendBeacon` (or `fetch` fallback) to `POST /api/v1/analytics/track`.

**Files:**
- `apps/web/lib/analytics.ts` — Client tracking module (`track()`, `trackError()`, `setUserId()`)

### Backend Analytics Storage

In-memory event store in `apps/api/routes/v1_analytics.py`. Events are stored as dict entries with session grouping. Data persists for the lifetime of the backend server process.

**Endpoints:**
| Endpoint | Auth | Description |
|----------|------|-------------|
| `POST /api/v1/analytics/track` | None | Store event (event name, properties, session_id, user_id, timestamp) |
| `GET /api/v1/analytics/events?event=X` | Admin | List stored events, optionally filtered |
| `GET /api/v1/admin/analytics/overview` | Admin | Full analytics overview (see section 6) |

### Funnel Dashboard

The funnel is computed from two sources:
1. **Existing Supabase tables** — `profiles` (total users), `broker_credentials` (broker connected), `orders` (traded), `strategy_assignments` (assigned)
2. **In-memory events** — signup/OTP events from client tracking

Displayed as stacked progress bars in the founder dashboard.

---

## 3. Error Tracking — Sentry

**Integration:** `@sentry/nextjs` v10.63.0

**Enabled only when** `NEXT_PUBLIC_SENTRY_DSN` environment variable is set. All config files check `!!SENTRY_DSN` before initializing.

**Frontend setup:**
- `sentry.client.config.ts` — Client-side Sentry init
- `instrumentation.ts` — Server/Edge-side Sentry init (replaces `sentry.server.config.ts` and `sentry.edge.config.ts`)
- `app/global-error.tsx` — Global error boundary that captures React rendering errors
- `lib/sentry.ts` — Helper module (`captureError()`, `setSentryUser()`)

**Release version and user ID:**
- Release tag set from `NEXT_PUBLIC_APP_VERSION`
- User ID set via `setSentryUser()` in auth flow
- Backend already has Sentry in `apps/api/core/sentry.py`

**Files:**
- `apps/web/sentry.client.config.ts`
- `apps/web/instrumentation.ts`
- `apps/web/app/global-error.tsx`
- `apps/web/lib/sentry.ts`
- `apps/web/next.config.js` — wrapped with `withSentryConfig`

---

## 4. User Feedback — Floating Button

**Component:** `apps/web/components/feedback-button.tsx`

A floating "Report a bug" button (pencil icon) fixed at bottom-right of every page.

**Auto-attached metadata:**
- Browser (user agent, name/version)
- Page (current URL path)
- Console errors (last 20 captured `console.error` calls)
- App version (`NEXT_PUBLIC_APP_VERSION`)
- Screen resolution

**Submission:** `POST /api/v1/feedback` (authenticated) stores to in-memory feedback store.

**Backend:** `apps/api/routes/v1_feedback.py`
| Endpoint | Auth | Description |
|----------|------|-------------|
| `POST /api/v1/feedback` | User | Submit bug report, feature request, or NPS |
| `GET /api/v1/admin/feedback` | Admin | List all feedback entries |
| `PATCH /api/v1/admin/feedback/{id}` | Admin | Update status/notes |

**Files:**
- `apps/web/components/feedback-button.tsx` — Floating button + form
- `apps/web/components/feedback-wrapper.tsx` — Dynamic import wrapper (avoids SSR)
- `apps/web/app/layout.tsx` — Feedback button rendered in root layout
- `apps/api/routes/v1_feedback.py` — Backend endpoints

The existing `/feedback` page remains unchanged (it's client-side only). The floating button is the primary feedback mechanism.

---

## 5. Release Tracking — APP_VERSION

**Script:** `apps/web/scripts/version.sh`
```
#!/usr/bin/env bash
git describe --tags --abbrev=0 2>/dev/null || echo "0.0.0"
- git rev-parse --short HEAD
```

**Usage:** `NEXT_PUBLIC_APP_VERSION=$(scripts/version.sh)`

**Display locations:**
- **Status bar** (`apps/web/components/status-bar.tsx`) — Shows `v{VERSION}` next to "SYS: OK"
- **Admin page** (`apps/web/app/admin/page.tsx`) — Version in subtitle
- **Founder dashboard** (`apps/web/app/admin/founder/page.tsx`) — Version in header and footer
- **Footer component** (`apps/web/components/app-version.tsx`) — Reusable `<AppVersion />`

**In Sentry:** `release` field set from `NEXT_PUBLIC_APP_VERSION`
**In backend logs:** `settings.app_version` (already available)

**Files:**
- `apps/web/scripts/version.sh` — Version generation
- `apps/web/components/app-version.tsx` — Display component
- `apps/web/components/status-bar.tsx` — Status bar display
- `apps/web/app/admin/page.tsx` — Admin page display

---

## 6. Founder Dashboard — New Metrics

The founder dashboard (`/admin/founder`) now includes analytics data from `GET /api/v1/admin/analytics/overview`.

### New metric tiles

| Tile | Source | Derivation |
|------|--------|-----------|
| **DAU** | `audit_log` + tracked events | Unique users with activity today |
| **WAU** | `audit_log` + tracked events | Unique users with activity last 7 days |
| **MAU** | `audit_log` + tracked events | Unique users with activity last 30 days |
| **Activation Rate** | `orders` table | Users with ≥1 trade / total users |
| **Retention Rate** | audit_log + events | WAU / MAU × 100 |
| **Crash-Free Sessions** | tracked error events | (1 − crash_sessions / total_sessions) × 100 |
| **Avg Session Length** | tracked events | Average time between first and last event per session |
| **Tracked Events** | analytics store | Total events received |
| **Funnel** | Supabase tables | 5-step funnel: Signed Up → Connected Broker → Assigned Strategy → Placed Trade → Live Trade |

### Funnel visualization

Stacked progress bars showing conversion at each stage:

```
Signed Up            ━━━━━━━━━━━━━━━━━━━━ 100 (100%)
Connected Broker     ━━━━━━━━━━━━━━━      80 (80%)
Assigned Strategy    ━━━━━━━━━━━━━        65 (65%)
Placed Trade         ━━━━━━━━━            45 (45%)
Live Trade           ━━━━━                 20 (20%)
```

---

## File Inventory

### New files created

| File | Purpose |
|------|---------|
| `apps/api/routes/v1_analytics.py` | Backend analytics endpoints + in-memory event store |
| `apps/api/routes/v1_feedback.py` | Backend feedback endpoints + in-memory store |
| `apps/web/lib/analytics.ts` | Client-side event tracking |
| `apps/web/lib/sentry.ts` | Sentry helper module |
| `apps/web/sentry.client.config.ts` | Sentry client init |
| `apps/web/instrumentation.ts` | Sentry server/edge init |
| `apps/web/app/global-error.tsx` | Global error boundary |
| `apps/web/components/clarity.tsx` | Clarity script injection |
| `apps/web/components/feedback-button.tsx` | Floating feedback button |
| `apps/web/components/feedback-wrapper.tsx` | Dynamic import wrapper |
| `apps/web/components/app-version.tsx` | Version display component |
| `apps/web/scripts/version.sh` | Git-based version generation |

### Files modified

| File | Changes |
|------|---------|
| `apps/api/main.py` | Added analytics + feedback routers |
| `apps/web/next.config.js` | Sentry `withSentryConfig` wrapper, CSP updated for Clarity |
| `apps/web/app/layout.tsx` | Added ClarityScript, FeedbackButtonWrapper |
| `apps/web/app/admin/page.tsx` | Added AppVersion in header |
| `apps/web/app/admin/founder/page.tsx` | Full rewrite with analytics data, funnel, DAU/WAU/MAU |
| `apps/web/components/status-bar.tsx` | Added version display |
| `apps/web/.env.example` | Added beta intelligence env vars |
| `apps/web/.env` | Added default beta intelligence values |

---

## Configuration

```env
# Required
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
NEXT_PUBLIC_API_URL=...
NEXT_PUBLIC_WS_URL=...

# Beta Intelligence (all optional)
NEXT_PUBLIC_CLARITY_PROJECT_ID=    # Enables Clarity session replay
NEXT_PUBLIC_SENTRY_DSN=            # Enables Sentry error tracking
NEXT_PUBLIC_APP_VERSION=0.1.0      # Set via scripts/version.sh
NEXT_PUBLIC_APP_ENV=development    # Environment label for Sentry
```

All beta intelligence features are **opt-in** — they activate only when their respective environment variable is configured.

---

## Data Persistence Note

Client-side analytics events and feedback submissions are stored **in-memory** on the backend server. Data is lost on server restart. For production, replace the in-memory stores with Supabase tables:

- `analytics_events` table — `(id, event, properties, session_id, user_id, timestamp)`
- `feedback` table — `(id, user_id, category, title, description, metadata, status, created_at)`

The in-memory approach trades durability for zero-infrastructure setup, appropriate for closed beta where the primary goal is proving usefulness before committing to schema migrations.
