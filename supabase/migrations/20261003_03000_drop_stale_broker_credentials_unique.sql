-- Drop the unique (user_id, broker) index that the market-data role migration did not remove.
--
-- Why
-- ---
-- Two migrations disagree about what makes a broker credential unique, and the older one wins.
--
--   20260828_02200_broker_connection_status.sql   creates, as a standalone unique *index*,
--       uq_broker_credentials_user_broker ON (user_id, broker)
--       — for the OAuth connect/refresh upsert's `on_conflict="user_id,broker"` target.
--
--   20261002_01000_broker_credentials_market_data_role.sql   adds the `role` column and
--       UNIQUE (user_id, broker, role), so one tenant can hold an execution credential *and* a
--       market-data-only credential for the same broker.
--
-- `01000` tried to clear the way with
--
--     ALTER TABLE broker_credentials DROP CONSTRAINT IF EXISTS broker_credentials_user_id_broker_key;
--
-- but that is the name PostgreSQL generated for the inline `UNIQUE (user_id, broker)` in the init
-- migration — a different object. `DROP CONSTRAINT` cannot drop a plain unique index; that needs
-- `DROP INDEX`. So on any database where both migrations ran, `uq_broker_credentials_user_broker`
-- survived, and it is the stricter of the two: two rows for the same (user_id, broker) are
-- impossible no matter what `role` says.
--
-- The consequence is that the market-data / execution credential split does not work. Saving a
-- market-data-only credential raises
--
--     duplicate key value violates unique constraint "uq_broker_credentials_user_broker"
--
-- Reproduced locally: `tests/test_broker_market_data_role_db.py::
-- test_both_roles_coexist_and_are_separately_addressable` fails with that exact error, having
-- passed before this index was reintroduced by applying the migration set in order.
--
-- Nothing here detects it at runtime. `core.safe_query` turns the failure into `None`, so the save
-- reports success and no market-data row exists. `verify_production_broker_roles.py` checks that
-- the `role` column is readable and that rows are addressable by role — it does not insert a
-- second role, which is why the production verification of `01000` passed while this was broken:
-- all 17 production rows are `execution`, so no pair collided and the stale index was invisible.
--
-- What this does
-- --------------
-- 1. Drops the stale index if it exists.
-- 2. Re-asserts `(user_id, broker, role)` uniqueness, which is what the table's model says and
--    what `broker_repository` already filters on.
--
-- Applying to a database where the stale index is absent — because `02200` never ran there, or
-- ran before `01000` — is a no-op apart from re-adding a constraint that already exists. Both
-- statements are guarded.
--
-- Safe to run before deploying 01000 as well: if `role` does not exist yet the `DO` block below
-- skips, and the `DROP INDEX` still removes the stale one.

DROP INDEX IF EXISTS public.uq_broker_credentials_user_broker;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'broker_credentials' AND column_name = 'role'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid = 'public.broker_credentials'::regclass
              AND conname = 'broker_credentials_user_id_broker_role_key'
        ) THEN
            ALTER TABLE public.broker_credentials
                ADD CONSTRAINT broker_credentials_user_id_broker_role_key
                UNIQUE (user_id, broker, role);
            RAISE NOTICE 'added UNIQUE (user_id, broker, role) to broker_credentials';
        ELSE
            RAISE NOTICE 'UNIQUE (user_id, broker, role) already present on broker_credentials';
        END IF;
    ELSE
        RAISE NOTICE 'broker_credentials.role does not exist yet — skipped';
    END IF;
END $$;