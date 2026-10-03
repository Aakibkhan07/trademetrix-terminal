-- strategy_runs.strategy_id must accept a builder strategy id, which is not a uuid.
--
-- Why
-- ---
-- Three tables in this schema use two different id vocabularies, and `strategy_runs` was wired to
-- only one of them:
--
--     strategies.id           uuid    (legacy catalogue)
--     builder_strategies.id   text    (Strategy Builder — `uuid4().hex[:12]`, 12 hex chars)
--     strategy_runs.strategy_id uuid  NOT NULL, FK → strategies(id) ON DELETE CASCADE
--
-- `builder/models.py` mints strategy ids with `uuid.uuid4().hex[:12]`, which **cannot** be parsed as
-- a uuid at all:
--
--     >>> uuid.UUID('3838c1dcdc97')
--     ValueError: badly formed hexadecimal UUID string
--
-- So a builder strategy can never satisfy the column's type, let alone the foreign key. Every run
-- row for a Builder strategy fails to insert, and `POST /engine/start` answers
-- `INTERNAL_ERROR` for an id that is perfectly valid.
--
-- ## Why this was quiet rather than loud
--
-- `strategy_runtime/manager.py` already worked around it, and the workaround is worse than the
-- failure:
--
--     try:
--         sid_str = str(uuid.UUID(record.spec.strategy_id))
--     except (ValueError, TypeError):
--         sid_str = str(uuid.uuid4())
--
-- When the id is a builder hex string the coercion fails, so a **random uuid is substituted** and the
-- run row is written against a strategy that never existed. The later status update filters on that
-- same fabricated id, so it finds the row it just wrote and behaves as though all is well. The run is
-- unattributable — there is no way to tell afterwards which strategy produced it — and nothing is
-- logged, because the `except` that swallows the insert failure logs at WARNING and continues.
--
-- A fabricated identifier that satisfies its own foreign key is the most expensive kind of wrong
-- record: it passes every check and cannot be audited. This column has to hold both vocabularies, or
-- the substitution has to become a visible error.
--
-- ## The change
--
-- `strategy_id` becomes TEXT. A uuid is valid text, so existing legacy rows are preserved exactly —
-- `USING strategy_id::text` is lossless in that direction. No reader needs a cast: nothing in the
-- codebase compares this column to `strategies.id`, and there is no PostgREST embed joining the two
-- (`grep` for `strategies!inner` / `strategy_runs!` returns nothing). Every comparison against the
-- column is `.eq("strategy_id", …)` on `strategy_runs` itself, which is text-to-text either way.
--
-- `user_id` is deliberately left as uuid: it is still only ever written with an authenticated
-- profile id, and it has a working foreign key that is worth keeping.
--
-- ## The foreign key is dropped, and that is a real behaviour change
--
-- The FK cannot survive a uuid→text change (Postgres requires matching types), and it could not have
-- been correct anyway: a run can belong to a `builder_strategies` row, which `strategies` knows
-- nothing about.
--
-- The cost is that `ON DELETE CASCADE` goes with it. `strategy_catalog_service.delete_strategy`
-- deletes from `strategies`, and until this migration that also removed the strategy's run rows.
-- After it, runs survive their strategy. **That is the intended direction** — a run is a record of
-- trading that actually happened, and a catalogue tidy-up should not erase it — but it is a change,
-- not a no-op, and it is stated here rather than left to be discovered. If cascading deletes are
-- wanted back, the cleaner shape is an explicit delete in `delete_strategy`, scoped to the strategy
-- and the user, rather than a foreign key that cannot represent the relationship.
--
-- Idempotent: the constraint drop and the column check are both guarded.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.strategy_runs'::regclass
          AND conname = 'strategy_runs_strategy_id_fkey'
    ) THEN
        ALTER TABLE public.strategy_runs
            DROP CONSTRAINT strategy_runs_strategy_id_fkey;
    END IF;
END $$;

-- Only rewrite the column if it is still a uuid type, so a re-run is a no-op rather than a cast of
-- text to text.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'strategy_runs'
          AND column_name = 'strategy_id'
          AND data_type = 'uuid'
    ) THEN
        ALTER TABLE public.strategy_runs
            ALTER COLUMN strategy_id TYPE TEXT USING strategy_id::text;
    END IF;
END $$;

-- Not nullable, still: a run must say which strategy it was for. The old NOT NULL is preserved by the
-- type change, and this asserts it rather than assuming it.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'strategy_runs'
          AND column_name = 'strategy_id'
          AND is_nullable = 'NO'
    ) THEN
        ALTER TABLE public.strategy_runs
            ALTER COLUMN strategy_id SET NOT NULL;
    END IF;
END $$;

-- The column is now the natural lookup key for "runs of this strategy", and the type change drops any
-- index that was implicitly tied to the old type.
CREATE INDEX IF NOT EXISTS idx_strategy_runs_strategy_id ON public.strategy_runs (strategy_id);

COMMENT ON COLUMN public.strategy_runs.strategy_id IS
    'Either a legacy strategies.id (uuid, rendered as text) or a builder_strategies.id (12 hex chars). '
    'Not a uuid column: builder ids cannot parse as one. No foreign key, because a run may belong to '
    'either table and a uuid-keyed FK cannot represent that. Runs are retained when a strategy is '
    'deleted — they are trading history, not catalogue rows.';
COMMENT ON TABLE public.strategy_runs IS
    'One row per strategy run. strategy_id is deliberately TEXT and unconstrained: it spans two id '
    'vocabularies (legacy uuid, builder hex) and a uuid column plus FK silently refused every builder '
    'run.';