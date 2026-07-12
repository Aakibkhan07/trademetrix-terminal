"""
PAPER-MODE end-to-end test of multi-user mirror fan-out.
Creates test fixtures, runs all 8 scenarios, cleans up.
"""
import asyncio
import os
import sys
import uuid

import requests

# ── Env must be set before any app imports ──────────────────────
os.environ.setdefault("SUPABASE_URL", "https://nwutlfuowiulfpbsrldn.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im53dXRsZnVvd2l1bGZwYnNybGRuIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MTYyMTk1MSwiZXhwIjoyMDk3MTk3OTUxfQ.D2nVCb_gdUpfnZQ9xKU1Dibppvec6umjr5qTI5qKGT8")
os.environ.setdefault("ENCRYPTION_KEY", "ZTtsuGQCgigNHKjnANV_FyTsMqZuRKPOCyYK8nps7x0=")
os.environ.setdefault("SECRET_KEY", "a7f8c9d0e1b2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.db import get_supabase
from core.models import NormalizedOrder, OrderSide, OrderType, ProductType, Exchange
from engine.gate import execute_order


STRATEGY_KEY = "trend_rider"
SIGNAL_QTY = 1000
SIGNAL_PRICE = 150.0
TEST_TAG = f"t{int(__import__('time').time())}"
SIGNAL_REASON = f"test-mirror-fanout-{uuid.uuid4().hex[:8]}"


# ── Fixture helpers ────────────────────────────────────────────

_USER_IDS = {}


def uid(prefix: str) -> str:
    return _USER_IDS[prefix]


def _make_uid(prefix: str) -> str:
    u = str(uuid.uuid4())
    _USER_IDS[prefix] = u
    return u


def _ensure_table_exists():
    """Ensure strategy_assignments table exists (via psql fallback)."""
    sb = get_supabase()
    try:
        sb.table("strategy_assignments").select("id").limit(1).execute()
        return  # table already exists
    except Exception:
        pass
    _psql("""
        CREATE TABLE IF NOT EXISTS public.strategy_assignments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
            strategy_key TEXT NOT NULL,
            required_tier TEXT NOT NULL DEFAULT 'free',
            mirror_enabled BOOLEAN NOT NULL DEFAULT true,
            active BOOLEAN NOT NULL DEFAULT true,
            assigned_by uuid REFERENCES public.profiles(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sa_user_key
            ON public.strategy_assignments(user_id, strategy_key);
        CREATE INDEX IF NOT EXISTS idx_sa_user_active
            ON public.strategy_assignments(user_id, active);
    """)



def _cleanup(sb=None):
    """Remove all traces of test users via Admin API + REST."""
    auth_url = f"{os.environ['SUPABASE_URL']}/auth/v1/admin/users"
    auth_headers = {
        "apikey": os.environ["SUPABASE_SERVICE_KEY"],
        "Authorization": f"Bearer {os.environ['SUPABASE_SERVICE_KEY']}",
    }
    for prefix in ("user_a", "user_b", "user_c", "user_d", "user_e"):
        u = _USER_IDS.get(prefix)
        if u:
            try:
                requests.delete(f"{auth_url}/{u}", headers=auth_headers)
            except Exception:
                pass
    # Also clean stale users by email pattern
    try:
        all_resp = requests.get(auth_url, headers=auth_headers)
        if all_resp.ok:
            for u in (all_resp.json().get("users") or []):
                email = u.get("email", "")
                if email.endswith("@test.trademetrix.tech"):
                    requests.delete(f"{auth_url}/{u['id']}", headers=auth_headers)
    except Exception:
        pass
    if sb:
        for key in ("user_a", "user_b", "user_c", "user_d", "user_e"):
            uid_val = _USER_IDS.get(key)
            if uid_val:
                for table in ("orders", "audit_log", "risk_settings", "broker_credentials", "strategy_assignments"):
                    try:
                        sb.table(table).delete().eq("user_id", uid_val).execute()
                    except Exception:
                        pass
    print("[cleanup] Removed all test fixtures\n")


def _psql(sql: str):
    """Execute raw SQL on the Supabase postgres database."""
    import subprocess
    env = {**os.environ, "PGPASSWORD": "Aakibkhan1@23"}
    r = subprocess.run(
        ["psql", "-h", "db.nwutlfuowiulfpbsrldn.supabase.co", "-U", "postgres", "-d", "postgres", "-c", sql],
        env=env, capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0:
        print(f"  [psql] stderr: {r.stderr[:200]}")
    return r.stdout


def _create_user(prefix: str, tier: str = "free", is_admin: bool = False):
    sb = get_supabase()
    email = f"{prefix}-{TEST_TAG}@test.trademetrix.tech"
    auth_url = f"{os.environ['SUPABASE_URL']}/auth/v1/admin/users"
    auth_headers = {
        "apikey": os.environ["SUPABASE_SERVICE_KEY"],
        "Authorization": f"Bearer {os.environ['SUPABASE_SERVICE_KEY']}",
        "Content-Type": "application/json",
    }

    # Create (or recreate) user via GoTrue Admin API
    resp = requests.post(auth_url, headers=auth_headers, json={
        "email": email,
        "password": "testpass123!",
        "email_confirm": True,
    })
    if resp.status_code == 409:
        # User exists — find and delete, then retry
        all_resp = requests.get(auth_url, headers=auth_headers)
        if all_resp.ok:
            for u in (all_resp.json().get("users") or []):
                if u.get("email") == email:
                    requests.delete(f"{auth_url}/{u['id']}", headers=auth_headers)
        resp = requests.post(auth_url, headers=auth_headers, json={
            "email": email,
            "password": "testpass123!",
            "email_confirm": True,
        })
    resp.raise_for_status()
    u = resp.json()["id"]
    _USER_IDS[prefix] = u

    # Create profile via REST
    sb.table("profiles").upsert({
        "id": u,
        "name": f"Test {prefix}",
        "email": email,
        "subscription_tier": tier,
        "is_admin": is_admin,
    }).execute()
    return u


_STRATEGY_UUID = ""


def _ensure_strategy(sb) -> str:
    global _STRATEGY_UUID
    if _STRATEGY_UUID:
        return _STRATEGY_UUID
    # Create a strategy row so the FK from risk_settings / orders can reference it
    existing = sb.table("strategies").select("id").eq("name", STRATEGY_KEY).maybe_single().execute()
    if existing and existing.data:
        _STRATEGY_UUID = existing.data["id"]
        return _STRATEGY_UUID
    result = sb.table("strategies").insert({
        "name": STRATEGY_KEY,
        "type": "builtin",
    }).execute()
    _STRATEGY_UUID = result.data[0]["id"]
    return _STRATEGY_UUID


def _risk_settings(sb, user_id: str, **overrides):
    sb.table("risk_settings").delete().eq("user_id", user_id).execute()
    data = {
        "user_id": user_id,
        "strategy_id": _STRATEGY_UUID,
        "max_capital": 0.0,
        "max_position_size": 0.0,
        "max_open_positions": 10,
        "max_daily_loss": 0.0,
        "max_drawdown_pct": 0.0,
        "kill_switch_enabled": False,
        "is_live": False,
    }
    data.update(overrides)
    sb.table("risk_settings").insert(data).execute()


def _broker_creds(sb, user_id: str):
    sb.table("broker_credentials").delete().eq("user_id", user_id).execute()
    sb.table("broker_credentials").insert({
        "user_id": user_id,
        "broker": "angelone",
        "encrypted_api_key": "test_key",
        "encrypted_secret_key": "test_secret",
        "is_active": True,
    }).execute()


def _assign(sb, user_id: str, mirror_enabled: bool = True, active: bool = True):
    sb.table("strategy_assignments").delete().eq("user_id", user_id).eq("strategy_key", STRATEGY_KEY).execute()
    sb.table("strategy_assignments").insert({
        "user_id": user_id,
        "strategy_key": STRATEGY_KEY,
        "required_tier": "free",
        "mirror_enabled": mirror_enabled,
        "active": active,
    }).execute()


# ── Scenarios ──────────────────────────────────────────────────

def _section(title: str, body: str) -> str:
    n = len(title) + 6
    return f"\n╔══ {title} ══╗\n{body}\n╚{'═' * n}╝"


async def scenario_1_recipients():
    """Verify recipient selection."""
    from routes.v1_tradingview import _get_mirror_recipients
    all_recipients = await _get_mirror_recipients(STRATEGY_KEY)

    a = uid("user_a")
    b = uid("user_b")
    c = uid("user_c")
    d = uid("user_d")
    e = uid("user_e")
    our_ids = {a, b, c, d, e}

    # Only consider our test users (ignore stale leftovers from prior aborted runs)
    recipients = [u for u in all_recipients if u in our_ids]
    recipient_ids = set(recipients)

    print(_section("1: Recipients", f"""
All recipients in DB: {len(all_recipients)} (includes stale users from prior runs)
Filtered to our users: {sorted(recipients)}

Expected: A, B, E  (C=no mirror, D=no assignment)
A in list: {a in recipient_ids}
B in list: {b in recipient_ids}
C in list: {c in recipient_ids}  (should be FALSE)
D in list: {d in recipient_ids}  (should be FALSE)
E in list: {e in recipient_ids}
"""))
    assert a in recipient_ids, "A must be in recipients"
    assert b in recipient_ids, "B must be in recipients"
    assert c not in recipient_ids, "C must NOT be in recipients (mirror_enabled=false)"
    assert d not in recipient_ids, "D must NOT be in recipients (no assignment)"
    assert e in recipient_ids, "E must be in recipients"
    return recipients


SAFE_QTY = 100  # small enough to pass both A and B position-size checks


async def scenario_2_and_3_and_6(sb, recipients):
    """Execute order for each recipient, verify gate path, and reason string."""
    a = uid("user_a")
    b = uid("user_b")
    e = uid("user_e")
    print(_section("2 & 6: Gate path + reason", ""))

    results = {}
    for user_id in recipients:
        order = NormalizedOrder(
            symbol="NIFTY",
            exchange=Exchange.NFO,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            product=ProductType.INTRADAY,
            quantity=SAFE_QTY,
            price=SIGNAL_PRICE,
            reason=SIGNAL_REASON,
        )
        result = await execute_order(user_id, order, source="mirror")
        results[user_id] = result
        label = {a: "A", b: "B", e: "E"}.get(user_id, user_id[:8])
        qty = result.order.quantity if result.order else order.quantity
        print(f"  {label}: status={result.status}  qty={qty}  msg={result.message}  broker_order_id={result.broker_order_id}")

    a_result = results.get(a)
    b_result = results.get(b)
    e_result = results.get(e)

    # Scenario 2: gate path — source="mirror" is confirmed by audit rows (scenario 5)
    print("\n  [2] Gate path confirmed: each recipient called execute_order with source=mirror")
    assert a_result is not None and a_result.status in ("paper", "placed"), f"A should have succeeded, got {a_result}"
    assert b_result is not None and b_result.status in ("paper", "placed"), f"B should have succeeded, got {b_result}"

    # Scenario 6: reason string carried through (via result.order.reason)
    a_reason = a_result.order.reason if a_result and a_result.order else ""
    b_reason = b_result.order.reason if b_result and b_result.order else ""
    print("\n  [6] Reason check:")
    print(f"      Signal reason: {SIGNAL_REASON}")
    print(f"      A order reason: {a_reason}")
    print(f"      B order reason: {b_reason}")
    assert SIGNAL_REASON in str(a_reason), f"Reason not carried to A: {a_reason}"
    assert SIGNAL_REASON in str(b_reason), f"Reason not carried to B: {b_reason}"

    return results


def _get_user_orders(sb, user_id):
    data = sb.table("orders").select("*").eq("user_id", user_id).eq("source", "mirror").order("created_at", desc=True).limit(5).execute()
    return data.data or []


def _get_user_audit(sb, user_id):
    data = sb.table("audit_log").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(5).execute()
    return data.data or []


def scenario_4_kill_switch(sb, recipients, results):
    """E should be rejected with KILL_SWITCH; A and B still passed."""
    a = uid("user_a")
    b = uid("user_b")
    e = uid("user_e")
    print(_section("4: Kill switch isolation", ""))

    a_ok = results.get(a) and results.get(a).status in ("paper", "placed")
    b_ok = results.get(b) and results.get(b).status in ("paper", "placed")
    e_status = results.get(e).status if results.get(e) else "N/A"
    e_msg = results.get(e).message if results.get(e) else "N/A"

    print(f"  A status: {results.get(a).status if results.get(a) else 'N/A'}  (should be paper)")
    print(f"  B status: {results.get(b).status if results.get(b) else 'N/A'}  (should be paper)")
    print(f"  E status: {e_status}  message: {e_msg}  (should be rejected, KILL_SWITCH)")
    print(f"  E kill_switch status: {sb.table('risk_settings').select('kill_switch_enabled').eq('user_id', e).maybe_single().execute().data}")

    assert a_ok, f"A should have executed, got {results.get(a)}"
    assert b_ok, f"B should have executed, got {results.get(b)}"
    assert results.get(e) and results.get(e).status == "rejected", f"E should be rejected, got {results.get(e)}"
    assert results.get(e) and "KILL_SWITCH" in (results.get(e).message or ""), f"E should say KILL_SWITCH, got {results.get(e).message}"


def scenario_5_audit(sb, recipients):
    """One audit row per processed recipient with correct source and reason."""
    a = uid("user_a")
    b = uid("user_b")
    e = uid("user_e")
    print(_section("5: Audit log", ""))

    for label, uid_val in [("A", a), ("B", b), ("E", e)]:
        rows = _get_user_audit(sb, uid_val)
        print(f"\n  {label} ({uid_val}) audit rows:")
        for r in rows:
            rid = str(r.get("id", ""))[:8]
            print(f"    id={rid} action={r['action']} source={r.get('source','?')} "
                  f"reason={r.get('reason','?')} broker={r.get('broker','?')} "
                  f"symbol={r.get('symbol','?')} side={r.get('side','?')} qty={r.get('quantity','?')}")
        mirror_rows = [r for r in rows if r.get("source") == "mirror"]
        assert len(mirror_rows) >= 1, f"{label} should have at least 1 audit row with source=mirror"
        if label == "E":
            # E should have a "rejected" audit row
            rejected = [r for r in rows if r.get("action") == "rejected"]
            assert len(rejected) >= 1, "E should have a 'rejected' audit row"
            assert any("KILL_SWITCH" in (r.get("reason") or "") for r in rejected), "E rejection reason should contain KILL_SWITCH"
        else:
            assert any(r.get("source") == "mirror" for r in rows), f"{label} audit should have source=mirror"


def scenario_7_idempotency(sb, recipients):
    """Re-broadcast — no duplicate orders for A or B."""
    a = uid("user_a")
    b = uid("user_b")
    print(_section("7: Idempotency (re-broadcast)", ""))

    before_a = _get_user_orders(sb, a)
    before_b = _get_user_orders(sb, b)
    before_a_count = len(before_a)
    before_b_count = len(before_b)

    # Re-broadcast to A and B using execute_order (same params => same client_order_id)
    order_a = NormalizedOrder(
        symbol="NIFTY", exchange=Exchange.NFO, side=OrderSide.BUY,
        order_type=OrderType.MARKET, product=ProductType.INTRADAY,
        quantity=SIGNAL_QTY, price=SIGNAL_PRICE,
        strategy_id=STRATEGY_KEY, reason=SIGNAL_REASON,
    )
    result_a2 = asyncio.get_event_loop().run_until_complete(execute_order(a, order_a, source="mirror"))

    order_b = NormalizedOrder(
        symbol="NIFTY", exchange=Exchange.NFO, side=OrderSide.BUY,
        order_type=OrderType.MARKET, product=ProductType.INTRADAY,
        quantity=SIGNAL_QTY, price=SIGNAL_PRICE,
        strategy_id=STRATEGY_KEY, reason=SIGNAL_REASON,
    )
    result_b2 = asyncio.get_event_loop().run_until_complete(execute_order(b, order_b, source="mirror"))

    after_a = _get_user_orders(sb, a)
    after_b = _get_user_orders(sb, b)
    after_a_count = len(after_a)
    after_b_count = len(after_b)

    # Show client_order_ids
    for label, orders in [("A", after_a), ("B", after_b)]:
        print(f"  {label} orders ({len(orders)}):")
        for o in orders:
            print(f"    client_order_id={o.get('client_order_id','?')}  status={o.get('status','?')}  broker_order_id={o.get('broker_order_id','?')[:24]}")

    print(f"\n  A: {before_a_count} before -> {after_a_count} after  (should be {before_a_count})")
    print(f"  B: {before_b_count} before -> {after_b_count} after  (should be {before_b_count})")
    print(f"  A result: status={result_a2.status} msg={result_a2.message}")
    print(f"  B result: status={result_b2.status} msg={result_b2.message}")

    assert after_a_count == before_a_count, f"A: order count increased ({before_a_count} -> {after_a_count}) — duplicate created!"
    assert after_b_count == before_b_count, f"B: order count increased ({before_b_count} -> {after_b_count}) — duplicate created!"
    assert result_a2.status == "duplicate", f"A re-broadcast should say duplicate, got {result_a2.status}"
    assert result_b2.status == "duplicate", f"B re-broadcast should say duplicate, got {result_b2.status}"


def scenario_8_paper_safety(sb, recipients):
    """Confirm no live orders were placed."""
    a = uid("user_a")
    b = uid("user_b")
    e = uid("user_e")
    print(_section("8: Paper safety", ""))

    for label, uid_val in [("A", a), ("B", b), ("E", e)]:
        settings = sb.table("risk_settings").select("is_live").eq("user_id", uid_val).maybe_single().execute()
        is_live = settings.data.get("is_live", True) if settings and settings.data else "UNKNOWN"
        orders = _get_user_orders(sb, uid_val)
        is_paper = all(o.get("is_paper", False) for o in orders) if orders else "NO_ORDERS"
        print(f"  {label}: is_live={is_live}  orders_is_paper={is_paper}")
        assert is_live is False or is_live == "NO_ORDERS" or is_paper, f"{label} should be in paper mode!"

    print("\n  ✅ All users confirmed PAPER mode. No live orders placed.")


# ── Main ───────────────────────────────────────────────────────

async def main():
    sb = get_supabase()
    from engine.gate import scaled_qty

    # ── Ensure test table exists ──
    _ensure_table_exists()

    # ── Create fixtures ──
    print("═══ Creating test fixtures ═══")
    user_a = _create_user("user_a", tier="pro")
    user_b = _create_user("user_b", tier="pro")
    user_c = _create_user("user_c", tier="starter")
    user_d = _create_user("user_d", tier="free")
    user_e = _create_user("user_e", tier="pro")

    print(f"  A: {user_a} (pro, max_position_size=150000)")
    print(f"  B: {user_b} (pro, max_position_size=50000)")
    print(f"  C: {user_c} (starter, mirror_enabled=false)")
    print(f"  D: {user_d} (free, no assignment)")
    print(f"  E: {user_e} (pro, kill_switch=true)")

    _ensure_strategy(sb)
    _risk_settings(sb, user_a, max_position_size=150000.0)
    _risk_settings(sb, user_b, max_position_size=50000.0)
    _risk_settings(sb, user_c, max_position_size=100000.0)
    _risk_settings(sb, user_d, max_position_size=100000.0)
    _risk_settings(sb, user_e, max_position_size=100000.0, kill_switch_enabled=True)

    _broker_creds(sb, user_a)
    _broker_creds(sb, user_b)
    _broker_creds(sb, user_c)
    _broker_creds(sb, user_d)
    _broker_creds(sb, user_e)

    _assign(sb, user_a, mirror_enabled=True)
    _assign(sb, user_b, mirror_enabled=True)
    _assign(sb, user_c, mirror_enabled=False)
    _assign(sb, user_e, mirror_enabled=True)
    # D intentionally not assigned

    print("  ✅ Fixtures ready\n")

    # ── Run scenarios ──
    recipients = await scenario_1_recipients()
    results = await scenario_2_and_3_and_6(sb, recipients)
    scenario_4_kill_switch(sb, recipients, results)
    scenario_5_audit(sb, recipients)
    scenario_8_paper_safety(sb, recipients)

    # ── Scenario 3 (scaling) — call scaled_qty for A and B directly ──
    print(_section("3: Quantity scaling", ""))
    a_qty = scaled_qty(user_a, SIGNAL_QTY, SIGNAL_PRICE)
    b_qty = scaled_qty(user_b, SIGNAL_QTY, SIGNAL_PRICE)
    print(f"  Signal base qty: {SIGNAL_QTY}")
    print(f"  User A max_position_size=150000  price={SIGNAL_PRICE}  max_qty={int(150000/SIGNAL_PRICE)}  →  scaled={a_qty}")
    print(f"  User B max_position_size=50000   price={SIGNAL_PRICE}  max_qty={int(50000/SIGNAL_PRICE)}   →  scaled={b_qty}")
    assert a_qty != b_qty, f"Quantities MUST differ! A={a_qty} B={b_qty}"
    assert a_qty > b_qty, f"A ({a_qty}) should have larger qty than B ({b_qty})"
    print()

    # ── Scenario 7: re-broadcast for idempotency ──
    print("\n═══ Re-running broadcast for idempotency check ═══")
    # First determine what client_order_ids were generated (from the first broadcast)
    first_a_results = results.get(user_a)
    first_b_results = results.get(user_b)
    if first_a_results and first_a_results.order:
        print(f"  First broadcast A client_order_id: {first_a_results.order.client_order_id}")
    if first_b_results and first_b_results.order:
        print(f"  First broadcast B client_order_id: {first_b_results.order.client_order_id}")

    order_a2 = NormalizedOrder(
        symbol="NIFTY", exchange=Exchange.NFO, side=OrderSide.BUY,
        order_type=OrderType.MARKET, product=ProductType.INTRADAY,
        quantity=SAFE_QTY, price=SIGNAL_PRICE,
        reason=SIGNAL_REASON,
    )
    result_a2 = await execute_order(user_a, order_a2, source="mirror")
    order_b2 = NormalizedOrder(
        symbol="NIFTY", exchange=Exchange.NFO, side=OrderSide.BUY,
        order_type=OrderType.MARKET, product=ProductType.INTRADAY,
        quantity=SAFE_QTY, price=SIGNAL_PRICE,
        reason=SIGNAL_REASON,
    )
    result_b2 = await execute_order(user_b, order_b2, source="mirror")

    if result_a2.order:
        print(f"  Re-broadcast A client_order_id: {result_a2.order.client_order_id}")
    if result_b2.order:
        print(f"  Re-broadcast B client_order_id: {result_b2.order.client_order_id}")
    print(f"  A result: status={result_a2.status} msg={result_a2.message}  (should be 'duplicate')")
    print(f"  B result: status={result_b2.status} msg={result_b2.message}  (should be 'duplicate')")
    assert result_a2.status == "duplicate", f"A re-broadcast should be duplicate, got {result_a2.status}"
    assert result_b2.status == "duplicate", f"B re-broadcast should be duplicate, got {result_b2.status}"

    # Verify client_order_id is the same between broadcasts
    if first_a_results and first_a_results.order and result_a2.order:
        assert first_a_results.order.client_order_id == result_a2.order.client_order_id, "A client_order_id changed between broadcasts!"
    if first_b_results and first_b_results.order and result_b2.order:
        assert first_b_results.order.client_order_id == result_b2.order.client_order_id, "B client_order_id changed between broadcasts!"

    # ── Cleanup ──
    _cleanup(sb)

    print("\n⚠️  DONE — All assertions passed. Cleanup complete.")


if __name__ == "__main__":
    asyncio.run(main())
