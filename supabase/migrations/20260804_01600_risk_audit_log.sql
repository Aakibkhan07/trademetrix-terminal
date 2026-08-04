-- 20260804_01600_risk_audit_log.sql
-- Kill-switch audit trail (EMERGENCY_STOP / EMERGENCY_STOP_RELEASED events).
-- Idempotent; safe to apply repeatedly via psql.
CREATE TABLE IF NOT EXISTS public.risk_audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    event TEXT NOT NULL,
    reason TEXT DEFAULT '',
    triggered_by TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_audit_log_user_event
    ON public.risk_audit_log (user_id, event, created_at DESC);
