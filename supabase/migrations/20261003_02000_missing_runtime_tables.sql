-- The eight tables the code depends on that no migration in this repository created.
--
-- Why
-- ---
-- A sweep of every `supabase.table("...")` reference in `apps/api` against a database built by
-- applying this directory in order found 8 tables the code reads or writes and the repository
-- never creates. Every one of them exists in production because it was created there by hand over
-- psql — recorded in AGENTS.md session notes like "`user_alerts` … created" — and none of that
-- reached a migration.
--
-- The consequence is the same one the missing `service_role` grants had, and it is not cosmetic:
-- **a fresh environment built from this repository cannot start.** Each failure is silent rather
-- than loud, because every query goes through `core.safe_query`, whose `async_safe_single` and
-- `async_safe_execute` catch all exceptions and return `None`/`[]`. So the caller reads "no
-- alerts" or "no rows" instead of "the table is missing", and PostgREST answers `PGRST205` in the
-- log where nobody is looking.
--
-- `/alerts` was the proof: `POST /api/v1/alerts/` answered **500** because `user_alerts` does not
-- exist, and the page itself showed an empty list — which is indistinguishable from a user who has
-- set no alerts. Found only by creating an alert through the product's own endpoint; reading the
-- page would never have revealed it.
--
-- Column shapes are taken from the code that uses them, not guessed:
--   user_alerts             application/services/alert_service.py, market/alert_checker.py
--   notification_prefs      application/services/alert_service.py, market/alert_checker.py
--   margin_snapshot         execution/validation.py, ai/copilot.py
--   squareoff_config        application/services/admin_service.py
--   strategy_health         alembic/versions/003_create_strategy_and_user_tables.py
--   multi_leg_strategies    application/services/multileg_service.py
--   multi_leg_strategy_legs application/services/multileg_service.py
--
-- `backtest_results` is deliberately **not** created here. `ai/copilot.py` reads that name, but
-- nothing has ever written to it — `backtest/manager.py` persists to `backtest_runs`. The copilot's
-- recent-backtests context has therefore always been empty, swallowed by the `except` around it.
-- Creating the table it reads would have made a dead query look alive; the caller is fixed
-- separately to read the table that exists.
--
-- Every statement is `IF NOT EXISTS`, so applying this to production — where all eight already
-- exist — is a no-op rather than a failure.

-- ─────────────────────────────────────────────────────────────────────────────
-- user_alerts
--
-- `alert_service.create_alert` rejects anything other than 'above'/'below' at the application
-- level, so the CHECK is a second line rather than the only one; it exists so a bad row cannot be
-- written by anything that bypasses that check.
CREATE TABLE IF NOT EXISTS public.user_alerts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    symbol        TEXT NOT NULL,
    condition     TEXT NOT NULL CHECK (condition IN ('above', 'below')),
    target_price  DOUBLE PRECISION NOT NULL,
    note          TEXT NOT NULL DEFAULT '',
    is_active     BOOLEAN NOT NULL DEFAULT true,
    triggered_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- `list_alerts` orders by `created_at desc` for one user; `alert_checker` scans active ones.
