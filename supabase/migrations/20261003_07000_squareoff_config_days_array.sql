-- ─────────────────────────────────────────────────────────────────────────────
-- squareoff_config.days is an integer array, not text — and the default is {0,1,2,3,4}
--
-- 20261003_02000 declared:
--
--     days  TEXT NOT NULL DEFAULT '1,2,3,4,5'
--
-- and both halves of that are wrong, in a way that only shows up at runtime.
--
-- The type: `squareoff_service.set_config` is typed `days: list[int]` and writes the list
-- straight through —
--
--     await async_supabase(lambda: supabase.table(SQUAREOFF_TABLE).upsert(row, on_conflict="user_id"))
--
-- Measured on a text column, that write **does not fail**. It succeeds, and PostgREST coerces the
-- list to the string `'[0,1,2,3,4]'`. That is worse than a rejection, because nothing reports it.
-- The scheduler then reads the column back and evaluates
--
--     if current_dow not in days:        # squareoff_service.py:183, current_dow is an int
--
-- which raises `TypeError: 'in <string>' requires string as left operand, not int`. That sits inside
-- the `while True` loop's own `try`, whose handler logs `Squareoff loop error: %s` and moves on to
-- `asyncio.sleep(30)` — abandoning the `for row in configs` loop it was in. So the first enabled row
-- holding a coerced string stops **every** user's square-off for that minute, and it repeats every
-- 30 seconds indefinitely, with a single log line as the only evidence.
--
-- (It is worth stating what this is *not*, because both were assumed before being measured: it is
-- not substring matching, so no quiet wrong-day, and it is not a rejected write. It is a caught
-- exception that silently disables the feature.)
--
-- Production has never been affected: measured there, the column is `integer[]` (`udt = _int4`) and
-- the table holds 0 rows. Every environment built from this repository was.
--
-- No reader treats the value as a string: `SquareoffConfig.days` is `list[int] | None`,
-- `admin_service.get_scheduled_tasks_summary` defaults it to `[0, 1, 2, 3, 4]`, and the route
-- accepts `days: list[int] = [0, 1, 2, 3, 4]`. The only consumer is the `in` test above, and a list
-- is what it needs.
--
-- The default: `{0,1,2,3,4}`, not `'1,2,3,4,5'`. The value is a weekday index on the same
-- 0-based convention the code uses everywhere else (production's default and the admin
-- fallback both read `[0, 1, 2, 3, 4]`). A 1-based default does not merely differ, it fires
-- the square-off a day late: index 5 is Sunday, and the intent is Saturday.
--
-- The `02000` comment claimed this table was mirrored from
-- `alembic/versions/003_create_strategy_and_user_tables.py`. That file does not declare
-- `squareoff_config` at all — it stops at `user_strategies` — so the claim was wrong and
-- there was nothing to mirror from. Production is the only authority that measured this
-- column, and it says `integer[]`.
--
-- Idempotent, and a no-op on production, which already has `integer[]`.
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
DECLARE
    current_type TEXT;
BEGIN
    SELECT data_type INTO current_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name   = 'squareoff_config'
      AND column_name  = 'days';

    IF current_type IS NULL THEN
        RAISE NOTICE 'squareoff_config.days does not exist; nothing to correct';
        RETURN;
    END IF;

    IF current_type = 'ARRAY' THEN
        RAISE NOTICE 'squareoff_config.days is already an array; left alone';
        RETURN;
    END IF;

    ALTER TABLE public.squareoff_config
        ALTER COLUMN days DROP DEFAULT,
        ALTER COLUMN days TYPE INTEGER[] USING (
            CASE
                WHEN days IS NULL THEN NULL
                ELSE string_to_array(
                    regexp_replace(days, '[{}]', '', 'g'),
                    ','
                )::INTEGER[]
            END
        ),
        ALTER COLUMN days SET DEFAULT '{0,1,2,3,4}'::INTEGER[];

    RAISE NOTICE 'squareoff_config.days converted from % to integer[] with default {0,1,2,3,4}',
        current_type;
END
$$;