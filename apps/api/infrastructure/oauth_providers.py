from __future__ import annotations

import hashlib
import logging
from urllib.parse import urlencode

from application.interfaces.broker_oauth import BrokerOAuthProvider
from domain.broker import BrokerOAuthConfig, BrokerTokenResult
from core.config import settings

logger = logging.getLogger(__name__)

FYERS_REDIRECT_URI = settings.fyers_redirect_uri or "https://api.ai.trademetrix.tech/api/v1/brokers/fyers/callback"


class FyersOAuthProvider(BrokerOAuthProvider):
    name = "fyers"

    def build_auth_url(self, config: BrokerOAuthConfig, state: str) -> str:
        params = urlencode({
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "response_type": "code",
            "state": state,
        })
        return f"https://api-t1.fyers.in/api/v3/generate-authcode?{params}"

    async def exchange_code(self, config: BrokerOAuthConfig, secret_key: str, code: str) -> BrokerTokenResult:
        from core.http_client import get_http_client

        client = await get_http_client()
        app_id_hash = hashlib.sha256(f"{config.client_id}:{secret_key}".encode()).hexdigest()
        resp = await client.post(
            "https://api-t1.fyers.in/api/v3/validate-authcode",
            json={
                "grant_type": "authorization_code",
                "appIdHash": app_id_hash,
                "code": code,
            },
        )
        data = resp.json()
        if data.get("s") != "ok":
            msg = data.get("message", data.get("errmsg", "unknown"))
            raise ValueError(f"Fyers auth failed: {msg}")
        return BrokerTokenResult(access_token=data["access_token"])


class DhanOAuthProvider(BrokerOAuthProvider):
    name = "dhan"

    def build_auth_url(self, config: BrokerOAuthConfig, state: str) -> str:
        params = urlencode({
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "response_type": "code",
            "state": state,
        })
        return f"https://api.dhan.co/v2/oauth/authorize?{params}"

    async def exchange_code(self, config: BrokerOAuthConfig, secret_key: str, code: str) -> BrokerTokenResult:
        from core.http_client import get_http_client

        client = await get_http_client()
        resp = await client.post(
            "https://api.dhan.co/v2/oauth/token",
            data={
                "client_id": config.client_id,
                "client_secret": secret_key,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": config.redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = resp.json()
        if resp.status_code != 200 or not data.get("access_token"):
            msg = data.get("message", data.get("error_description", "unknown"))
            raise ValueError(f"Dhan auth failed: {msg}")
        return BrokerTokenResult(access_token=data["access_token"])


class UpstoxOAuthProvider(BrokerOAuthProvider):
    name = "upstox"

    def build_auth_url(self, config: BrokerOAuthConfig, state: str) -> str:
        params = urlencode({
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "response_type": "code",
            "state": state,
        })
        return f"https://api.upstox.com/v2/login/authorization/dialog?{params}"

    async def exchange_code(self, config: BrokerOAuthConfig, secret_key: str, code: str) -> BrokerTokenResult:
        from core.http_client import get_http_client

        client = await get_http_client()
        resp = await client.post(
            "https://api.upstox.com/v2/login/authorization/token",
            data={
                "code": code,
                "client_id": config.client_id,
                "client_secret": secret_key,
                "redirect_uri": config.redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = resp.json()
        if resp.status_code != 200 or not data.get("access_token"):
            msg = data.get("message", data.get("error_description", "unknown"))
            raise ValueError(f"Upstox auth failed: {msg}")
        return BrokerTokenResult(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
        )


_oauth_providers: dict[str, BrokerOAuthProvider] = {
    "fyers": FyersOAuthProvider(),
    "dhan": DhanOAuthProvider(),
    "upstox": UpstoxOAuthProvider(),
}


def get_oauth_provider(broker: str) -> BrokerOAuthProvider:
    provider = _oauth_providers.get(broker)
    if not provider:
        raise ValueError(f"No OAuth provider for broker: {broker}")
    return provider


def get_redirect_uri(broker: str) -> str:
    redirect_map = {
        "fyers": FYERS_REDIRECT_URI,
        "dhan": settings.dhan_redirect_uri or "https://api.ai.trademetrix.tech/api/v1/brokers/dhan/callback",
        "upstox": settings.upstox_redirect_uri or "https://api.ai.trademetrix.tech/api/v1/brokers/upstox/callback",
    }
    return redirect_map.get(broker, "")
