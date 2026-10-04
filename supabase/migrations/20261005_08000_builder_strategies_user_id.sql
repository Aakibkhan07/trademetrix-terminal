-- Give `builder_strategies` an owner, so one tenant cannot read or run another's strategies.
--
-- Why
-- ---
-- `builder_strategies` was created without any ownership column at all:
--
--     id, version, name, description, author, status, tags, settings, nodes, edges,
--     created_at, updated_at, parent_id, version_number, deployment
--
-- `builder_manager` holds every strategy in one process-wide dict and `list()` returned all
-- of them, so `GET /api/v1/builder/strategies` handed every signed-in user every strategy in
-- the deployment. `get()` looked strategies up by id alone, so any user could read another
-- tenant's full DSL — its nodes, edges, symbol, interval and risk settings. `update`,
-- `delete`, `deploy` and `start` resolved the id the same way.
--
-- Measured on production before this migration: a user created that morning, with zero
-- strategies of their own, read another account's strategy and received HTTP 200 with its
-- 8-node graph and settings.
--
-- ## Why `author` was not usable as-is
--
-- `author` looks like an owner but is not one. On production it holds three distinct kinds
-- of value:
--
--     'user'                                  1144 rows   a literal default, not a user
--     'fa668109-4b1e-4758-a49b-015027ea4115'    16 rows   an internal test account
--     '17ba8349-30e6-48fa-a0f3-9a06389fe44b'     7 rows   the admin account
--
-- So `author` is a uuid for 23 rows and the literal string 'user' for the rest, and code
-- that treats it as an owner silently matches every strategy in the deployment.
--
-- This migration adds a real `user_id` and backfills it from `author` only where `author`
-- is genuinely a uuid — recovering the ownership that was recorded but never queryable. The
-- rows that recorded nothing keep a NULL owner rather than being assigned to a user at
-- random; they are filtered out of every tenant's view and can be retired separately.
--
-- ## Why nullable rather than NOT NULL
--
-- NOT NULL is the stronger constraint and is what a fresh install wants, but it cannot be
-- added here: the rows whose `author` was the literal 'user' recorded no owner, and forcing
-- one would invent an ownership claim that never existed. A NULL owner means "not visible to
-- anyone", which is the safe direction. The column is NOT NULL in the application layer —
-- `create` is the only writer and is given the authenticated user's id — so the only rows
-- that can be NULL are the historical ones this migration cannot attribute.
--
-- Idempotent.

ALTER TABLE public.builder_strategies
    ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES public.profiles(id) ON DELETE CASCADE;

-- Recover ownership where `author` recorded a real user id. The uuid shape is checked in
-- SQL rather than by casting, so the literal 'user' rows cannot abort the statement.
DO $$
DECLARE
    recovered integer;
BEGIN
    UPDATE public.builder_strategies
       SET user_id = author::uuid
     WHERE user_id IS NULL
       AND author ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';

    GET DIAGNOSTICS recovered = ROW_COUNT;
    RAISE NOTICE 'builder_strategies: recovered ownership for % row(s) from author', recovered;
END $$;

-- Every per-tenant read filters on this, including the "which of mine are running" join.
CREATE INDEX IF NOT EXISTS idx_builder_strategies_user_id
    ON public.builder_strategies (user_id);

-- The lifecycle log and version history are read through the same owner check, so they are
-- indexed by strategy id already; this keeps the tenant filter cheap on the versions table,
-- which is queried by strategy id and version.
COMMENT ON COLUMN public.builder_strategies.user_id IS
    'Owning profile. NULL means the row predates ownership tracking and is visible to no tenant.';
