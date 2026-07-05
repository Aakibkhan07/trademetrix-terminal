"""One-time script to create Razorpay subscription plans.

Usage:
    python scripts/setup_plans.py

Requires RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env.

Creates 4 plans: monthly, quarterly, halfyearly, yearly.
Outputs the plan IDs to add to your .env file.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import settings
from payments.razorpay import RazorpayClient

PLANS = [
    {"period": "monthly", "interval": 1, "name": "TradeMetrix Monthly", "amount": 1550000, "tier": "monthly"},
    {"period": "monthly", "interval": 3, "name": "TradeMetrix Quarterly", "amount": 3550000, "tier": "quarterly"},
    {"period": "monthly", "interval": 6, "name": "TradeMetrix Half Yearly", "amount": 6950000, "tier": "halfyearly"},
    {"period": "monthly", "interval": 12, "name": "TradeMetrix Yearly", "amount": 12500000, "tier": "yearly"},
]


async def main():
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        print("ERROR: RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in .env")
        sys.exit(1)

    client = RazorpayClient()
    print("Creating Razorpay plans...\n")

    for p in PLANS:
        result = await client.create_plan(
            period=p["period"],
            interval=p["interval"],
            name=p["name"],
            amount=p["amount"],
            notes={"tier": p["tier"]},
        )
        if result.get("id"):
            plan_id = result["id"]
            print(f"✅ {p['tier']:12s} → RAZORPAY_PLAN_{p['tier'].upper():12s}={plan_id}")
        else:
            print(f"❌ {p['tier']:12s} → ERROR: {result.get('error', result)}")


if __name__ == "__main__":
    asyncio.run(main())
