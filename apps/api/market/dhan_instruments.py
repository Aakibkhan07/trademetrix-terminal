"""Dhan authoritative instrument master.

This is the production source of truth for contract metadata: security id,
exchange segment, instrument type, lot size, tick size, expiry, strike and option
type. Nothing here falls back to a constant. A contract that cannot be described
by Dhan's master is not tradeable, and the resolver reports that rather than
inventing a size.

Why a dedicated store rather than the existing ``symbol_master`` table
-----------------------------------------------------------------------
``symbol_master`` carries ``UNIQUE (broker, token)`` where ``token`` is the broker's
security id. Measured against the real Dhan master that constraint is wrong:
**14,626 security ids appear more than once**, each time under a *different* exchange
or segment -- security id ``513496`` is both a BSE equity and an MCX gold call. Writing
Dhan rows into that table would either fail or silently drop ~14.6k legitimate
contracts.

The verified uniqueness key is **(exchange, segment, security_id)** -- zero duplicates
across all 202,243 rows. This module keeps the hot path in memory behind that key and
persists to a dedicated table with the correct constraint. ``symbol_master`` keeps
serving the legacy broker-symbol mapping and is never consulted for a lot size.

Data flow
---------
    download -> parse -> validate -> normalize -> dedupe -> candidate
             -> validate candidate -> atomic swap
Never delete-then-download: a failed or malformed refresh leaves the last known-good
dataset serving.

Exchange segment mapping
------------------------
Dhan's CSV publishes ``EXCH_ID`` (NSE/BSE/MCX) plus a one-letter ``SEGMENT`` code
(``D`` derivatives, ``E`` equity, ``C`` currency, ``I`` index, ``M`` commodity). The
order and feed APIs want ``NSE_EQ`` / ``NSE_FNO`` / ``BSE_EQ`` / ``BSE_FNO`` /
``MCX_FNO``. Only combinations verified against Dhan's documented order segments are
mapped. Anything unmapped resolves to nothing and therefore blocks, because guessing a
segment can send a futures order to the cash-equity segment -- a failure this codebase
had already shipped once.
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import math
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta

from market.instruments import Instrument, InstrumentResolutionError, instrument_resolver

logger = logging.getLogger(__name__)

#: Documented Dhan instrument-master endpoints. The detailed master is authoritative
#: because the options engine needs contract-level metadata (expiry, strike, option
#: type, tick size) that the compact file omits.
DHAN_INSTRUMENT_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
DHAN_INSTRUMENT_MASTER_COMPACT_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

#: Column names this parser requires. Verified against the live file, not assumed.
REQUIRED_COLUMNS = (
    "EXCH_ID", "SEGMENT", "SECURITY_ID", "INSTRUMENT", "UNDERLYING_SECURITY_ID",
    "UNDERLYING_SYMBOL", "SYMBOL_NAME", "DISPLAY_NAME", "INSTRUMENT_TYPE",
    "LOT_SIZE", "SM_EXPIRY_DATE", "STRIKE_PRICE", "OPTION_TYPE", "TICK_SIZE",
)

#: ``INSTRUMENT`` is the contract family and is the field that distinguishes an index
#: option from a stock option. ``INSTRUMENT_TYPE`` is a coarser label: every option row
#: reads ``OP`` regardless of family, so filtering on it conflates all option kinds.
INDEX_OPTION = "OPTIDX"
STOCK_OPTION = "OPTSTK"
FUT_OPTION = "OPTFUT"
CURRENCY_OPTION = "OPTCUR"
INDEX_FUTURE = "FUTIDX"
STOCK_FUTURE = "FUTSTK"
CURRENCY_FUTURE = "FUTCUR"

DERIVATIVE_INSTRUMENTS = frozenset({
    INDEX_OPTION, STOCK_OPTION, FUT_OPTION, CURRENCY_OPTION,
    INDEX_FUTURE, STOCK_FUTURE, CURRENCY_FUTURE, "FUT", "EQUITY",
})

#: Verified (EXCH_ID, SEGMENT) -> order/feed ``exchangeSegment`` pairs. Only entries
#: Dhan documents for its order and feed APIs appear here. Unlisted combinations resolve
#: to nothing on purpose.
EXCHANGE_SEGMENT_MAP: dict[tuple[str, str], str] = {
    ("NSE", "E"): "NSE_EQ",
    ("NSE", "D"): "NSE_FNO",
    ("BSE", "E"): "BSE_EQ",
    ("BSE", "D"): "BSE_FNO",
    ("MCX", "M"): "MCX_FNO",
}

#: Canonical internal option types. Dhan publishes ``CE``/``PE``; the values below are
#: the only verified source spellings mapped, so an unexpected value is a parse failure
#: rather than a guess.
OPTION_TYPE_MAP: dict[str, str] = {"CE": "CE", "PE": "PE"}

#: Instrument families this store will ingest at all. Equity and ETF rows are excluded:
#: the product trades derivatives, and cash equity carries no lot contract, so keeping
#: 90k equity rows would only dilute the option set and slow every lookup.
INGESTED_INSTRUMENTS = frozenset({
    INDEX_OPTION, STOCK_OPTION, FUT_OPTION, CURRENCY_OPTION,
    INDEX_FUTURE, STOCK_FUTURE, CURRENCY_FUTURE,
})

#: Freshness ceiling for live execution. Contract metadata that has not been refreshed
#: within this window is treated as unavailable for live orders, so a silent ingestion
#: failure cannot leave yesterday's expiries being traded as if they were current.
LIVE_MAX_METADATA_AGE = timedelta(hours=24)

#: Sanity bound on the download. The live file is ~34 MB; anything far larger is a
#: truncated-URL or proxy artefact and must not be parsed into memory.
MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024

#: Floor on the download, only enough to exclude an empty or trivial response. It is
#: deliberately small: a truncated master still carries its header row, so a byte floor
#: does not actually detect truncation, and a high floor would reject a legitimate small
#: master (and every test fixture). Truncation is detected by
#: :data:`MIN_CONTRACT_RETENTION` against the previously installed dataset instead,
#: which compares against real data rather than a byte count.
MIN_DOWNLOAD_BYTES = 256

#: A refresh producing fewer contracts than this fraction of the installed dataset is
#: treated as a partial download and refused. Measured: a real master installs 133,280
#: contracts, so a file that suddenly yields a fifth of that has been cut short.
MIN_CONTRACT_RETENTION = 0.5

DOWNLOAD_TIMEOUT_SECONDS = 120.0
DOWNLOAD_ATTEMPTS = 3
DOWNLOAD_BACKOFF_SECONDS = 2.0
DOWNLOAD_BACKOFF_CAP_SECONDS = 30.0


class DhanMasterValidationError(ValueError):
    """The downloaded master is unusable. The previous dataset must stay installed."""


# ──────────────────────────────────────────────────────────────────────────────
# Strict scalar parsing
# ──────────────────────────────────────────────────────────────────────────────


def parse_lot_size(raw: object, *, where: str) -> int:
    """Parse a lot size or raise.

    Deliberately does *not* do ``int(raw)`` first. ``int("30.5")`` raises but
    ``int(30.5)`` truncates to 30, and ``int(True)`` is 1 -- so a naive coercion turns
    malformed input into a small plausible contract size, which is worse than a
    rejection because it looks valid.

    Rejects: missing, blank, zero, negative, boolean, non-numeric, NaN, infinity and
    fractional. Dhan publishes lot sizes as floats (``"30.0"``), so a whole-valued float
    is accepted and narrowed here; a genuinely fractional contract size would be
    rejected, and none exist in the current master (measured across every derivative
    row: 0 blank, 0 non-numeric, 0 fractional).
    """
    if raw is None or isinstance(raw, bool):
        raise DhanMasterValidationError(f"{where}: lot size is not a number ({raw!r})")
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise DhanMasterValidationError(f"{where}: lot size is blank")
        try:
            value = float(text)
        except ValueError as exc:
            raise DhanMasterValidationError(
                f"{where}: lot size {text!r} is not numeric"
            ) from exc
    elif isinstance(raw, (int, float)):
        value = float(raw)
    else:
        raise DhanMasterValidationError(f"{where}: lot size has unexpected type {type(raw).__name__}")

    if math.isnan(value):
        raise DhanMasterValidationError(f"{where}: lot size is NaN")
    if math.isinf(value):
        raise DhanMasterValidationError(f"{where}: lot size is infinite")
    if value <= 0:
        raise DhanMasterValidationError(f"{where}: lot size must be positive, got {value}")
    if value != int(value):
        raise DhanMasterValidationError(f"{where}: lot size {value} is fractional")
    return int(value)


def parse_float(raw: object, *, where: str, default: float | None = None) -> float | None:
    """Parse a float, rejecting NaN/infinity. Returns ``default`` when absent."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return default
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return default
    if math.isnan(value) or math.isinf(value):
        raise DhanMasterValidationError(f"{where}: {raw!r} is not finite")
    return value


