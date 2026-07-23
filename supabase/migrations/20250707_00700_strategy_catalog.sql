CREATE TABLE IF NOT EXISTS strategy_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    required_tier TEXT NOT NULL DEFAULT 'free',
    category TEXT NOT NULL DEFAULT 'trend',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE strategy_catalog ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admins can manage strategy_catalog"
    ON strategy_catalog
    FOR ALL
    USING (
        auth.role() = 'service_role'
        OR EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = auth.uid()
            AND profiles.is_admin = TRUE
        )
    );

CREATE POLICY "Anyone can read strategy_catalog"
    ON strategy_catalog
    FOR SELECT
    USING (TRUE);
