-- Beta Operations Mode: analytics + feedback persistence (2026-08-01)
-- Replaces the in-memory AnalyticsService/feedback store. Idempotent.

create table if not exists analytics_events (
  id bigserial primary key,
  event text not null,
  properties jsonb not null default '{}'::jsonb,
  session_id text not null default '',
  user_id uuid,
  created_at timestamptz not null default now()
);

create index if not exists idx_analytics_events_event on analytics_events (event, created_at desc);
create index if not exists idx_analytics_events_session on analytics_events (session_id, created_at);
create index if not exists idx_analytics_events_user on analytics_events (user_id, created_at desc);
create index if not exists idx_analytics_events_created on analytics_events (created_at desc);

create table if not exists feedback_items (
  id bigserial primary key,
  user_id uuid,
  user_email text not null default '',
  full_name text not null default '',
  category text not null default 'bug',
  title text not null default '',
  description text not null default '',
  metadata jsonb not null default '{}'::jsonb,
  status text not null default 'new',
  notes text not null default '',
  created_at timestamptz not null default now()
);

create index if not exists idx_feedback_items_status on feedback_items (status, created_at desc);
create index if not exists idx_feedback_items_category on feedback_items (category, created_at desc);
