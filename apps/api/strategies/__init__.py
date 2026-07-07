from pydantic import BaseModel

from strategies.base import BaseStrategy, SignalResult
from strategies.bollinger_bandit import BollingerBandit
from strategies.expiry_hunter import ExpiryHunter
from strategies.macd_cross import MACDCross
from strategies.orb_pro import ORBPro
from strategies.rsi_mean_reversion import RSIMeanReversion
from strategies.smc_sniper import SMCSniper
from strategies.trend_rider import TrendRider
from strategies.vwap_band import VWAPBand
from strategies.momentum_buyer import MomentumBreakoutBuyer
from strategies.trend_rider_buyer import TrendRiderBuyer
from strategies.long_straddle import LongStraddle

_strategy_registry: dict[str, type[BaseStrategy]] = {}


class StrategyInfo(BaseModel):
    key: str
    name: str
    description: str
    required_tier: str


def register_strategy(name: str, cls: type[BaseStrategy]) -> None:
    _strategy_registry[name] = cls


def get_strategy(name: str) -> type[BaseStrategy]:
    if name not in _strategy_registry:
        raise ValueError(f"Unknown strategy: {name}")
    return _strategy_registry[name]


def list_strategies() -> list[str]:
    return list(_strategy_registry.keys())


def get_strategy_catalog() -> list[StrategyInfo]:
    return [_STRATEGY_TIERS[k] for k in _strategy_registry]


def get_strategy_tier(strategy_key: str) -> str | None:
    info = _STRATEGY_TIERS.get(strategy_key)
    return info.required_tier if info else None


def get_strategy_category(strategy_key: str) -> str:
    return _STRATEGY_CATEGORIES.get(strategy_key, "trend")


_STRATEGY_CATEGORIES: dict[str, str] = {
    "trend_rider": "trend",
    "macd_cross": "trend",
    "smc_sniper": "trend",
    "orb_pro": "breakout",
    "expiry_hunter": "options",
    "rsi_mean_reversion": "mean_reversion",
    "bollinger_bandit": "mean_reversion",
    "vwap_band": "scalping",
    "graph_strategy": "trend",
    "momentum_breakout_buyer": "options_buying",
    "trend_rider_buyer": "options_buying",
    "long_straddle": "options_buying",
}


_STRATEGY_TIERS: dict[str, StrategyInfo] = {
    "trend_rider": StrategyInfo(
        key="trend_rider", name="Trend Rider", description="Follows EMA crossover trends with momentum confirmation", required_tier="free",
    ),
    "macd_cross": StrategyInfo(
        key="macd_cross", name="MACD Cross", description="MACD crossover signals for trend reversals", required_tier="free",
    ),
    "vwap_band": StrategyInfo(
        key="vwap_band", name="VWAP Band", description="VWAP-based mean reversion with volatility bands", required_tier="starter",
    ),
    "rsi_mean_reversion": StrategyInfo(
        key="rsi_mean_reversion", name="RSI Mean Reversion", description="RSI-based overbought/oversold reversals", required_tier="starter",
    ),
    "bollinger_bandit": StrategyInfo(
        key="bollinger_bandit", name="Bollinger Bandit", description="Bollinger Band squeeze breakouts", required_tier="pro",
    ),
    "orb_pro": StrategyInfo(
        key="orb_pro", name="ORB Pro", description="Opening range breakout with volume confirmation", required_tier="pro",
    ),
    "smc_sniper": StrategyInfo(
        key="smc_sniper", name="SMC Sniper", description="Smart Money Concepts — order blocks and liquidity grabs", required_tier="enterprise",
    ),
    "expiry_hunter": StrategyInfo(
        key="expiry_hunter", name="Expiry Hunter", description="Weekly expiry theta decay and gamma scalping", required_tier="enterprise",
    ),
    "graph_strategy": StrategyInfo(
        key="graph_strategy", name="Graph Strategy", description="Visual strategy builder — drag, connect, deploy", required_tier="pro",
    ),
    "momentum_breakout_buyer": StrategyInfo(
        key="momentum_breakout_buyer", name="Momentum Breakout Buyer", description="Intraday options buyer — OR breakout + volume confirmation + premium management", required_tier="starter",
    ),
    "trend_rider_buyer": StrategyInfo(
        key="trend_rider_buyer", name="Trend Rider Buyer", description="Options buyer — EMA9/21 + VWAP + ADX trend filter + Supertrend trail", required_tier="pro",
    ),
    "long_straddle": StrategyInfo(
        key="long_straddle", name="Long Straddle", description="ATM CE+PE buy for volatility expansion with IV gate", required_tier="enterprise",
    ),
}

register_strategy("trend_rider", TrendRider)
register_strategy("orb_pro", ORBPro)
register_strategy("smc_sniper", SMCSniper)
register_strategy("expiry_hunter", ExpiryHunter)
register_strategy("rsi_mean_reversion", RSIMeanReversion)
register_strategy("bollinger_bandit", BollingerBandit)
register_strategy("macd_cross", MACDCross)
register_strategy("vwap_band", VWAPBand)
register_strategy("momentum_breakout_buyer", MomentumBreakoutBuyer)
register_strategy("trend_rider_buyer", TrendRiderBuyer)
register_strategy("long_straddle", LongStraddle)


__all__ = [
    "BaseStrategy",
    "SignalResult",
    "TrendRider",
    "ORBPro",
    "SMCSniper",
    "ExpiryHunter",
    "RSIMeanReversion",
    "BollingerBandit",
    "MACDCross",
    "VWAPBand",
    "MomentumBreakoutBuyer",
    "TrendRiderBuyer",
    "LongStraddle",
    "BuyerBase",
    "BuyerConfig",
    "Phase",
    "StrategyInfo",
    "register_strategy",
    "get_strategy",
    "list_strategies",
    "get_strategy_catalog",
    "get_strategy_tier",
    "get_strategy_category",
]
