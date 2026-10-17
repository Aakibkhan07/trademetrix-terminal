"""End-to-end paper order through the real HTTP path in production.

This is the test that matters for "is the platform functional": route -> gate -> risk ->
OMS queue -> Redis -> worker -> paper broker -> fill -> position -> audit. Every step the
UI depends on, driven as a signed-in user.

Paper only: is_paper=True, so nothing can reach a real exchange even if the paper path
were wrong. Run from inside the API container so create_access_token is available.
"""
import asyncio

import httpx

API = "https://api.ai.trademetrix.tech/api/v1"
USER_ID = "fa668109-4b1e-4758-a49b-015027ea4115"  # long-standing paper test account


def ok(resp) -> bool:
    return resp.status_code < 400


def show(label, passed, detail=""):
    print(f"  {'PASS' if passed else 'FAIL'}  {label}{('  ' + detail) if detail else ''}")
    return bool(passed)


def count(resp, key="positions") -> int:
    if not ok(resp):
        return -1
    return len(resp.json().get(key) or [])


async def main() -> int:
    from core.security import create_access_token

    token = create_access_token(USER_ID)
    results = []

    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as c:
        headers = {"Authorization": f"Bearer {token}"}

        r = await c.get(f"{API}/auth/csrf", headers=headers)
        csrf = r.json().get("csrf_token") or r.cookies.get("csrf_token")
        post_headers = {**headers, "X-CSRF-Token": csrf}

        before = await c.get(f"{API}/engine/positions", headers=headers)
        before_n = count(before)
        results.append(show("GET /engine/positions (baseline)", ok(before),
                            f"HTTP {before.status_code}, {before_n} positions"))

        payload = {
            "symbol": "NSE:NIFTY50-INDEX", "side": "BUY", "quantity": 1,
            "order_type": "MARKET", "product": "MIS", "is_paper": True,
            "source": "e2e_paper_check",
        }
        r = await c.post(f"{API}/engine/trade", json=payload, headers=post_headers)
        raw = r.text
        results.append(show("POST /engine/trade (paper BUY)", ok(r),
                            f"HTTP {r.status_code}  {raw[:400]}"))

        order_id = None
        if ok(r):
            data = r.json()
            # The id lives under result.order.broker_order_id, and the sibling `id` is an
            # EMPTY STRING -- reading the top level, or `id`, reports "no order was
            # placed" for an order that was accepted. Measured response shape:
            #   {"result":{"success":true,"broker_order_id":"paper_1_...",
            #              "order":{"id":"","broker_order_id":"paper_1_...", ...}}}
            result = data.get("result") or {}
            order = result.get("order") or {}
            order_id = (order.get("broker_order_id") or order.get("id")
                        or result.get("broker_order_id")
                        or data.get("order_id") or data.get("id"))
            results.append(show("  order accepted", bool(order_id),
                                f"id={order_id} success={result.get('success')}"))

        if order_id:
            final = None
            for _ in range(14):
                await asyncio.sleep(4)
                rr = await c.get(f"{API}/engine/orders", headers=headers)
                if not ok(rr):
                    continue
                for o in rr.json().get("orders") or []:
                    if str(o.get("order_id")) == str(order_id) or \
                       str(o.get("id")) == str(order_id):
                        final = o
                        break
                if final and str(final.get("status", "")).upper() in {
                        "FILLED", "PENDING", "PARTIAL", "REJECTED", "CANCELLED"}:
                    break
            if final:
                st = str(final.get("status", "")).upper()
                results.append(show("  order visible in /engine/orders", True,
                                    f"status={st} filled={final.get('filled_quantity')} "
                                    f"avg={final.get('average_price')}"))
                results.append(show("  order FILLED", st == "FILLED", f"(status={st})"))
            else:
                results.append(show("  order visible in /engine/orders", False,
                                    "not found after ~56s"))

            rc = await c.delete(f"{API}/engine/orders/{order_id}", headers=post_headers)
            print(f"  info  cleanup DELETE /engine/orders/{order_id}: HTTP {rc.status_code}")

        after = await c.get(f"{API}/engine/positions", headers=headers)
        after_n = count(after)
        results.append(show("GET /engine/positions (after)", ok(after),
                            f"HTTP {after.status_code}, {after_n} positions"))
        results.append(show("  positions readable", after_n >= 0,
                            f"{before_n} -> {after_n}"))

    passed = sum(1 for x in results if x)
    print(f"\n  {passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


raise SystemExit(asyncio.run(main()))
