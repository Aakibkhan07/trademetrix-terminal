-- Phase 4 — Strategy Builder V2 persistence
-- Builder DSL strategies + version history were previously in-memory only
-- (lost on API restart). These tables mirror builder/manager.py state
-- write-through; route shapes unchanged.

CREATE TABLE IF NOT EXISTS builder_strategies (
    id TEXT PRIMARY KEY,
    version TEXT NOT NULL DEFAULT '1.0',
    name TEXT NOT NULL DEFAULT 'Untitled Strategy',
    description TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT 'user',
    status TEXT NOT NULL DEFAULT 'draft',
    tags JSONB NOT NULL DEFAULT '[]',
    settings JSONB NOT NULL DEFAULT '{}',
    nodes JSONB NOT NULL DEFAULT '[]',
    edges JSONB NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    parent_id TEXT NOT NULL DEFAULT '',
    version_number INT NOT NULL DEFAULT 1,
    deployment JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS builder_strategy_versions (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL REFERENCES builder_strategies(id) ON DELETE CASCADE,
    version INT NOT NULL,
    data JSONB NOT NULL,
    saved_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_builder_versions_strategy ON builder_strategy_versions(strategy_id);

-- Phase 4.3: strategy lifecycle execution logs (decisions/signals/orders/rejections/exits)
CREATE TABLE IF NOT EXISTS builder_strategy_logs (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL REFERENCES builder_strategies(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL DEFAULT '',
    ts TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'info',
    level TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL DEFAULT '',
    detail JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_builder_logs_strategy_ts ON builder_strategy_logs(strategy_id, ts);
