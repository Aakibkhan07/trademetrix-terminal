"""
Fyers API v3 connect adapter.

Flow:
  1. Redirect user to generate-authcode (they log in on Fyers' domain).
  2. Fyers redirects back to our callback with ?auth_code=...&state=...
  3. We POST that code + appIdHash to validate-authcode -> access/refresh token.
  4. We hit /profile to grab the fy_id (the broker's user id).

VERIFY against your working Fyers v3 adapter:
  - Base host: api-t1.fyers.in
  - Header format used by your trading calls: "{app_id}:{access_token}"
"""

from __future__ import annotations

import hashlib

import httpx

from .base import BrokerConnector, BrokerToken, default_daily_expiry
from ..config import BrokerAppCreds

AUTH_BASE = "https://api-t1.fyers.in/api/v3"


class FyersConnector(BrokerConnector):
    broker_key = "fyers"

    def __init__(self, creds: BrokerAppCreds):
        self._creds = creds

    async def authorization_url(self, state: str) -> str:
        # Fyers builds its login page from these query params. No secret here.
        return (
            f"{AUTH_BASE}/generate-authcode"
            f"?client_id={self._creds.app_id}"
            f"&redirect_uri={self._creds.redirect_uri}"
            f"&response_type=code"
            f"&state={state}"
        )

    async def exchange(self, params: dict) -> BrokerToken:
        auth_code = params.get("auth_code") or params.get("code")
        if not auth_code:
            raise ValueError("Fyers callback missing auth_code.")

        app_id_hash = hashlib.sha256(
            f"{self._creds.app_id}:{self._creds.secret}".encode()
        ).hexdigest()

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{AUTH_BASE}/validate-authcode",
                json={
                    "grant_type": "authorization_code",
                    "appIdHash": app_id_hash,
                    "code": auth_code,
                },
            )
            data = resp.json()
            if data.get("s") != "ok" or not data.get("access_token"):
                raise ValueError(f"Fyers token exchange failed: {data}")

            access_token = data["access_token"]
            refresh_token = data.get("refresh_token")

            # fetch fy_id
            broker_user_id = None
            try:
                prof = await client.get(
                    f"{AUTH_BASE}/profile",
                    headers={"Authorization": f"{self._creds.app_id}:{access_token}"},
                )
                pj = prof.json()
                broker_user_id = (pj.get("data") or {}).get("fy_id")
            except Exception:
                pass  # profile is best-effort; token is what matters

        return BrokerToken(
            access_token=access_token,
            refresh_token=refresh_token,
            broker_user_id=broker_user_id,
            expires_at=default_daily_expiry(hour_ist=6),
        )
