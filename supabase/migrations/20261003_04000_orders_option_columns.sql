-- orders: the five fields the order model sends and the table has never had.
--
-- Why
-- ---
-- `core.models.NormalizedOrder` carries `expiry_date`, `instrument_type`, `option_type`,
-- `strike_price` and `validity`. `_insert_order_atomic` in `execution/manager.py` dumps the whole
-- model and inserts it, so **every order insert sent all five** — and PostgREST rejected it:
--
--     PGRST204  Could not find the 'expiry_date' column of 'orders' in the schema cache
--
-- No other field was missing, so this is not a partial drift: the table was created before the
-- option fields were added to the model, and nothing ever reconciled the two.
--
-- The failure is total and it is silent in the worst way. `_insert_order_atomic` catches the
-- exception, logs at ERROR and returns `None`; the caller treats `None` as "no existing order"
-- and answers
--
--     ExecutionResult(success=False, message="Order insert failed — unknown error",
--                      error_code="INSERT_FAILED")
--
-- which is what the user sees. So **no order is ever recorded** — not a wrong one, none. The
-- consequences reach further than the trade itself:
--
--   * `GET /engine/orders` is permanently empty, so every trade-history table is empty
--   * `risk.helpers.compute_daily_pnl_fifo` reads `orders`, so daily P&L is always 0
--   * `/analytics/pnl?period=1d` therefore reports nothing regardless of what traded
--   * the order audit trail — the record of what the platform actually sent a broker — does not
--     exist, which is the thing an operator needs most when something goes wrong
--
-- Why it survived so long: the tests that exercise order placement mock the database, and the
-- browser crawls never place an order. `scripts/audit_model_schema.py` did not catch it either,
-- because it derives a table name from the model class name — `NormalizedOrder` looks for a table
-- called `normalizedorder` and skips it, which is the right call for a non-table model but means
-- this shape of drift (a model that *is* a table row, gaining fields) is outside what it watches.
--
-- Whether production has these columns was **not verified from here** — the VPS does not answer
-- from this workstation. Production is recorded as having placed filled orders through this path,
-- which implies the columns are present there, but that is inference and `IF NOT EXISTS` makes
-- applying this either way a no-op rather than a failure.
--
-- Column types follow `NormalizedOrder`: `expiry_date` is a `str` in the model (it is a contract
-- code like `26AUG`, not a date), so TEXT rather than DATE — the engine formats it as text and a
-- DATE column would reject it. `instrument_type` and `option_type` are enums stored as their
-- values, with CHECK constraints matching `InstrumentType` and `OptionType` exactly so a bad value
-- fails at the database rather than reaching a broker payload.
--
-- Nullable throughout, because every field has a default in the model and `EQ` cash orders carry
-- none of them. Idempotent.

ALTER TABLE public.orders
    ADD COLUMN IF NOT EXISTS instrument_type TEXT,
    ADD COLUMN IF NOT EXISTS option_type     TEXT,
    ADD COLUMN IF NOT EXISTS strike_price    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS expiry_date     TEXT,
    ADD COLUMN IF NOT EXISTS validity        TEXT;

-- Enum mirrors of `core.models.InstrumentType` and `OptionType`. Added separately and guarded by
-- name so a re-run, or a database that already carries them under another name, is quiet.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.orders'::regclass
          AND conname = 'orders_instrument_type_check'
    ) THEN
        ALTER TABLE public.orders
            ADD CONSTRAINT orders_instrument_type_check
            CHECK (instrument_type IS NULL OR instrument_type IN ('EQ', 'FUT', 'OPT'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.orders'::regclass
          AND conname = 'orders_option_type_check'
    ) THEN
        ALTER TABLE public.orders
            ADD CONSTRAINT orders_option_type_check
            CHECK (option_type IS NULL OR option_type IN ('CE', 'PE'));
    END IF;
END $$;

-- An option leg always has all three of these together, and none of them for cash. Stated as a
-- constraint rather than left to application code because the fields arrived together in the model
-- and a half-populated option order is a payload a broker will reject with something far less
-- legible than this.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.orders'::regclass
          AND conname = 'orders_option_fields_consistent'
    ) THEN
        ALTER TABLE public.orders
            ADD CONSTRAINT orders_option_fields_consistent
            CHECK (
                (instrument_type IS DISTINCT FROM 'OPT')
                OR (option_type IS NOT NULL AND strike_price IS NOT NULL AND expiry_date IS NOT NULL)
            );
    END IF;
END $$;

COMMENT ON COLUMN public.orders.expiry_date IS
    'Option contract code as the broker spells it (e.g. 26AUG). Text, not DATE: the engine formats '
    'this as a string and a date column rejects the value.';
COMMENT ON COLUMN public.orders.instrument_type IS
    'Mirrors core.models.InstrumentType: EQ, FUT or OPT.';
COMMENT ON COLUMN public.orders.option_type IS
    'Mirrors core.models.OptionType: CE or PE. Null for anything that is not an option.';
COMMENT ON COLUMN public.orders.strike_price IS
    'Strike, for options only.';

COMMENT ON COLUMN public.orders.validity IS
    'Order validity as the broker spells it (DAY, IOC, GTC). The insert loop only drops this field '
    'when it is falsy, so a normal DAY order does send it — which is why the column has to exist '
    'for any order to be recorded at all.';