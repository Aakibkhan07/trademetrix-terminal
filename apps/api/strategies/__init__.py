from strategies.base import BaseStrategy, SignalResult
from strategies.trend_rider import TrendRider
from strategies.orb_pro import ORBPro
from strategies.smc_sniper import SMCSniper
from strategies.expiry_hunter import ExpiryHunter

_strategy_registry: dict[str, type[BaseStrategy]] = {}


def register_strategy(name: str, cls: type[BaseStrategy]) -> None:
    _strategy_registry[name] = cls


def get_strategy(name: str) -> type[BaseStrategy]:
    if name not in _strategy_registry:
        raise ValueError(f"Unknown strategy: {name}")
    return _strategy_registry[name]


def list_strategies() -> list[str]:
    return list(_strategy_registry.keys())


register_strategy("trend_rider", TrendRider)
register_strategy("orb_pro", ORBPro)
register_strategy("smc_sniper", SMCSniper)
register_strategy("expiry_hunter", ExpiryHunter)


__all__ = [
    "BaseStrategy",
    "SignalResult",
    "TrendRider",
    "ORBPro",
    "SMCSniper",
    "ExpiryHunter",
    "register_strategy",
    "get_strategy",
    "list_strategies",
]
