-- Beta Operations: dev/prod schema parity for user_strategies (2026-08-04)
-- Prod user_strategies evolved to store legacy strategy fields under a `config`
-- jsonb column and strategy legs as a jsonb `legs` column (denormalized). The
-- canonical migrations (00500) kept a purely relational shape, so local/dev
-- databases drifted from prod and the legacy /user-strategies service failed
-- on prod only. This migration makes the relational schema additive-compatible
-- with prod: idempotent no-op where the columns already exist (prod), and
-- adds them where they are missing (fresh/dev/staging databases).
--
-- After applying on PostgREST hosts:
--   NOTIFY pgrst, 'reload schema';

ALTER TABLE user_strategies ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE user_strategies ADD COLUMN IF NOT EXISTS legs   JSONB NOT NULL DEFAULT '[]'::jsonb;