"""Unified Broker SDK — capability system tests.

Also asserts the SDK matrix is bit-for-bit equivalent to the legacy
execution-layer matrix (which it replaced as the single source of truth).
"""

import pytest

from brokers.sdk.capabilities import (
    BROKER_CAPABILITY_MATRIX,
    BrokerCapabilities,
    CapabilityFlag,
    capabilities_from_bools,
    get_capabilities,
)
from brokers.sdk.errors import UnsupportedFeatureError

LEGACY_BOOLS = {
    "fyers": dict(supports_orders=True, supports_modify=True, supports_cancel=True, supports_bracket=True,
                  supports_cover=False, supports_gtt=False, supports_websocket=True, supports_option_chain=True,
                  supports_positions=True, supports_holdings=True),
    "dhan": dict(supports_orders=True, supports_modify=True, supports_cancel=True, supports_bracket=False,
                 supports_cover=False, supports_gtt=True, supports_websocket=True, supports_option_chain=False,
                 supports_positions=True, supports_holdings=True),
    "zerodha": dict(supports_orders=True, supports_modify=True, supports_cancel=True, supports_bracket=True,
                    supports_cover=True, supports_gtt=True, supports_websocket=False, supports_option_chain=False,
                    supports_positions=True, supports_holdings=True),
    "angelone": dict(supports_orders=True, supports_modify=True, supports_cancel=True, supports_bracket=True,
                     supports_cover=True, supports_gtt=True, supports_websocket=True, supports_option_chain=False,
                     supports_positions=True, supports_holdings=True),
    "upstox": dict(supports_orders=True, supports_modify=True, supports_cancel=True, supports_bracket=True,
                   supports_cover=True, supports_gtt=True, supports_websocket=True, supports_option_chain=False,
                   supports_positions=True, supports_holdings=True),
    "fivepaisa": dict(supports_orders=True, supports_modify=True, supports_cancel=True, supports_bracket=False,
                      supports_cover=False, supports_gtt=False, supports_websocket=False, supports_option_chain=False,
                      supports_positions=True, supports_holdings=True),
    "aliceblue": dict(supports_orders=True, supports_modify=True, supports_cancel=True, supports_bracket=False,
                      supports_cover=False, supports_gtt=False, supports_websocket=True, supports_option_chain=False,
                      supports_positions=True, supports_holdings=True),
    "finvasia": dict(supports_orders=True, supports_modify=True, supports_cancel=True, supports_bracket=False,
                     supports_cover=False, supports_gtt=False, supports_websocket=True, supports_option_chain=False,
                     supports_positions=True, supports_holdings=True),
    "flattrade": dict(supports_orders=True, supports_modify=True, supports_cancel=True, supports_bracket=False,
                      supports_cover=False, supports_gtt=False, supports_websocket=True, supports_option_chain=False,
                      supports_positions=True, supports_holdings=True),
    "kotakneo": dict(supports_orders=True, supports_modify=True, supports_cancel=True, supports_bracket=True,
                     supports_cover=False, supports_gtt=True, supports_websocket=True, supports_option_chain=False,
                     supports_positions=True, supports_holdings=True),
}


class TestCapabilityEnum:
    def test_values(self):
        assert CapabilityFlag("websocket") == CapabilityFlag.WEBSOCKET
        assert CapabilityFlag("option_chain").value == "option_chain"

    def test_all_matrix_cells_are_valid_enum_members(self):
        for broker, flags in BROKER_CAPABILITY_MATRIX.items():
            for flag in flags:
                assert isinstance(flag, CapabilityFlag)


class TestBrokerCapabilities:
    def test_supports_and_require(self):
        caps = get_capabilities("fyers")
        assert caps.supports(CapabilityFlag.OPTION_CHAIN)
        assert caps.supports("websocket")
        caps.require(CapabilityFlag.OPTION_CHAIN)
        caps.require("websocket")

    def test_require_raises_typed_error(self):
        caps = get_capabilities("fivepaisa")
        with pytest.raises(UnsupportedFeatureError) as excinfo:
            caps.require(CapabilityFlag.WEBSOCKET)
        assert excinfo.value.code == "unsupported_feature"
        assert excinfo.value.broker == "fivepaisa"
        assert excinfo.value.feature == "websocket"

    def test_contains(self):
        caps = get_capabilities("dhan")
        assert CapabilityFlag.GTT in caps
        assert "gtt" in caps

    def test_legacy_bool_surface(self):
        caps = get_capabilities("fyers")
        assert caps.supports_bracket is True
        assert caps.supports_option_chain is True
        caps2 = get_capabilities("dhan")
        assert caps2.supports_bracket is False
        assert caps2.supports_gtt is True

    def test_unknown_broker_returns_empty(self):
        caps = get_capabilities("not_a_broker")
        assert caps.supports_orders is False

    def test_to_dict(self):
        d = get_capabilities("fyers").to_dict()
        assert d["broker"] == "fyers"
        assert "option_chain" in d["capabilities"]


class TestLegacyEquivalence:
    """The SDK matrix must be identical to the legacy execution-layer matrix."""

    @pytest.mark.parametrize("broker", sorted(LEGACY_BOOLS))
    def test_matrix_matches_legacy(self, broker):
        caps = get_capabilities(broker)
        expected = LEGACY_BOOLS[broker]
        for field, value in expected.items():
            assert getattr(caps, field) is value, (
                f"{broker}.{field} = {getattr(caps, field)}, expected {value}"
            )


class TestCapabilitiesFromBools:
    def test_round_trip(self):
        caps = capabilities_from_bools("paper", dict(supports_orders=True, supports_bracket=True))
        assert caps.supports_orders is True
        assert caps.supports_bracket is True
        assert caps.supports_gtt is False
