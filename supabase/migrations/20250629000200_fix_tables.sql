-- Fix existing tables and create missing ones
-- Run this in Supabase SQL Editor (or via psql)

-- ── 1. FIX EXISTING TABLES ────────────────────────────────────

ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS full_name TEXT DEFAULT '';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS subscription_tier TEXT DEFAULT 'free' CHECK (subscription_tier IN ('free', 'starter', 'pro', 'enterprise'));
-- Copy name -> full_name for existing rows
UPDATE public.profiles SET full_name = name WHERE full_name = '' AND name IS NOT NULL;

ALTER TABLE public.strategies ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE;
ALTER TABLE public.strategies ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'builtin' CHECK (type IN ('builtin', 'custom_python', 'visual'));
ALTER TABLE public.strategies ADD COLUMN IF NOT EXISTS config JSONB DEFAULT '{}';
ALTER TABLE public.strategies ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

-- ── 2. CREATE MISSING TABLES ──────────────────────────────────

CREATE TABLE IF NOT EXISTS public.broker_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    broker TEXT NOT NULL CHECK (broker IN ('fyers','dhan','zerodha','angelone','upstox','fivepaisa','aliceblue','finvasia','flattrade','kotakneo')),
    encrypted_api_key TEXT NOT NULL,
    encrypted_secret_key TEXT NOT NULL,
    encrypted_access_token TEXT DEFAULT '',
    additional_params JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, broker)
);

CREATE TABLE IF NOT EXISTS public.risk_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    strategy_id UUID REFERENCES public.strategies(id) ON DELETE CASCADE,
    max_capital DOUBLE PRECISION DEFAULT 0.0,
    max_position_size DOUBLE PRECISION DEFAULT 0.0,
    max_open_positions INT DEFAULT 10,
    max_daily_loss DOUBLE PRECISION DEFAULT 0.0,
    max_drawdown_pct DOUBLE PRECISION DEFAULT 0.0,
    kill_switch_enabled BOOLEAN DEFAULT FALSE,
    is_live BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, strategy_id)
);

