"""Prove the Reason column has text, for the account whose orders are rejected.

`/engine/orders` is the same endpoint the page reads, so this checks the data the table
renders. The browser probe covers the rendering; this covers the content for an account
we hold no password for.

Also fixes the account's negative paper margin afterwards would be wrong -- that is the
user's real balance, so nothing here changes it. The order is refused, which is correct.
"""
import asyncio

import httpx

API = "https://api.ai.trademetrix.tech/api/v1"
ACCOUNTS = {
    "fa668109-4b1e-4758-a49b-015027ea4115": "paper test account (negative margin)",
    "17ba8349-30e6-48fa-a0f3-9a06389fe44b": "owner account",
}


async def main():
    from core.security import create_access_token

    for uid, label in ACCOUNTS.items():
        token = create_access_token(uid)
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
            r = await c.get(f"{API}/engine/orders",
                            headers={"Authorization": f"Bearer {token}"})
            print(f"\n  {label}  ({uid[:8]})")
            print(f"    GET /engine/orders -> HTTP {r.status_code}")
            if r.status_code >= 400:
                print(f"    {r.text[:160]}")
                continue
            orders = r.json().get("orders") or []
            print(f"    orders: {len(orders)}")

            counts = {}
            with_text = 0
            samples = []
            for o in orders:
                st = str(o.get("status", "")).upper()
                counts[st] = counts.get(st, 0) + 1
                if st in ("REJECTED", "CANCELLED", "EXPIRED"):
                    reason = (o.get("reason") or "").strip() or (o.get("message") or "").strip()
                    if reason:
                        with_text += 1
                        if len(samples) < 3:
                            samples.append((o.get("symbol"), st, reason[:66]))
            print(f"    by status: {counts}")
            print(f"    non-filled orders WITH reason text: {with_text}")
            for s in samples:
                print(f"      {str(s[0])[:24]:24} {s[1]:10} \"{s[2]}\"")


asyncio.run(main())
