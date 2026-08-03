"""Fyers auth provider + observability glue (SDK v2 Phase 3/4).

``FyersAuthProvider`` implements :class:`AuthProvider` for Fyers' token model
(client_id + access_token, OAuth consent flow; no silent refresh).  The
credential refresh path drops through to re-auth when the existing token cannot
be refreshed — which is exactly Fyers' real behavior.

Live observability glue lives *here*, not in the shared SDK:
:func:`register_fyers_observability` wires the live transport snapshot into the
default broker metrics registry and the default health service so the
Phase 4 endpoints report real Fyers numbers when a token is present.
"""
from __future__ import annotations

import time
from typing import Any

from brokers.sdk.auth import AuthProvider, ReAuthRequiredError, Token
from brokers.sdk.metrics import default_broker_metrics
from brokers.sdk.health import default_health_service


class FyersTokenProvider(AuthProvider):
    """Issuer access-token provider for Fyers.

    ``login`` accepts either ``{access_token, ...}`` (API-key path) or the raw
    Fyers session dict with ``client_id``/``access_token``. ``refresh`` has no
    silent route for Fyers, so it raises ``ReAuthRequiredError`` — the managed
    session then transitions the auth state to REAUTH_REQUIRED.
    """

    broker = "fyers"

    async def login(self, credentials: dict[str, Any]) -> Token:
        client_id = credentials.get("client_id") or credentials.get("api_key") or ""
        access_token = credentials.get("access_token") or credentials.get("token") or ""
        if not client_id or not access_token:
            raise ReAuthRequiredError(
                "Fyers login requires client_id + access_token (authorize via the OAuth link)"
            )
        return Token(
            access_token=access_token,
            refresh_token="",
            expires_at=credentials.get("expires_at"),
            token_type="Bearer",
            issuer="access_token",
            client_id=client_id,
            metadata={"credentials": credentials},
        )

    async def refresh(self, token: Token) -> Token:
        raise ReAuthRequiredError("Fyers provides no silent token refresh — re-consent required")


def _fyers_transport_resolver():
    try:
        from brokers.fyers_http import _transports

        # pick the most recently active transport (largest stats ledger)
        best = None
        for tr in _transports.values():
            if tr._stats and (best is None or len(tr._stats) > len(best._stats)):
                best = tr
        return best
    except Exception:
        return None


def register_fyers_observability() -> None:
    """Register Fyers' live transport into the default metrics + health services.

    Idempotent: re-registration replaces the source (registry keys by broker).
    """
    from brokers.sdk.observability import TransportMetricSource

    source = TransportMetricSource("fyers", _fyers_transport_resolver)
    try:
        default_broker_metrics.register("fyers", source)
    except Exception:
        pass
    try:
        default_health_service.report_rest_health("fyers", healthy=True, detail="transport-registered")
        default_health_service.report_auth("fyers", ok=True)
    except Exception:
        pass


def report_fyers_session_health(ok: bool, *, error: str = "") -> None:
    default_health_service.report_auth("fyers", ok=ok, error=error)