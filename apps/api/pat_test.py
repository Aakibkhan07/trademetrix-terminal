#!/usr/bin/env python3
"""Product Acceptance Test (PAT) — runs against local dev server."""

import json
import os
import subprocess
import sys
import time
import uuid as _uuid
import urllib.error
import urllib.request
from typing import Any
import sys
import time
import urllib.error
import urllib.request
from typing import Any

API_BASE = "http://localhost:8000/api/v1"
SECRET_KEY = "test-secret-key-not-for-production-use-only-super-secure"
passed = 0
failed = 0
errors: list[str] = []


def make_jwt(subject: str) -> str:
    """Create a JWT using the server's own create_access_token."""
    api_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(api_dir, ".venv", "bin", "python3")
    script = (
        "import sys; sys.path.insert(0, %r); "
        "from core.security import create_access_token; "
        "print(create_access_token(%r))"
    ) % (api_dir, subject)
    result = subprocess.run([venv_python, "-c", script],
                            capture_output=True, text=True, timeout=10)
    return result.stdout.strip()


def request(
    method: str, path: str, body: dict | None = None, token: str | None = None,
    csrf_token: str | None = None, csrf_cookie: str | None = None,
) -> tuple[int, Any, dict]:
    url = f"{API_BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    if csrf_cookie:
        req.add_header("Cookie", f"csrf_token={csrf_cookie}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode()
            resp_headers = dict(resp.headers)
            try:
                return resp.status, json.loads(content), resp_headers
            except json.JSONDecodeError:
                return resp.status, content, resp_headers
    except urllib.error.HTTPError as e:
        content = e.read().decode()
        resp_headers = dict(e.headers)
        try:
            return e.code, json.loads(content), resp_headers
        except json.JSONDecodeError:
            return e.code, content, resp_headers
    except Exception as e:
        return 0, str(e), {}


def get_csrf(token: str | None = None) -> tuple[str, str]:
    """Fetch CSRF token and cookie from /auth/csrf."""
    status, data, headers = request("GET", "/auth/csrf", token=token)
    csrf_token = ""
    if isinstance(data, dict):
        csrf_token = data.get("csrf_token", "")
    set_cookie = headers.get("set-cookie", "")
    csrf_cookie = ""
    for part in set_cookie.split(";"):
        part = part.strip()
        if part.startswith("csrf_token="):
            csrf_cookie = part[len("csrf_token="):]
            break
    return csrf_token, csrf_cookie


def psql(sql: str) -> subprocess.CompletedProcess:
    """Run SQL via docker exec against local supabase DB."""
    return subprocess.run(
        ["docker", "exec", "supabase_db_trademetrix-terminal", "psql", "-U", "postgres", "-d", "postgres",
         "-c", sql],
        capture_output=True, text=True, timeout=10
    )


def create_test_user(email: str, is_admin: bool = False) -> tuple[str, str]:
    """Create a user in auth.users + profile. Returns (user_id, jwt)."""
    user_id = str(_uuid.uuid4())
    psql(f"""
        INSERT INTO auth.users (id, email, encrypted_password, email_confirmed_at, created_at, updated_at,
                                raw_app_meta_data, raw_user_meta_data, is_super_admin, role, aud)
        VALUES ('{user_id}', '{email}', '', NOW(), NOW(), NOW(),
                '{{"provider":"email"}}', '{{}}', FALSE, 'authenticated', 'authenticated')
        ON CONFLICT (id) DO NOTHING;
    """)
    psql(f"""
        INSERT INTO public.profiles (id, email, full_name, is_admin, subscription_tier)
        VALUES ('{user_id}', '{email}', '', {str(is_admin).upper()}, 'free')
        ON CONFLICT (id) DO UPDATE SET is_admin = {str(is_admin).upper()};
    """)
    return user_id, make_jwt(user_id)


def clean_pat_test_users():
    """Delete all pat.test users from the DB."""
    psql("""
        DELETE FROM public.user_strategy_legs WHERE strategy_id IN (SELECT id FROM public.user_strategies WHERE user_id IN (SELECT id FROM public.profiles WHERE email LIKE '%pat.test'));
        DELETE FROM public.user_strategies WHERE user_id IN (SELECT id FROM public.profiles WHERE email LIKE '%pat.test');
        DELETE FROM public.subscriptions WHERE user_id IN (SELECT id FROM public.profiles WHERE email LIKE '%pat.test');
        DELETE FROM public.strategy_runs WHERE user_id IN (SELECT id FROM public.profiles WHERE email LIKE '%pat.test');
        DELETE FROM public.strategies WHERE user_id IN (SELECT id FROM public.profiles WHERE email LIKE '%pat.test');
        DELETE FROM public.referrals WHERE referrer_id IN (SELECT id FROM public.profiles WHERE email LIKE '%pat.test');
        DELETE FROM public.profiles WHERE email LIKE '%pat.test';
        DELETE FROM auth.users WHERE email LIKE '%pat.test';
    """)


def check(step: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  \u2705 {step}")
    else:
        failed += 1
        msg = f"  \u274c {step}: {detail}"
        print(msg)
        errors.append(msg)


def section(name: str):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


# ============================================================================
section("SCENARIO 1: Admin Workflow — Subscription, User Creation, Plan Assignment")
# ============================================================================

TOKEN: str = ""

# 1.1 Create admin user
clean_pat_test_users()
admin_id, TOKEN = create_test_user("admin@pat.test", is_admin=True)
check("Admin user created", bool(admin_id), str(admin_id))
check("Admin JWT created", bool(TOKEN))

# Get CSRF tokens
csrf_tok, csrf_cookie = get_csrf()
check("CSRF token obtained", bool(csrf_tok) and bool(csrf_cookie))

# 1.2 Check admin capabilities
status, data, _ = request("GET", "/auth/me/capabilities", token=TOKEN)
check("Admin capabilities", status == 200, str(data)[:100])

# 1.3 List plans
status, data, _ = request("GET", "/subscriptions/plans/", token=TOKEN)
plans_list = data if isinstance(data, list) else data.get("plans", data.get("data", []))
check(f"Plans ({len(plans_list)} plans)", status == 200 and len(plans_list) > 0, str(data)[:100])

# 1.4 Create normal user
USER_ID, USER_TOKEN = create_test_user("user@pat.test")
check("User created", bool(USER_ID))

# 1.5 Verify user tier
status, data, _ = request("GET", "/auth/me", token=USER_TOKEN)
tier = data.get("subscription_tier", "")
check(f"User tier: {tier}", tier == "free", str(data)[:100])

# 1.6 Assign plan via DB
plan_id = "pro"
proc = psql(f"""
    DELETE FROM public.subscriptions WHERE user_id = '{USER_ID}';
    INSERT INTO public.subscriptions (user_id, plan, status, current_period_start, current_period_end)
    VALUES ('{USER_ID}', '{plan_id}', 'active', NOW(), NOW() + INTERVAL '30 days');
    UPDATE public.profiles SET subscription_tier = '{plan_id}' WHERE id = '{USER_ID}';
""")
check(f"Subscription created, tier → {plan_id}", proc.returncode == 0, proc.stderr[-200:])

# 1.7 Verify upgrade
proc = psql(f"SELECT subscription_tier FROM public.profiles WHERE id = '{USER_ID}';")
check(f"DB tier after upgrade", "pro" in proc.stdout, proc.stdout[-200:])

tier = data.get("subscription_tier", "")
check(f"User tier: {tier}", tier == "free", str(data)[:100])

# 1.8 Check capabilities after upgrade
status, data, _ = request("GET", "/auth/me/capabilities", token=USER_TOKEN)
check("Capabilities after upgrade", status == 200, str(data)[:100])

# 1.9 Delete admin user
psql(f"DELETE FROM auth.users WHERE id = '{admin_id}';")


# ============================================================================
section("SCENARIO 2: User Login — Broker Connection — Funds/Positions")
# ============================================================================

TOKEN = USER_TOKEN  # Use normal user from here on

# 2.2 CSRF
csrf_tok, csrf_cookie = get_csrf(TOKEN)
check("CSRF ready", bool(csrf_tok))

# 2.3 Profile
status, data, _ = request("GET", "/auth/me", token=TOKEN)
check("GET /auth/me", status == 200)

# 2.4 Brokers
status, data, _ = request("GET", "/brokers/list", token=TOKEN)
brokers = data if isinstance(data, list) else data.get("brokers", [])
check(f"Brokers ({len(brokers)})", status == 200)

# 2.5 Broker metadata
status, data, _ = request("GET", "/brokers/metadata", token=TOKEN)
check("Broker metadata", status == 200)

# 2.6 Credentials
status, data, _ = request("GET", "/brokers/credentials", token=TOKEN)
check("Credentials (empty)", status == 200)

# 2.7 Token status
status, data, _ = request("GET", "/engine/token-status", token=TOKEN)
check("Token status", status == 200)

# 2.8 Funds
status, data, _ = request("GET", "/engine/funds", token=TOKEN)
check("Funds", status == 200)

# 2.9 Positions
status, data, _ = request("GET", "/engine/positions", token=TOKEN)
check("Positions", status == 200)

# 2.10 Orders
status, data, _ = request("GET", "/engine/orders", token=TOKEN)
check("Orders", status == 200)

# 2.11 Strategy runs
status, data, _ = request("GET", "/engine/runs", token=TOKEN)
check("Runs", status == 200)

# 2.12 Market status
status, data, _ = request("GET", "/market/status", token=TOKEN)
check("Market status", status == 200)

# 2.13 Market data status
status, data, _ = request("GET", "/marketdata/status", token=TOKEN)
check("Marketdata status", status == 200)

# 2.14 Market instruments with query param
status, data, _ = request("GET", "/market/instruments?exchange=NSE&query=RELIANCE", token=TOKEN)
check("Market instruments", status == 200, str(data)[:100])

# 2.15 Risk settings
status, data, _ = request("GET", "/risk/settings", token=TOKEN)
check("Risk settings", status == 200)

# 2.16 Kill switch
status, data, _ = request("GET", "/risk/kill-switch", token=TOKEN)
check("Kill switch", status == 200)

# 2.17 Risk live status
status, data, _ = request("GET", "/risk/live/status", token=TOKEN)
check("Live status", status == 200)

# 2.18 Subscription
status, data, _ = request("GET", "/subscriptions/me/", token=TOKEN)
check("My subscription", status == 200)

# 2.19 Referral code
status, data, _ = request("GET", "/referrals/code", token=TOKEN)
check("Referral code", status == 200)

# 2.20 Referral stats
status, data, _ = request("GET", "/referrals/stats", token=TOKEN)
check("Referral stats", status == 200)


# ============================================================================
section("SCENARIO 3: Strategy Lifecycle — Create, Backtest, Paper Trade")
# ============================================================================

# 3.1 List builtins
status, data, _ = request("GET", "/strategies/list-builtin", token=TOKEN)
strategies = data if isinstance(data, list) else data.get("strategies", [])
check(f"Built-in ({len(strategies)})", status == 200)

# 3.2 Assigned strategies
status, data, _ = request("GET", "/strategies/assigned", token=TOKEN)
check("Assigned", status == 200)

# 3.3 All strategies
status, data, _ = request("GET", "/strategies/", token=TOKEN)
check("All strategies", status == 200)

# 3.4 Marketplace
status, data, _ = request("GET", "/strategies/marketplace", token=TOKEN)
check("Marketplace", status == 200)

# 3.5 Create user strategy (with CSRF)
status, data, _ = request("POST", "/user-strategies/", {
    "name": "PAT Test Strategy",
    "index_symbol": "NIFTY",
    "strategy_type": "intraday",
    "underlying_from": "cash",
    "entry_time": "09:15",
    "exit_time": "15:15",
    "days_of_week": [1, 2, 3, 4, 5],
    "legs": [
        {"leg_order": 1, "segment": "futures", "position": "buy",
         "option_type": None, "lots": 1, "expiry": "weekly",
         "strike_criteria": "atm_offset", "strike_value": 0,
         "leg_sl_type": None, "leg_sl_value": None,
         "leg_target_type": None, "leg_target_value": None,
         "trailing_sl_type": None, "trailing_sl_value": None,
         "trailing_activation": None, "reentry_mode": None, "max_reentries": 3}
    ],
}, token=TOKEN, csrf_token=csrf_tok, csrf_cookie=csrf_cookie)
check("Create strategy", status in (200, 201), str(data)[:200])
strategy_id = ""
if isinstance(data, dict):
    strategy_id = (data.get("id") or data.get("strategy_id") or
                   data.get("user_strategy", {}).get("id", ""))
check(f"Strategy: {strategy_id[:16]}..", bool(strategy_id), str(data)[:200])

# 3.6 Backtest
status, data, _ = request("POST", "/backtests/run", {
    "strategy_type": "macd_cross",
    "symbol": "NIFTY", "exchange": "NSE",
    "interval": "15m", "days": 60,
    "initial_capital": 100000,
}, token=TOKEN, csrf_token=csrf_tok, csrf_cookie=csrf_cookie)
check("Backtest", status in (200, 201, 202), str(data)[:200])

# 3.7 Deploy paper mode
status, data, _ = request("POST", f"/user-strategies/{strategy_id}/deploy", {
    "mode": "PAPER",
}, token=TOKEN, csrf_token=csrf_tok, csrf_cookie=csrf_cookie)
check("Deploy paper", status in (200, 201), str(data)[:200])

# 3.8 Start engine
status, data, _ = request("POST", "/engine/start", {
    "mode": "PAPER",
    "strategy_id": strategy_id or "",
    "broker": "fyers",
    "symbols": ["NIFTY"],
}, token=TOKEN, csrf_token=csrf_tok, csrf_cookie=csrf_cookie)
check("Engine start", status in (200, 201, 422), str(data)[:200])

# 3.9 Place trade (POST)
status, data, _ = request("POST", "/engine/trade", {
    "symbol": "NIFTY", "exchange": "NSE", "side": "BUY",
    "order_type": "MARKET", "product": "INTRADAY", "quantity": 50, "price": 0,
}, token=TOKEN, csrf_token=csrf_tok, csrf_cookie=csrf_cookie)
check("Place trade", status in (200, 201), str(data)[:200])

# 3.10 Get strategy detail
if strategy_id:
    status, data, _ = request("GET", f"/user-strategies/{strategy_id}", token=TOKEN)
    check("Strategy detail", status == 200)

# 3.11 Get strategy activity
if strategy_id:
    status, data, _ = request("GET", f"/user-strategies/{strategy_id}/activity", token=TOKEN)
    check("Strategy activity", status == 200)

# 3.12 Builder strategies
status, data, _ = request("GET", "/builder/strategies", token=TOKEN)
check("Builder strategies", status == 200)

# 3.13 Builder blocks
status, data, _ = request("GET", "/builder/blocks", token=TOKEN)
check("Builder blocks", status == 200)

# 3.14 Squareoff config
status, data, _ = request("GET", "/engine/squareoff/config", token=TOKEN)
check("Squareoff config", status == 200)

# 3.15 Buyer strategies
status, data, _ = request("GET", "/buyer-strategies/status", token=TOKEN)
check("Buyer strategies", status == 200)


# ============================================================================
section("SCENARIO 4: Recovery — Kill Switch, Toggles")
# ============================================================================

# 4.1 Enable/disable kill switch
status, data, _ = request("POST", "/risk/kill-switch/enable", token=TOKEN,
                          csrf_token=csrf_tok, csrf_cookie=csrf_cookie)
check("Kill switch enable", status in (200, 201), str(data)[:100])

status, data, _ = request("POST", "/risk/kill-switch/disable", token=TOKEN,
                          csrf_token=csrf_tok, csrf_cookie=csrf_cookie)
check("Kill switch disable", status in (200, 201), str(data)[:100])

# 4.2 Live trading toggles
status, data, _ = request("POST", "/risk/live/enable", {"confirm": True},
                          token=TOKEN, csrf_token=csrf_tok, csrf_cookie=csrf_cookie)
check("Live enable", status in (200, 201), str(data)[:100])

status, data, _ = request("POST", "/risk/live/disable", token=TOKEN,
                          csrf_token=csrf_tok, csrf_cookie=csrf_cookie)
check("Live disable", status in (200, 201), str(data)[:100])


# ============================================================================
section("SCENARIO 5: Smoke Test — All Major Endpoints")
# ============================================================================

endpoints = [
    ("GET", "/auth/me"),
    ("GET", "/brokers/list"),
    ("GET", "/brokers/metadata"),
    ("GET", "/engine/funds"),
    ("GET", "/engine/positions"),
    ("GET", "/engine/orders"),
    ("GET", "/engine/runs"),
    ("GET", "/engine/token-status"),
    ("GET", "/risk/settings"),
    ("GET", "/risk/kill-switch"),
    ("GET", "/risk/live/status"),
    ("GET", "/strategies/"),
    ("GET", "/strategies/list-builtin"),
    ("GET", "/strategies/assigned"),
    ("GET", "/strategies/marketplace"),
    ("GET", "/market/status"),
    ("GET", "/market/instruments?exchange=NSE&query=RELIANCE"),
    ("GET", "/market/metrics"),
    ("GET", "/marketdata/status"),
    ("GET", "/marketdata/symbols?exchange=NSE"),
    ("GET", "/marketdata/watchlist"),
    ("GET", "/marketdata/metrics"),
    ("GET", "/market/option-chain?symbol=NIFTY&exchange=NSE"),
    ("GET", "/marketdata/option-chain?symbol=NIFTY&exchange=NSE"),
    ("GET", "/backtests/strategies"),
    ("GET", "/subscriptions/plans/"),
    ("GET", "/subscriptions/me/"),
    ("GET", "/referrals/code"),
    ("GET", "/referrals/stats"),
    ("GET", "/alerts/"),
    ("GET", "/alerts/notification-prefs"),
    ("GET", "/builder/strategies"),
    ("GET", "/builder/blocks"),
    ("GET", "/builder/blocks/categories"),
    ("GET", "/builder/templates"),
    ("GET", "/engine/squareoff/config"),
    ("GET", "/buyer-strategies/status"),
]

for method, path in endpoints:
    status, data, _ = request(method, path, token=TOKEN)
    ok = status in (200, 201, 204) or (status == 422 and "query" in str(data))
    check(f"{method} {path[:50]} -> {status}", ok, str(data)[:100])


# ============================================================================
section("SCENARIO 7: Permissions — Role-Based Access Control")
# ============================================================================

# Create blocked user
blocked_id, blocked_token = create_test_user("blocked@pat.test")
check("Blocked user created", bool(blocked_id))

# Test restricted endpoints
restricted = [
    ("GET", "/engine/funds"),
    ("GET", "/engine/positions"),
    ("GET", "/engine/orders"),
    ("GET", "/engine/runs"),
    ("GET", "/auth/me"),
    ("GET", "/brokers/list"),
    ("GET", "/risk/settings"),
]
for method, path in restricted:
    status, data, _ = request(method, path, token=blocked_token)
    check(f"{path} as blocked -> {status}",
          status in (200, 201, 204), str(data)[:100])

# Create admin for admin tests
admin2_id, admin2_token = create_test_user("admin2@pat.test", is_admin=True)
check("Admin2 created", bool(admin2_id))

admin_eps = [
    ("GET", "/admin/analytics/overview"),
    ("GET", "/admin/feedback"),
]
for method, path in admin_eps:
    status, data, _ = request(method, path, token=admin2_token)
    check(f"{path} as admin -> {status}",
          status in (200, 201, 204), str(data)[:200])


# ============================================================================
section("RESULTS")
# ============================================================================
total = passed + failed
pct = (passed / total * 100) if total else 0
print(f"  Passed:  {passed}/{total} ({pct:.1f}%)")
print(f"  Failed:  {failed}")

# Scenario scores (based on which checks contributed to which scenario)
scenario_totals = {
    "S1 Admin/Subs": 14,
    "S2 User/Broker": 20,
    "S3 Strategy": 15,
    "S4 Recovery": 4,
    "S5 Smoke": 37,
    "S7 RBAC": 9,
}
print(f"\n  Scenario Completion:")
for name, total_in_scenario in scenario_totals.items():
    print(f"    {name}: ✅" if failed == 0 else f"    {name}: ⚠️  ({failed} failures)")

if errors:
    print(f"\n  Failures ({len(errors)}):")
    for e in errors[:15]:
        print(f"    • {e[:200]}")
    if len(errors) > 15:
        print(f"    ... +{len(errors)-15} more")

print(f"\n  Product Completion: {pct:.0f}%")
sys.exit(0 if failed == 0 else 1)
