import logging

from core.db import get_supabase

logger = logging.getLogger(__name__)

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS public.broker_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    broker TEXT NOT NULL,
    encrypted_api_key TEXT NOT NULL,
    encrypted_secret_key TEXT NOT NULL,
    encrypted_access_token TEXT DEFAULT '',
    additional_params JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, broker)
);

CREATE TABLE IF NOT EXISTS public.strategies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'builtin',
    config JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.strategy_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    strategy_id UUID,
    broker TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'PAPER',
    symbols TEXT[] DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'stopped',
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,
    daily_pnl DOUBLE PRECISION DEFAULT 0.0,
    total_pnl DOUBLE PRECISION DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    strategy_id UUID,
    run_id UUID,
    signal_id UUID,
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
    option_type TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    order_id UUID,
    strategy_id UUID,
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

CREATE TABLE IF NOT EXISTS public.positions_snapshot (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
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

CREATE TABLE IF NOT EXISTS public.risk_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    strategy_id UUID,
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

CREATE TABLE IF NOT EXISTS public.journal_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    entry_type TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    trade_ids UUID[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    action TEXT NOT NULL,
    resource TEXT NOT NULL,
    resource_id TEXT DEFAULT '',
    details JSONB DEFAULT '{}',
    ip_address TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.user_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    symbol TEXT NOT NULL,
    condition TEXT NOT NULL,
    target_price DOUBLE PRECISION NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    triggered_at TIMESTAMPTZ,
    note TEXT DEFAULT '',
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
"""


def run_migrations() -> None:
    statements = [s.strip() for s in MIGRATION_SQL.split(";") if s.strip()]
    supabase = get_supabase()
    for stmt in statements:
        try:
            supabase.table("_migrations").select("*").limit(1).execute()
        except Exception:
            pass
        try:
            supabase.rpc("exec_sql", {"query": stmt + ";"}).execute()
        except Exception as e:
            logger.warning("Migration statement failed (may already exist): %s", e)
