from brokers.aliceblue_adapter import AliceBlueAdapter
from brokers.angelone_adapter import AngelOneAdapter
from brokers.base import BaseBroker
from brokers.dhan_adapter import DhanAdapter
from brokers.finvasia_adapter import FinvasiaAdapter
from brokers.fivepaisa_adapter import FivePaisaAdapter
from brokers.flattrade_adapter import FlattradeAdapter
from brokers.fyers_adapter import FyersAdapter
from brokers.kotakneo_adapter import KotakNeoAdapter
from brokers.upstox_adapter import UpstoxAdapter
from brokers.zerodha_adapter import ZerodhaAdapter

_broker_registry: dict[str, type[BaseBroker]] = {}


def register_broker(name: str, cls: type[BaseBroker]) -> None:
    _broker_registry[name] = cls


def get_broker(name: str) -> type[BaseBroker]:
    if name not in _broker_registry:
        raise ValueError(f"Unknown broker: {name}. Available: {list(_broker_registry.keys())}")
    return _broker_registry[name]


def list_brokers() -> list[str]:
    return list(_broker_registry.keys())


register_broker("fyers", FyersAdapter)
register_broker("dhan", DhanAdapter)
register_broker("zerodha", ZerodhaAdapter)
register_broker("angelone", AngelOneAdapter)
register_broker("upstox", UpstoxAdapter)
register_broker("fivepaisa", FivePaisaAdapter)
register_broker("aliceblue", AliceBlueAdapter)
register_broker("finvasia", FinvasiaAdapter)
register_broker("flattrade", FlattradeAdapter)
register_broker("kotakneo", KotakNeoAdapter)


__all__ = [
    "BaseBroker",
    "AliceBlueAdapter",
    "AngelOneAdapter",
    "DhanAdapter",
    "FinvasiaAdapter",
    "FivePaisaAdapter",
    "FlattradeAdapter",
    "FyersAdapter",
    "KotakNeoAdapter",
    "UpstoxAdapter",
    "ZerodhaAdapter",
    "register_broker",
    "get_broker",
    "list_brokers",
]
