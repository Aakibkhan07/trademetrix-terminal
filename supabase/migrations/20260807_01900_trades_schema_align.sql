-- v1.6.9 P1-2: align prod `trades` schema to canonical init.sql (20250628000100)
-- The prod `trades` table was schema-drifted to a minimal shape (id, user_id,
-- symbol, quantity, pnl) — missing created_at, trade_time, order_id, side,
-- price, value, broker, exchange, is_paper, strategy_id. This migration adds
-- the missing columns idempotently so the AI Journal (_get_recent_trades) can
-- read a well-formed schema and never 500 on a malformed query.
-- NOTE: existing drifted rows lack side/price/value/broker/exchange, so the
-- journal's orders-first + graceful-degradation path remains authoritative.

ALTER TABLE public.trades
    ADD COLUMN IF NOT EXISTS order_id UUID REFERENCES public.orders(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS strategy_id UUID REFERENCES public.strategies(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS broker TEXT,
    ADD COLUMN IF NOT EXISTS exchange TEXT,
    ADD COLUMN IF NOT EXISTS side TEXT,
    ADD COLUMN IF NOT EXISTS price DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS value DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS trade_time TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS is_paper BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_trades_user_created
    ON public.trades (user_id, created_at DESC);