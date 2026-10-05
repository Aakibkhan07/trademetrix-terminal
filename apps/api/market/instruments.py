"""Canonical instrument resolution — the single source of truth for contract metadata.

Why this module exists
----------------------
Position sizing, quantity validation, exposure calculation, order construction and
the risk engine all need the same facts about a contract: what its security id is,
which exchange segment it trades on, what instrument type it is, and what its lot
size is. Historically each of those asked separately and got a different answer:

* strategies read ``LOT_SIZES.get(self.symbol, 75)`` — a hardcoded dict keyed by
  bare index names, with nine different fallback defaults across the codebase
* ``engine/gate._get_lot_size`` substring-matched the symbol (``"NIFTY" in s``)
  against the same dict
* ``market/instrument_service.lot_size`` did ``LOT_SIZES.get(index, 65)``
* ``broker_connect/execution/symbols.resolve`` read the ``symbol_master`` table
* ``brokers/dhan_adapter.place_order`` sent ``order.symbol`` in the ``securityId``
  field, where Dhan requires a broker-assigned id

The disagreement was not cosmetic. The gate multiplied the requested quantity by
ten lots before the risk engine saw it, while the strategy had derived a different
number from a different lot size, and the broker was handed a display symbol in a
field that wants an internal id.

The contract enforced here
--------------------------
Exactly one resolver. Callers ask for an :class:`Instrument` and either get a
fully-populated one or get nothing. There is no default lot size, no default
segment and no default instrument type, because a guessed value here becomes an
order quantity.

Authoritative providers
-----------------------
A provider must be registered as authoritative to satisfy a resolution. As of this
commit **none is**: Dhan instrument ingestion is not implemented
(``SymbolMaster._sync_dhan_instruments`` returns 0) and the ``symbol_master`` table
holds 68 rows all tagged ``broker='master'``, last refreshed 2026-07-28, whose index
lot sizes match neither Dhan nor the repo's own constants. A legacy source may be
registered for *diagnostics* but is deliberately not allowed to satisfy a
production resolution, so derivative orders fail closed and say why instead of
trading on an assumed contract size.

Adding Dhan
-----------
Implement ``DhanInstrumentProvider`` against Dhan's instrument endpoint, register
it authoritative, and every consumer picks it up with no further change. Do not
add a second provider for the same fact — the whole point is that there is one.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Instrument types that carry a lot contract. Cash equity does not, and is
# deliberately excluded from lot validation everywhere downstream.
LOT_BEARING_INSTRUMENT_TYPES = frozenset({"FUT", "OPT", "FUTIDX", "OPTIDX", "CE", "PE"})


class InstrumentResolutionError(RuntimeError):
    """Raised when a caller demands an instrument and none can be resolved."""


@dataclass(frozen=True)
class Instrument:
    """A fully-resolved contract. There are no defaults on any field.

    ``lot_size`` is units per lot. ``security_id`` is the broker's own identifier
    for the contract, which is not the same string as ``broker_symbol`` and not the
    same string as the app's canonical ``symbol``.
    """

    broker: str
    security_id: str
    broker_symbol: str
    exchange_segment: str
    instrument_type: str
    lot_size: int
    tick_size: float = 0.05
    underlying: str = ""
    expiry: str = ""
    strike: float | None = None
    option_type: str = ""
    source: str = ""

    @property
    def has_lot_contract(self) -> bool:
        return self.instrument_type.upper() in LOT_BEARING_INSTRUMENT_TYPES

    def lots_for_units(self, units: int) -> float:
        """How many lots ``units`` represents. Never multiplies a quantity."""
        if self.lot_size <= 0:
            raise ValueError(f"lot_size must be positive, got {self.lot_size}")
        return units / self.lot_size

    def units_for_lots(self, lots: int) -> int:
        """The one place units are produced from lots."""
        if self.lot_size <= 0:
            raise ValueError(f"lot_size must be positive, got {self.lot_size}")
        if lots <= 0:
            raise ValueError(f"lots must be positive, got {lots}")
        return lots * self.lot_size


# A provider is either a plain callable resolving a symbol, or an object exposing
# ``resolve`` plus optionally ``resolve_option`` / ``resolve_future``. Supporting both
# keeps the common case (a single contract lookup) a one-line lambda while leaving room
# for a master-backed provider that can answer exact-contract questions.
InstrumentProvider = Callable[..., "Instrument | None"]


def _provider_lookup(provider: InstrumentProvider, method: str, *args, **kwargs):
    """Call ``method`` on a provider if it exposes it, else the provider itself.

    A bare callable is treated as the ``resolve`` entry point. Anything exposing the
    named method is preferred, so a master-backed provider can answer a narrower
    question (an exact option contract) without every caller knowing its shape.
    """
    target = getattr(provider, method, None)
    if callable(target):
        return target(*args, **kwargs)
    if method == "resolve" and callable(provider):
        return provider(*args, **kwargs)
    return None


@dataclass
class _Provider:
    name: str
    fn: InstrumentProvider
    authoritative: bool
    note: str = ""
    calls: int = field(default=0, init=False)
    hits: int = field(default=0, init=False)


class InstrumentResolver:
    """Registry of instrument-metadata providers.

    Providers marked authoritative are consulted in registration order; the first
    non-None answer wins. Non-authoritative providers are never consulted to satisfy
    a resolution — registering them is only useful for diagnostics via
    :meth:`explain`, so an operator can see what the legacy data claims without that
    claim reaching an order.
    """

    def __init__(self) -> None:
        self._providers: list[_Provider] = []

    def register(
        self,
        name: str,
        fn: InstrumentProvider,
        *,
        authoritative: bool,
        note: str = "",
    ) -> None:
        if authoritative and self.authoritative_providers():
            # Not an error: multiple authoritative providers are legitimate only
            # while one is being rolled out behind the other. The first registered
            # wins at resolution time and the second is reported by explain().
            logger.warning(
                "Instrument provider %r registered as authoritative; %s already is. "
                "Resolution uses the first registered (%s).",
                name, self.authoritative_providers()[0].name, self.authoritative_providers()[0].name,
            )
        self._providers.append(_Provider(name=name, fn=fn, authoritative=authoritative, note=note))

    def authoritative_providers(self) -> list[_Provider]:
        return [p for p in self._providers if p.authoritative]

    def resolve(
        self,
        symbol: str,
        *,
        broker: str,
        instrument_type: str,
    ) -> Instrument | None:
        """Return a fully-resolved instrument, or None when metadata is unavailable.

        None is the honest answer when no authoritative provider can resolve the
        symbol. Callers must block on None for lot-bearing instruments rather than
        substituting a default.
        """
        for provider in self.authoritative_providers():
            provider.calls += 1
            try:
                found = _provider_lookup(
                    provider.fn, "resolve", symbol, broker=broker,
                    instrument_type=instrument_type,
                )
            except Exception as exc:
                logger.warning(
                    "Instrument provider %r raised for %s (%s): %s",
                    provider.name, symbol, instrument_type, exc,
                )
                continue
            if found is not None:
                provider.hits += 1
                return found
        return None

    def require(
        self,
        symbol: str,
        *,
        broker: str,
        instrument_type: str,
    ) -> Instrument:
        """Resolve or raise with the operator-facing reason.

        The message is deliberately explicit about which metadata is missing, so a
        blocked order says what to fix rather than failing with a generic code.
        """
        found = self.resolve(symbol, broker=broker, instrument_type=instrument_type)
        if found is not None:
            return found
        raise InstrumentResolutionError(
            "Unable to resolve authoritative instrument metadata. "
            f"Symbol: {symbol}. Broker: {broker}. Instrument type: {instrument_type}. "
            "Required metadata: Security ID, Exchange Segment, Instrument Type, Lot Size."
        )

    def explain(self, symbol: str, *, broker: str, instrument_type: str) -> dict:
        """What each provider claims, for diagnostics. Never used to build an order."""
        report: dict = {
            "symbol": symbol,
            "broker": broker,
            "instrument_type": instrument_type,
            "providers": [],
            "resolved": False,
        }
        for provider in self._providers:
            entry = {
                "name": provider.name,
                "authoritative": provider.authoritative,
                "calls": provider.calls,
                "hits": provider.hits,
                "note": provider.note,
            }
            try:
                found = _provider_lookup(
                    provider.fn, "resolve", symbol, broker=broker,
                    instrument_type=instrument_type,
                )
                entry["claims"] = (
                    None if found is None else {
                        "security_id": found.security_id,
                        "broker_symbol": found.broker_symbol,
                        "exchange_segment": found.exchange_segment,
                        "instrument_type": found.instrument_type,
                        "lot_size": found.lot_size,
                    }
                )
            except Exception as exc:
                entry["error"] = str(exc)
            report["providers"].append(entry)
        report["resolved"] = any(p["authoritative"] and p.get("claims") for p in report["providers"])
        return report


instrument_resolver = InstrumentResolver()


def needs_instrument_metadata(order) -> bool:
    """Whether this order requires resolvable contract metadata before it may trade.

    Cash equity has no lot contract, so it is exempt: its quantity is validated by
    the risk engine and by the broker, and inventing a lot size for it would be
    meaningless. Everything else — futures, options, and anything unrecognised —
    must resolve.
    """
    instrument_type = ""
    raw = getattr(order, "instrument_type", "")
    instrument_type = getattr(raw, "value", raw) or ""
    return instrument_type.upper() != "EQ"


def resolve_for_order(order, *, broker: str) -> Instrument | None:
    """Resolve the instrument for a NormalizedOrder, or None when unavailable."""
    raw_type = getattr(order, "instrument_type", "")
    instrument_type = getattr(raw_type, "value", raw_type) or ""
    return instrument_resolver.resolve(
        order.symbol,
        broker=broker,
        instrument_type=str(instrument_type),
    )


def blocked_message(symbol: str, broker: str, instrument_type: str) -> str:
    """The exact operator-facing text for an unresolvable contract."""
    return (
        "ORDER BLOCKED — Unable to resolve authoritative instrument metadata. "
        f"Symbol: {symbol}. Broker: {broker}. Instrument type: {instrument_type}. "
        "Required metadata: Security ID, Exchange Segment, Instrument Type, Lot Size."
    )


#: The broker whose instrument master is the system of record for contract
#: metadata. Lot sizes are a property of the contract rather than of the broker,
#: so a lot size resolved here is usable even when the order will be routed
#: elsewhere — but the security id and exchange segment are broker-specific and
#: must never be taken from a different broker's master.
REFERENCE_BROKER = "dhan"


def resolve_lot_size(
    symbol: str,
    *,
    broker: str = REFERENCE_BROKER,
    instrument_type: str = "",
) -> int | None:
    """The authoritative lot size for ``symbol``, or None when unresolved.

    Returns None rather than a default. A caller that receives None must fail
    closed; it must not substitute a literal. Every such caller previously
    substituted one of 1, 25, 40, 50, 65 or 75.
    """
    instrument = instrument_resolver.resolve(
        symbol, broker=broker, instrument_type=instrument_type
    )
    return instrument.lot_size if instrument is not None else None


def resolve_option_contract(
    underlying: str,
    *,
    expiry: str,
    strike: float,
    option_type: str,
    broker: str = REFERENCE_BROKER,
) -> Instrument | None:
    """Resolve one exact option contract, or None.

    Lot size varies per underlying *and* per contract, so a lookup keyed on the
    underlying alone is not sufficient for a stock option. The exact contract is
    identified by underlying, expiry, strike and CE/PE, and the security id comes
    from the master alongside the lot size.

    Providers implement this by narrowing their master rows. It is a separate
    entry point from :func:`resolve` precisely because "NIFTY" and "a NIFTY call
    struck 24000 expiring 2026-08-28" are different questions, and answering the
    second with the first is how an option gets sized on an index lot size.
    """
    opt = str(option_type or "").upper()
    if opt not in ("CE", "PE"):
        return None
    underlying_key = (underlying or "").split(":")[-1].upper()

    for provider in instrument_resolver.authoritative_providers():
        provider.calls += 1
        try:
            found = _provider_lookup(
                provider.fn, "resolve_option",
                underlying_key,
                expiry=str(expiry),
                strike=float(strike),
                option_type=opt,
                broker=broker,
            )
        except Exception as exc:
            logger.warning(
                "Option-contract lookup via %r failed for %s %s %s %s: %s",
                provider.name, underlying_key, expiry, strike, opt, exc,
            )
            continue
        if found is not None:
            provider.hits += 1
            return found
    return None


def resolve_future_contract(
    underlying: str,
    *,
    expiry: str,
    broker: str = REFERENCE_BROKER,
) -> Instrument | None:
    """Resolve one exact futures contract, or None."""
    underlying_key = (underlying or "").split(":")[-1].upper()
    for provider in instrument_resolver.authoritative_providers():
        provider.calls += 1
        try:
            found = _provider_lookup(
                provider.fn, "resolve_future",
                underlying_key, expiry=str(expiry), broker=broker,
            )
        except Exception as exc:
            logger.warning(
                "Future-contract lookup via %r failed for %s %s: %s",
                provider.name, underlying_key, expiry, exc,
            )
            continue
        if found is not None:
            provider.hits += 1
            return found
    return None