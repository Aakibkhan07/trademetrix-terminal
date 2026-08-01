-- Phase 5 — Institutional Backtest Engine persistence
-- 1) Durable candle store (historical OHLCV+OI fetched from Fyers/Yahoo is
--    otherwise lost on API restart — backtests need long-range history).
-- 2) Corporate actions (splits / bonuses / dividends) for price adjustment.
-- 3) Backtest run archive (results persist across restarts).

CREATE TABLE IF NOT EXISTS candles (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    interval TEXT NOT NULL DEFAULT '15m',
    ts TIMESTAMPTZ NOT NULL,
    open DOUBLE PRECISION NOT NULL DEFAULT 0,
    high DOUBLE PRECISION NOT NULL DEFAULT 0,
    low DOUBLE PRECISION NOT NULL DEFAULT 0,
    close DOUBLE PRECISION NOT NULL DEFAULT 0,
    volume BIGINT NOT NULL DEFAULT 0,
    oi BIGINT NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'fyers',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_candles_unique ON candles (symbol, exchange, interval, ts);
CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles (exchange, interval, symbol, ts);

CREATE TABLE IF NOT EXISTS corporate_actions (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    ex_date DATE NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('SPLIT', 'BONUS', 'DIVIDEND')),
    ratio TEXT NOT NULL DEFAULT '',        -- e.g. '1:2' (old:new) for split/bonus
    dividend_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    record_date DATE,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_corporate_actions_symbol ON corporate_actions (symbol, ex_date);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT '',
    strategy_type TEXT NOT NULL DEFAULT '',
    strategy_id TEXT NOT NULL DEFAULT '',
    symbol TEXT NOT NULL DEFAULT '',
    interval TEXT NOT NULL DEFAULT '15m',
    days INT NOT NULL DEFAULT 60,
    config JSONB NOT NULL DEFAULT '{}',
    summary JSONB NOT NULL DEFAULT '{}',
    trades JSONB NOT NULL DEFAULT '[]',
    equity_curve JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_user ON backtest_runs (user_id, created_at DESC);
