# Live Certification — fyers

- Result: `LIVE_CERTIFIED`
- Elapsed: 18.14s

| Check | Status | Detail | Latency |
|-------|--------|--------|---------|
| login | PASS | access_token='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiZDoxIiwiZDoyIiwie… | 0.2ms |
| token_refresh | SKIP | [unsupported_feature] fyers: Broker fyers does not support: refresh_token | 0.1ms |
| quotes | PASS | [Quote(symbol='NSE:NIFTY', exchange=<Exchange.NSE: 'NSE'>, last_price=0.0, open=… | 242.5ms |
| history | PASS | [] | 7743.0ms |
| option_chain | SKIP | [unsupported_feature] fyers: Broker fyers does not support: get_option_chain | 0.1ms |
| websocket | PASS | subscription connected (no tick — market closed?) | 10095.6ms |
| positions | PASS | [Position(symbol='NIFTY2680424300PE', exchange=<Exchange.NSE: 'NSE'>, quantity=0… | 19.4ms |
| holdings | PASS | [] | 19.7ms |
| funds | PASS | total_margin=2993.14 used_margin=0.0 available_margin=2282.04 payin=0.0 payout=0… | 18.6ms |
| disconnect | PASS |  | 0.1ms |
| reconnect | PASS | access_token='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiZDoxIiwiZDoyIiwie… | 0.1ms |
| token_expiry | SKIP | [unsupported_feature] fyers: Broker fyers does not support: refresh_token | 0.1ms |
| circuit_recovery | PASS | access_token='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiZDoxIiwiZDoyIiwie… | 0.1ms |
| place_order | SKIP | skipped (opt-in: allow_orders=True) | 0.0ms |
| modify_order | SKIP | skipped (opt-in: allow_orders=True) | 0.0ms |
| cancel_order | SKIP | skipped (opt-in: allow_orders=True) | 0.0ms |
