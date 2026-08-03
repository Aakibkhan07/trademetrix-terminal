-- Runtime Persistence + Recovery (Execution Engine add-on)
-- Durable checkpoints of the minimum required paper-trading runtime state:
--   1) kind='engine'    — open positions + FIFO lots + P&L accounts per user
--   2) kind='strategy'  — running graph strategies (params needed to re-start)
-- Written after every portfolio rebuild (engine) and on strategy start/stop
-- (strategy); restored on API startup by execution_engine.persistence
-- recover_runtime_state(). Upsert semantics make persistence idempotent.

CREATE TABLE IF NOT EXISTS execution_checkpoints (
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, kind, key)
);

CREATE INDEX IF NOT EXISTS idx_execution_checkpoints_kind ON execution_checkpoints (kind);
