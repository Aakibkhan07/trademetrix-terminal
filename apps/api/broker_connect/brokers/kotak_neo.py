"""
Kotak Neo connect connector.

Kotak Neo (Kotak Securities) does NOT use an OAuth redirect login. Its Trade API
authenticates with API credentials instead:

  1. session_init  POST {SESSION_BASE}/oauth2/token
                    Authorization: Basic <base64(consumer_key)>
                    body: {grant_type: "client_credentials"}
                    -> access_token (bearer)
  2. totp_login     POST {SESSION_BASE}/login/1.0/tradeApiLogin
                    Authorization: <consumer_key>
                    body: {mobileNumber, ucc, totp}
                    -> data.token (view token), data.sid
  3. totp_validate  POST {SESSION_BASE}/login/1.0/tradeApiValidate
                    Authorization: <consumer_key>, sid: <sid>, Auth: <view_token>
                    body: {mpin}
                    -> data.token (TRADE token), data.baseUrl

Endpoint paths and hosts are taken from Kotak Neo's official `Kotak-neo-api-v2`
SDK (settings.PROD_URL / urls.SESSION_PROD_BASE_URL). No fabricated endpoints.

The resulting trade token is daily (SEBI 2FA); the portal will nudge a reconnect.
We do NOT persist the MPIN or TOTP — only the trade token + non-secret identifiers
(consumer_key / mobile / ucc / base_url / sid) needed for re-auth.
"""

from __future__ import annotations

import base64

import httpx

from .base import BrokerConnector, BrokerToken, BrokerConnectUnsupportedError, default_daily_expiry

# From Kotak-neo-api-v2 urls.SESSION_PROD_BASE_URL
SESSION_BASE = "https://mnapi.kotaksecurities.com"


class KotakNeoConnector(BrokerConnector):
    broker_key = "kotakneo"
    uses_credential_login = True

    def __init__(self, consumer_key: str):
        # Kotak Neo login takes the consumer_key directly (no app_id/secret/redirect).
        self._consumer_key = consumer_key

    async def authorization_url(self, state: str) -> str:
        raise BrokerConnectUnsupportedError(
            "Kotak Neo uses API-credential login (consumer_key + TOTP + MPIN), not an OAuth redirect."
        )

    async def exchange(self, params: dict):
        raise BrokerConnectUnsupportedError(
            "Kotak Neo has no OAuth callback — use the credential-login flow instead."
        )

    async def login(self, credentials: dict) -> BrokerToken:
        consumer_key = self._consumer_key
        mobile = credentials.get("mobile_number") or credentials.get("mobileNumber")
        ucc = credentials.get("ucc")
        totp = credentials.get("totp")
        mpin = credentials.get("mpin")
        if not (mobile and ucc and totp and mpin):
            raise ValueError("Kotak Neo login requires mobile_number, ucc, totp and mpin.")

        basic = "Basic " + base64.b64encode(consumer_key.encode()).decode()

        async with httpx.AsyncClient(timeout=20) as client:
            # 1. session init
            r1 = await client.post(
                f"{SESSION_BASE}/oauth2/token",
                headers={"Authorization": basic, "Content-Type": "application/json"},
                json={"grant_type": "client_credentials"},
            )
            d1 = r1.json()
            if d1.get("access_token") is None:
                raise ValueError(f"Kotak Neo session init failed: {d1}")

            # 2. TOTP login
            r2 = await client.post(
                f"{SESSION_BASE}/login/1.0/tradeApiLogin",
                headers={"Authorization": consumer_key, "Content-Type": "application/json"},
                json={"mobileNumber": mobile, "ucc": ucc, "totp": totp},
            )
            d2 = r2.json()
            data2 = d2.get("data") or {}
            if not data2.get("token"):
                raise ValueError(f"Kotak Neo TOTP login failed: {d2.get('data') or d2}")
            view_token = data2["token"]
            sid = data2.get("sid")

            # 3. TOTP validate -> trade token
            r3 = await client.post(
                f"{SESSION_BASE}/login/1.0/tradeApiValidate",
                headers={
                    "Authorization": consumer_key,
                    "sid": sid or "",
                    "Auth": view_token,
                    "Content-Type": "application/json",
                },
                json={"mpin": mpin},
            )
            d3 = r3.json()
            data3 = d3.get("data") or {}
            if not data3.get("token"):
                raise ValueError(f"Kotak Neo TOTP validate failed: {d3.get('data') or d3}")
            trade_token = data3["token"]
            base_url = data3.get("baseUrl")

        return BrokerToken(
            access_token=trade_token,
            refresh_token=None,
            broker_user_id=ucc,
            expires_at=default_daily_expiry(),
            extra={
                "base_url": base_url,
                "sid": sid,
                "consumer_key": consumer_key,
                "mobile_number": mobile,
                "ucc": ucc,
            },
        )
