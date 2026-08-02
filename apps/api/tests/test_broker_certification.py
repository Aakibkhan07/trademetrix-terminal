"""Broker certification suite (Level A interface cert for every registered broker,
Level B behavioral flow with a canned transport for Fyers)."""

import pytest

from brokers.sdk.capabilities import CapabilityFlag
from brokers.sdk.certification import (
    BEHAVIORAL_STEPS,
    V2_METHODS,
    certify_behavior,
    certify_interface,
)
from brokers.sdk.registry import registry

CERTIFIED_BROKERS = sorted(registry.names())


class TestInterfaceCertification:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("broker", CERTIFIED_BROKERS)
    async def test_all_brokers_expose_full_v2_surface(self, broker):
        adapter = registry.create(broker, wrap_circuit_breaker=False)
        report = await certify_interface(adapter)
        report_dict = report.to_dict()
        assert report.passed, f"{broker} NOT CERTIFIED: {report_dict}"
        assert len([c for c in report.checks if c["check"].startswith("surface:")]) == len(V2_METHODS)

    @pytest.mark.asyncio
    async def test_unsupported_feature_is_typed_not_attribute_error(self):
        from brokers.sdk.errors import UnsupportedFeatureError

        for broker in CERTIFIED_BROKERS:
            adapter = registry.create(broker, wrap_circuit_breaker=False)
            caps = adapter.capabilities()
            if not caps.supports(CapabilityFlag.OPTION_CHAIN):
                with pytest.raises(UnsupportedFeatureError):
                    await adapter.get_option_chain("NIFTY")
            if not caps.supports(CapabilityFlag.MARGIN_CALCULATOR):
                with pytest.raises(UnsupportedFeatureError):
                    caps.require(CapabilityFlag.MARGIN_CALCULATOR)

    @pytest.mark.asyncio
    async def test_health_and_capabilities_contract(self):
        for broker in CERTIFIED_BROKERS:
            adapter = registry.create(broker, wrap_circuit_breaker=False)
            health = await adapter.health()
            assert isinstance(health, dict)
            assert health.get("broker") == broker
            caps = adapter.capabilities()
            assert caps.broker == broker
            assert isinstance(caps.capabilities, set)

    def test_capability_gaps_recorded_but_typed(self):
        from brokers.sdk.certification import CertificationReport

        report = CertificationReport(broker="fyers")
        report.add("surface:get_option_chain", True)
        report.capability_gaps.append("fyers:option_chain")
        assert report.passed is True
        assert report.capability_gaps == ["fyers:option_chain"]


class TestBehavioralCertification:
    def test_canonical_flow_steps(self):
        assert BEHAVIORAL_STEPS == [
            "authenticate", "funds", "holdings", "positions", "orders",
            "place", "modify", "cancel", "quotes", "historical", "stream", "disconnect",
        ]

    @pytest.mark.asyncio
    async def test_fyers_behavioral_cert_with_canned_transport(self):
        """Fyers certifies the full engine-agnostic flow against a canned transport."""

        import json
        from unittest.mock import AsyncMock

        from brokers.fyers_adapter import FyersAdapter

        adapter = FyersAdapter()
        adapter._access_token = "cert_token"
        adapter._client_id = "cert_client"

        def make_resp(payload):
            return type(
                "Resp",
                (),
                {"status_code": 200, "headers": {}, "text": json.dumps(payload),
                 "json": lambda: payload, "content": json.dumps(payload).encode()},
            )

        transport = AsyncMock()
        transport.request.side_effect = lambda *a, **kw: make_resp({"s": "ok", "orders": [], "id": "cert123"})
        adapter._http = transport

        report = await certify_behavior(adapter, {"authenticate", "funds", "holdings", "positions", "orders",
                                                  "place", "modify", "cancel", "quotes", "historical", "stream", "disconnect"})
        assert report.passed

        # The engine-agnostic call flow works on the real adapter via the interface.
        from core.models import Exchange, NormalizedOrder, OrderSide, OrderType, ProductType

        order = NormalizedOrder(
            symbol="NSE:NIFTY26AUG25000CE", exchange=Exchange.NSE, quantity=65, side=OrderSide.BUY,
            order_type=OrderType.MARKET, product=ProductType.INTRADAY,
        )
        result = await adapter.place_order(order)
        assert result is not None
        assert transport.request.await_count >= 1
