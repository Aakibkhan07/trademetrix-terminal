-- Allow NULL user_id on audit_log.
-- Unauthenticated security-relevant events (e.g. login throttling / lockout)
-- have no actor; the current NOT NULL + FK column silently drops those audit
-- rows at insert time (PostgREST rejects "" as invalid uuid).
-- FK remains; NULL simply bypasses the reference (system/anonymous events).
ALTER TABLE public.audit_log ALTER COLUMN user_id DROP NOT NULL;