-- OMS state tables: the order queue's durable record of what it is holding.
--
-- Why
-- ---
-- `oms/persistence.py` upserts every `OmniOrder`, `BracketOrder` and `OCOOrder` into
-- `oms_orders`, `oms_bracket_orders` and `oms_oco_orders`. The module's own docstring says to
-- "run in Supabase SQL Editor" and gives an abbreviated schema — but **no migration in this
-- directory creates any of the three**, which is why they exist in production and not here.
--
-- The failure is the same shape as the eight tables in `20261003_02000`, and the same silence:
-- `save_order` catches the exception and logs a WARNING, so the queue keeps running and the API
-- answers 200 while nothing is persisted.
--
--     Failed to persist OMS order 47951fc0…: PGRST205
--     Could not find the table 'public.oms_orders' in the schema cache
--
-- What that costs, concretely: `oms_orders` is what makes active orders survive a restart.
-- `OrderManager._recover_active_orders` reads it on boot, so with the table absent a restart
-- silently loses every in-flight order — the process forgets what it had already sent to a broker,
-- which is the one moment where re-sending is genuinely dangerous. Reconciliation and the
-- cancel/duplicate paths read it too.
--
-- Columns are taken from the models rather than the docstring's sketch. The docstring lists four
-- columns for `oms_orders` and "all OmniOrder fields from model_dump(mode='json')" in a comment;
-- `model_dump` sends all **37**, and PostgREST rejects the whole upsert if any one is missing. So
-- the table is declared with the full set — derived by dumping the model, not guessed.
--
-- `state` is indexed because the worker's drain query and the recovery path both filter on it, and
-- `oms_order_id` is the primary key and the upsert's conflict target in all three tables.
--
-- Types follow the model: enums (`exchange`, `side`, `order_type`, `product`, `relation_type`,
-- `state`) as TEXT, `child_order_ids` and `metadata` as JSONB, timestamps as TIMESTAMPTZ.
--
-- No foreign keys on `user_id`. `profiles.id` is a UUID and `OmniOrder.user_id` is a string that
-- may hold `paper:<user_id>` for sandbox runs (the backtest engine registers brokers under
-- synthetic ids like `backtest:<run_id>`), so a FK would reject legitimate rows. That is the same
-- reasoning as `strategy_runs.strategy_id` in AGENTS.md.
--
-- Whether production has these tables was **not verified from here** — the VPS does not answer from
-- this workstation. Production is recorded as recovering active orders on restart, which implies
-- they exist there. `IF NOT EXISTS` makes applying this either way safe.
--
-- Idempotent throughout.

-- ─────────────────────────────────────────────────────────────────────────────
-- oms_orders
CREATE TABLE IF NOT EXISTS public.oms_orders (
    oms_order_id          TEXT PRIMARY KEY,
    execution_request_id  TEXT,
    client_order_id       TEXT,
    broker_order_id       TEXT,
    user_id               TEXT,
    broker                TEXT,
    symbol                TEXT,
    exchange              TEXT        DEFAULT 'NSE',
    side                  TEXT,
    order_type            TEXT        DEFAULT 'MARKET',
    product               TEXT        DEFAULT 'INTRADAY',
    quantity              INTEGER     NOT NULL DEFAULT 0,
    filled_quantity       INTEGER     NOT NULL DEFAULT 0,
    average_price         DOUBLE PRECISION NOT NULL DEFAULT 0,
    price                 DOUBLE PRECISION NOT NULL DEFAULT 0,
    trigger_price         DOUBLE PRECISION,
    state                 TEXT        NOT NULL DEFAULT 'NEW',
    prev_state            TEXT,
    relation_type         TEXT        DEFAULT 'NONE',
    parent_order_id       TEXT,
    sibling_order_id      TEXT,
    child_order_ids       JSONB       DEFAULT '[]'::jsonb,
    strategy_id           TEXT,
    source                TEXT        DEFAULT 'manual',
    retry_count           INTEGER     NOT NULL DEFAULT 0,
    max_retries           INTEGER     NOT NULL DEFAULT 3,
    priority              INTEGER     NOT NULL DEFAULT 0,
    is_paper              BOOLEAN     NOT NULL DEFAULT false,
    error_code            TEXT,
    message               TEXT,
    latency_ms            DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at            TIMESTAMPTZ DEFAULT now(),
    updated_at            TIMESTAMPTZ DEFAULT now(),
    sent_at               TIMESTAMPTZ,
    filled_at             TIMESTAMPTZ,
    cancelled_at          TIMESTAMPTZ,
    metadata              JSONB       DEFAULT '{}'::jsonb
);

