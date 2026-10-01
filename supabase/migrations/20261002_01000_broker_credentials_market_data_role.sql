-- broker_credentials: separate the EXECUTION credential from the MARKET-DATA one.
--
-- Why
-- ---
-- Today the table carries `UNIQUE(user_id, broker)` and `is_active`, and
-- `activate_broker()` deactivates every *other* broker for the user. So a tenant has
-- exactly one credential and it is used for everything: order placement, positions,
-- funds, quotes, the WebSocket feed.
--
-- That is a real constraint, not a convenience. Two things follow from it:
--
-- 1. A broker that authenticates for orders but serves no market data cannot be used
--    at all without losing the other half. Dhan on the SaaS deployment authenticates
--    and reports funds (proved live: session health and funds both VALID) but answers
--    `806 Data APIs not Subscribed` for quotes, while Fyers serves quotes and needs a
--    daily human PIN re-auth. Neither broker does both unattended, so "execution" and
--    "market data" genuinely need to be different brokers for the same tenant.
--
-- 2. Every read path resolves through `get_active_broker()`, which selects
--    `is_active = True` with `.limit(1)` and no ordering. Once a second row can exist
--    per user, that query can return the market-data row and the *execution* path then
--    reads prices through the market-data broker's credentials — which is the exact
--    inversion that made execution point at a venue with no order endpoint. Every such
--    query is role-scoped in the same commit; this migration is what makes that
--    scoping necessary rather than optional.
--
-- Backfill
-- -------
-- Every existing row is labelled `execution`. All 31 existing tenants keep exactly the
-- behaviour they have now: their current credential is still the one used for orders
-- *and* for data. Nothing is re-pointed and no row is duplicated.
--
-- The fallback that keeps it that way lives in the repository, not here: a tenant with
-- no market-data row resolves market data through the execution credential. Absence of
-- a market-data row therefore means "use the execution broker", never "no data" — which
-- is the fail-closed-in-the-right-direction reading and the reason this migration cannot
-- break a live tenant on its own.
--
-- Idempotent. Safe to run against a database that already has the column, including one
-- where a market-data row exists: the DEFAULT only applies to rows written without a
-- role, and the constraint is dropped before being re-added.

ALTER TABLE public.broker_credentials
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'execution';

ALTER TABLE public.broker_credentials
    DROP CONSTRAINT IF EXISTS broker_credentials_role_check;

ALTER TABLE public.broker_credentials
    ADD CONSTRAINT broker_credentials_role_check
    CHECK (role IN ('execution', 'market_data'));

-- The old uniqueness is what makes "same broker for both roles" impossible. Replace it
-- with one that includes the role, so a tenant may hold both an execution and a
-- market-data credential for the same broker name.
--
-- `broker_credentials_user_id_broker_key` is the name PostgreSQL generated for the
-- inline `UNIQUE(user_id, broker)` in the init migration; it is dropped by name rather
-- than assumed, and `IF EXISTS` keeps a re-run quiet.
ALTER TABLE public.broker_credentials
    DROP CONSTRAINT IF EXISTS broker_credentials_user_id_broker_key;

ALTER TABLE public.broker_credentials
    ADD CONSTRAINT broker_credentials_user_id_broker_role_key
    UNIQUE (user_id, broker, role);

-- Reading the active broker must not be able to return a market-data row. There is no
-- index on (user_id, is_active) and the queries select a single row, so this is left as
-- a plain index rather than a partial one: the table is small (one to two rows per
-- tenant) and a partial index would need re-creating every time a tenant's role mix
-- changed.
CREATE INDEX IF NOT EXISTS idx_broker_credentials_user_role_active
    ON public.broker_credentials (user_id, role, is_active);
