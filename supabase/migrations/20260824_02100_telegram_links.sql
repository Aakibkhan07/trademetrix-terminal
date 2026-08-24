-- Per-user Telegram alert links.
-- One Trade Metrix bot (TELEGRAM_BOT_TOKEN); each user links their own chat via
-- a /start deep-link code. chat_id unique so one Telegram account can't be
-- double-linked, user_id PK so one account has at most one chat.

CREATE TABLE IF NOT EXISTS public.telegram_links (
    user_id UUID PRIMARY KEY REFERENCES public.profiles(id) ON DELETE CASCADE,
    chat_id TEXT NOT NULL UNIQUE,
    username TEXT DEFAULT '',
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_telegram_links_chat ON public.telegram_links(chat_id);