-- The worker drains by state and recovery selects non-terminal ones; both are on this column.
CREATE INDEX IF NOT EXISTS idx_oms_orders_state ON public.oms_orders (state);
CREATE INDEX IF NOT EXISTS idx_oms_orders_user ON public.oms_orders (user_id);
-- The reconciliation loop matches on the broker's own id.
CREATE INDEX IF NOT EXISTS idx_oms_orders_broker_oid ON public.oms_orders (broker_order_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- oms_bracket_orders
--
-- Columns from `BracketOrder.model_dump(mode="json")` — 15 fields, all of which the upsert sends.
-- The monitor's `active = true` scan is the hot query here: `_bracket_loop` runs every 2s and
-- loads live brackets, so a partial index on `active` is the right shape rather than a plain one.
CREATE TABLE IF NOT EXISTS public.oms_bracket_orders (
    oms_order_id       TEXT PRIMARY KEY,
    parent_order_id    TEXT,
    user_id            TEXT,
    symbol             TEXT,
    quantity           INTEGER      NOT NULL DEFAULT 0,
    entry_price        DOUBLE PRECISION NOT NULL DEFAULT 0,
    stop_loss_price    DOUBLE PRECISION NOT NULL DEFAULT 0,
    target_price       DOUBLE PRECISION NOT NULL DEFAULT 0,
    trailing_sl_pct    DOUBLE PRECISION NOT NULL DEFAULT 0,
    entry_filled       BOOLEAN      NOT NULL DEFAULT false,
    sl_order_id        TEXT,
    target_order_id    TEXT,
    active             BOOLEAN      NOT NULL DEFAULT true,
    side               TEXT         DEFAULT 'BUY',
    broker             TEXT         DEFAULT 'fyers'
);

CREATE INDEX IF NOT EXISTS idx_oms_bracket_active
    ON public.oms_bracket_orders (parent_order_id) WHERE active;

-- ─────────────────────────────────────────────────────────────────────────────
-- oms_oco_orders
--
-- Columns from `OCOOrder.model_dump(mode="json")` — 9 fields.
CREATE TABLE IF NOT EXISTS public.oms_oco_orders (
    oms_order_id    TEXT PRIMARY KEY,
    user_id         TEXT,
    symbol          TEXT,
    quantity        INTEGER      NOT NULL DEFAULT 0,
    order_a_id      TEXT,
    order_b_id      TEXT,
    order_a_filled  BOOLEAN      NOT NULL DEFAULT false,
    order_b_filled  BOOLEAN      NOT NULL DEFAULT false,
    active          BOOLEAN      NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_oms_oco_active
    ON public.oms_oco_orders (active) WHERE active;

COMMENT ON TABLE public.oms_orders IS
    'Durable record of in-flight OMS orders. Read by _recover_active_orders on boot, by the '
    'reconciliation loop, and by cancel/duplicate paths — its absence costs every in-flight order '
    'on restart.';
COMMENT ON TABLE public.oms_bracket_orders IS
    'Live auto-brackets attached to a filled order. The monitor scans active rows every 2s.';
COMMENT ON TABLE public.oms_oco_orders IS
    'One-cancels-the-other legs.';
COMMENT ON COLUMN public.oms_orders.user_id IS
    'No foreign key: may hold a synthetic id such as paper:<user_id> or backtest:<run_id>, which a '
    'profiles FK would reject.';