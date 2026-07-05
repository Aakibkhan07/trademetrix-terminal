-- Billing: Subscriptions + Webhook Idempotency Tables
-- Managed by Razorpay webhook handler + capability resolver.

-- ── subscription_status enum ──
DO $$ BEGIN
  CREATE TYPE subscription_status AS ENUM (
    'created', 'authenticated', 'active', 'halted',
    'cancelled', 'completed', 'expired'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── subscription_tier enum ──
DO $$ BEGIN
  CREATE TYPE subscription_tier AS ENUM (
    'monthly', 'quarterly', 'halfyearly', 'yearly'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── subscriptions ──
CREATE TABLE IF NOT EXISTS subscriptions (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                 UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  razorpay_subscription_id VARCHAR(64) NOT NULL,
  razorpay_plan_id        VARCHAR(64) NOT NULL,
  tier                    subscription_tier NOT NULL,
  status                  subscription_status NOT NULL DEFAULT 'created',
  current_period_start    TIMESTAMPTZ,
  current_period_end      TIMESTAMPTZ,
  trial_end               TIMESTAMPTZ,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_subscriptions_razorpay_id
  ON subscriptions(razorpay_subscription_id);

CREATE INDEX IF NOT EXISTS ix_subscriptions_user_status
  ON subscriptions(user_id, status);

-- ── processed_webhooks (idempotency) ──
CREATE TABLE IF NOT EXISTS processed_webhooks (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id      VARCHAR(128) NOT NULL UNIQUE,
  event_type    VARCHAR(64) NOT NULL,
  processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_processed_webhooks_event_id
  ON processed_webhooks(event_id);

-- ── RLS ──
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE processed_webhooks ENABLE ROW LEVEL SECURITY;

-- Owner + service-role access on subscriptions
CREATE POLICY subscriptions_user_all ON subscriptions
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY subscriptions_admin_all ON subscriptions
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE profiles.id = auth.uid()
        AND (profiles.role IN ('super_admin', 'admin') OR profiles.is_admin = TRUE)
    )
  );

-- Service-role only on processed_webhooks (webhook handler uses service key)
CREATE POLICY processed_webhooks_service_all ON processed_webhooks
  FOR ALL USING (auth.role() = 'service_role');

-- ── Auto-update updated_at ──
CREATE OR REPLACE FUNCTION update_subscriptions_updated_at()
RETURNS TRIGGER AS $$ BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_subscriptions_updated_at ON subscriptions;
CREATE TRIGGER trg_subscriptions_updated_at
  BEFORE UPDATE ON subscriptions
  FOR EACH ROW EXECUTE FUNCTION update_subscriptions_updated_at();
