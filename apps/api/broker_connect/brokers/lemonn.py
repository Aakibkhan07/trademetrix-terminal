"""
Lemonn connect scaffold.

Lemonn (lemonn.co.in — NU Investors Technologies Pvt Ltd, SEBI INZ000304837)
publishes NO public trading API today (no developer portal, no API keys; their
algo offering runs hosted on their own platform only). This connector is a
placeholder so the broker is registered and visible; the connect flow is
intentionally NOT implemented (no fabricated endpoints). Mirrors the platform's
existing lemonn adapter honesty contract — every runtime call stays disabled
until Lemonn ships an API.
"""

from __future__ import annotations

from .base import BrokerConnector, BrokerConnectUnsupportedError
from ..config import BrokerAppCreds

_PENDING = (
    "Lemonn (lemonn.co.in) has no public broker API yet — the connect flow is "
    "scaffolded and disabled. Track https://lemonn.co.in for API availability."
)


class LemonnConnector(BrokerConnector):
    broker_key = "lemonn"

    def __init__(self, creds: BrokerAppCreds):
        self._creds = creds

    async def authorization_url(self, state: str) -> str:
        raise BrokerConnectUnsupportedError(_PENDING)

    async def exchange(self, params: dict):
        raise BrokerConnectUnsupportedError(_PENDING)
