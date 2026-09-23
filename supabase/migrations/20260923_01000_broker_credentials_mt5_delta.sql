-- broker_credentials.broker CHECK: add 'mt5' and 'delta' to the allowed list.
-- Idempotent: drop by auto-generated name if present, then re-add the superset.
-- Covers every broker with an adapter registered in brokers/__init__.py.

ALTER TABLE public.broker_credentials
    DROP CONSTRAINT IF EXISTS broker_credentials_broker_check;

ALTER TABLE public.broker_credentials
    ADD CONSTRAINT broker_credentials_broker_check
    CHECK (broker IN (
        'fyers','groww','dhan','zerodha','angelone','upstox','fivepaisa',
        'aliceblue','finvasia','flattrade','kotakneo','lemonn',
        'icici','hdfc','iifl','motilal','geojit','reliance','axis',
        'binance','bybit','okx','oanda','interactive_brokers','alpaca',
        'mt5','delta'
    ));
