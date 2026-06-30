-- Strategy Assignments — admin assigns built-in strategies to users per tier
-- 2025-06-30
-- For human review. Do NOT execute against production without review.

-- ── STRATEGY ASSIGNMENTS ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.strategy_assignments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    strategy_key TEXT NOT NULL,
    required_tier TEXT NOT NULL DEFAULT 'free',
    mirror_enabled BOOLEAN NOT NULL DEFAULT true,
    active BOOLEAN NOT NULL DEFAULT true,
    assigned_by uuid REFERENCES public.profiles(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A strategy can only be assigned once per user
CREATE UNIQUE INDEX IF NOT EXISTS idx_strategy_assignments_user_key
    ON public.strategy_assignments(user_id, strategy_key);

-- Fast lookups: which assignments does a user have?
CREATE INDEX IF NOT EXISTS idx_strategy_assignments_user_active
    ON public.strategy_assignments(user_id, active);

-- Fast lookups: which users can receive a signal for a given strategy?
CREATE INDEX IF NOT EXISTS idx_strategy_assignments_key_active
    ON public.strategy_assignments(strategy_key, active)
    WHERE active = true AND mirror_enabled = true;


COMMENT ON TABLE public.strategy_assignments IS
    'Links built-in strategies to users. Controls mirror/broadcast fan-out.';
COMMENT ON COLUMN public.strategy_assignments.strategy_key IS
    'Built-in strategy identifier, e.g. smc_sniper (matches strategies/__init__.py keys)';
COMMENT ON COLUMN public.strategy_assignments.required_tier IS
    'Snapshot of the strategy tier at assignment time (free/starter/pro/enterprise)';
COMMENT ON COLUMN public.strategy_assignments.mirror_enabled IS
    'If true, user receives auto-mirrored trades for this strategy';
COMMENT ON COLUMN public.strategy_assignments.assigned_by IS
    'Admin user id who created this assignment';
