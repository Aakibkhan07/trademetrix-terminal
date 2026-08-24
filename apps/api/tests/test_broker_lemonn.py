"""Lemonn broker scaffold tests.

Contract: Lemonn (lemonn.co.in) has NO public trading API. The adapter must
register cleanly, accept the connect flow (credential validation), and raise
typed UnsupportedFeatureError for EVERY trading/data capability — never a raw
exception, never fabricated data.
"""

import pytest

from brokers import list_brokers
from brokers.lemonn_adapter import LemonnAdapter
from brokers.sdk.errors import UnsupportedFeatureError
from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType


@pytest.fixture
def adapter():
    return LemonnAdapter()


class TestRegistration:
    def test_registered_in_legacy_registry(self):
        assert "lemonn" in list_brokers()

    def test_sdk_registry_spec(self):
        from brokers.sdk.registry import registry

        spec = registry.spec("lemonn")
        assert spec.display_name == "Lemonn"
        assert spec.auth_type == "credentials"
        assert spec.oauth_available is False
        keys = {f["key"] for f in spec.fields}
        assert {"client_code", "secret_key"} <= keys

    def test_capability_matrix_empty(self):
        from brokers.sdk.capabilities import get_capabilities

        caps = get_capabilities("lemonn")
        assert caps.capabilities == set()
        assert caps.supports_orders is False
        assert caps.supports_positions is False

    def test_execution_layer_capabilities_all_false(self):
        from execution.broker_adapter import BROKER_CAPABILITIES

        caps = BROKER_CAPABILITIES["lemonn"]
        assert not caps.supports_orders
        assert not caps.supports_modify
        assert not caps.supports_cancel


class TestConnectFlow:
    @pytest.mark.asyncio
    async def test_authenticate_missing_credentials_raises_value_error(self, adapter: LemonnAdapter):
        with pytest.raises(ValueError, match="Lemonn requires"):
            await adapter.authenticate({})

    @pytest.mark.asyncio
    async def test_authenticate_with_credentials_raises_typed_error(self, adapter: LemonnAdapter):
        creds = {"client_code": "LC1234", "secret_key": "pw"}
        with pytest.raises(UnsupportedFeatureError, match="authenticate"):
            await adapter.authenticate(creds)

    @pytest.mark.asyncio
    async def test_disconnect_is_safe_noop(self, adapter: LemonnAdapter):
        await adapter.disconnect()


def _order() -> NormalizedOrder:
    return NormalizedOrder(
        symbol="NSE:RELIANCE-EQ",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        product=ProductType.INTRADAY,
        exchange=Exchange.NSE,
    )


class TestTypedUnsupportedSurface:
    @pytest.mark.asyncio
    async def test_place_order(self, adapter: LemonnAdapter):
        with pytest.raises(UnsupportedFeatureError, match="place_order"):
            await adapter.place_order(_order())

    @pytest.mark.asyncio
    async def test_modify_order(self, adapter: LemonnAdapter):
        with pytest.raises(UnsupportedFeatureError, match="modify_order"):
            await adapter.modify_order("oid", {"quantity": 2})

    @pytest.mark.asyncio
    async def test_cancel_order(self, adapter: LemonnAdapter):
        with pytest.raises(UnsupportedFeatureError, match="cancel_order"):
            await adapter.cancel_order("oid")

    @pytest.mark.asyncio
    async def test_get_orderbook(self, adapter: LemonnAdapter):
        with pytest.raises(UnsupportedFeatureError, match="get_orderbook"):
            await adapter.get_orderbook()

    @pytest.mark.asyncio
    async def test_get_positions(self, adapter: LemonnAdapter):
        with pytest.raises(UnsupportedFeatureError, match="get_positions"):
            await adapter.get_positions()

    @pytest.mark.asyncio
    async def test_get_holdings(self, adapter: LemonnAdapter):
        with pytest.raises(UnsupportedFeatureError, match="get_holdings"):
            await adapter.get_holdings()

    @pytest.mark.asyncio
    async def test_get_funds(self, adapter: LemonnAdapter):
        with pytest.raises(UnsupportedFeatureError, match="get_funds"):
            await adapter.get_funds()

    @pytest.mark.asyncio
    async def test_get_quotes(self, adapter: LemonnAdapter):
        with pytest.raises(UnsupportedFeatureError, match="get_quotes"):
            await adapter.get_quotes(["NSE:NIFTY50-INDEX"])

    @pytest.mark.asyncio
    async def test_get_historical(self, adapter: LemonnAdapter):
        with pytest.raises(UnsupportedFeatureError, match="get_historical"):
            await adapter.get_historical("NSE:NIFTY50-INDEX", "1d")

    @pytest.mark.asyncio
    async def test_stream(self, adapter: LemonnAdapter):
        with pytest.raises(UnsupportedFeatureError, match="stream"):
            await adapter.stream(["NSE:NIFTY50-INDEX"], lambda tick: None)

    @pytest.mark.asyncio
    async def test_v2_surface_unsupported_features_stay_typed(self, adapter: LemonnAdapter):
        with pytest.raises(UnsupportedFeatureError):
            await adapter.refresh_token({})
        with pytest.raises(UnsupportedFeatureError):
            await adapter.exit_position("NSE:RELIANCE-EQ", 1)
        with pytest.raises(UnsupportedFeatureError):
            await adapter.get_option_chain("NIFTY")


class TestIntrospection:
    @pytest.mark.asyncio
    async def test_health_contract(self, adapter: LemonnAdapter):
        health = await adapter.health()
        assert health["broker"] == "lemonn"
        assert health["connected"] is False

    def test_capabilities_contract(self, adapter: LemonnAdapter):
        caps = adapter.capabilities()
        assert caps.broker == "lemonn"
        assert caps.capabilities == set()
