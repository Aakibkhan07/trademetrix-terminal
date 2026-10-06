-- The derivative identity of an order must survive the OMS.
--
-- Measured, not inferred: with an NIFTY option resolved dynamically from the Dhan master
-- (securityId 40749, NSE_FNO, expiry 2026-10-06, strike 23250, CE, lot 65), an order placed
-- through the real OMS queue path reached Dhan with the correct securityId and
-- exchangeSegment but NO expiry, NO strike and NO option type.
--
-- `DhanAdapter.place_order` emits drvExpiryDate / drvStrikePrice / drvOptionType only when
-- `instrument_type` is FUT or OPT, and `instrument_type` was not a column here, so
-- `OmniOrder` could not carry it and `_process_queue` could not rebuild it. A direct
-- `ExecutionManager.place_order` call carried all of them -- the two order paths disagreed
-- about which contract was being traded, and only the queue path is what production uses.
--
-- Idempotent. Every column is nullable or defaulted so existing rows and an equity order
-- both remain valid, and `OmniOrder(**row)` still loads them.

ALTER TABLE public.oms_orders
    ADD COLUMN IF NOT EXISTS instrument_type     TEXT,
    ADD COLUMN IF NOT EXISTS expiry_date         TEXT,
    ADD COLUMN IF NOT EXISTS strike_price        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS option_type         TEXT,
    ADD COLUMN IF NOT EXISTS validity            TEXT,
    ADD COLUMN IF NOT EXISTS disclosed_quantity  INTEGER;

COMMENT ON COLUMN public.oms_orders.instrument_type IS
    'OPT / FUT / EQ. Without it the broker adapter emits no derivative identity at all.';
COMMENT ON COLUMN public.oms_orders.expiry_date IS
    'Contract expiry (drvExpiryDate). Restored into ExecutionRequest by the OMS worker.';
COMMENT ON COLUMN public.oms_orders.strike_price IS
    'Contract strike (drvStrikePrice).';
COMMENT ON COLUMN public.oms_orders.option_type IS
    'CE or PE (drvOptionType).';
COMMENT ON COLUMN public.oms_orders.validity IS
    'DAY / IOC. Sent as the broker order validity.';
COMMENT ON COLUMN public.oms_orders.disclosed_quantity IS
    'Disclosed quantity for the broker order.';
