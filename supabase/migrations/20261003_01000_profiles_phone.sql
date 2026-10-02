-- profiles.phone
--
-- Why
-- ---
-- `core/models.py::UserProfile` declares `phone`, `/auth/signup` accepts one, and the signup
-- form collects it — but no migration in this directory ever adds the column. Production has
-- it, so it was added there by hand and never captured, which is the same failure mode as the
-- missing `service_role` grants: the repository cannot reproduce a working environment, and the
-- gap is invisible until a write is attempted.
--
-- The symptom is misleading rather than loud. A write to this column answers PostgREST
-- `PGRST204` (or `42703` for a raw select), `core.safe_query` wraps every query in
-- `async_safe_single` / `async_safe_execute`, and those catch all exceptions and return `None`.
-- So a profile write "succeeds" from the caller's point of view and the value is simply not
-- there. Found by `scripts/audit_model_schema.py`, which compares every model against the live
-- schema — it reported this as the only genuine gap across all 28 tables.
--
-- Nullable, matching the model (`phone: str | None = None`). A signup that does not collect a
-- number must keep working, and it already does on production, so adding the column must not
-- change that.
--
-- Whether production already has this column was not verified from here — the reasoning is
-- that the model, the signup route and the signup form all reference it, and the column is
-- absent locally. `IF NOT EXISTS` makes the statement safe either way: a re-run against a
-- database that has it is a no-op, so applying this to production before a deploy is not a
-- risk.
--
-- Idempotent.

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS phone TEXT;

-- Kept in step with the model's `str | None`, so a row is either absent or a real value and
-- never an empty string that reads as "provided".
ALTER TABLE public.profiles
    ALTER COLUMN phone SET DEFAULT NULL;
