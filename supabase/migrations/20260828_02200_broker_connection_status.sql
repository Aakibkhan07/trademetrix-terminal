-- =============================================================================
-- Trade Metrix — broker_connection_status view + vault unique index
-- 2026-08-28
--
-- Adds the ciphertext-free status VIEW the Broker Connect module reads from
-- (migration 002 in the module), AND the (user_id, broker) unique index its
-- OAuth upsert requires (on_conflict="user_id,broker").
--
-- Idempotent — safe to re-run.
-- NOTE: if broker_credentials already has duplicate (user_id, broker) rows,
-- the unique index below will fail — dedupe first (keep the latest is_active).
-- =============================================================================

-- 1) Status view over the existing broker_credentials vault -------------------
create or replace view public.broker_connection_status
with (security_invoker = true) as
  select
    id,
    user_id,
    broker,
    (additional_params ->> 'broker_user_id') as broker_user_id,
    token_expires_at,
    -- normalise the engine's token_status vocab (valid/active/connected) to the
    -- portal's single "connected" state; everything else passes through.
    case
      when token_status in ('connected', 'active', 'valid') then 'connected'
      else token_status
    end as status,
    last_token_refresh_at as last_connected_at,
    (
      is_active
      and token_status in ('connected', 'active', 'valid')
      and token_expires_at > now()
    ) as is_live
  from public.broker_credentials;

-- 2) Unique (user_id, broker) so the connect/refresh upsert has a conflict target
create unique index if not exists uq_broker_credentials_user_broker
  on public.broker_credentials (user_id, broker);

-- 3) RLS: a user may only read their own broker_credentials (the view uses
--    security_invoker=true, so this policy governs anon-key access). Writes
--    continue to happen only from the backend via the service-role key.
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'broker_credentials'
      and policyname = 'own_creds_select'
  ) then
    create policy own_creds_select
      on public.broker_credentials
      for select
      using (auth.uid() = user_id);
  end if;
end $$;
