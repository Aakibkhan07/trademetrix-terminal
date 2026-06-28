-- Trade Metrix Terminal — Supabase Schema + RLS
-- Run this in Supabase SQL Editor to bootstrap.

-- 0. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- 1. TABLES

CREATE TABLE public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT DEFAULT '',
    is_admin BOOLEAN DEFAULT FALSE,
    subscription_tier TEXT DEFAULT 'free' CHECK (subscription_tier IN ('free', 'starter', 'pro', 'enterprise')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE public.broker_credentials (
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

CREATE TABLE public.strategies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'builtin' CHECK (type IN ('builtin', 'custom_python', 'visual')),
    config JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE public.strategy_runs (
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

CREATE TABLE public.signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    strategy_id UUID NOT NULL REFERENCES public.strategies(id) ON DELETE CASCADE,
    run_id UUID REFERENCES public.strategy_runs(id) ON DELETE SET NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_type TEXT NOT NULL DEFAULT 'MARKET',
    product TEXT NOT NULL DEFAULT 'INTRADAY',
    quantity INT NOT NULL DEFAULT 0,
    price DOUBLE PRECISION DEFAULT 0.0,
    trigger_price DOUBLE PRECISION,
    reason TEXT DEFAULT '',
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    risk_checked_at TIMESTAMPTZ,
    risk_passed BOOLEAN,
    risk_reason TEXT,
    executed BOOLEAN DEFAULT FALSE
);

CREATE TABLE public.orders (
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
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE public.trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    order_id UUID REFERENCES public.orders(id) ON DELETE SET NULL,
    strategy_id UUID REFERENCES public.strategies(id) ON DELETE SET NULL,
    broker TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INT NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    trade_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_paper BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE public.positions_snapshot (
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
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE public.risk_settings (
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

CREATE TABLE public.journal_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    entry_type TEXT NOT NULL CHECK (entry_type IN ('ai_analysis', 'manual', 'system')),
    content TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    trade_ids UUID[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE public.broadcasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'critical')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE public.subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    plan TEXT NOT NULL CHECK (plan IN ('starter', 'pro', 'enterprise')),
    razorpay_subscription_id TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'cancelled', 'expired')),
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE public.plans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    price_monthly INT NOT NULL DEFAULT 0,
    price_yearly INT NOT NULL DEFAULT 0,
    max_brokers INT DEFAULT 1,
    max_strategies INT DEFAULT 1,
    max_symbols INT DEFAULT 5,
    live_trading BOOLEAN DEFAULT FALSE,
    ai_desk BOOLEAN DEFAULT FALSE,
    api_access BOOLEAN DEFAULT FALSE,
    description TEXT DEFAULT '',
    features JSONB DEFAULT '[]'
);

CREATE TABLE public.audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    resource TEXT NOT NULL,
    resource_id TEXT DEFAULT '',
    details JSONB DEFAULT '{}',
    ip_address TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- audit_log is append-only; no updates or deletes.

CREATE TABLE public.symbol_master (
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

CREATE INDEX idx_symbol_master_lookup ON public.symbol_master(broker, exchange, symbol);

-- 2. ROW LEVEL SECURITY

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

-- 3. RLS POLICIES — default-deny, owner-scoped

CREATE POLICY "users_read_own_profile" ON public.profiles
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "users_update_own_profile" ON public.profiles
    FOR UPDATE USING (auth.uid() = id) WITH CHECK (auth.uid() = id);

CREATE POLICY "users_read_own_broker_creds" ON public.broker_credentials
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "users_manage_own_broker_creds" ON public.broker_credentials
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users_read_own_strategies" ON public.strategies
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "users_manage_own_strategies" ON public.strategies
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users_read_own_runs" ON public.strategy_runs
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "users_manage_own_runs" ON public.strategy_runs
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users_read_own_signals" ON public.signals
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "users_manage_own_signals" ON public.signals
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users_read_own_orders" ON public.orders
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "users_manage_own_orders" ON public.orders
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users_read_own_trades" ON public.trades
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "users_read_own_positions" ON public.positions_snapshot
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "users_read_own_risk" ON public.risk_settings
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "users_manage_own_risk" ON public.risk_settings
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users_read_own_journal" ON public.journal_entries
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "users_manage_own_journal" ON public.journal_entries
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users_read_audit_own" ON public.audit_log
    FOR SELECT USING (auth.uid() = user_id);

-- Broadcasts are readable by all authenticated users
CREATE POLICY "broadcasts_read_all" ON public.broadcasts
    FOR SELECT USING (auth.role() = 'authenticated');

-- Admin-only policies
CREATE POLICY "admin_all_profiles" ON public.profiles
    FOR ALL USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND is_admin = TRUE)
    );

CREATE POLICY "admin_all_audit" ON public.audit_log
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND is_admin = TRUE)
    );

-- 4. AUTO-CREATE PROFILE ON SIGNUP
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name)
    VALUES (NEW.id, NEW.email, COALESCE(NEW.raw_user_meta_data->>'full_name', ''));
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();

-- 5. DEFAULT PLANS
INSERT INTO public.plans (id, name, price_monthly, price_yearly, max_brokers, max_strategies, max_symbols, live_trading, ai_desk, api_access, description, features) VALUES
('free', 'Free', 0, 0, 1, 1, 3, FALSE, FALSE, FALSE, 'Get started with paper trading', '["1 Broker", "1 Strategy", "3 Symbols", "Paper Trading Only"]'),
('starter', 'Starter', 999, 9990, 2, 3, 10, FALSE, TRUE, FALSE, 'For serious learners', '["2 Brokers", "3 Strategies", "10 Symbols", "AI Trade Journal"]'),
('pro', 'Pro', 2499, 24990, 5, 10, 50, TRUE, TRUE, TRUE, 'For active algo traders', '["5 Brokers", "10 Strategies", "50 Symbols", "Live Trading", "AI Trading Desk", "API Access"]'),
('enterprise', 'Enterprise', 9999, 99990, 20, 50, 500, TRUE, TRUE, TRUE, 'For power users and firms', '["20 Brokers", "50 Strategies", "500 Symbols", "Live Trading", "AI Trading Desk", "API Access", "Priority Support"]');
