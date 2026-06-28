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

    async def create_order(self, amount: int, currency: str = "INR", receipt: str = "") -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/orders",
                json={"amount": amount, "currency": currency, "receipt": receipt},
                auth=(self.key_id, self.key_secret),
            )
            return resp.json()

    async def create_subscription(self, plan_id: str, customer_email: str, total_count: int = 12) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/subscriptions",
                json={
                    "plan_id": plan_id,
                    "customer_notify": 1,
                    "total_count": total_count,
                    "quantity": 1,
                },
                auth=(self.key_id, self.key_secret),
            )
            return resp.json()

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
