import hashlib
import hmac
import logging

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


class RazorpayClient:
    def __init__(self):
        self.key_id = settings.razorpay_key_id
        self.key_secret = settings.razorpay_key_secret
        self._base_url = "https://api.razorpay.com/v1"

    async def _post(self, path: str, data: dict) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}{path}",
                json=data,
                auth=(self.key_id, self.key_secret),
            )
            return resp.json()

    async def _get(self, path: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}{path}",
                auth=(self.key_id, self.key_secret),
            )
            return resp.json()

    async def create_order(self, amount: int, currency: str = "INR", receipt: str = "") -> dict:
        return await self._post("/orders", {"amount": amount, "currency": currency, "receipt": receipt})

    async def create_plan(self, period: str, interval: int, name: str, amount: int, currency: str = "INR", notes: dict | None = None) -> dict:
        return await self._post("/plans", {
            "period": period,
            "interval": interval,
            "item": {"name": name, "amount": amount, "currency": currency},
            "notes": notes or {},
        })

    async def create_subscription(
        self,
        plan_id: str,
        total_count: int,
        customer_notify: bool = True,
        quantity: int = 1,
        trial_period_days: int = 0,
        notes: dict | None = None,
    ) -> dict:
        body = {
            "plan_id": plan_id,
            "total_count": total_count,
            "customer_notify": 1 if customer_notify else 0,
            "quantity": quantity,
            "notes": notes or {},
        }
        if trial_period_days:
            body["trial_period_days"] = trial_period_days
        return await self._post("/subscriptions", body)

    async def fetch_subscription(self, subscription_id: str) -> dict:
        return await self._get(f"/subscriptions/{subscription_id}")

    async def cancel_subscription(self, subscription_id: str, cancel_at_cycle_end: bool = True) -> dict:
        return await self._post(f"/subscriptions/{subscription_id}/cancel", {"cancel_at_cycle_end": 1 if cancel_at_cycle_end else 0})

    def verify_payment(self, order_id: str, payment_id: str, signature: str) -> bool:
        expected = hmac.new(
            self.key_secret.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_webhook(self, body: bytes, signature: str, secret: str) -> bool:
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
