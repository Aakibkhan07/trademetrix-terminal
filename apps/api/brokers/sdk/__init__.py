"""Unified Broker SDK v2 — shared contracts for broker-agnostic trading.

Phase 1: typed errors, capability system, broker registry, interface.
Later phases add transport, auth, websocket, health, audit layers (see
docs/evolution/BROKER_SDK_V2.md for the roadmap).
"""

from brokers.sdk.capabilities import BROKER_CAPABILITY_MATRIX, BrokerCapabilities, CapabilityFlag, get_capabilities
from brokers.sdk.errors import (
    BrokerAuthError,
    BrokerConnectionError,
    BrokerDisconnectedError,
    BrokerError,
    BrokerErrorInfo,
    BrokerRateLimitError,
    BrokerServerError,
    BrokerTimeoutError,
    BrokerValidationError,
    BrokerWAFError,
    MarginInsufficientError,
    OrderRejectedError,
    UnsupportedFeatureError,
    parse_retry_after,
    translate_broker_error,
    translate_exception,
)
from brokers.sdk.interface import BrokerAdapterBase, BrokerPort
from brokers.sdk.registry import BrokerRegistry, BrokerSpec, get_registry, registry

__all__ = [
    # capabilities
    "BrokerCapabilities",
    "CapabilityFlag",
    "BROKER_CAPABILITY_MATRIX",
    "get_capabilities",
    # errors
    "BrokerError",
    "BrokerErrorInfo",
    "BrokerAuthError",
    "BrokerRateLimitError",
    "BrokerWAFError",
    "BrokerConnectionError",
    "BrokerTimeoutError",
    "BrokerDisconnectedError",
    "BrokerValidationError",
    "OrderRejectedError",
    "MarginInsufficientError",
    "BrokerServerError",
    "UnsupportedFeatureError",
    "parse_retry_after",
    "translate_broker_error",
    "translate_exception",
    # interface
    "BrokerPort",
    "BrokerAdapterBase",
    # registry
    "BrokerRegistry",
    "BrokerSpec",
    "registry",
    "get_registry",
]
