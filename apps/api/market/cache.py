import time
import logging
from collections import OrderedDict

from core.models import Tick

logger = logging.getLogger(__name__)


class MarketCache:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, tick_ttl: float = 60.0, quote_ttl: float = 30.0, chain_ttl: float = 10.0):
        if self._initialized:
            return
        self._initialized = True
        self._tick_ttl = tick_ttl
        self._quote_ttl = quote_ttl
        self._chain_ttl = chain_ttl
        self._ticks: dict[str, tuple[float, Tick]] = {}
        self._latest_ticks: OrderedDict[str, Tick] = OrderedDict()
        self._option_chains: dict[str, tuple[float, dict]] = {}
        self._quotes: dict[str, tuple[float, dict]] = {}
        self._market_status: tuple[float, dict] | None = None
        self._expiry_list: dict[str, tuple[float, list[str]]] = {}
        self._max_latest = 500

    def put_tick(self, tick: Tick) -> None:
        now = time.time()
        self._ticks[tick.symbol] = (now, tick)
        self._latest_ticks[tick.symbol] = tick
        self._latest_ticks.move_to_end(tick.symbol)
        while len(self._latest_ticks) > self._max_latest:
            self._latest_ticks.popitem(last=False)

    def get_tick(self, symbol: str) -> Tick | None:
        entry = self._ticks.get(symbol)
        if entry is None:
            return None
        ts, tick = entry
        if time.time() - ts > self._tick_ttl:
            del self._ticks[symbol]
            return None
        return tick

    def get_all_ticks(self) -> dict[str, Tick]:
        now = time.time()
        stale = [sym for sym, (ts, _) in self._ticks.items() if now - ts > self._tick_ttl]
        for sym in stale:
            del self._ticks[sym]
        return {sym: tick for sym, (_, tick) in self._ticks.items()}

    def get_latest_ticks(self, limit: int = 100) -> list[Tick]:
        return list(self._latest_ticks.values())[-limit:]

    def put_option_chain(self, key: str, data: dict) -> None:
        self._option_chains[key] = (time.time(), data)

    def get_option_chain(self, key: str) -> dict | None:
        entry = self._option_chains.get(key)
        if entry is None:
            return None
        ts, data = entry
        if time.time() - ts > self._chain_ttl:
            del self._option_chains[key]
            return None
        return data

    def put_expiries(self, key: str, expiries: list[str]) -> None:
        self._expiry_list[key] = (time.time(), expiries)

    def get_expiries(self, key: str) -> list[str] | None:
        entry = self._expiry_list.get(key)
        if entry is None:
            return None
        ts, data = entry
        if time.time() - ts > 3600:
            del self._expiry_list[key]
            return None
        return data

    def put_quote(self, symbol: str, data: dict) -> None:
        self._quotes[symbol] = (time.time(), data)

    def get_quote(self, symbol: str) -> dict | None:
        entry = self._quotes.get(symbol)
        if entry is None:
            return None
        ts, data = entry
        if time.time() - ts > self._quote_ttl:
            del self._quotes[symbol]
            return None
        return data

    def put_market_status(self, status: dict) -> None:
        self._market_status = (time.time(), status)

    def get_market_status(self) -> dict | None:
        if self._market_status is None:
            return None
        ts, status = self._market_status
        if time.time() - ts > 3600:
            self._market_status = None
            return None
        return status

    def clear(self) -> None:
        self._ticks.clear()
        self._latest_ticks.clear()
        self._option_chains.clear()
        self._quotes.clear()
        self._market_status = None
        self._expiry_list.clear()


market_cache = MarketCache()
