#!/usr/bin/env python3
"""Auth enforcement sweep — hit every protected endpoint without session cookie, assert 401/403.

Usage:
    python3 auth_sweep.py [--base-url https://api.ai.trademetrix.tech/api/v1]
"""
import sys
import httpx
import time

BASE = "https://api.ai.trademetrix.tech/api/v1"

# Every endpoint that requires auth (from route analysis)
# Format: (path, method, auth_level, note)
PROTECTED = [
    # ── USER level (get_current_user) ──
    ("GET", "/auth/me", "USER"),
    ("POST", "/auth/signout", "USER"),
    ("GET", "/ai/journal/entries", "USER"),
    ("GET", "/alerts/", "USER"),
    ("GET", "/alerts/notification-prefs", "USER"),
    ("GET", "/brokers/credentials", "USER"),
    ("GET", "/brokers/fyers/auth-url", "USER"),
    ("POST", "/brokers/fyers/re-auth", "USER"),
    ("GET", "/engine/funds", "USER"),
    ("GET", "/engine/orders", "USER"),
    ("GET", "/engine/orders/notes", "USER"),
    ("GET", "/engine/positions", "USER"),
    ("GET", "/engine/runs", "USER"),
    ("GET", "/engine/token-status", "USER"),
    ("GET", "/events/stream", "USER"),
    ("GET", "/risk/kill-switch", "USER"),
    ("POST", "/risk/kill-switch/disable", "USER"),
    ("POST", "/risk/kill-switch/enable", "USER"),
    ("POST", "/risk/live/disable", "USER"),
    ("GET", "/risk/live/status", "USER"),
    ("GET", "/risk/settings", "USER"),
    ("GET", "/strategies/", "USER"),
    ("GET", "/strategies/assigned", "USER"),
    # ── ADMIN level (require_admin) ──
    ("GET", "/admin/active-brokers", "ADMIN"),
    ("GET", "/admin/admins", "ADMIN"),
    ("GET", "/admin/brokers", "ADMIN"),
    ("GET", "/admin/risk", "ADMIN"),
    ("GET", "/admin/stats", "ADMIN"),
    ("GET", "/admin/users", "ADMIN"),
    # ── SUPER_ADMIN level (require_super_admin) ──
    ("POST", "/admin/admins", "SUPER_ADMIN"),
    ("PATCH", "/admin/admins/test-user-id", "SUPER_ADMIN"),
    ("DELETE", "/admin/admins/test-user-id", "SUPER_ADMIN"),
    # ── Feedback (USER) ──
    ("POST", "/feedback", "USER"),
    # ── Marketdata (USER) ──
    ("POST", "/marketdata/feed/start", "USER"),
    ("POST", "/marketdata/simulator/start", "USER"),
    ("POST", "/marketdata/simulator/stop", "USER"),
    # ── Admin analytics (ADMIN) ──
    ("GET", "/admin/analytics/overview", "ADMIN"),
]

# Endpoints in SAFE_PATHS that skip CSRF — paths match request.url.path (full /api/v1/...)
CSRF_SAFE = {
    "/auth/signout",
    "/marketdata/feed/start",
    "/marketdata/feed/stop",
    "/marketdata/simulator/start",
    "/marketdata/simulator/stop",
    "/alerts/",
}


def test_endpoint(client, method, path, auth_level):
    url = f"{BASE}{path}"
    try:
        resp = client.request(method, url, timeout=10)
        status = resp.status_code

        is_mutating = method in ("POST", "PUT", "PATCH", "DELETE")
        is_csrf_safe = path in CSRF_SAFE

        # Determine expected status
        if is_mutating and not is_csrf_safe:
            # CSRF middleware returns 403 first (no cookie/header)
            expected = 403
        else:
            # Auth dependency returns 401
            expected = 401

        ok = status == expected
        return (ok, status, expected, None)
    except Exception as e:
        return (False, 0, 0, str(e))


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else BASE

    client = httpx.Client(
        verify=False,  # self-signed or let's encrypt — ignore
        follow_redirects=False,
        headers={
            "User-Agent": "AuthSweep/1.0",
            "Accept": "application/json",
        },
    )
    # Intentionally NO cookies, NO Authorization header

    results = []
    print(f"Auth Sweep against: {base_url}")
    print(f"{'STATUS':8s} {'EXP':4s} {'METHOD':8s} {'ENDPOINT':65s} {'AUTH':15s}")
    print(f"{'-'*8} {'-'*4} {'-'*8} {'-'*65} {'-'*15}")
    for method, path, auth_level in PROTECTED:
        ok, status, expected, err = test_endpoint(client, method, path, auth_level)
        label = "✅" if ok else "❌"
        status_str = f"{status}" if status else "ERR"
        exp_str = f"{expected}"
        err_suffix = f"  [{err}]" if err else ""
        print(f"{label} {status_str:4s} {exp_str:4s} {method:8s} {path:65s} {auth_level:15s}{err_suffix}")
        results.append((ok, method, path, status, expected, err))

    print(f"\n{'='*110}")
    passed = sum(1 for r in results if r[0])
    failed = sum(1 for r in results if not r[0])
    print(f"PASSED: {passed}/{len(results)}")
    print(f"FAILED: {failed}/{len(results)}")

    if failed > 0:
        print(f"\n❌ FAILURES:")
        for ok, method, path, status, expected, err in results:
            if not ok:
                if err:
                    print(f"  {method:8s} {path:65s} → ERROR: {err}")
                else:
                    print(f"  {method:8s} {path:65s} → got {status}, expected {expected}")
        sys.exit(1)
    else:
        print(f"\n✅ All protected endpoints correctly reject unauthenticated requests.")


if __name__ == "__main__":
    main()