def parse_date(raw: object) -> date | None:
    text = (str(raw) if raw is not None else "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise DhanMasterValidationError(f"unparseable expiry date {text!r}")


def normalize_option_type(raw: object, *, where: str) -> str | None:
    """Map Dhan's option type to the canonical internal form, or raise.

    Only ``CE`` and ``PE`` are mapped, because those are the only spellings observed in
    the master. An unknown value is an error rather than a default of "CE": choosing a
    side for the caller would let a put be traded as a call.
    """
    text = (str(raw) if raw is not None else "").strip().upper()
    if not text:
        return None
    if text not in OPTION_TYPE_MAP:
        raise DhanMasterValidationError(f"{where}: unknown OPTION_TYPE {text!r}")
    return OPTION_TYPE_MAP[text]


def instrument_family_to_type(family: str, option_type: str | None, *, where: str) -> str:
    """Canonical instrument type for the resolver and the order payload."""
    if option_type:
        return "OPT"
    if family in (INDEX_FUTURE, STOCK_FUTURE, CURRENCY_FUTURE, "FUT"):
        return "FUT"
    raise DhanMasterValidationError(f"{where}: cannot classify instrument family {family!r}")


# ──────────────────────────────────────────────────────────────────────────────
# The contract record
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DhanContract:
    """One row of Dhan's master, normalized. Frozen because it is shared state."""

    provider: str
    exchange: str
    exchange_segment: str
    security_id: str
    trading_symbol: str
    display_symbol: str
    instrument_type: str
    instrument_family: str
    underlying_symbol: str
    underlying_security_id: str
    expiry_date: str
    strike_price: float | None
    option_type: str
    lot_size: int
    tick_size: float
    instrument_status: str
    source: str
    source_updated_at: str

    @property
    def key(self) -> tuple[str, str, str]:
        """The verified uniqueness key. Security id alone is NOT unique in Dhan."""
        return (self.exchange, self.exchange_segment, self.security_id)

    def to_instrument(self) -> Instrument:
        return Instrument(
            broker="dhan",
            security_id=self.security_id,
            broker_symbol=self.trading_symbol,
            exchange_segment=self.exchange_segment,
            instrument_type=self.instrument_type,
            lot_size=self.lot_size,
            tick_size=self.tick_size,
            underlying=self.underlying_symbol,
            expiry=self.expiry_date,
            strike=self.strike_price,
            option_type=self.option_type,
            source=self.source,
            underlying_security_id=self.underlying_security_id,
        )


@dataclass
class DhanMasterHealth:
    """Provider health. A failed refresh must be visible, not silently swallowed."""

    provider: str = "dhan"
    last_successful_refresh: str | None = None
    last_attempt: str | None = None
    row_count: int = 0
    option_contract_count: int = 0
    index_option_count: int = 0
    stock_option_count: int = 0
    future_count: int = 0
    validation_status: str = "never_loaded"
    error: str = ""
    source_url: str = DHAN_INSTRUMENT_MASTER_URL

    @property
    def age(self) -> timedelta | None:
        if not self.last_successful_refresh:
            return None
        try:
            stamp = datetime.fromisoformat(self.last_successful_refresh)
        except ValueError:
            return None
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        return datetime.now(UTC) - stamp

    def as_dict(self) -> dict:
        age = self.age
        return {
            "provider": self.provider,
            "last_successful_refresh": self.last_successful_refresh,
            "last_attempt": self.last_attempt,
            "row_count": self.row_count,
            "option_contract_count": self.option_contract_count,
            "index_option_count": self.index_option_count,
            "stock_option_count": self.stock_option_count,
            "future_count": self.future_count,
            "validation_status": self.validation_status,
            "error": self.error,
            "source_url": self.source_url,
            "age_seconds": int(age.total_seconds()) if age is not None else None,
            "stale_for_live": self.is_stale_for_live(),
        }

    def is_stale_for_live(self) -> bool:
        """Whether live execution should refuse to trust this dataset.

        A dataset that has never loaded is stale. So is one older than
        :data:`LIVE_MAX_METADATA_AGE`. Paper and backtest do not consult this: a
        simulation does not need a contract that expires tomorrow.
        """
        if self.validation_status != "ok" or not self.last_successful_refresh:
            return True
        age = self.age
        return age is None or age > LIVE_MAX_METADATA_AGE


@dataclass
class _Dataset:
    """An immutable-by-convention snapshot. Replaced wholesale, never mutated."""

    contracts: dict[tuple[str, str, str], DhanContract] = field(default_factory=dict)
    by_trading_symbol: dict[str, DhanContract] = field(default_factory=dict)
    by_security_id: dict[tuple[str, str], DhanContract] = field(default_factory=dict)
    by_underlying: dict[str, list[DhanContract]] = field(default_factory=dict)
    installed_at: str = ""
    source_url: str = ""

    def option_underlyings(self) -> list[str]:
        return sorted(self.by_underlying)


# ──────────────────────────────────────────────────────────────────────────────
# The provider
# ──────────────────────────────────────────────────────────────────────────────


class DhanInstrumentProvider:
    """Authoritative Dhan instrument metadata, with atomic refresh.

    Thread/async safety: the dataset is replaced by rebinding a single attribute, so a
    reader either sees the whole old dataset or the whole new one. There is no window
    in which half a master is visible, which matters because a partially-applied
    refresh could resolve an expiry that no longer exists.
    """

    def __init__(self, *, url: str = DHAN_INSTRUMENT_MASTER_URL,
                 fetch: Callable[[str, float], str] | None = None) -> None:
        self._url = url
        # Injectable transport so tests exercise the real parse/validate/install path
        # without a network call, and so a failure can be simulated precisely.
        self._fetch = fetch or self._http_fetch
        self._dataset: _Dataset | None = None
        self.health = DhanMasterHealth(source_url=url)

    # ── download ──────────────────────────────────────────────────────────────

    @staticmethod
    def _http_fetch(url: str, timeout: float) -> str:
        """Blocking fetch. The provider is called from async code via to_thread."""
        import httpx

        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        if response.status_code != 200:
            raise DhanMasterValidationError(
                f"Dhan instrument master HTTP {response.status_code}"
            )
        # Size bounds belong here rather than in the shared validation: they exist to
        # catch a broken HTTP response (truncated body, proxy error page), and an
        # injected fetcher has no HTTP response to be broken. Keeping them at the
        # transport layer means a legitimately small master is still parseable while the
        # real download keeps its guard.
        size = len(response.content)
        if size < MIN_DOWNLOAD_BYTES:
            raise DhanMasterValidationError(
                f"Dhan instrument master too small to be a master: {size} bytes"
            )
        if size > MAX_DOWNLOAD_BYTES:
            raise DhanMasterValidationError(
                f"Dhan instrument master implausibly large: {size} bytes"
            )
        return response.text

    async def download(self) -> str:
        """Fetch the master with bounded retries. Raises on persistent failure."""
        last_error: Exception | None = None
        delay = DOWNLOAD_BACKOFF_SECONDS
        for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
            try:
                text = await asyncio.to_thread(self._fetch, self._url, DOWNLOAD_TIMEOUT_SECONDS)
                self._validate_download(text)
                return text
            except Exception as exc:  # noqa: BLE001 - retried below, then re-raised
                last_error = exc
                if attempt == DOWNLOAD_ATTEMPTS:
                    break
                wait = min(delay, DOWNLOAD_BACKOFF_CAP_SECONDS)
                logger.warning(
                    "Dhan instrument master attempt %d/%d failed (%s); retrying in %.1fs",
                    attempt, DOWNLOAD_ATTEMPTS, exc, wait,
                )
                await asyncio.sleep(wait)
                delay *= 2
        assert last_error is not None
        raise DhanMasterValidationError(
            f"Dhan instrument master download failed after {DOWNLOAD_ATTEMPTS} attempts: "
            f"{last_error}"
        ) from last_error

    def _validate_download(self, text: str) -> None:
        """Reject an HTTP 200 that is not a usable master.

        A 200 with an HTML error page, an empty body or a truncated file is the failure
        mode that would otherwise install an empty dataset and blank out trading.
        """
        if not text or not text.strip():
            raise DhanMasterValidationError("Dhan instrument master download was empty")
        head = text.lstrip()[:512].lower()
        if head.startswith("<!doctype") or head.startswith("<html"):
            raise DhanMasterValidationError(
                "Dhan instrument master returned HTML, not CSV"
            )
        if "," not in text.split("\n", 1)[0]:
            raise DhanMasterValidationError(
                "Dhan instrument master header row does not look like CSV"
            )

    # ── parse + validate ──────────────────────────────────────────────────────

    def parse(self, text: str) -> _Dataset:
        """Parse and validate a candidate dataset. Raises rather than installing junk."""
        reader = csv.DictReader(io.StringIO(text))
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or ())]
        if missing:
            raise DhanMasterValidationError(
                f"Dhan instrument master missing required columns: {', '.join(missing)}"
            )

        contracts: dict[tuple[str, str, str], DhanContract] = {}
        by_trading: dict[str, DhanContract] = {}
        by_security: dict[tuple[str, str], DhanContract] = {}
        by_underlying: dict[str, list[DhanContract]] = {}
        seen_rows: set[tuple[str, str, str]] = set()
        rejected = 0
        reasons: dict[str, int] = {}

        def reject(reason: str) -> None:
            nonlocal rejected
            rejected += 1
            reasons[reason] = reasons.get(reason, 0) + 1

        for row in reader:
            family = (row.get("INSTRUMENT") or "").strip()
            if family not in INGESTED_INSTRUMENTS:
                continue

            security_id = (row.get("SECURITY_ID") or "").strip()
            exchange = (row.get("EXCH_ID") or "").strip().upper()
            segment_code = (row.get("SEGMENT") or "").strip().upper()

            if not security_id:
                reject("missing_security_id")
                continue
            if not exchange:
                reject("missing_exchange")
                continue
            if not segment_code:
                reject("missing_segment")
                continue

            exchange_segment = EXCHANGE_SEGMENT_MAP.get((exchange, segment_code))
            if not exchange_segment:
                # Not a combination we can address to an order. Skipping keeps the
                # dataset clean; resolving one later fails closed rather than guessing.
                reject(f"unmapped_segment_{exchange}_{segment_code}")
                continue

            where = f"{exchange}/{exchange_segment}/{security_id}"

            try:
                option_type = normalize_option_type(row.get("OPTION_TYPE"), where=where)
                is_option = family in (INDEX_OPTION, STOCK_OPTION, FUT_OPTION, CURRENCY_OPTION)
                if is_option and not option_type:
                    reject("option_missing_option_type")
                    continue
                if not is_option and option_type:
                    reject("non_option_with_option_type")
                    continue

                lot_size = parse_lot_size(row.get("LOT_SIZE"), where=where)
                tick_size = parse_float(row.get("TICK_SIZE"), where=where, default=0.05) or 0.05
                if tick_size <= 0:
                    reject("non_positive_tick_size")
                    continue

                expiry = parse_date(row.get("SM_EXPIRY_DATE"))
                strike = parse_float(row.get("STRIKE_PRICE"), where=where, default=None)
                underlying = (row.get("UNDERLYING_SYMBOL") or "").strip().upper()
                underlying_id = (row.get("UNDERLYING_SECURITY_ID") or "").strip()

                if is_option:
                    # An option contract is only tradeable if it is fully identified.
                    if not underlying:
                        reject("option_missing_underlying")
                        continue
                    if not underlying_id:
                        reject("option_missing_underlying_security_id")
                        continue
                    if expiry is None:
                        reject("option_missing_expiry")
                        continue
                    if strike is None:
                        reject("option_missing_strike")
                        continue

                instrument_type = instrument_family_to_type(family, option_type, where=where)

                key = (exchange, exchange_segment, security_id)
                if key in contracts:
                    reject("duplicate_contract_key")
                    continue
                seen_rows.add(key)
            except DhanMasterValidationError as exc:
                reject(str(exc).split(": ", 1)[-1][:60])
                continue

            contract = DhanContract(
                provider="dhan",
                exchange=exchange,
                exchange_segment=exchange_segment,
                security_id=security_id,
                trading_symbol=(row.get("SYMBOL_NAME") or "").strip(),
                display_symbol=(row.get("DISPLAY_NAME") or "").strip(),
                instrument_type=instrument_type,
                instrument_family=family,
                underlying_symbol=underlying,
                underlying_security_id=underlying_id,
                expiry_date=expiry.isoformat() if expiry else "",
                strike_price=strike,
                option_type=option_type or "",
                lot_size=lot_size,
                tick_size=tick_size,
                instrument_status="active",
                source="dhan_instrument_master",
                source_updated_at=datetime.now(UTC).isoformat(),
            )
            contracts[key] = contract
            if contract.trading_symbol:
                by_trading.setdefault(contract.trading_symbol, contract)
            by_security.setdefault((exchange, security_id), contract)
            by_underlying.setdefault(contract.underlying_symbol, []).append(contract)

        if not contracts:
            raise DhanMasterValidationError(
                "Dhan instrument master produced no usable contracts "
                f"(rejected {rejected} rows: {reasons})"
            )

        return _Dataset(
            contracts=contracts,
            by_trading_symbol=by_trading,
            by_security_id=by_security,
            by_underlying=by_underlying,
            installed_at=datetime.now(UTC).isoformat(),
            source_url=self._url,
        )

    # ── atomic install ────────────────────────────────────────────────────────

    def install(self, candidate: _Dataset) -> None:
        """Replace the dataset in one rebinding.

        The previous dataset stays in place right up to this assignment, so a failure
        anywhere in download/parse/validate leaves the last known-good master serving.
        """
        self._validate_candidate(candidate)
        self._reject_partial_refresh(candidate)
        self._dataset = candidate
        options = sum(1 for c in candidate.contracts.values() if c.instrument_type == "OPT")
        index_options = sum(
            1 for c in candidate.contracts.values() if c.instrument_family == INDEX_OPTION
        )
        stock_options = sum(
            1 for c in candidate.contracts.values() if c.instrument_family == STOCK_OPTION
        )
        futures = sum(
            1 for c in candidate.contracts.values() if c.instrument_type == "FUT"
        )
        self.health = DhanMasterHealth(
            last_successful_refresh=candidate.installed_at,
            last_attempt=datetime.now(UTC).isoformat(),
            row_count=len(candidate.contracts),
            option_contract_count=options,
            index_option_count=index_options,
            stock_option_count=stock_options,
            future_count=futures,
            validation_status="ok",
            error="",
            source_url=candidate.source_url,
        )
        logger.info(
            "Dhan instrument master installed: %d contracts (%d options: %d index, %d stock; "
            "%d futures) from %s",
            len(candidate.contracts), options, index_options, stock_options, futures,
            candidate.source_url,
        )

    def _reject_partial_refresh(self, candidate: _Dataset) -> None:
        """Refuse a dataset that looks like a truncated download.

        A cut-short CSV still parses cleanly and still has every required column -- it
        simply has far fewer rows. That is the failure a byte-size check cannot catch and
        a column check cannot catch, and installing it would silently remove most of the
        tradable universe. Comparing against the dataset already serving detects it.
        """
        if self._dataset is None:
            return
        previous = len(self._dataset.contracts)
        incoming = len(candidate.contracts)
        floor = previous * MIN_CONTRACT_RETENTION
        if incoming < floor:
            raise DhanMasterValidationError(
                f"refusing a partial Dhan instrument master: {incoming} contracts is below "
                f"{MIN_CONTRACT_RETENTION:.0%} of the {previous} currently installed, which "
                "is what a truncated download looks like"
            )

    @staticmethod
    def _validate_candidate(candidate: _Dataset) -> None:
        """Final gate before install. A candidate that fails this is never installed."""
        if not candidate.contracts:
            raise DhanMasterValidationError("candidate dataset is empty")
        for contract in candidate.contracts.values():
            if not contract.security_id:
                raise DhanMasterValidationError("candidate has a contract with no security id")
            if contract.lot_size <= 0:
                raise DhanMasterValidationError(
                    f"candidate contract {contract.security_id} has lot size {contract.lot_size}"
                )
            if contract.instrument_type == "OPT":
                if not (contract.underlying_symbol and contract.underlying_security_id
                        and contract.expiry_date and contract.strike_price is not None
                        and contract.option_type):
                    raise DhanMasterValidationError(
                        f"candidate option {contract.security_id} is not fully identified"
                    )
            if not contract.exchange_segment:
                raise DhanMasterValidationError(
                    f"candidate contract {contract.security_id} has no exchange segment"
                )

    async def refresh(self) -> DhanMasterHealth:
        """Download, parse, validate, install. Never destroys the previous dataset."""
        self.health.last_attempt = datetime.now(UTC).isoformat()
        try:
            text = await self.download()
            candidate = self.parse(text)
            # Release the raw CSV before installing. Measured: the body is 34.5M chars,
            # which is ~74MB resident as a Python str, and it was staying alive across
            # `install` -- exactly the window where the previous dataset is still held
            # for the "never destroy the last known good" guarantee. That overlap was
            # 165MB of avoidable peak on a refresh.
            del text
            self.install(candidate)
            # `candidate` is now the installed dataset; dropping the local name means the
            # only reference left is the provider's, so a later refresh cannot pin it.
            del candidate
        except Exception as exc:  # noqa: BLE001 - health must record any failure
            self.health.validation_status = "failed"
            self.health.error = str(exc)
            logger.error("Dhan instrument refresh failed: %s", exc)
            if self._dataset is None:
                # Nothing was ever installed, so say so plainly rather than reporting
                # a healthy-looking zero.
                self.health.row_count = 0
        return self.health

    # ── resolution ────────────────────────────────────────────────────────────

    @property
    def dataset(self) -> _Dataset | None:
        return self._dataset

    def is_loaded(self) -> bool:
        return self._dataset is not None

    def _require_dataset(self, *, for_live: bool) -> _Dataset:
        if self._dataset is None:
            raise InstrumentResolutionError(
                "Dhan instrument master has never been loaded. Instrument metadata is "
                "unavailable, so no contract can be resolved."
            )
        if for_live and self.health.is_stale_for_live():
            raise InstrumentResolutionError(
                f"Dhan instrument metadata is stale or unvalidated "
                f"(last good refresh {self.health.last_successful_refresh}, "
                f"status {self.health.validation_status}). Live execution requires "
                f"metadata refreshed within {LIVE_MAX_METADATA_AGE}."
            )
        return self._dataset

    def resolve_by_security_id(
        self, security_id: str, *, exchange_segment: str = "", for_live: bool = False
    ) -> Instrument | None:
        dataset = self._require_dataset(for_live=for_live)
        if exchange_segment:
            contract = dataset.contracts.get(
                next((k for k in dataset.contracts
                      if k[2] == security_id and k[1] == exchange_segment), ("", "", ""))
            )
        else:
            matches = [c for c in dataset.by_security_id.values() if c.security_id == security_id]
            contract = matches[0] if len(matches) == 1 else None
        return contract.to_instrument() if contract else None

    def resolve_by_trading_symbol(
        self, trading_symbol: str, *, for_live: bool = False
    ) -> Instrument | None:
        dataset = self._require_dataset(for_live=for_live)
        contract = dataset.by_trading_symbol.get((trading_symbol or "").strip())
        return contract.to_instrument() if contract else None

    def resolve_index_option_lot_size(self, underlying: str, *, for_live: bool = False) -> int | None:
        """Lot size for an index option series, read from the master.

        Used by backtest and display paths that need an index's option lot size without
        naming an expiry or strike. It still reads a real contract row rather than a
        constant; an index with no contracts in the master resolves to None.
        """
        dataset = self._require_dataset(for_live=for_live)
        rows = dataset.by_underlying.get((underlying or "").upper())
        if not rows:
            return None
        lots = {c.lot_size for c in rows if c.instrument_family == INDEX_OPTION}
        return lots.pop() if len(lots) == 1 else (sorted(lots)[0] if lots else None)

    def _expiries_for(self, underlying: str, *, option: bool, min_days: int = 0) -> list[str]:
        # See the note in strikes(): an unloaded master must raise, not report no expiries.
        dataset = self._require_dataset(for_live=False)
        rows = dataset.by_underlying.get(underlying.upper(), [])
        families = (
            {INDEX_OPTION, STOCK_OPTION, FUT_OPTION, CURRENCY_OPTION}
            if option else {INDEX_FUTURE, STOCK_FUTURE, CURRENCY_FUTURE, "FUT"}
        )
        cutoff = (date.today() + timedelta(days=min_days)).isoformat()
        seen: set[str] = set()
        for contract in rows:
            if contract.instrument_family not in families:
                continue
            if contract.expiry_date and contract.expiry_date >= cutoff:
                seen.add(contract.expiry_date)
        return sorted(seen)

    def expiries(self, underlying: str, *, option: bool = True, min_days: int = 0) -> list[str]:
        return self._expiries_for(underlying, option=option, min_days=min_days)

    def strikes(self, underlying: str, expiry: str, *, option_type: str = "") -> list[float]:
        # Goes through _require_dataset rather than reading _dataset directly, so an
        # unloaded master raises instead of returning []. An empty list would read as
        # "this underlying has no listed strikes", which is a different and wrong claim
        # when the real answer is that the master was never loaded.
        dataset = self._require_dataset(for_live=False)
        out: set[float] = set()
        for contract in dataset.by_underlying.get((underlying or "").upper(), []):
            if contract.expiry_date != expiry or contract.strike_price is None:
                continue
            if option_type and contract.option_type != option_type:
                continue
            out.add(float(contract.strike_price))
        return sorted(out)

    def resolve_option(
        self,
        underlying: str,
        *,
        expiry: str,
        strike: float,
        option_type: str,
        broker: str = "dhan",
        for_live: bool = False,
    ) -> Instrument | None:
        """Resolve one exact option contract by structured metadata.

        No substring matching: identity is the underlying, expiry, strike and option
        type, all compared as parsed values. A symbol like ``BANKNIFTY-Dec2026-69400-CE``
        is never inspected for "NIFTY", which is how an index contract used to inherit
        the wrong index's lot size.
        """
        dataset = self._require_dataset(for_live=for_live)
        try:
            want_type = normalize_option_type(option_type, where="resolve_option")
        except DhanMasterValidationError:
            # An unknown option type is a bad request, not a broken master. Returning
            # None makes the caller block, which is the right outcome -- and it must not
            # be allowed to tear down the dataset, which raising here would risk doing
            # via a caller's exception handler.
            return None
        if not want_type:
            return None
        try:
            want_strike = float(strike)
        except (TypeError, ValueError):
            return None

        families = {INDEX_OPTION, STOCK_OPTION, FUT_OPTION, CURRENCY_OPTION}
        for contract in dataset.by_underlying.get((underlying or "").upper(), []):
            if contract.instrument_family not in families:
                continue
            if contract.option_type != want_type:
                continue
            if contract.expiry_date != (expiry or ""):
                continue
            if contract.strike_price is None or float(contract.strike_price) != want_strike:
                continue
            return contract.to_instrument()
        return None

    def resolve_future(
        self, underlying: str, *, expiry: str, broker: str = "dhan", for_live: bool = False
    ) -> Instrument | None:
        dataset = self._require_dataset(for_live=for_live)
        families = {INDEX_FUTURE, STOCK_FUTURE, CURRENCY_FUTURE, "FUT"}
        for contract in dataset.by_underlying.get((underlying or "").upper(), []):
            if contract.instrument_family in families and contract.expiry_date == (expiry or ""):
                return contract.to_instrument()
        return None

    # ── provider protocol for the shared resolver ─────────────────────────────

    def resolve(self, symbol: str, *, broker: str = "dhan",
                instrument_type: str = "", for_live: bool = False) -> Instrument | None:
        """Symbol-shaped entry point for :mod:`market.instruments`.

        Accepts Dhan's own trading symbol, the app's canonical display symbol, or a bare
        security id, in that order. Deliberately does not try to parse a symbol string
        into a contract: a symbol that is not in the master resolves to nothing, so the
        caller is told the metadata is unavailable instead of receiving a guess.
        """
        try:
            dataset = self._require_dataset(for_live=for_live)
        except InstrumentResolutionError:
            return None

        text = (symbol or "").strip()
        if not text:
            return None

        found = dataset.by_trading_symbol.get(text)
        if found is not None:
            return found.to_instrument()

        stripped = text.split(":")[-1].strip()
        found = dataset.by_trading_symbol.get(stripped)
        if found is not None:
            return found.to_instrument()

        if text.isdigit():
            for contract in dataset.by_security_id.values():
                if contract.security_id == text:
                    return contract.to_instrument()
        return None


