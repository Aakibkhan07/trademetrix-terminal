"""
Dhan v2 connect adapter — PARTNER consent flow.

Unlike Fyers' single-redirect OAuth, Dhan onboards many customers via the
Partner program:
  1. generate-consent  (server->Dhan, using partner_id + partner_secret) -> consentId
  2. redirect the user to the consent-login page with that consentId
  3. Dhan redirects back with ?tokenId=...
  4. consume-consent   (server->Dhan) -> accessToken + dhanClientId

VERIFY the exact endpoints/response keys against your Dhan partner dashboard —
Dhan has iterated these paths. This adapter matches the documented partner flow
shape; confirm host + field names for your account.

Because generate-consent is a server call that must happen *before* the redirect,
authorization_url() performs it and stashes the consentId inside the returned
URL. The tokenId that comes back on the callback is all we need to consume it.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from .base import BrokerConnector, BrokerToken, default_daily_expiry
from ..config import BrokerAppCreds

AUTH_BASE = "https://auth.dhan.co"


class DhanConnector(BrokerConnector):
    broker_key = "dhan"

    def __init__(self, creds: BrokerAppCreds):
        # For Dhan, app_id = partner_id, secret = partner_secret
        self._creds = creds

    def _partner_headers(self) -> dict:
        return {
            "partner_id": self._creds.app_id,
            "partner_secret": self._creds.secret,
        }

    async def authorization_url(self, state: str) -> str:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{AUTH_BASE}/partner/generate-consent",
                headers=self._partner_headers(),
            )
            data = resp.json()
            consent_id = data.get("consentId") or data.get("consentAppId")
            if not consent_id:
                raise ValueError(f"Dhan generate-consent failed: {data}")

        # We pass our own `state` back via the redirect_uri so the callback can
        # match it (Dhan echoes the redirect but not arbitrary state).
        return (
            f"{AUTH_BASE}/consent-login"
            f"?consentId={consent_id}"
            f"&state={state}"
        )

    async def exchange(self, params: dict) -> BrokerToken:
        token_id = params.get("tokenId") or params.get("token_id")
        if not token_id:
            raise ValueError("Dhan callback missing tokenId.")

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{AUTH_BASE}/partner/consume-consent",
                headers=self._partner_headers(),
                params={"tokenId": token_id},
            )
            data = resp.json()
            access_token = data.get("accessToken") or data.get("access_token")
            if not access_token:
                raise ValueError(f"Dhan consume-consent failed: {data}")

            broker_user_id = data.get("dhanClientId") or data.get("dhan_client_id")

            # Dhan may return an explicit expiry; use it if present.
            expires_at = default_daily_expiry(hour_ist=6)
            raw_exp = data.get("expiryTime") or data.get("expiry")
            if raw_exp:
                try:
                    expires_at = datetime.fromisoformat(
                        str(raw_exp).replace("Z", "+00:00")
                    ).astimezone(timezone.utc)
                except Exception:
                    pass

        return BrokerToken(
            access_token=access_token,
            refresh_token=None,
            broker_user_id=broker_user_id,
            expires_at=expires_at,
        )
