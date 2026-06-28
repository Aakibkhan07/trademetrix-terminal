import hashlib
import json
import logging

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


class PaytmClient:
    def __init__(self):
        self.mid = settings.paytm_merchant_id
        self.key = settings.paytm_merchant_key
        self._base_url = "https://securegw.paytm.in"

    async def create_order(self, order_id: str, amount: str, customer_id: str, callback_url: str) -> dict:
        payload = {
            "body": {
                "requestType": "Payment",
                "mid": self.mid,
                "websiteName": "TRADEMETRIX",
                "orderId": order_id,
                "txnAmount": {"value": amount, "currency": "INR"},
                "userInfo": {"custId": customer_id},
                "callbackUrl": callback_url,
            }
        }

        checksum = self._generate_checksum(payload["body"])
        payload["head"] = {"signature": checksum}

        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self._base_url}/theia/api/v1/initiateTransaction", json=payload)
            return resp.json()

    def verify_checksum(self, payload: dict, signature: str) -> bool:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        expected = hashlib.sha256(body.encode() + self.key.encode()).hexdigest()
        return expected == signature

    def _generate_checksum(self, body: dict) -> str:
        body_str = json.dumps(body, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(body_str.encode() + self.key.encode()).hexdigest()
