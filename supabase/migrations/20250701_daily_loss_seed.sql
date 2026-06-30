-- Daily loss cap seed: set tier defaults for rows with max_daily_loss = 0/null
-- Tier defaults: free=2000  starter=3000  pro=5000  enterprise=10000
-- Do NOT overwrite any existing non-zero custom value.
-- Preview before running:
--   BEGIN;  (or run SELECT first to review)
--   <UPDATE below>
--   ROLLBACK;  (or COMMIT if satisfied)

-- === PREVIEW: affected rows and their new values ===
SELECT
  p.email,
  p.subscription_tier,
  rs.max_daily_loss AS old_value,
  CASE p.subscription_tier
    WHEN 'free'       THEN 2000
    WHEN 'starter'    THEN 3000
    WHEN 'pro'        THEN 5000
    WHEN 'enterprise' THEN 10000
    ELSE 2000
  END AS new_value
FROM public.risk_settings rs
JOIN public.profiles p ON p.id = rs.user_id
WHERE rs.max_daily_loss IS NULL OR rs.max_daily_loss = 0
ORDER BY p.email;

-- === UPDATE: set tier default where currently 0/null ===
UPDATE public.risk_settings rs
SET max_daily_loss = CASE p.subscription_tier
    WHEN 'free'       THEN 2000
    WHEN 'starter'    THEN 3000
    WHEN 'pro'        THEN 5000
    WHEN 'enterprise' THEN 10000
    ELSE 2000
  END
FROM public.profiles p
WHERE p.id = rs.user_id
  AND (rs.max_daily_loss IS NULL OR rs.max_daily_loss = 0);
