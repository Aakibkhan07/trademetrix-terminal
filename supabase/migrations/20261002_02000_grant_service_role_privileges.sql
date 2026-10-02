-- Table privileges for the roles the API actually uses.
--
-- Why
-- ---
-- Every migration in this directory creates tables, indexes and constraints. **Not one of
-- them grants a privilege.** A database built purely from these migrations therefore leaves
-- `service_role` — the role behind `SUPABASE_SERVICE_KEY`, which the whole API reads and
-- writes through — with no SELECT, INSERT, UPDATE or DELETE on anything.
--
-- On a local stack that is not theoretical. Building this repository's tables into a fresh
-- Supabase and running the API against it produced, for all 28 public tables:
--
--     {"code":"42501",
--      "hint":"Grant the required privileges to the current role with:
--              GRANT SELECT ON public.broker_credentials TO service_role;",
--      "message":"permission denied for table broker_credentials"}
--
-- And the failure is invisible at the application level, which is what makes it worth a
-- migration rather than a README note. `core.safe_query` wraps every query in
-- `async_safe_single` / `async_safe_execute`, which catch all exceptions and return `None`.
-- A permission error therefore arrives in the UI as "no broker connected", "no positions",
-- "no orders" — indistinguishable from a genuinely empty account. A production restore, a
-- staging box, or a new machine built from these migrations would look healthy on /health
-- and empty everywhere else.
--
-- Production evidently has these grants, which is why nobody noticed: they were applied by
-- hand, out of band, and never captured here. This migration is what makes the repository
-- self-sufficient.
--
-- Scope
-- -----
-- `service_role` only. It carries `BYPASSRLS` and is used exclusively server-side with the
-- secret key, so full table privileges are the Supabase-recommended posture for it.
--
-- `authenticated` is deliberately NOT granted DML here. Twelve of the 28 public tables have
-- RLS disabled, and granting a role table-wide DML on a table without RLS exposes every row
-- to every signed-in user. Which of those tables should be readable by the client is a
-- deliberate security decision that needs a review of those twelve, not a side effect of
-- fixing a service-role permission error.
--
-- `anon` needs nothing: it is only ever sent as the `apikey` header on GoTrue `/auth/v1/*`
-- calls, never on a PostgREST table query.
--
-- Idempotent. Safe to re-run.

-- Schema USAGE first: a role needs it before any object grant is reachable.
GRANT USAGE ON SCHEMA public TO service_role;

-- Existing tables.
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON ALL TABLES IN SCHEMA public TO service_role;

-- Identity columns and other sequences. Without this, an INSERT that relies on a
-- DEFAULT nextval() fails with 42501 even when the table grant succeeded, which reads as a
-- permissions problem that was only half fixed.
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- Functions the API calls through PostgREST/RPC.
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO service_role;

-- Future objects. Without this, the next migration that creates a table reintroduces the
-- same gap and the problem comes back one release later — the failure mode that let it
-- survive in the first place.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT EXECUTE ON FUNCTIONS TO service_role;

-- Deliberately NOT changing table ownership.
--
-- A migration cannot ALTER TABLE ... OWNER TO service_role on a Supabase database, because
-- `public` is not owned by the role the migrations run as — the statement fails with
-- "permission denied for schema public". The attempt is recorded because the instinct to
-- add it is reasonable and the reason it is wrong is not obvious: ownership is not needed for
-- any grant above to take effect, the tables are already writable by `service_role`, and
-- moving ownership of one arbitrarily chosen table would be inconsistent with the other 27.
-- If a future migration genuinely cannot alter a table, solve that where it arises rather
-- than pre-emptively transferring ownership of one table here.
