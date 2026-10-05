-- Dhan authoritative instrument master.
--
-- Why a new table rather than more rows in symbol_master
-- -------------------------------------------------------
-- symbol_master carries UNIQUE (broker, token), where `token` is the broker's security
-- id. Measured against Dhan's published detailed master (202,243 rows, fetched
-- 2026-10-06), that constraint is wrong: 14,626 security ids occur more than once, each
-- time under a different exchange or segment -- security id 513496 is both a BSE equity
-- and an MCX gold call. Writing Dhan rows there would fail or silently drop ~14.6k real
-- contracts.
--
-- The verified uniqueness key is (exchange, exchange_segment, security_id): zero
-- duplicates across all 202,243 rows. That is the constraint created below.
--
-- symbol_master is left in place, still serving the legacy broker-symbol mapping. It is
-- NOT authoritative for contract metadata or lot sizes and must never be consulted for
-- them; `source` records which rows came from where so precedence is explicit rather
-- than accidental.

CREATE TABLE IF NOT EXISTS public.dhan_instruments (
    id                    BIGSERIAL PRIMARY KEY,

    -- Identity. security_id alone is NOT unique in Dhan, hence the composite key.
    security_id           TEXT        NOT NULL,
    exchange              TEXT        NOT NULL,
    exchange_segment      TEXT        NOT NULL,
    provider              TEXT        NOT NULL DEFAULT 'dhan',

    -- Symbols
    trading_symbol        TEXT        NOT NULL DEFAULT '',
    display_symbol        TEXT        NOT NULL DEFAULT '',
    underlying_symbol     TEXT        NOT NULL DEFAULT '',
    underlying_security_id TEXT       NOT NULL DEFAULT '',

    -- Contract shape
    instrument_type       TEXT        NOT NULL,
    instrument_family     TEXT        NOT NULL DEFAULT '',
    expiry_date           DATE,
    strike_price          DOUBLE PRECISION,
    option_type           TEXT        NOT NULL DEFAULT '',

    -- Trading parameters. lot_size is INT and strictly positive: the application
    -- rejects zero, negative, boolean, NaN, infinite and fractional lot sizes before a
    -- row is ever built, so the column only ever holds a whole positive number.
    lot_size              INTEGER     NOT NULL CHECK (lot_size > 0),
    tick_size             DOUBLE PRECISION NOT NULL DEFAULT 0.05 CHECK (tick_size > 0),

    instrument_status     TEXT        NOT NULL DEFAULT 'active',

    -- Provenance. A row without a source cannot be audited, and an un-auditable lot
    -- size is exactly the thing this table exists to eliminate.
    source                TEXT        NOT NULL DEFAULT 'dhan_instrument_master',
    source_url            TEXT        NOT NULL DEFAULT '',
    source_updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT dhan_instruments_identity
        UNIQUE (provider, exchange, exchange_segment, security_id),

    -- Option contracts are only tradeable when fully identified. Enforced in the
    -- database as well as in the parser, so a bad row cannot be inserted by any other
    -- path.
    CONSTRAINT dhan_instruments_option_complete CHECK (
        instrument_type <> 'OPT' OR (
            underlying_symbol <> ''
            AND underlying_security_id <> ''
            AND expiry_date IS NOT NULL
            AND strike_price IS NOT NULL
            AND option_type IN ('CE', 'PE')
        )
    )
);

-- Resolution is by (exchange, segment, security_id) and by security id alone within an
-- exchange; both are covered by the unique index's leading columns.
CREATE INDEX IF NOT EXISTS idx_dhan_instruments_security
    ON public.dhan_instruments (exchange, security_id);

-- Option-chain style lookup: every contract for an underlying on an expiry.
CREATE INDEX IF NOT EXISTS idx_dhan_instruments_underlying_expiry
    ON public.dhan_instruments (underlying_symbol, expiry_date, strike_price)
    WHERE instrument_type = 'OPT';

CREATE INDEX IF NOT EXISTS idx_dhan_instruments_trading_symbol
    ON public.dhan_instruments (trading_symbol);

-- Refresh bookkeeping: how many rows a successful sync installed, and when.
CREATE TABLE IF NOT EXISTS public.dhan_instrument_sync (
    id                    BIGSERIAL PRIMARY KEY,
    source_url            TEXT        NOT NULL,
    started_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at          TIMESTAMPTZ,
    row_count             INTEGER     NOT NULL DEFAULT 0,
    index_option_count    INTEGER     NOT NULL DEFAULT 0,
    stock_option_count    INTEGER     NOT NULL DEFAULT 0,
    option_contract_count INTEGER     NOT NULL DEFAULT 0,
    future_count          INTEGER     NOT NULL DEFAULT 0,
    validation_status     TEXT        NOT NULL DEFAULT 'pending',
    error                 TEXT        NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_dhan_instrument_sync_recent
    ON public.dhan_instrument_sync (started_at DESC);

ALTER TABLE public.dhan_instruments ENABLE ROW LEVEL SECURITY;