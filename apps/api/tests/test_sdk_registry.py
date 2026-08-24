"""Unified Broker SDK — registry + factory + metadata facade tests."""

import pytest

from brokers import create_broker, get_broker, list_brokers
from brokers.circuit_breaker_broker import CircuitBreakerBroker
from brokers.fyers_adapter import FyersAdapter
from brokers.registry import get_broker_metadata
from brokers.sdk.capabilities import CapabilityFlag
from brokers.sdk.errors import UnsupportedFeatureError
from brokers.sdk.registry import BrokerRegistry, BrokerSpec


class TestBrokerRegistry:
    def test_register_and_lookup(self):
        r = BrokerRegistry()
        r.register(BrokerSpec(name="alpha", display_name="Alpha", adapter_class=FyersAdapter))
        assert "alpha" in r
        assert r.spec("alpha").display_name == "Alpha"
        assert r.names() == ["alpha"]

    def test_register_keyword_form(self):
        r = BrokerRegistry()
        r.register(name="beta", adapter_class=FyersAdapter, capabilities=None)
        assert r.spec("beta").adapter_class is FyersAdapter

    def test_register_requires_name(self):
        r = BrokerRegistry()
        with pytest.raises(ValueError):
            r.register(adapter_class=FyersAdapter)

    def test_unknown_broker_raises(self):
        r = BrokerRegistry()
        with pytest.raises(ValueError):
            r.spec("nope")

    def test_unregister(self):
        r = BrokerRegistry()
        r.register(name="gamma", adapter_class=FyersAdapter)
        r.unregister("gamma")
        assert "gamma" not in r

    def test_default_capabilities_attached(self):
        r = BrokerRegistry()
        spec = r.register(name="delta", adapter_class=FyersAdapter)
        assert spec.capabilities is not None
        assert spec.capability_flags()

    def test_create_returns_circuit_breaker_wrapped(self):
        r = BrokerRegistry()
        r.register(name="epsilon", adapter_class=FyersAdapter)
        adapter = r.create("epsilon")
        assert isinstance(adapter, CircuitBreakerBroker)
        assert adapter._breaker_name == "broker_epsilon"

    def test_create_raw_adapter(self):
        r = BrokerRegistry()
        r.register(name="zeta", adapter_class=FyersAdapter)
        adapter = r.create("zeta", wrap_circuit_breaker=False)
        assert isinstance(adapter, FyersAdapter)

    def test_create_requires_adapter_class(self):
        r = BrokerRegistry()
        r.register(name="eta", adapter_class=None)
        with pytest.raises(ValueError):
            r.create("eta")

    def test_capabilities_gate(self):
        r = BrokerRegistry()
        r.register(name="theta", adapter_class=FyersAdapter)
        assert r.supports("theta", CapabilityFlag.ORDERS)
        r.require("theta", CapabilityFlag.ORDERS)
        with pytest.raises(UnsupportedFeatureError):
            r.require("theta", CapabilityFlag.GREEKS)

    def test_require_unknown_broker_raises_value_error(self):
        r = BrokerRegistry()
        with pytest.raises(ValueError):
            r.require("ghost", CapabilityFlag.ORDERS)

    def test_metadata_payload(self):
        r = BrokerRegistry()
        r.register(
            BrokerSpec(
                name="iota",
                display_name="Iota Broker",
                auth_type="oauth",
                fields=[{"key": "client_id", "label": "App ID", "required": True}],
                instructions="Step 1",
            )
        )
        meta = r.metadata("iota")
        assert meta["broker"] == "iota"
        assert meta["display_name"] == "Iota Broker"
        assert meta["auth_type"] == "oauth"
        assert meta["fields"] == [{"key": "client_id", "label": "App ID", "required": True}]
        assert meta["instructions"] == "Step 1"
        all_meta = r.metadata()
        assert isinstance(all_meta, list)
        assert len(all_meta) == 1


class TestProductionRegistry:
    def test_all_legacy_brokers_registered(self):
        for name in ("fyers", "dhan", "zerodha", "angelone", "upstox", "fivepaisa",
                     "aliceblue", "finvasia", "flattrade", "kotakneo", "groww", "lemonn"):
            assert name in list_brokers(), name
            assert get_broker(name)

    def test_metadata_facade_unchanged_shape(self):
        meta = get_broker_metadata()
        assert isinstance(meta, list)
        by_name = {m["broker"]: m for m in meta}
        assert by_name["fyers"]["display_name"] == "Fyers"
        assert by_name["angelone"]["auth_type"] == "credentials"
        assert by_name["kotakneo"]["auth_type"] == "api_key_secret"
        single = get_broker_metadata("dhan")
        assert single["broker"] == "dhan"
        assert single["oauth_available"] is True

    def test_metadata_facade_unknown_raises(self):
        with pytest.raises(ValueError):
            get_broker_metadata("not_a_broker")

    def test_factory_contract_preserved(self):
        adapter = create_broker("fyers")
        assert isinstance(adapter, CircuitBreakerBroker)
        assert adapter._breaker_name == "broker_fyers"

    def test_factory_unknown_raises(self):
        with pytest.raises(ValueError):
            create_broker("not_a_broker")