CREATE INDEX IF NOT EXISTS idx_user_alerts_user_created
    ON public.user_alerts (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_alerts_active
    ON public.user_alerts (user_id) WHERE is_active;

-- ─────────────────────────────────────────────────────────────────────────────
-- notification_prefs
--
-- One row per user, hence the unique constraint: `alert_checker` reads it by `user_id` and a
-- duplicate would make "the user's preference" ambiguous. `channels` is JSONB because it is a
-- list of channel names, and AGENTS.md records it as created that way.
CREATE TABLE IF NOT EXISTS public.notification_prefs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL UNIQUE REFERENCES public.profiles(id) ON DELETE CASCADE,
    channels    JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- margin_snapshot
--
-- `execution/validation.py::_check_margin` selects `available_margin` for (user_id, broker) and
-- **fails closed**: an exception blocks the trade. A missing table therefore means every margin
-- check either blocks or is bypassed depending on how the exception lands, which is exactly the
-- kind of coupling that makes a missing table hard to notice.
--
-- `ai/copilot.py` selects `*` and uses the row directly as its `funds` context.
CREATE TABLE IF NOT EXISTS public.margin_snapshot (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    broker            TEXT NOT NULL,
    total_margin      DOUBLE PRECISION NOT NULL DEFAULT 0,
    used_margin       DOUBLE PRECISION NOT NULL DEFAULT 0,
    available_margin  DOUBLE PRECISION NOT NULL DEFAULT 0,
    snapshot_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_margin_snapshot_user_broker
    ON public.margin_snapshot (user_id, broker);

-- ─────────────────────────────────────────────────────────────────────────────
-- squareoff_config
--
-- Read by `admin_service` as `user_id, enabled, squareoff_time, days` filtered to `enabled = true`,
-- one row per user. `squareoff_time` is text, not a time type, because the default in the reader is
-- the string `"15:15"` and an IST trading close is a display concern as much as a scheduling one.
CREATE TABLE IF NOT EXISTS public.squareoff_config (
    user_id         UUID PRIMARY KEY REFERENCES public.profiles(id) ON DELETE CASCADE,
    enabled         BOOLEAN NOT NULL DEFAULT false,
    squareoff_time  TEXT NOT NULL DEFAULT '15:15',
    days            TEXT NOT NULL DEFAULT '1,2,3,4,5',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- strategy_health
--
-- Mirrored from `alembic/versions/003_create_strategy_and_user_tables.py`, which is the
-- authoritative definition. Alembic is not part of the deploy path — the deploy script applies this
-- directory — which is why the table never reached a plain SQL migration and `runtime/manager.py`
-- found it missing. `strategy_id` is TEXT, not UUID, because builder strategies use 12-hex ids
-- (`uuid.uuid4().hex[:12]`) and a uuid column rejects them with 22P02.
CREATE TABLE IF NOT EXISTS public.strategy_health (
    strategy_id  TEXT PRIMARY KEY,
    user_id      UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
    status       TEXT NOT NULL DEFAULT 'draft',
    last_run     TIMESTAMPTZ,
    run_count    INTEGER NOT NULL DEFAULT 0,
    error_count  INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT,
    heartbeat_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- multi_leg_strategies / multi_leg_strategy_legs
--
-- Columns taken verbatim from the insert payloads in `multileg_service.create_strategy`, so the
-- names cannot drift from what the writer sends. `legs` is ordered by `leg_index`, and a delete
-- removes legs before the parent, so the child needs an index on `strategy_id`.
CREATE TABLE IF NOT EXISTS public.multi_leg_strategies (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    underlying   TEXT NOT NULL DEFAULT '',
    expiry       TEXT NOT NULL DEFAULT '',
    leg_count    INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'draft',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.multi_leg_strategy_legs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id      UUID NOT NULL REFERENCES public.multi_leg_strategies(id) ON DELETE CASCADE,
    leg_index        INTEGER NOT NULL,
    action           TEXT NOT NULL,
    symbol           TEXT NOT NULL,
    quantity         NUMERIC NOT NULL DEFAULT 0,
    exchange         TEXT NOT NULL DEFAULT '',
    order_type       TEXT NOT NULL DEFAULT '',
    product          TEXT NOT NULL DEFAULT '',
    price            DOUBLE PRECISION,
    trigger_price    DOUBLE PRECISION,
    instrument_type  TEXT NOT NULL DEFAULT '',
    strike_price     DOUBLE PRECISION,
    expiry_date      TEXT NOT NULL DEFAULT '',
    option_type      TEXT NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_multi_leg_legs_strategy
    ON public.multi_leg_strategy_legs (strategy_id, leg_index);
CREATE INDEX IF NOT EXISTS idx_multi_leg_strategies_user
    ON public.multi_leg_strategies (user_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- RLS
--
-- These are per-tenant tables: every one of them is keyed by `user_id` and read through the
-- service_role key, which bypasses RLS. RLS is therefore not what protects them, and it is left off
-- deliberately rather than half-configured. Adding it without also granting `authenticated` the
-- matching policies would block the direct-client paths while appearing to add protection; the
-- existing tables' policy set should be reviewed as its own piece of work.
--
-- `strategies`, `orders` and the rest of the schema already run this way, so this matches.