CREATE TABLE IF NOT EXISTS public.orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    strategy_id UUID REFERENCES public.strategies(id) ON DELETE SET NULL,
    run_id UUID REFERENCES public.strategy_runs(id) ON DELETE SET NULL,
    signal_id UUID REFERENCES public.signals(id) ON DELETE SET NULL,
    broker TEXT NOT NULL,
    broker_order_id TEXT DEFAULT '',
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    product TEXT NOT NULL,
    quantity INT NOT NULL,
    price DOUBLE PRECISION DEFAULT 0.0,
    trigger_price DOUBLE PRECISION,
    status TEXT NOT NULL DEFAULT 'PENDING',
    filled_quantity INT DEFAULT 0,
    average_price DOUBLE PRECISION DEFAULT 0.0,
    total_value DOUBLE PRECISION DEFAULT 0.0,
    message TEXT DEFAULT '',
    signal_at TIMESTAMPTZ,
    risk_checked_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    filled_at TIMESTAMPTZ,
    latency_ms DOUBLE PRECISION,
    slippage DOUBLE PRECISION,
    is_paper BOOLEAN DEFAULT TRUE,
    instrument_type TEXT DEFAULT 'EQ',
    strike_price DOUBLE PRECISION,
    expiry_date TEXT,
    option_type TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.strategy_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    strategy_id UUID NOT NULL REFERENCES public.strategies(id) ON DELETE CASCADE,
    broker TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'PAPER' CHECK (mode IN ('PAPER', 'LIVE')),
    symbols TEXT[] DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'stopped' CHECK (status IN ('running', 'paused', 'stopped', 'error')),
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,
    daily_pnl DOUBLE PRECISION DEFAULT 0.0,
    total_pnl DOUBLE PRECISION DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.positions_snapshot (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    broker TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    quantity INT DEFAULT 0,
    buy_quantity INT DEFAULT 0,
    sell_quantity INT DEFAULT 0,
    average_buy_price DOUBLE PRECISION DEFAULT 0.0,
    average_sell_price DOUBLE PRECISION DEFAULT 0.0,
    unrealised_pnl DOUBLE PRECISION DEFAULT 0.0,
    realised_pnl DOUBLE PRECISION DEFAULT 0.0,
    m2m DOUBLE PRECISION DEFAULT 0.0,
    product TEXT NOT NULL,
    instrument_type TEXT DEFAULT 'EQ',
    strike_price DOUBLE PRECISION,
    expiry_date TEXT,
    option_type TEXT DEFAULT '',
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.journal_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    entry_type TEXT NOT NULL CHECK (entry_type IN ('ai_analysis', 'manual', 'system')),
    content TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    trade_ids UUID[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    resource TEXT NOT NULL,
    resource_id TEXT DEFAULT '',
    details JSONB DEFAULT '{}',
    ip_address TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.symbol_master (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    broker TEXT NOT NULL,
    broker_symbol TEXT NOT NULL,
    token TEXT NOT NULL,
    instrument_type TEXT DEFAULT '',
    expiry DATE,
    strike DOUBLE PRECISION DEFAULT 0.0,
    option_type TEXT DEFAULT '',
    lot_size INT DEFAULT 1,
    tick_size DOUBLE PRECISION DEFAULT 0.05,
    segment TEXT DEFAULT '',
    last_updated DATE DEFAULT CURRENT_DATE,
    UNIQUE(broker, token)
);

CREATE INDEX IF NOT EXISTS idx_symbol_master_lookup ON public.symbol_master(broker, exchange, symbol);
CREATE INDEX IF NOT EXISTS idx_orders_user ON public.orders(user_id, created_at DESC);

-- ── 3. ROW LEVEL SECURITY ─────────────────────────────────────

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.broker_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.strategies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.strategy_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.positions_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risk_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.journal_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

-- ── 4. RLS POLICIES ───────────────────────────────────────────

-- Profiles
DROP POLICY IF EXISTS "users_read_own_profile" ON public.profiles;
CREATE POLICY "users_read_own_profile" ON public.profiles
    FOR SELECT USING (auth.uid() = id);
DROP POLICY IF EXISTS "users_update_own_profile" ON public.profiles;
CREATE POLICY "users_update_own_profile" ON public.profiles
    FOR UPDATE USING (auth.uid() = id) WITH CHECK (auth.uid() = id);

-- Broker credentials
DROP POLICY IF EXISTS "users_read_own_broker_creds" ON public.broker_credentials;
CREATE POLICY "users_read_own_broker_creds" ON public.broker_credentials
    FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "users_manage_own_broker_creds" ON public.broker_credentials;
CREATE POLICY "users_manage_own_broker_creds" ON public.broker_credentials
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Strategies
DROP POLICY IF EXISTS "users_read_own_strategies" ON public.strategies;
CREATE POLICY "users_read_own_strategies" ON public.strategies
    FOR SELECT USING (auth.uid() = user_id OR user_id IS NULL);
DROP POLICY IF EXISTS "users_manage_own_strategies" ON public.strategies;
CREATE POLICY "users_manage_own_strategies" ON public.strategies
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Strategy runs
DROP POLICY IF EXISTS "users_read_own_runs" ON public.strategy_runs;
CREATE POLICY "users_read_own_runs" ON public.strategy_runs
    FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "users_manage_own_runs" ON public.strategy_runs;
CREATE POLICY "users_manage_own_runs" ON public.strategy_runs
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Signals
DROP POLICY IF EXISTS "users_read_own_signals" ON public.signals;
CREATE POLICY "users_read_own_signals" ON public.signals
    FOR SELECT USING (true);

-- Orders
DROP POLICY IF EXISTS "users_read_own_orders" ON public.orders;
CREATE POLICY "users_read_own_orders" ON public.orders
    FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "users_manage_own_orders" ON public.orders;
CREATE POLICY "users_manage_own_orders" ON public.orders
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Trades
DROP POLICY IF EXISTS "users_read_own_trades" ON public.trades;
CREATE POLICY "users_read_own_trades" ON public.trades
    FOR SELECT USING (auth.uid() = user_id);

-- Positions
DROP POLICY IF EXISTS "users_read_own_positions" ON public.positions_snapshot;
CREATE POLICY "users_read_own_positions" ON public.positions_snapshot
    FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "users_manage_own_positions" ON public.positions_snapshot;
CREATE POLICY "users_manage_own_positions" ON public.positions_snapshot
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Risk settings
DROP POLICY IF EXISTS "users_read_own_risk" ON public.risk_settings;
CREATE POLICY "users_read_own_risk" ON public.risk_settings
    FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "users_manage_own_risk" ON public.risk_settings;
CREATE POLICY "users_manage_own_risk" ON public.risk_settings
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Journal
DROP POLICY IF EXISTS "users_read_own_journal" ON public.journal_entries;
CREATE POLICY "users_read_own_journal" ON public.journal_entries
    FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "users_manage_own_journal" ON public.journal_entries;
CREATE POLICY "users_manage_own_journal" ON public.journal_entries
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Audit log
DROP POLICY IF EXISTS "users_read_audit_own" ON public.audit_log;
CREATE POLICY "users_read_audit_own" ON public.audit_log
    FOR SELECT USING (auth.uid() = user_id);

-- Broadcasts
DROP POLICY IF EXISTS "broadcasts_read_all" ON public.broadcasts;
CREATE POLICY "broadcasts_read_all" ON public.broadcasts
    FOR SELECT USING (auth.role() = 'authenticated');

-- Admin policies
DROP POLICY IF EXISTS "admin_all_profiles" ON public.profiles;
CREATE POLICY "admin_all_profiles" ON public.profiles
    FOR ALL USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND is_admin = TRUE)
    );
DROP POLICY IF EXISTS "admin_all_audit" ON public.audit_log;
CREATE POLICY "admin_all_audit" ON public.audit_log
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND is_admin = TRUE)
    );
