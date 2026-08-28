"""
Kotak Neo connect scaffold.

Kotak Neo (kotakneo.com / Kotak Securities) does expose a trading API, but this
module wires it ONLY as a connect-only scaffold: the OAuth login flow is not
implemented here yet (no fabricated authorize/token endpoints). The broker is
registered so it is visible and can be enabled later by implementing
`authorization_url` / `exchange` against Kotak Neo's real OAuth endpoints and
flipping this connector to a working one. Trading via this broker stays
disabled (paper-only / fail-closed) until then.
"""

from __future__ import annotations

from .base import BrokerConnector, BrokerConnectUnsupportedError
from ..config import BrokerAppCreds

_PENDING = (
    "Kotak Neo connect flow is scaffolded (not yet wired to Kotak Neo's OAuth "
    "endpoints). Set the app credentials and implement authorization_url/exchange "
    "against Kotak Neo's real API to enable linking."
)


class KotakNeoConnector(BrokerConnector):
    broker_key = "kotakneo"

    def __init__(self, creds: BrokerAppCreds):
        self._creds = creds

    async def authorization_url(self, state: str) -> str:
        raise BrokerConnectUnsupportedError(_PENDING)

    async def exchange(self, params: dict):
        raise BrokerConnectUnsupportedError(_PENDING)
