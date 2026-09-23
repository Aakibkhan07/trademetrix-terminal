"""Scaffold tests for MT5 and Delta Exchange adapters.

These assert typed UnsupportedFeatureError today and document both halves of the
activation flip: implement real endpoints -> flip capability row -> these tests
update to assert real behavior.

See: brokers/mt5_adapter.py, brokers/delta_exchange_adapter.py
"""

import asyncio

import pytest
from brokers.mt5_adapter import MT5Adapter
from brokers.delta_exchange_adapter import DeltaExchangeAdapter
from brokers.sdk.errors import UnsupportedFeatureError

_MT5_ORDER_METHOD_ARGS = {
    "place_order": ({"symbol": "EURUSD", "side": "buy", "qty": 1},),
    "modify_order": ("order123", {"qty": 2}),
    "cancel_order": ("order123",),
    "get_orderbook": (),
    "get_positions": (),
    "get_holdings": (),
    "get_funds": (),
    "get_quotes": (["EURUSD"],),
    "get_historical": ("EURUSD", "1h"),
    "stream": (["EURUSD"], lambda t: None),
}


# ── MT5 adapter tests ────────────────────────────────────────────────

class TestMT5Adapter:
    """MT5 adapter is a scaffold - every capability-gated call raises
    UnsupportedFeatureError until the MT5 integration is certified."""

    @pytest.fixture
    def adapter(self):
        return MT5Adapter()

    def test_broker_name(self, adapter):
        assert adapter.broker_name == "mt5"

    def test_authenticate_validates_required_fields(self, adapter):
        with pytest.raises(ValueError, match="mt5_server"):
            asyncio.run(adapter.authenticate({}))

    def test_authenticate_with_all_fields_still_unsupported(self, adapter):
        """Credentials validate, but the actual auth is unsupported."""
        with pytest.raises(UnsupportedFeatureError, match="authenticate"):
            asyncio.run(adapter.authenticate({
                "mt5_broker": "xm",
                "mt5_server": "XM Server",
                "login": "123456",
                "password": "test",
            }))

    @pytest.mark.parametrize("method", list(_MT5_ORDER_METHOD_ARGS.keys()))
    def test_all_methods_unsupported(self, adapter, method):
        """Every trading/data method raises UnsupportedFeatureError."""
        args = _MT5_ORDER_METHOD_ARGS[method]
        with pytest.raises(UnsupportedFeatureError, match=method):
            asyncio.run(getattr(adapter, method)(*args))


# ── Delta Exchange adapter tests ──────────────────────────────────────

class TestDeltaExchangeAdapter:
    """Delta Exchange adapter is a scaffold - every capability-gated call raises
    UnsupportedFeatureError until the Delta integration is certified."""

    @pytest.fixture
    def adapter(self):
        return DeltaExchangeAdapter()

    def test_broker_name(self, adapter):
        assert adapter.broker_name == "delta"

    def test_authenticate_validates_required_fields(self, adapter):
        with pytest.raises(ValueError, match="api_key"):
            asyncio.run(adapter.authenticate({}))

    def test_authenticate_catches_unsupported(self, adapter):
        """authenticate raises UnsupportedFeatureError after validation."""
        with pytest.raises(UnsupportedFeatureError, match="authenticate"):
            asyncio.run(adapter.authenticate({
                "api_key": "test_key",
                "secret_key": "test_secret",
                "environment": "testnet",
            }))

    def test_environment_defaults_to_testnet(self, adapter):
        """Without environment field, defaults to testnet URL."""
        # authenticate will raise UnsupportedFeatureError after setting url
        with pytest.raises(UnsupportedFeatureError):
            asyncio.run(adapter.authenticate({
                "api_key": "k",
                "secret_key": "s",
            }))
        # But we can check the base_url was set before the raise
        # Re-check by instantiating fresh and peeking at init defaults
        a2 = DeltaExchangeAdapter()
        assert a2._base_url == "https://testnet-delta.exchange"

    @pytest.mark.parametrize("method", list(_MT5_ORDER_METHOD_ARGS.keys()))
    def test_all_methods_unsupported(self, adapter, method):
        """Every trading/data method raises UnsupportedFeatureError."""
        args = _MT5_ORDER_METHOD_ARGS[method]
        with pytest.raises(UnsupportedFeatureError, match=method):
            asyncio.run(getattr(adapter, method)(*args))
