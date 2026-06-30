-- Order Safety Layer — idempotency, audit enrichment, token tracking
-- 2025-06-30
-- For human review. Do NOT execute against production without review.

-- ── ORDERS ────────────────────────────────────────────────────

ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS client_order_id TEXT DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_client_order_id
    ON public.orders(user_id, client_order_id)
    WHERE client_order_id != '';

ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'manual';
ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS reason TEXT DEFAULT '';


-- ── AUDIT LOG (enriched columns) ─────────────────────────────

ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS source TEXT DEFAULT '';
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS client_order_id TEXT DEFAULT '';
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS reason TEXT DEFAULT '';
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS broker TEXT DEFAULT '';
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS symbol TEXT DEFAULT '';
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS side TEXT DEFAULT '';
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS quantity INT DEFAULT 0;
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS intended_price DOUBLE PRECISION DEFAULT 0.0;
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS signal_id TEXT DEFAULT '';
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS strategy_id TEXT DEFAULT '';


-- ── BROKER CREDENTIALS (token lifecycle tracking) ────────────

ALTER TABLE public.broker_credentials ADD COLUMN IF NOT EXISTS token_status TEXT DEFAULT 'valid'
    CHECK (token_status IN ('valid', 'expired', 'needs_attention'));
ALTER TABLE public.broker_credentials ADD COLUMN IF NOT EXISTS token_expires_at TIMESTAMPTZ;
ALTER TABLE public.broker_credentials ADD COLUMN IF NOT EXISTS last_token_refresh_at TIMESTAMPTZ;
