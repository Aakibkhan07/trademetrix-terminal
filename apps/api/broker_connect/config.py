"""
Central config for broker connect. All secrets come from environment.
Nothing here is sent to the client.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Ensure .env is loaded into os.environ for local/dev runs (deployed environments
# already export these via the compose env_file).
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv optional; ignore if unavailable
    pass


def _req(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


@dataclass(frozen=True)
class BrokerAppCreds:
    app_id: str
    secret: str
    redirect_uri: str


@dataclass(frozen=True)
class Settings:
    # Supabase (backend uses the service-role key; RLS-bypassing, server-only)
    supabase_url: str
    supabase_service_key: str

    # Redis — used to hold short-lived OAuth `state` (CSRF) during redirect
    redis_url: str

    # Where the callback route sends the user back to inside the portal
    portal_return_url: str

    # Broker app credentials (only load the ones you use)
    fyers: BrokerAppCreds | None
    dhan: BrokerAppCreds | None
    zerodha: BrokerAppCreds | None
    upstox: BrokerAppCreds | None
    angel: BrokerAppCreds | None
    lemonn: BrokerAppCreds | None
    kotakneo: BrokerAppCreds | None

    # How long an OAuth state token lives in Redis (seconds)
    oauth_state_ttl: int = 600


def _load_broker(prefix: str, default_redirect: str | None) -> BrokerAppCreds | None:
    app_id = os.environ.get(f"{prefix}_APP_ID")
    secret = os.environ.get(f"{prefix}_SECRET")
    # Per-broker REDIRECT_URI wins; otherwise fall back to the global default.
    redirect = os.environ.get(f"{prefix}_REDIRECT_URI") or default_redirect
    if app_id and secret and redirect:
        return BrokerAppCreds(app_id=app_id, secret=secret, redirect_uri=redirect)
    return None


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings(
            supabase_url=_req("SUPABASE_URL"),
            supabase_service_key=_req("SUPABASE_SERVICE_KEY"),
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            portal_return_url=_req("PORTAL_RETURN_URL"),
            fyers=_load_broker("FYERS", os.environ.get("REDIRECT_URI")),
            dhan=_load_broker("DHAN", os.environ.get("REDIRECT_URI")),
            zerodha=_load_broker("ZERODHA", os.environ.get("REDIRECT_URI")),
            upstox=_load_broker("UPSTOX", os.environ.get("REDIRECT_URI")),
            angel=_load_broker("ANGEL", os.environ.get("REDIRECT_URI")),
            lemonn=_load_broker("LEMONN", os.environ.get("REDIRECT_URI")),
            kotakneo=_load_broker("KOTAKNEO", os.environ.get("REDIRECT_URI")),
            oauth_state_ttl=int(os.environ.get("OAUTH_STATE_TTL", "600")),
        )
    return _settings
