"""
Zerodha Kite Connect login connector.

Flow (verified against kite.trade/docs/connect/v3):
  1. Redirect user to https://kite.zerodha.com/connect/login?v=3&api_key=xxx
     (redirect_uri is fixed in the Kite developer console, NOT in the URL).
  2. Kite redirects back to that registered URL with ?request_token=...
     We carry our own `state` back via the `redirect_params` param.
  3. POST request_token + checksum (SHA-256 of api_key+request_token+api_secret)
     to https://api.kite.trade/session/token -> access_token + user_id.

Notes:
  - One Kite Connect app (api_key/secret) serves many users — each logs in with
    their own Zerodha creds and gets their own access_token. Requires an ACTIVE
    Kite Connect subscription (paid, flat per app — verify current price).
  - access_token expires daily ~06:00 IST. Header for API calls:
    Authorization: token {api_key}:{access_token}
  - The registered redirect URI in the console must be your /api/broker/callback.
"""

from __future__ import annotations

import hashlib

import httpx

from .base import BrokerConnector, BrokerToken, default_daily_expiry
from ..config import BrokerAppCreds

LOGIN = "https://kite.zerodha.com/connect/login"
API = "https://api.kite.trade"


class ZerodhaConnector(BrokerConnector):
    broker_key = "zerodha"

    def __init__(self, creds: BrokerAppCreds):
        self._c = creds  # app_id = api_key, secret = api_secret

    async def authorization_url(self, state: str) -> str:
        # carry our state back via redirect_params (Kite appends it to the redirect)
        return f"{LOGIN}?v=3&api_key={self._c.app_id}&redirect_params=state%3D{state}"

    async def exchange(self, params: dict) -> BrokerToken:
        request_token = params.get("request_token")
        if not request_token:
            raise ValueError("Zerodha callback missing request_token.")

        checksum = hashlib.sha256(
            f"{self._c.app_id}{request_token}{self._c.secret}".encode()
        ).hexdigest()

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{API}/session/token",
                headers={"X-Kite-Version": "3"},
                data={
                    "api_key": self._c.app_id,
                    "request_token": request_token,
                    "checksum": checksum,
                },
            )
            body = resp.json()
            if body.get("status") != "success" or not body.get("data", {}).get("access_token"):
                raise ValueError(f"Zerodha token exchange failed: {body}")
            data = body["data"]

        return BrokerToken(
            access_token=data["access_token"],
            refresh_token=None,  # Kite has no refresh token; daily re-login
            broker_user_id=data.get("user_id"),
            expires_at=default_daily_expiry(hour_ist=6),
        )
