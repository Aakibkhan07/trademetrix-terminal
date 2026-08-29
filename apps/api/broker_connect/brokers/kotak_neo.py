"""
Kotak Neo connect connector.

Kotak Neo (Kotak Securities) Trade API authenticates with API credentials
(NO OAuth redirect). The verified flow (from Kotak-Neo/Kotak-neo-api-v2 SDK) is:

  1. totp_login     POST {SESSION_BASE}/api/1.0/login/v6/totp/login
                   Authorization: <consumer_key>
                   neo-fin-key: neotradeapi
                   body: {mobileNumber, ucc, totp}
                   -> data.token (VIEW token), data.sid (view sid)
  2. totp_validate  POST {SESSION_BASE}/api/1.0/login/v6/totp/validate
                   Authorization: <consumer_key>
                   sid: <view sid>
                   Auth: <view token>
                   neo-fin-key: neotradeapi
                   body: {mpin}
                   -> data.token (TRADE/EDIT token), data.sid (edit sid),
                      data.hsServerId (server id), data.baseUrl (trading base url)

The TRADE token + edit sid + server id + base url are what the execution
adapter (brokers/kotakneo_adapter.py) needs for every subsequent call.

The consumer_key ("API access token") is generated in the Neo app:
More -> Trade API -> Generate application -> copy token. It is passed in the
Authorization header for login AND quotes.

We do NOT persist the MPIN or TOTP — only the trade token + non-secret
identifiers needed to call the trading endpoints until the next daily reset.
"""

from __future__ import annotations

import httpx

from .base import BrokerConnector, BrokerToken, BrokerConnectUnsupportedError, default_daily_expiry

# From Kotak-neo-api-v2 urls.SESSION_PROD_BASE_URL / PROD_BASE_URL
SESSION_BASE = "https://mnapi.kotaksecurities.com"
# neo_api_client.neo_utility.NeoUtility.get_neo_fin_key() -> "neotradeapi" for prod
NEO_FIN_KEY = "neotradeapi"


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

        async with httpx.AsyncClient(timeout=20) as client:
            # 1. TOTP login -> view token
            r1 = await client.post(
                f"{SESSION_BASE}/api/1.0/login/v6/totp/login",
                headers={
                    "Authorization": consumer_key,
                    "neo-fin-key": NEO_FIN_KEY,
                    "Content-Type": "application/json",
                },
                json={"mobileNumber": mobile, "ucc": ucc, "totp": totp},
            )
            d1 = r1.json()
            data1 = d1.get("data") or {}
            if not data1.get("token"):
                raise ValueError(
                    f"Kotak Neo TOTP login failed: {d1.get('message') or d1.get('emsg') or d1}"
                )
            view_token = data1["token"]
            view_sid = data1.get("sid")

            # 2. TOTP validate (MPIN) -> trade token + session routing
            r2 = await client.post(
                f"{SESSION_BASE}/api/1.0/login/v6/totp/validate",
                headers={
                    "Authorization": consumer_key,
                    "sid": view_sid or "",
                    "Auth": view_token,
                    "neo-fin-key": NEO_FIN_KEY,
                    "Content-Type": "application/json",
                },
                json={"mpin": mpin},
            )
            d2 = r2.json()
            data2 = d2.get("data") or {}
            if not data2.get("token"):
                raise ValueError(
                    f"Kotak Neo TOTP validate failed: {d2.get('message') or d2.get('emsg') or d2}"
                )
            trade_token = data2["token"]
            edit_sid = data2.get("sid") or view_sid
            server_id = data2.get("hsServerId")
            base_url = data2.get("baseUrl")

        return BrokerToken(
            access_token=trade_token,
            refresh_token=None,
            broker_user_id=ucc,
            expires_at=default_daily_expiry(),
            extra={
                "base_url": base_url,
                "sid": edit_sid,
                "serverId": server_id,
                "api_key": consumer_key,
                "consumer_key": consumer_key,
                "mobile_number": mobile,
                "ucc": ucc,
            },
        )
