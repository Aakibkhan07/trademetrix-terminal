-- 2026-08-03: onboarding completion flag for profiles
-- The web onboarding flow persists onboarding_completed via PATCH /api/v1/auth/profile.
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN NOT NULL DEFAULT false;
