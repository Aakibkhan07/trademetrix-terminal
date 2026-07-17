CREATE TABLE public.admin_ip_whitelist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ip_address TEXT NOT NULL,
    label TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX idx_admin_ip_whitelist_ip ON public.admin_ip_whitelist(ip_address);

INSERT INTO public.admin_ip_whitelist (ip_address, label) VALUES ('*', 'Allow all (default)') ON CONFLICT (ip_address) DO NOTHING;
