-- Execution Audit Log enrichment — add columns needed by execution/audit.py
-- 2025-07-10
-- Idempotent; safe to run against production.

ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS broker_order_id TEXT DEFAULT '';
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS execution_request_id TEXT DEFAULT '';
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS price DOUBLE PRECISION DEFAULT 0.0;
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS latency_ms DOUBLE PRECISION DEFAULT 0.0;
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS status TEXT DEFAULT '';
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS message TEXT DEFAULT '';
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS payload_hash TEXT DEFAULT '';
ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS result TEXT DEFAULT '';