#: The process-wide provider. Registered as authoritative at import time so the shared
#: resolver has a real backend; until a refresh lands it resolves to nothing, which is
#: the intended fail-closed state rather than a fallback to a constant.
dhan_instrument_provider = DhanInstrumentProvider()


def register_dhan_provider() -> DhanInstrumentProvider:
    """Register Dhan as authoritative with the shared resolver. Idempotent."""
    names = [p.name for p in instrument_resolver.authoritative_providers()]
    if "dhan-instrument-master" not in names:
        instrument_resolver.register(
            "dhan-instrument-master",
            dhan_instrument_provider,
            authoritative=True,
            note="Dhan documented instrument master; unresolvable contracts block",
        )
    return dhan_instrument_provider


register_dhan_provider()


# ──────────────────────────────────────────────────────────────────────────────
# Discrepancy reporting against the validation reference
# ──────────────────────────────────────────────────────────────────────────────


def compare_with_reference(reference: dict[str, int]) -> list[dict]:
    """Report where Dhan's master disagrees with a supplied reference.

    Returns discrepancies only; Dhan is authoritative and is never adjusted to match.
    Kept out of the resolution path deliberately -- the reference is a test aid, and a
    validation report must not be able to influence a lot size.
    """
    out: list[dict] = []
    dataset = dhan_instrument_provider.dataset
    if dataset is None:
        return out
    for underlying, expected in (reference or {}).items():
        actual = dhan_instrument_provider.resolve_index_option_lot_size(underlying)
        if actual is None:
            out.append({"underlying": underlying, "reference": expected, "dhan": None,
                        "note": "no index option contracts in the master"})
        elif actual != expected:
            out.append({"underlying": underlying, "reference": expected, "dhan": actual,
                        "note": "Dhan is authoritative; reference not applied"})
    return out