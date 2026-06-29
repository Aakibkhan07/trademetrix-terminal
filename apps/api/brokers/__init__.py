from brokers.angelone_adapter import AngelOneAdapter
from brokers.base import BaseBroker
from brokers.dhan_adapter import DhanAdapter
from brokers.fyers_adapter import FyersAdapter
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


__all__ = [
    "BaseBroker",
    "AngelOneAdapter",
    "FyersAdapter",
    "DhanAdapter",
    "ZerodhaAdapter",
    "register_broker",
    "get_broker",
    "list_brokers",
]
