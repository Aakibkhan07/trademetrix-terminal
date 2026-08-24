-- broker_credentials.broker CHECK: add 'lemonn' (+ 'groww', which was registered
-- in code but never added to this constraint — saving Groww credentials on any
-- environment with the original init schema would fail with 23514).
-- Idempotent: drop by auto-generated name if present, then re-add the superset.

ALTER TABLE public.broker_credentials
    DROP CONSTRAINT IF EXISTS broker_credentials_broker_check;

ALTER TABLE public.broker_credentials
    ADD CONSTRAINT broker_credentials_broker_check
    CHECK (broker IN (
        'fyers','dhan','zerodha','angelone','upstox','fivepaisa',
        'aliceblue','finvasia','flattrade','kotakneo','groww','lemonn'
    ));
