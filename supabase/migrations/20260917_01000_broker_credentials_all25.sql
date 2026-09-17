-- broker_credentials.broker CHECK: expand to all 25 registered brokers.
-- Idempotent: drop by auto-generated name if present, then re-add the superset.
-- Covers every broker with an adapter registered in brokers/__init__.py.

ALTER TABLE public.broker_credentials
    DROP CONSTRAINT IF EXISTS broker_credentials_broker_check;

ALTER TABLE public.broker_credentials
    ADD CONSTRAINT broker_credentials_broker_check
    CHECK (broker IN (
        'fyers','groww','dhan','zerodha','angelone','upstox','fivepaisa',
        'aliceblue','finvasia','flattrade','kotakneo','lemonn',
        'binance','bybit','okx','oanda','interactive_brokers','alpaca',
        'icici','hdfc','iifl','motilal','geojit','reliance','axis'
    ));
