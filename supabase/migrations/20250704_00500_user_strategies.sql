-- User-Created Visual Strategy Builder Tables
-- Each user can create multi-leg options strategies (1–6 legs).
-- RLS: owner-only CRUD, admins can read all.

-- ── Enum types ──
DO $$ BEGIN
  CREATE TYPE user_strategy_status AS ENUM ('draft', 'active', 'paused');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE strategy_type AS ENUM ('intraday', 'positional');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE underlying_from AS ENUM ('cash', 'futures');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE leg_segment AS ENUM ('options', 'futures');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE leg_position AS ENUM ('buy', 'sell');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE leg_option_type AS ENUM ('CE', 'PE');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE leg_expiry AS ENUM ('weekly', 'next_weekly', 'monthly');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE strike_criteria AS ENUM ('atm_offset', 'premium_closest', 'premium_range', 'delta');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE sl_target_type AS ENUM ('percent', 'points', 'premium');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── user_strategies ──
CREATE TABLE IF NOT EXISTS user_strategies (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  status          user_strategy_status NOT NULL DEFAULT 'draft',
  strategy_type   strategy_type NOT NULL DEFAULT 'intraday',
  index_symbol    TEXT NOT NULL,
  underlying_from underlying_from NOT NULL DEFAULT 'cash',
  entry_time      TIME NOT NULL,
  exit_time       TIME NOT NULL,
  days_of_week    INTEGER[] NOT NULL DEFAULT '{1,2,3,4,5}',
  overall_sl_type       sl_target_type,
  overall_sl_value      REAL,
  overall_target_type   sl_target_type,
  overall_target_value  REAL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── user_strategy_legs ──
CREATE TABLE IF NOT EXISTS user_strategy_legs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  strategy_id         UUID NOT NULL REFERENCES user_strategies(id) ON DELETE CASCADE,
  leg_order           SMALLINT NOT NULL CHECK (leg_order BETWEEN 1 AND 6),
  segment             leg_segment NOT NULL,
  position            leg_position NOT NULL,
  option_type         leg_option_type,
  lots                INTEGER NOT NULL CHECK (lots >= 1),
  expiry              leg_expiry NOT NULL,
  strike_criteria     strike_criteria NOT NULL,
  strike_value        REAL NOT NULL,
  leg_sl_type         sl_target_type,
  leg_sl_value        REAL,
  leg_target_type     sl_target_type,
  leg_target_value    REAL,
  trailing_sl_type    sl_target_type,
  trailing_sl_value   REAL,
  trailing_activation REAL,
  UNIQUE (strategy_id, leg_order)
);

-- ── Indexes ──
CREATE INDEX IF NOT EXISTS idx_user_strategies_user_id ON user_strategies(user_id);
CREATE INDEX IF NOT EXISTS idx_user_strategies_status  ON user_strategies(status);
CREATE INDEX IF NOT EXISTS idx_user_strategy_legs_strategy_id ON user_strategy_legs(strategy_id);

-- ── RLS ──
ALTER TABLE user_strategies ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_strategy_legs ENABLE ROW LEVEL SECURITY;

-- Owner full access
CREATE POLICY user_strategies_owner_all ON user_strategies
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY user_strategy_legs_owner_all ON user_strategy_legs
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM user_strategies
      WHERE user_strategies.id = user_strategy_legs.strategy_id
        AND user_strategies.user_id = auth.uid()
    )
  );

-- Admin read-only
CREATE POLICY user_strategies_admin_read ON user_strategies
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE profiles.id = auth.uid()
        AND (profiles.is_admin = TRUE OR profiles.role = 'super_admin' OR profiles.role = 'admin')
    )
  );

CREATE POLICY user_strategy_legs_admin_read ON user_strategy_legs
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE profiles.id = auth.uid()
        AND (profiles.is_admin = TRUE OR profiles.role = 'super_admin' OR profiles.role = 'admin')
    )
  );

-- ── Auto-update updated_at ──
CREATE OR REPLACE FUNCTION update_user_strategies_updated_at()
RETURNS TRIGGER AS $$ BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_user_strategies_updated_at ON user_strategies;
CREATE TRIGGER trg_user_strategies_updated_at
  BEFORE UPDATE ON user_strategies
  FOR EACH ROW EXECUTE FUNCTION update_user_strategies_updated_at();
