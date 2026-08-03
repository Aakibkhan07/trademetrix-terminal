"""FIFO lot engine for realized P&L (Execution Engine v1.0).

Tracks open lots per (user, broker, symbol) in strict FIFO order so closing
fills realize P&L against the oldest open lot first — matching Indian broker
defaults and the historical FIFO math in ``risk/helpers.py``, but in-memory,
thread-safe and event-driven.
"""
from __future__ import annotations

import threading


class FifoLots:
    """Thread-safe FIFO open-lot ledger for one symbol.

    ``apply(side, qty, price)`` mutates lots and returns the realized P&L of
    the fill (positive = profit). Reversal fills (closing more than the open
    position) automatically open a lot in the opposite direction.
    """

    _EPS = 1e-9

    def __init__(self) -> None:
        self._longs: list[list[float]] = []  # [qty, price]
        self._shorts: list[list[float]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    @property
    def long_quantity(self) -> int:
        with self._lock:
            return int(round(sum(lot[0] for lot in self._longs)))

    @property
    def short_quantity(self) -> int:
        with self._lock:
            return int(round(sum(lot[0] for lot in self._shorts)))

    @property
    def net_quantity(self) -> int:
        return self.long_quantity - self.short_quantity

    @property
    def is_open(self) -> bool:
        return self.net_quantity != 0

    def average_price(self, side: str) -> float:
        """Volume-weighted average of open lots on one side (0.0 when flat)."""
        with self._lock:
            lots = self._longs if side == "BUY" else self._shorts
            total = sum(lot[0] for lot in lots)
            if total <= self._EPS:
                return 0.0
            return sum(lot[0] * lot[1] for lot in lots) / total

    # ------------------------------------------------------------------
    def apply(self, side: str, quantity: int, price: float) -> float:
        """Apply one fill; returns realized P&L for this fill."""
        qty = int(quantity)
        if qty <= 0:
            return 0.0
        realized = 0.0
        with self._lock:
            if side == "BUY":
                rem = qty
                while rem > 0 and self._shorts:
                    lot = self._shorts[0]
                    used = min(rem, lot[0])
                    realized += used * (lot[1] - price)
                    rem -= used
                    lot[0] -= used
                    if lot[0] <= self._EPS:
                        self._shorts.pop(0)
                if rem > 0:
                    self._longs.append([rem, price])
            elif side == "SELL":
                rem = qty
                while rem > 0 and self._longs:
                    lot = self._longs[0]
                    used = min(rem, lot[0])
                    realized += used * (price - lot[1])
                    rem -= used
                    lot[0] -= used
                    if lot[0] <= self._EPS:
                        self._longs.pop(0)
                if rem > 0:
                    self._shorts.append([rem, price])
            else:
                raise ValueError(f"Invalid side: {side!r}")
        return round(realized, 2)

    def unrealized_pnl(self, last_price: float) -> float:
        """Unrealized P&L of the open position at ``last_price``."""
        if last_price <= 0:
            return 0.0
        long_pnl = self.long_quantity * (last_price - self.average_price("BUY"))
        short_pnl = self.short_quantity * (self.average_price("SELL") - last_price)
        return round(long_pnl + short_pnl, 2)

    def clear(self) -> None:
        with self._lock:
            self._longs.clear()
            self._shorts.clear()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "long_quantity": self.long_quantity,
                "short_quantity": self.short_quantity,
                "net_quantity": self.net_quantity,
                "average_buy_price": self.average_price("BUY"),
                "average_sell_price": self.average_price("SELL"),
            }

    # ------------------------------------------------------------------
    # Serialization (runtime persistence): open lots are the ground truth
    # for unrealized + future realized P&L, so they are checkpointed with
    # the engine state.
    # ------------------------------------------------------------------
    def to_lots(self) -> dict[str, list[list[float]]]:
        """Export open lots as [[qty, price], ...] pairs (canonical JSON)."""
        with self._lock:
            return {
                "longs": [[float(qty), float(price)] for qty, price in self._longs],
                "shorts": [[float(qty), float(price)] for qty, price in self._shorts],
            }

    @classmethod
    def from_lots(cls, lots: dict[str, list[list[float]]]) -> "FifoLots":
        """Reconstruct from ``to_lots`` output (deterministic round-trip)."""
        fifo = cls()
        fifo._longs = [[float(qty), float(price)] for qty, price in lots.get("longs", [])]
        fifo._shorts = [[float(qty), float(price)] for qty, price in lots.get("shorts", [])]
        return fifo
