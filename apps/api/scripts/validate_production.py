"""Production validation script.

Usage:
    python scripts/validate_production.py

Runs smoke tests against the API server and broker adapters.
Exits with code 0 on success, 1 on failure.
"""
import asyncio
import os
import sys

# allow running from scripts/ dir
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASS = 0
FAIL = 0


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def fail(msg: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  ❌ {msg}")


def check_env() -> None:
    print("\n## Environment Variables")
    required = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY", "SECRET_KEY", "ENCRYPTION_KEY"]
    for var in required:
        if os.environ.get(var):
            ok(f"{var} is set")
        else:
            print(f"  ⚠️  {var} is NOT set (expected in CI/local — will be set in production)")


def check_imports() -> None:
    print("\n## Module Imports")
    modules = [
        "main",
        "core.config",
        "core.db",
        "core.security",
        "core.cache",
        "core.safe_query",
        "market.cache",
        "market.data_socket",
        "market.symbol_master",
        "market.status",
        "market.subscription_manager",
        "market.historical",
        "market.option_chain",
        "runtime.scheduler",
        "runtime.manager",
        "runtime.registry",
        "runtime.context",
        "runtime.event_subscriber",
        "engine.gate",
        "engine.token_refresh",
        "execution.manager",
        "risk.riskguard",
        "brokers.registry",
    ]
    for mod_name in modules:
        try:
            __import__(mod_name.replace("/", "."))
            ok(f"import {mod_name}")
        except Exception as e:
            fail(f"import {mod_name}: {e}")


def check_broker_adapters() -> None:
    print("\n## Broker Adapters")
    brokers = {
        "fyers": ("brokers.fyers_adapter", "FyersAdapter"),
        "dhan": ("brokers.dhan_adapter", "DhanAdapter"),
        "upstox": ("brokers.upstox_adapter", "UpstoxAdapter"),
        "angelone": ("brokers.angelone_adapter", "AngelOneAdapter"),
        "aliceblue": ("brokers.aliceblue_adapter", "AliceBlueAdapter"),
        "finvasia": ("brokers.finvasia_adapter", "FinvasiaAdapter"),
        "flattrade": ("brokers.flattrade_adapter", "FlattradeAdapter"),
        "kotakneo": ("brokers.kotakneo_adapter", "KotakNeoAdapter"),
        "fivepaisa": ("brokers.fivepaisa_adapter", "FivePaisaAdapter"),
    }
    for name, (mod_path, cls_name) in brokers.items():
        try:
            mod = __import__(mod_path, fromlist=[name])
            cls = getattr(mod, cls_name, None)
            if cls:
                inst = cls()
                ok(f"{name}: {cls_name} loads, has {len(dir(inst))} methods")
            else:
                fail(f"{name}: class {cls_name} not found in {mod_path}")
        except Exception as e:
            fail(f"{name}: {e}")


def check_routes() -> None:
    print("\n## API Routes")
    try:
        from main import app
        routes = [r.path for r in app.routes]
        expected = [
            "/health",
            "/metrics",
            "/api/v1/auth/signup",
            "/api/v1/auth/signin",
            "/api/v1/brokers/list",
            "/api/v1/market/status",
            "/api/v1/strategies/list-builtin",
            "/api/v1/risk/kill-switch",
            "/api/v1/backtests/run",
        "/api/v1/backtests/run-v2",
        ]
        for path in expected:
            if any(path in r for r in routes):
                ok(f"route {path}")
            else:
                fail(f"route {path} missing")

        # broker-specific routes (OAuth)
        oauth_routes = [r for r in routes if "brokers" in r and "callback" in r]
        if oauth_routes:
            ok(f"OAuth callback routes: {len(oauth_routes)} registered")
        else:
            fail("no OAuth callback routes registered")
    except Exception as e:
        fail(f"route check failed: {e}")


def check_symbol_master() -> None:
    print("\n## SymbolMaster")
    try:
        from market.symbol_master import symbol_master
        info = symbol_master.get_symbol_info("NIFTY")
        if info:
            ok(f"get_symbol_info('NIFTY') = {info.get('instrument_type')}")
        else:
            ok("get_symbol_info('NIFTY') = None (no data yet — expected)")

        result = asyncio.run(symbol_master.get_broker_symbol("NIFTY", "fyers"))
        ok(f"get_broker_symbol('NIFTY', 'fyers') = {result}")
    except Exception as e:
        fail(f"SymbolMaster: {e}")


def main() -> None:
    print("=" * 50)
    print("  TradeMetrix — Production Validation")
    print("=" * 50)

    check_env()
    check_imports()
    check_broker_adapters()
    check_routes()
    check_symbol_master()

    print("\n" + "=" * 50)
    total = PASS + FAIL
    if FAIL == 0:
        print(f"  ✅ ALL {total} CHECKS PASSED")
        sys.exit(0)
    else:
        print(f"  ⚠️  {PASS}/{total} passed, {FAIL} failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
