from brokers.aliceblue_adapter import AliceBlueAdapter
from brokers.alpaca_adapter import AlpacaAdapter
from brokers.angelone_adapter import AngelOneAdapter
from brokers.axis_adapter import AxisSecuritiesAdapter
from brokers.base import BaseBroker
from brokers.binance_adapter import BinanceAdapter
from brokers.bybit_adapter import BybitAdapter
from brokers.circuit_breaker_broker import CircuitBreakerBroker
from brokers.dhan_adapter import DhanAdapter
from brokers.finvasia_adapter import FinvasiaAdapter
from brokers.fivepaisa_adapter import FivePaisaAdapter
from brokers.flattrade_adapter import FlattradeAdapter
from brokers.fyers_adapter import FyersAdapter
from brokers.geojit_adapter import GeojitAdapter
from brokers.groww_adapter import GrowwAdapter
from brokers.hdfc_adapter import HDFCSecuritiesAdapter
from brokers.interactive_brokers_adapter import InteractiveBrokersAdapter
from brokers.iifl_adapter import IIFLSecuritiesAdapter
from brokers.kotakneo_adapter import KotakNeoAdapter
from brokers.lemonn_adapter import LemonnAdapter
from brokers.icici_adapter import ICICIDirectAdapter
from brokers.motilal_adapter import MotilalOswalAdapter
from brokers.oanda_adapter import OandaAdapter
from brokers.okx_adapter import OkxAdapter
from brokers.reliance_adapter import RelianceSecuritiesAdapter
from brokers.sdk.registry import BrokerSpec, registry as _sdk_registry
from brokers.upstox_adapter import UpstoxAdapter
from brokers.zerodha_adapter import ZerodhaAdapter

# ── Unified Broker SDK v2 registry (single source of truth) ──────────
# Adapter classes + UI metadata + capabilities all live in the SDK registry.
# The functions below are the legacy facade; they delegate to it so behaviour
# is unchanged for existing callers (execution layer, token manager, engine).


def _register_spec(name: str, cls: type[BaseBroker]) -> None:
    from brokers.registry import BROKER_METADATA

    meta = BROKER_METADATA.get(name, {})
    _sdk_registry.register(
        BrokerSpec(
            name=name,
            display_name=meta.get("display_name", name),
            auth_type=meta.get("auth_type", "oauth"),
            description=meta.get("description", ""),
            fields=meta.get("fields", []),
            has_additional_params=meta.get("has_additional_params", False),
            additional_params_fields=meta.get("additional_params_fields", []),
            instructions=meta.get("instructions", ""),
            oauth_available=meta.get("oauth_available", False),
            adapter_class=cls,
        )
    )


_broker_registry: dict[str, type[BaseBroker]] = {}


def register_broker(name: str, cls: type[BaseBroker]) -> None:
    _broker_registry[name] = cls
    _register_spec(name, cls)


def get_broker(name: str) -> type[BaseBroker]:
    if name not in _broker_registry:
        raise ValueError(f"Unknown broker: {name}. Available: {list(_broker_registry.keys())}")
    return _broker_registry[name]


def create_broker(name: str) -> CircuitBreakerBroker:
    """Instantiate the broker adapter wrapped in a circuit breaker (legacy contract).

    Delegates to the SDK registry factory, which wraps with
    CircuitBreakerBroker(breaker_name=f"broker_{name}").
    """

    return _sdk_registry.create(name, wrap_circuit_breaker=True)


def list_brokers() -> list[str]:
    return list(_broker_registry.keys())


register_broker("fyers", FyersAdapter)
register_broker("groww", GrowwAdapter)
register_broker("dhan", DhanAdapter)
register_broker("zerodha", ZerodhaAdapter)
register_broker("angelone", AngelOneAdapter)
register_broker("upstox", UpstoxAdapter)
register_broker("fivepaisa", FivePaisaAdapter)
register_broker("aliceblue", AliceBlueAdapter)
register_broker("finvasia", FinvasiaAdapter)
register_broker("flattrade", FlattradeAdapter)
register_broker("kotakneo", KotakNeoAdapter)
register_broker("lemonn", LemonnAdapter)
register_broker("binance", BinanceAdapter)
register_broker("bybit", BybitAdapter)
register_broker("okx", OkxAdapter)
register_broker("oanda", OandaAdapter)
register_broker("interactive_brokers", InteractiveBrokersAdapter)
register_broker("alpaca", AlpacaAdapter)
register_broker("icici", ICICIDirectAdapter)
register_broker("hdfc", HDFCSecuritiesAdapter)
register_broker("iifl", IIFLSecuritiesAdapter)
register_broker("motilal", MotilalOswalAdapter)
register_broker("geojit", GeojitAdapter)
register_broker("reliance", RelianceSecuritiesAdapter)
register_broker("axis", AxisSecuritiesAdapter)


__all__ = [
    "AxisSecuritiesAdapter",
    "BaseBroker",
    "AliceBlueAdapter",
    "AlpacaAdapter",
    "AngelOneAdapter",
    "BinanceAdapter",
    "BybitAdapter",
    "CircuitBreakerBroker",
    "DhanAdapter",
    "FinvasiaAdapter",
    "FivePaisaAdapter",
    "FlattradeAdapter",
    "FyersAdapter",
    "GeojitAdapter",
    "GrowwAdapter",
    "HDFCSecuritiesAdapter",
    "ICICIDirectAdapter",
    "IIFLSecuritiesAdapter",
    "InteractiveBrokersAdapter",
    "KotakNeoAdapter",
    "LemonnAdapter",
    "MotilalOswalAdapter",
    "OandaAdapter",
    "OkxAdapter",
    "RelianceSecuritiesAdapter",
    "UpstoxAdapter",
    "ZerodhaAdapter",
    "register_broker",
    "get_broker",
    "create_broker",
    "list_brokers",
]
