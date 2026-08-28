"""
Upstox API v2 login connector (standard OAuth 2.0 authorization code).

Flow (verified against upstox.com/developer/api-documentation/authentication):
  1. Redirect user to
     https://api.upstox.com/v2/login/authorization/dialog
       ?response_type=code&client_id={API_KEY}&redirect_uri={REDIRECT}&state={state}
  2. Upstox redirects back with ?code=...&state=...
  3. POST (form-encoded) to
     https://api.upstox.com/v2/login/authorization/token
       code, client_id, client_secret, redirect_uri, grant_type=authorization_code
     -> access_token (+ user profile fields).

Notes:
  - client_id = API Key, client_secret = API Secret (NOT the customer's UCC).
  - One app serves many users. Token expires daily (~03:30 IST). Auth code is
    single-use. redirect_uri must EXACTLY match the registered one.
"""

from __future__ import annotations

import httpx

from .base import BrokerConnector, BrokerToken, default_daily_expiry
from ..config import BrokerAppCreds

AUTH = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN = "https://api.upstox.com/v2/login/authorization/token"


class UpstoxConnector(BrokerConnector):
    broker_key = "upstox"

    def __init__(self, creds: BrokerAppCreds):
        self._c = creds

    async def authorization_url(self, state: str) -> str:
        return (
            f"{AUTH}?response_type=code"
            f"&client_id={self._c.app_id}"
            f"&redirect_uri={self._c.redirect_uri}"
            f"&state={state}"
        )

    async def exchange(self, params: dict) -> BrokerToken:
        code = params.get("code")
        if not code:
            raise ValueError("Upstox callback missing code.")

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                TOKEN,
                headers={
                    "accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "code": code,
                    "client_id": self._c.app_id,
                    "client_secret": self._c.secret,
                    "redirect_uri": self._c.redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            data = resp.json()
            if not data.get("access_token"):
                raise ValueError(f"Upstox token exchange failed: {data}")

        return BrokerToken(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            broker_user_id=data.get("user_id") or data.get("client_id"),
            expires_at=default_daily_expiry(hour_ist=3),
        )
