"""
Angel One SmartAPI login connector — PUBLISHER LOGIN (the zero-reveal path).

Flow (verified against smartapi.angelone.in docs):
  1. Redirect user to
     https://smartapi.angelone.in/publisher-login?api_key=xxx&redirect_url={REDIRECT}&state={state}
     The user logs in on Angel's page with client code + PIN + TOTP — those
     credentials stay on Angel's side (that's why publisher-login is used instead
     of the credential-based loginByPassword flow).
  2. Angel redirects back with ?auth_token=...&feed_token=...
     auth_token is a JWT (the access token) with the client id encoded in it.

KNOWN QUIRK: Angel has historically not passed `state` back reliably on the
publisher redirect. If your callback receives no `state`, fall back to the
portal session cookie (get_current_user) to identify the user. Handle that in
the callback route for the 'angelone' broker specifically.

Notes:
  - Session valid till ~midnight IST (daily re-login).
  - feed_token (for live market data websocket) also comes back; stash it in
    additional_params if your data layer needs it.
  - api_key here is the SmartAPI key; secret is kept for the order/data layer.
"""

from __future__ import annotations

import base64
import json

from .base import BrokerConnector, BrokerToken, default_daily_expiry
from ..config import BrokerAppCreds

PUBLISHER_LOGIN = "https://smartapi.angelone.in/publisher-login"


def _client_id_from_jwt(jwt: str) -> str | None:
    """Best-effort: decode the JWT payload to read the Angel client code."""
    try:
        payload_b64 = jwt.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # pad
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("sub") or payload.get("clientcode") or payload.get("userId")
    except Exception:
        return None


class AngelConnector(BrokerConnector):
    broker_key = "angelone"

    def __init__(self, creds: BrokerAppCreds):
        self._c = creds

    async def authorization_url(self, state: str) -> str:
        return (
            f"{PUBLISHER_LOGIN}?api_key={self._c.app_id}"
            f"&redirect_url={self._c.redirect_uri}"
            f"&state={state}"
        )

    async def exchange(self, params: dict) -> BrokerToken:
        auth_token = params.get("auth_token")
        if not auth_token:
            raise ValueError("Angel callback missing auth_token.")

        # feed_token (params.get("feed_token")) is available for the data layer.
        return BrokerToken(
            access_token=auth_token,
            refresh_token=params.get("refresh_token"),
            broker_user_id=_client_id_from_jwt(auth_token),
            expires_at=default_daily_expiry(hour_ist=6),
        )
