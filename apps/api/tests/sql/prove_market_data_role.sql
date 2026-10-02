-- Proves what the market-data-role migration actually bought, against the real table.
--
-- Read this as five claims, each of which the pre-migration schema would have failed:
--   1. one tenant may hold BOTH roles for the same broker  (old: UNIQUE(user_id, broker))
--   2. a row written without a role is an execution row   (the backfill rule)
--   3. a second row for the same user+broker+role is still refused
--   4. a role outside the enum is refused
--   5. the two roles are independently addressable, which is what the repository's
--      role-scoped reads depend on
--
-- Everything runs in one transaction and rolls back, so the table is left untouched.
-- Runs inside a transaction deliberately: the unique-violation and check-violation cases
-- below abort the statement, and an aborted transaction outside a block would take the
-- rest of the script with it.
\set ON_ERROR_STOP on
BEGIN;

-- Without this, the `RAISE NOTICE` lines below are swallowed and the two "correctly
-- refused" claims look like they did nothing. The proof is really the absence of the
-- `RAISE EXCEPTION 'UNEXPECTED…'` branch — that is what aborts the transaction and makes
-- psql exit non-zero — but a proof you cannot read is a poor artifact.
SET client_min_messages = NOTICE;

-- A pre-existing profile is used rather than a fabricated tenant: `profiles.id` carries a
-- foreign key to `auth.users`, and a GoTrue user cannot be created from psql alone.

\echo ''
\echo '--- 1. both roles coexist for the SAME user + broker ---'
\echo '    (the old UNIQUE(user_id, broker) rejected the second row outright)'
INSERT INTO public.broker_credentials
    (user_id, broker, encrypted_api_key, encrypted_secret_key, is_active, role)
VALUES
    (:'uid', 'fyers', 'exec-key',   's', true, 'execution'),
    (:'uid', 'fyers', 'market-key', 's', true, 'market_data');
SELECT role, encrypted_api_key FROM public.broker_credentials
 WHERE user_id = :'uid' ORDER BY role;

\echo ''
\echo '--- 2. role omitted on insert defaults to execution (the backfill rule) ---'
\echo '    (this is why the migration cannot re-point an existing tenant)'
INSERT INTO public.broker_credentials
    (user_id, broker, encrypted_api_key, encrypted_secret_key, is_active)
VALUES (:'uid', 'dhan', 'k', 's', true);
SELECT broker, role FROM public.broker_credentials
 WHERE user_id = :'uid' AND broker = 'dhan';

\echo ''
\echo '--- 3. a second row for the same user + broker + role is still refused ---'
DO $$
BEGIN
    INSERT INTO public.broker_credentials
        (user_id, broker, encrypted_api_key, encrypted_secret_key, role)
    VALUES (:UID_LITERAL, 'fyers', 'dup', 's', 'execution');
    RAISE EXCEPTION 'UNEXPECTED: duplicate user+broker+role was accepted';
EXCEPTION WHEN unique_violation THEN
    RAISE NOTICE 'correctly refused: %', SQLERRM;
END $$;

\echo ''
\echo '--- 4. a role outside the enum is refused ---'
DO $$
BEGIN
    INSERT INTO public.broker_credentials
        (user_id, broker, encrypted_api_key, encrypted_secret_key, role)
    VALUES (:UID_LITERAL, 'fyers', 'k', 's', 'typo_role');
    RAISE EXCEPTION 'UNEXPECTED: an invalid role was accepted';
EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'correctly refused: %', SQLERRM;
END $$;

\echo ''
\echo '--- 5. each role is independently addressable ---'
\echo '    (the shape of every role-scoped query in broker_repository.py)'
SELECT 'execution' AS role,
       count(*) FILTER (WHERE is_active) AS active
  FROM public.broker_credentials WHERE user_id = :'uid' AND role = 'execution'
UNION ALL
SELECT 'market_data',
       count(*) FILTER (WHERE is_active)
  FROM public.broker_credentials WHERE user_id = :'uid' AND role = 'market_data';

ROLLBACK;
