from abc import ABC, abstractmethod

from pydantic import BaseModel

from core.models import Candle, NormalizedOrder, Tick


class SignalResult(BaseModel):
    orders: list[NormalizedOrder]
    reason: str = ""


def _positive_int(value, *, default: int | None) -> int | None:
    """Coerce a config value to a positive int, or return ``default``.

    Deliberately tolerant of junk (None, "", "abc", 0, negative) because these
    values arrive from a user-facing form. A malformed number must not become a
    silent default *lot size*; returning ``default`` here means "not supplied",
    which downstream callers treat as unresolved rather than as a guess.

    A fractional number is also junk for this field. ``int(1.5)`` is 1, so a
    careless coercion would turn a malformed lot size into a small real one — the
    worst outcome, because it looks valid. Booleans are rejected too: ``True`` is
    an int in Python and would otherwise become a lot size of 1.
    """
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, float) and not value.is_integer():
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


class BaseStrategy(ABC):
    name: str = ""
    description: str = ""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._position: dict = {}

        # Position size is expressed in LOTS and converted to units exactly once,
        # here. It used to be assigned in each strategy as
        # `LOT_SIZES.get(self.symbol, 75)`, which did three wrong things at once:
        # it read a lot size from a hardcoded dict keyed by bare index names, it
        # fell back to one of nine different literals when the key missed, and it
        # assigned that lot *size* straight into `quantity` — a units field. The
        # result was a 75-unit order against a 65-unit contract, which the
        # execution gate now (correctly) refuses.
        #
        # `lot_size` is injected by whoever resolved the contract. It is never
        # guessed: absent means "contract metadata unresolved", which makes
        # `quantity` 0 and blocks the order downstream with a message naming the
        # missing metadata, instead of trading on an assumed contract size.
        self.lots = _positive_int(self.config.get("lots"), default=1)
        self.lot_size = _positive_int(self.config.get("lot_size"), default=None)
        # An explicit unit quantity still wins, for callers that genuinely mean
        # units rather than lots.
        self._explicit_quantity = _positive_int(self.config.get("quantity"), default=None)

    @property
    def quantity(self) -> int:
        """Order size in UNITS.

        0 means the contract's lot size is unknown. That is a deliberate signal,
        not a size: no execution path should treat it as orderable, and the gate
        turns it into an ORDER BLOCKED naming the missing metadata.
        """
        if self._explicit_quantity:
            return self._explicit_quantity
        if not self.lot_size:
            return 0
        return self.lots * self.lot_size

    @property
    def has_resolved_lot_size(self) -> bool:
        return bool(self.lot_size)

    @abstractmethod
    async def on_tick(self, tick: Tick) -> SignalResult | None:
        ...

    @abstractmethod
    async def on_candle(self, candle: Candle) -> SignalResult | None:
        ...

    @abstractmethod
    async def on_start(self) -> None:
        ...

    @abstractmethod
    async def on_stop(self) -> None:
        ...

    def update_position(self, symbol: str, quantity: int) -> None:
        self._position[symbol] = self._position.get(symbol, 0) + quantity
