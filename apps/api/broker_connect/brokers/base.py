"""
Connect-layer broker interface.

This is the *onboarding* interface — how a customer's account gets linked via
OAuth and how we obtain an access token. It is intentionally separate from your
existing trading BaseBroker ABC (place_order / positions / etc.). Wire the token
this produces into your trading adapter.

Contract:
  - authorization_url(state) -> the broker's OWN login URL to redirect the user
    to. The customer authenticates on the broker's domain; we never see the
    password/PIN.
  - exchange(params) -> takes the callback query params and returns a BrokerToken
    (access token + optional refresh token + the broker's user id).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# India Standard Time (no DST)
IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class BrokerToken:
    access_token: str
    refresh_token: str | None
    broker_user_id: str | None
    expires_at: datetime  # tz-aware, UTC
    extra: dict | None = None  # broker-specific extras (e.g. base_url/sid for Kotak Neo)


def default_daily_expiry(hour_ist: int = 6) -> datetime:
    """
    Most Indian broker tokens die at the next daily reset (SEBI 2FA). If the
    broker doesn't hand us an explicit expiry, assume the next HH:00 IST and
    return it as UTC. Conservative by design — a stale token is worse than an
    early reconnect nudge.
    """
    now_ist = datetime.now(IST)
    target = now_ist.replace(hour=hour_ist, minute=0, second=0, microsecond=0)
    if target <= now_ist:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc)


class BrokerConnectUnsupportedError(RuntimeError):
    """Raised by scaffold connectors whose real OAuth/trading API is not wired yet.

    Used for brokers we register (so they're visible / can be enabled later) but
    whose connect flow is intentionally not implemented — no fabricated endpoints.
    """


class BrokerConnector(ABC):
    #: matches the `broker_key` enum value in Postgres
    broker_key: str

    #: brokers that authenticate with API credentials (consumer_key + TOTP + MPIN)
    #: instead of an OAuth redirect. The portal shows a credential-entry form.
    uses_credential_login: bool = False

    @abstractmethod
    async def authorization_url(self, state: str) -> str:
        """Build (and if needed pre-register) the broker login redirect URL."""
        raise NotImplementedError

    @abstractmethod
    async def exchange(self, params: dict) -> BrokerToken:
        """Exchange the callback params for an access token."""
        raise NotImplementedError

    async def login(self, credentials: dict) -> BrokerToken:
        """Credential-based login (consumer_key + TOTP + MPIN style).

        Only implemented by connectors whose broker has no OAuth redirect. The
        default raises so OAuth-only brokers can't be misused here.
        """
        raise BrokerConnectUnsupportedError(
            f"{self.broker_key} does not support credential login."
        )
