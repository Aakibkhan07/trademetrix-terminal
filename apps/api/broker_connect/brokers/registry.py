"""
Broker registry — maps a broker_key to a configured LOGIN connector.
All five major Indian brokers use redirect/publisher login = zero credential
reveal. Add 5paisa / Kotak / ICICI etc. here with the same pattern.
"""

from __future__ import annotations

from .base import BrokerConnector
from .fyers import FyersConnector
from .dhan import DhanConnector
from .zerodha import ZerodhaConnector
from .upstox import UpstoxConnector
from .angel import AngelConnector
from .lemonn import LemonnConnector
from .kotak_neo import KotakNeoConnector
from ..config import get_settings


class UnknownBrokerError(ValueError):
    pass


class BrokerNotConfiguredError(RuntimeError):
    pass


# broker_key -> (Settings attribute, Connector class)
_REGISTRY = {
    "fyers": ("fyers", FyersConnector),
    "dhan": ("dhan", DhanConnector),
    "zerodha": ("zerodha", ZerodhaConnector),
    "upstox": ("upstox", UpstoxConnector),
    "angelone": ("angel", AngelConnector),
    "lemonn": ("lemonn", LemonnConnector),
    "kotakneo": ("kotakneo", KotakNeoConnector),
}

# Brokers we register but whose connect flow is scaffolded (no live OAuth yet).
# Surfaced by /available as `coming_soon` so the portal can show them disabled.
COMING_SOON_BROKERS = ["lemonn"]

# Brokers that authenticate with API credentials (consumer_key + TOTP + MPIN) instead
# of an OAuth redirect. The portal shows a credential-entry form for these.
CREDENTIAL_LOGIN_BROKERS = ["kotakneo"]


def get_connector(broker_key: str) -> BrokerConnector:
    key = broker_key.lower().strip()
    if key not in _REGISTRY:
        raise UnknownBrokerError(f"No connector for broker '{broker_key}'.")

    attr, cls = _REGISTRY[key]
    creds = getattr(get_settings(), attr)
    if not creds:
        raise BrokerNotConfiguredError(f"{key} app credentials not set in env.")
    return cls(creds)


def configured_brokers() -> list[str]:
    """Which brokers are actually wired up right now (creds present in env)."""
    s = get_settings()
    return [key for key, (attr, _) in _REGISTRY.items() if getattr(s, attr)]


def get_credential_connector(broker_key: str, consumer_key: str) -> BrokerConnector:
    """Connector for a credential-login broker (e.g. Kotak Neo). The consumer_key
    is supplied by the user at connect time, so no env app creds are required."""
    key = broker_key.lower().strip()
    if key not in CREDENTIAL_LOGIN_BROKERS:
        raise BrokerConnectUnsupportedError(f"Broker '{broker_key}' does not support credential login.")
    # Currently only Kotak Neo uses this path.
    return KotakNeoConnector(consumer_key)
