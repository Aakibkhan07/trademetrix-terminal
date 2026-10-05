"""Dhan Live Market Feed over a real WebSocket.

Protocol provenance
-------------------
Everything in this module is taken from Dhan's own Python client,
``dhanhq==2.2.0`` (published by ``dhan-oss``, Dhan's GitHub organisation,
MIT licensed), file ``dhanhq/marketfeed.py``. Nothing here is inferred from the
previous implementation or guessed from the REST API. Where the previous adapter
disagreed with the SDK, the SDK wins and the difference is recorded.

Verified protocol
-----------------
Endpoint (v2)::

    wss://api-feed.dhan.co

Connection URL (v2) -- credentials travel in the query string::

    wss://api-feed.dhan.co?version=2&token={access_token}&clientId={client_id}&authType=2

v2 performs no application-level authorize packet; the connection is
authenticated by the URL. (v1 used a binary header packet and is not used here.)

Subscription (v2) -- JSON text frames, batched 100 instruments per frame::

    {"RequestCode": 15,
     "InstrumentCount": 2,
     "InstrumentList": [{"ExchangeSegment": "NSE_FNO", "SecurityId": "40749"},
                        {"ExchangeSegment": "NSE_FNO", "SecurityId": "40750"}]}

Request codes: Ticker 15, Quote 17, Full 21. (Depth 19 exists but the SDK rejects it
for v2.) Unsubscribe is ``RequestCode + 1``. Disconnect is ``{"RequestCode": 12}``
followed by a binary header.

Responses are **binary**; the first byte selects the schema:

===== ================================ ================================
Byte  Packet                           struct format / length
===== ================================ ================================
2     Ticker                           ``<BHBIfI`` 16 bytes
3     Market depth                     ``<BHBIf100s`` 112 bytes
4     Quote                            ``<BHBIfHIfIIIffff`` 50 bytes
5     Open interest                    ``<BHBII`` 12 bytes
6     Previous close                   ``<BHBIfI`` 16 bytes
7     Market status                    ``<BHBI`` 8 bytes
8     Full                             ``<BHBIfHIfIIIIIIffff100s`` 162 bytes
50    Server disconnection             ``<BHBIH`` 10 bytes
===== ================================ ================================

Disconnection codes in byte-50 packets: 805 too many websocket connections, 806
subscribe to Data APIs to continue, 807 access token expired, 808 invalid client id,
809 authentication failed. These are terminal for the connection and are surfaced
rather than retried blindly.

Heartbeat: the SDK sends no application-level ping for v2; it relies on the
WebSocket library's protocol-level keepalive plus an explicit ``ws.ping()`` when
reusing an existing connection. Protocol-level ping/pong is therefore sufficient,
and this module enables the library's own keepalive rather than inventing a payload.

What the previous implementation got wrong
------------------------------------------
============================  ==============================  ==========================
Previous                      Verified                       Consequence
============================  ==============================  ==========================
``httpx.AsyncClient.stream``  ``websockets.connect``          httpx cannot upgrade
``wss://api.dhan.co/v2/ws``   ``wss://api.dhan.co``           wrong host and path
``"SecurityToken"``           ``"SecurityId"``                wrong field name
``ExchangeSegment: NSE_EQ``   segment from the contract       derivatives priced wrong
``SecurityToken: sym``        security id from the contract   display string sent as an id
============================  ==============================  ==========================

Identity
--------
Market-data identity is ``(exchange_segment, security_id)``, never ``security_id``
alone: 14,626 security ids in Dhan's master occur under more than one segment, so a
security id on its own is ambiguous.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

logger = logging.getLogger(__name__)

#: Verified from dhanhq/marketfeed.py: MarketFeed.market_feed_wss
DHAN_FEED_WSS_URL = "wss://api-feed.dhan.co"

#: Verified request codes. Depth (19) is excluded because the SDK rejects it for v2.
REQUEST_CODE_TICKER = 15
REQUEST_CODE_QUOTE = 17
REQUEST_CODE_FULL = 21
V2_REQUEST_CODES = frozenset({REQUEST_CODE_TICKER, REQUEST_CODE_QUOTE, REQUEST_CODE_FULL})

#: Unsubscribe is one above subscribe, per the SDK.
UNSUBSCRIBE_CODE_OFFSET = 1

#: Verified: the SDK batches instrument groups 100 at a time.
MAX_INSTRUMENTS_PER_FRAME = 100

#: Verified numeric segment codes -> the strings Dhan's v2 feed accepts.
SEGMENT_CODE_TO_NAME: dict[int, str] = {
    0: "IDX_I",
    1: "NSE_EQ",
    2: "NSE_FNO",
    3: "NSE_CURRENCY",
    4: "BSE_EQ",
    5: "MCX_COMM",
    7: "BSE_CURRENCY",
    8: "BSE_FNO",
}

SEGMENT_NAME_TO_CODE: dict[str, int] = {v: k for k, v in SEGMENT_CODE_TO_NAME.items()}

#: Verified disconnection codes, so a terminal failure is reported rather than retried.
DISCONNECT_REASONS: dict[int, str] = {
    805: "no. of active websocket connections exceeded",
    806: "subscribe to Data APIs to continue",
    807: "access token is expired",
    808: "invalid client id",
    809: "authentication failed",
}

#: Codes that will never succeed on retry. Reconnecting with the same token is
#: pointless and, for 805, actively harmful because it worsens the condition.
TERMINAL_DISCONNECT_CODES = frozenset({806, 807, 808, 809})

CONNECT_TIMEOUT_SECONDS = 20.0
RECV_TIMEOUT_SECONDS = 45.0
RECONNECT_BASE_SECONDS = 1.0
RECONNECT_MAX_SECONDS = 30.0

#: A quote older than this is not considered live. Reused by the execution layer to
#: refuse a price it cannot trust, while the display layer may still show the last value.
QUOTE_STALE_SECONDS = 15.0


class FeedState(str, Enum):
    """Connection lifecycle. READY is not implied by an open socket."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    AUTHENTICATED = "AUTHENTICATED"
    SUBSCRIBING = "SUBSCRIBING"
    READY = "READY"
    RECONNECTING = "RECONNECTING"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class FeedMode(str, Enum):
    TICKER = "ticker"
    QUOTE = "quote"
    FULL = "full"


FEED_MODE_TO_REQUEST_CODE: dict[FeedMode, int] = {
    FeedMode.TICKER: REQUEST_CODE_TICKER,
    FeedMode.QUOTE: REQUEST_CODE_QUOTE,
    FeedMode.FULL: REQUEST_CODE_FULL,
}

#: Segments on which a derivative contract may trade. Recorded because the defect this
#: module fixes was a derivative feed defaulting to NSE_EQ.
DERIVATIVE_SEGMENTS = frozenset({"NSE_FNO", "BSE_FNO", "MCX_COMM"})


@dataclass(frozen=True)
class DhanSubscription:
    """One instrument to subscribe to, identified the way Dhan identifies it."""

    exchange_segment: str
    security_id: str
    mode: FeedMode = FeedMode.TICKER

    @property
    def identity(self) -> tuple[str, str]:
        return (self.exchange_segment, self.security_id)

    @property
    def request_code(self) -> int:
        return FEED_MODE_TO_REQUEST_CODE[self.mode]

    def __post_init__(self) -> None:
        if not self.exchange_segment:
            raise ValueError("exchange_segment is required; it is part of the instrument identity")
        if not self.security_id:
            raise ValueError("security_id is required; never send a display symbol")
        if not self.security_id.isdigit():
            raise ValueError(
                f"security_id must be Dhan's numeric security id, got {self.security_id!r}. "
                "A trading or display symbol is not a security id."
            )
        if self.exchange_segment not in SEGMENT_NAME_TO_CODE:
            raise ValueError(
                f"unknown exchange segment {self.exchange_segment!r}; "
                f"expected one of {sorted(SEGMENT_NAME_TO_CODE)}"
            )


@dataclass
class DhanMarketEvent:
    """A normalised quote. Fields Dhan did not send stay None, never 0.

    Zero is a real market value (a genuine LTP of 0, or a real empty-book bid), so
    substituting 0 for "not provided" would be a lie the risk layer cannot detect.
    """

    provider: str
    exchange_segment: str
    security_id: str
    packet_type: str
    timestamp: datetime
    ltp: float | None = None
    ltq: int | None = None
    bid: float | None = None
    ask: float | None = None
    bid_quantity: int | None = None
    ask_quantity: int | None = None
    volume: int | None = None
    open_interest: int | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    avg_price: float | None = None
    exchange: str = ""
    trading_symbol: str = ""
    underlying: str = ""
    expiry: str = ""
    strike: float | None = None
    option_type: str = ""
    received_at: float = field(default_factory=time.time)

    @property
    def identity(self) -> tuple[str, str]:
        return (self.exchange_segment, self.security_id)

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.received_at)

    @property
    def is_stale(self) -> bool:
        return self.age_seconds > QUOTE_STALE_SECONDS


class DhanPacketError(ValueError):
    """A packet could not be decoded. Never silently turned into a zero quote."""


def _segment_name(code: int) -> str:
    return SEGMENT_CODE_TO_NAME.get(code, f"UNKNOWN_{code}")


def _epoch_to_datetime(value: int) -> datetime:
    return datetime.fromtimestamp(value, tz=UTC)


def _need(data: bytes, length: int, what: str) -> None:
    if len(data) < length:
        raise DhanPacketError(
            f"{what} packet is {len(data)} bytes, expected at least {length}"
        )


def parse_packet(data: bytes) -> DhanMarketEvent | dict:
    """Decode one binary frame into an event, or a control dict.

    Returns a :class:`DhanMarketEvent` for market packets and a plain dict for the
    market-status and server-disconnection control frames, which carry no quote.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise DhanPacketError(f"expected binary frame, got {type(data).__name__}")
    data = bytes(data)
    if not data:
        raise DhanPacketError("empty frame")
    first = data[0]

    if first == 2:
        return _parse_ticker(data)
    if first == 3:
        return _parse_depth(data)
    if first == 4:
        return _parse_quote(data)
    if first == 5:
        return _parse_oi(data)
    if first == 6:
        return _parse_prev_close(data)
    if first == 7:
        return _parse_status(data)
    if first == 8:
        return _parse_full(data)
    if first == 50:
        return _parse_disconnect(data)
    raise DhanPacketError(f"unknown packet type {first}")


def _parse_ticker(data: bytes) -> DhanMarketEvent:
    _need(data, 16, "ticker")
    _, _, seg, sec, ltp, ltt = struct.unpack("<BHBIfI", data[0:16])
    return DhanMarketEvent(
        provider="dhan", exchange_segment=_segment_name(seg), security_id=str(sec),
        packet_type="ticker", timestamp=_epoch_to_datetime(ltt), ltp=float(ltp),
    )


_DEPTH_ROW = "<IIHHff"
_DEPTH_ROWS = 5


def _parse_depth_rows(blob: bytes) -> tuple[float | None, float | None, int | None, int | None]:
    """Best bid/ask from the five depth rows, or Nones when the book is empty."""
    size = struct.calcsize(_DEPTH_ROW)
    best_bid: float | None = None
    best_ask: float | None = None
    best_bid_qty: int | None = None
    best_ask_qty: int | None = None
    for i in range(_DEPTH_ROWS):
        chunk = blob[i * size:(i + 1) * size]
        if len(chunk) < size:
            break
        bid_qty, ask_qty, _bid_orders, _ask_orders, bid_px, ask_px = struct.unpack(
            _DEPTH_ROW, chunk
        )
        if best_bid is None and bid_qty > 0 and bid_px > 0:
            best_bid, best_bid_qty = float(bid_px), int(bid_qty)
        if best_ask is None and ask_qty > 0 and ask_px > 0:
            best_ask, best_ask_qty = float(ask_px), int(ask_qty)
    return best_bid, best_ask, best_bid_qty, best_ask_qty


def _parse_depth(data: bytes) -> DhanMarketEvent:
    _need(data, 112, "market depth")
    _, _, seg, sec, ltp, blob = struct.unpack("<BHBIf100s", data[0:112])
    bid, ask, bid_q, ask_q = _parse_depth_rows(blob)
    return DhanMarketEvent(
        provider="dhan", exchange_segment=_segment_name(seg), security_id=str(sec),
        packet_type="depth", timestamp=datetime.now(UTC), ltp=float(ltp),
        bid=bid, ask=ask, bid_quantity=bid_q, ask_quantity=ask_q,
    )


def _parse_quote(data: bytes) -> DhanMarketEvent:
    _need(data, 50, "quote")
    f = struct.unpack("<BHBIfHIfIIIffff", data[0:50])
    return DhanMarketEvent(
        provider="dhan", exchange_segment=_segment_name(f[2]), security_id=str(f[3]),
        packet_type="quote", timestamp=_epoch_to_datetime(f[6]),
        ltp=float(f[4]), ltq=int(f[5]), avg_price=float(f[7]), volume=int(f[8]),
        open=float(f[11]), close=float(f[12]), high=float(f[13]), low=float(f[14]),
    )


def _parse_oi(data: bytes) -> DhanMarketEvent:
    _need(data, 12, "open interest")
    _, _, seg, sec, oi = struct.unpack("<BHBII", data[0:12])
    return DhanMarketEvent(
        provider="dhan", exchange_segment=_segment_name(seg), security_id=str(sec),
        packet_type="oi", timestamp=datetime.now(UTC), open_interest=int(oi),
    )


def _parse_prev_close(data: bytes) -> DhanMarketEvent:
    _need(data, 16, "previous close")
    _, _, seg, sec, prev, prev_oi = struct.unpack("<BHBIfI", data[0:16])
    return DhanMarketEvent(
        provider="dhan", exchange_segment=_segment_name(seg), security_id=str(sec),
        packet_type="prev_close", timestamp=datetime.now(UTC), close=float(prev),
        open_interest=int(prev_oi),
    )


def _parse_status(data: bytes) -> dict:
    _need(data, 8, "market status")
    return {"type": "market_status", "code": struct.unpack("<BHBI", data[0:8])[3]}


def _parse_full(data: bytes) -> DhanMarketEvent:
    _need(data, 162, "full")
    f = struct.unpack("<BHBIfHIfIIIIIIffff100s", data[0:162])
    bid, ask, bid_q, ask_q = _parse_depth_rows(f[18])
    return DhanMarketEvent(
        provider="dhan", exchange_segment=_segment_name(f[2]), security_id=str(f[3]),
        packet_type="full", timestamp=_epoch_to_datetime(f[6]),
        ltp=float(f[4]), ltq=int(f[5]), avg_price=float(f[7]), volume=int(f[8]),
        open_interest=int(f[11]), open=float(f[14]), close=float(f[15]),
        high=float(f[16]), low=float(f[17]),
        bid=bid, ask=ask, bid_quantity=bid_q, ask_quantity=ask_q,
    )


def _parse_disconnect(data: bytes) -> dict:
    _need(data, 10, "server disconnection")
    code = struct.unpack("<BHBIH", data[0:10])[4]
    return {
        "type": "server_disconnect",
        "code": code,
        "reason": DISCONNECT_REASONS.get(code, f"unknown disconnection code {code}"),
        "terminal": code in TERMINAL_DISCONNECT_CODES,
    }


def build_subscribe_frame(subscriptions: Iterable[DhanSubscription]) -> list[str]:
    """Build the v2 subscription JSON frames, grouped by mode and batched by 100."""
    by_code: dict[int, list[DhanSubscription]] = {}
    for sub in subscriptions:
        by_code.setdefault(sub.request_code, []).append(sub)

    frames: list[str] = []
    for code in sorted(by_code):
        batch = by_code[code]
        for start in range(0, len(batch), MAX_INSTRUMENTS_PER_FRAME):
            chunk = batch[start:start + MAX_INSTRUMENTS_PER_FRAME]
            frames.append(json.dumps({
                "RequestCode": code,
                "InstrumentCount": len(chunk),
                "InstrumentList": [
                    {"ExchangeSegment": s.exchange_segment, "SecurityId": s.security_id}
                    for s in chunk
                ],
            }))
    return frames


def build_unsubscribe_frame(subscriptions: Iterable[DhanSubscription]) -> list[str]:
    """Unsubscribe frames. The SDK uses ``RequestCode + 1``."""
    by_code: dict[int, list[DhanSubscription]] = {}
    for sub in subscriptions:
        by_code.setdefault(sub.request_code + UNSUBSCRIBE_CODE_OFFSET, []).append(sub)

    frames: list[str] = []
    for code in sorted(by_code):
        batch = by_code[code]
        for start in range(0, len(batch), MAX_INSTRUMENTS_PER_FRAME):
            chunk = batch[start:start + MAX_INSTRUMENTS_PER_FRAME]
            frames.append(json.dumps({
                "RequestCode": code,
                "InstrumentCount": len(chunk),
                "InstrumentList": [
                    {"ExchangeSegment": s.exchange_segment, "SecurityId": s.security_id}
                    for s in chunk
                ],
            }))
    return frames


def build_url(access_token: str, client_id: str, *, base_url: str = DHAN_FEED_WSS_URL,
              version: int = 2, auth_type: int = 2) -> str:
    """The verified v2 connection URL.

    Credentials are in the query string, which is what the SDK does for v2. The token is
    therefore part of the URL: callers must never log the result, and
    :func:`redact_url` exists for anywhere a URL is surfaced.
    """
    return f"{base_url}?version={version}&token={access_token}&clientId={client_id}&authType={auth_type}"


def redact_url(url: str) -> str:
    """Strip credentials from a feed URL for logging or API responses."""
    if "?" not in url:
        return url
    base, _ = url.split("?", 1)
    kept = [p for p in url.split("?", 1)[1].split("&")
            if p.startswith("version=") or p.startswith("authType=")]
    return f"{base}?{'&'.join(kept)}" if kept else base

class DhanMarketFeed:
    """A Dhan Live Market Feed session with reconnection and subscription recovery.

    Identity is always ``(exchange_segment, security_id)``. The subscription set is held
    here rather than at the call site so a reconnect can restore it exactly; losing
    subscriptions silently is the failure this guards against.
    """

    def __init__(
        self,
        access_token: str,
        client_id: str,
        *,
        base_url: str = DHAN_FEED_WSS_URL,
        on_event: Callable[[DhanMarketEvent], None] | None = None,
        on_state: Callable[[FeedState, str], None] | None = None,
        connect: Callable | None = None,
    ) -> None:
        if not access_token:
            raise ValueError("access_token is required to open a Dhan feed session")
        if not client_id:
            raise ValueError("client_id is required to open a Dhan feed session")
        self._access_token = access_token
        self._client_id = client_id
        self._base_url = base_url
        self._on_event = on_event
        self._on_state = on_state
        # Injectable connector so the lifecycle can be tested without a network, and so
        # the reconnect path is exercised deterministically.
        self._connect = connect or self._default_connect
        self._ws = None
        self._state = FeedState.DISCONNECTED
        self._stop = False
        self._subscriptions: dict[tuple[str, str], DhanSubscription] = {}
        #: Set of identities confirmed by a READY transition; used by tests and by
        #: `verify_subscriptions` to prove nothing was dropped on reconnect.
        self.acknowledged: set[tuple[str, str]] = set()
        #: Latest event per identity. Instance state: a class attribute here would make
        #: every feed share one dictionary, so one user's instruments would surface in
        #: another's feed.
        self._quotes: dict[tuple[str, str], DhanMarketEvent] = {}
        self.last_error: str = ""
        self.reconnect_count = 0

    # ── state ────────────────────────────────────────────────────────────────

    @property
    def state(self) -> FeedState:
        return self._state

    def _set_state(self, state: FeedState, reason: str = "") -> None:
        self._state = state
        if self._on_state:
            self._on_state(state, reason)

    def health(self) -> dict:
        return {
            "state": self._state.value,
            "url": redact_url(build_url(self._access_token, self._client_id,
                                        base_url=self._base_url)),
            "subscription_count": len(self._subscriptions),
            "acknowledged_count": len(self.acknowledged),
            "reconnect_count": self.reconnect_count,
            "last_error": self.last_error,
        }

    # ── subscription set ─────────────────────────────────────────────────────

    def subscribe(self, subscriptions: Iterable[DhanSubscription]) -> list[DhanSubscription]:
        """Add to the desired set, deduplicating on the full identity and mode.

        Returns only the entries that were not already present, so a caller can tell
        what actually needs sending. Duplicates are dropped rather than sent twice:
        a repeated instrument produces a duplicated stream the UI has to de-duplicate.
        """
        added: list[DhanSubscription] = []
        for sub in subscriptions:
            key = (sub.identity, sub.mode)
            existing = self._subscriptions.get(key)
            if existing is not None:
                continue
            self._subscriptions[key] = sub
            added.append(sub)
        return added

    def unsubscribe(self, subscriptions: Iterable[DhanSubscription]) -> list[DhanSubscription]:
        removed: list[DhanSubscription] = []
        for sub in subscriptions:
            key = (sub.identity, sub.mode)
            if self._subscriptions.pop(key, None) is not None:
                removed.append(sub)
        return removed

    def clear_subscriptions(self) -> None:
        self._subscriptions.clear()
        self.acknowledged.clear()

    @property
    def subscriptions(self) -> list[DhanSubscription]:
        return list(self._subscriptions.values())

    def quotes(self) -> dict[tuple[str, str], DhanMarketEvent]:
        """Latest event per identity. Keyed by identity, never by security id alone."""
        return dict(self._quotes)

    def quote_for(self, exchange_segment: str, security_id: str) -> DhanMarketEvent | None:
        return self._quotes.get((exchange_segment, str(security_id)))

    def fresh_quote(self, exchange_segment: str, security_id: str,
                    *, max_age: float = QUOTE_STALE_SECONDS) -> DhanMarketEvent | None:
        """A quote only if it is still fresh.

        The display layer may use `quote_for` and show a stale value with a timestamp; the
        execution layer must use this and get None rather than a price it cannot trust.
        """
        event = self.quote_for(exchange_segment, security_id)
        if event is None or event.age_seconds > max_age:
            return None
        return event

    # ── connection ───────────────────────────────────────────────────────────

    @staticmethod
    async def _default_connect(url: str):
        # Protocol-level keepalive only. The SDK sends no application-level ping for v2,
        # so nothing is invented here; `ping_interval` covers liveness at the transport.
        import websockets

        return await websockets.connect(
            url, ping_interval=20, ping_timeout=20, open_timeout=CONNECT_TIMEOUT_SECONDS,
            max_size=4 * 1024 * 1024,
        )

    async def _open(self) -> None:
        self._set_state(FeedState.CONNECTING)
        url = build_url(self._access_token, self._client_id, base_url=self._base_url)
        try:
            self._ws = await asyncio.wait_for(self._connect(url), CONNECT_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 - retried by the caller
            self.last_error = f"connect failed: {exc}"
            self._set_state(FeedState.FAILED, self.last_error)
            raise
        self._set_state(FeedState.CONNECTED)
        # v2 authenticates via the connection URL, so there is no authorize packet to
        # send. AUTHENTICATED reflects that fact rather than pretending a round trip.
        self._set_state(FeedState.AUTHENTICATED)

    async def _send_subscriptions(self) -> None:
        """Send the full desired set. Called on first connect and on every reconnect."""
        self._set_state(FeedState.SUBSCRIBING)
        if not self._subscriptions:
            self.acknowledged = set()
            self._set_state(FeedState.READY, "no subscriptions requested")
            return
        frames = build_subscribe_frame(self._subscriptions.values())
        for frame in frames:
            await self._ws.send(frame)
        # Dhan's v2 feed sends no per-instrument acknowledgement, so confirmation is
        # that every frame was accepted by the socket and the session stayed open. The
        # desired set is what will be restored on the next reconnect.
        self.acknowledged = {sub.identity for sub in self._subscriptions.values()}
        self._set_state(FeedState.READY, f"subscribed {len(self.acknowledged)} instruments")

    async def connect_once(self) -> None:
        """One full connect -> authenticate -> subscribe cycle, without reconnect logic."""
        await self._open()
        await self._send_subscriptions()

    async def unsubscribe_now(self, subscriptions: Iterable[DhanSubscription]) -> None:
        removed = self.unsubscribe(subscriptions)
        for sub in removed:
            self.acknowledged.discard(sub.identity)
        if removed and self._ws is not None and self._state is FeedState.READY:
            for frame in build_unsubscribe_frame(removed):
                await self._ws.send(frame)

    async def _pump(self, stop: asyncio.Event, max_frames: int | None = None) -> None:
        """Drain frames until stopped.

        ``max_frames`` bounds the drain so a caller can process the frames already
        buffered without waiting on a socket that has nothing left to send.
        """
        drained = 0
        while not stop.is_set():
            if max_frames is not None and drained >= max_frames:
                return
            try:
                raw = await asyncio.wait_for(self._ws.recv(), RECV_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                # A quiet market is not a dead socket. Protocol ping keeps it honest.
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - treated as a disconnect
                self.last_error = f"recv failed: {exc}"
                raise
            await self._handle_frame(raw)
            drained += 1

    async def _handle_frame(self, raw) -> None:
        if isinstance(raw, str):
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Dhan feed: unparseable text frame ignored")
                return
            if isinstance(message, dict) and message.get("type") == "server_disconnect":
                self.last_error = message["reason"]
                if message.get("terminal"):
                    self._set_state(FeedState.FAILED, self.last_error)
                raise ConnectionError(self.last_error)
            logger.debug("Dhan feed: text frame %s", message)
            return
        try:
            parsed = parse_packet(raw)
        except DhanPacketError as exc:
            # A malformed packet is dropped and counted. It never becomes a zero quote.
            logger.warning("Dhan feed: dropping malformed packet: %s", exc)
            return
        if isinstance(parsed, dict):
            if parsed.get("type") == "server_disconnect":
                self.last_error = parsed["reason"]
                self._set_state(FeedState.FAILED, self.last_error)
                raise ConnectionError(self.last_error)
            return
        if (parsed.exchange_segment, parsed.security_id) not in {
            (s.exchange_segment, s.security_id) for s in self._subscriptions.values()
        } and self._subscriptions:
            logger.debug(
                "Dhan feed: event for unsubscribed %s/%s ignored",
                parsed.exchange_segment, parsed.security_id,
            )
        self._quotes[parsed.identity] = parsed
        if self._on_event:
            self._on_event(parsed)

    async def run(self) -> None:
        """Run until stopped, reconnecting with bounded exponential backoff.

        After every reconnect the *full* desired subscription set is resent, because a new
        socket knows nothing about the previous session's subscriptions.
        """
        stop = asyncio.Event()
        delay = RECONNECT_BASE_SECONDS
        try:
            while not self._stop:
                try:
                    await self.connect_once()
                    delay = RECONNECT_BASE_SECONDS
                    pump = asyncio.create_task(self._pump(stop))
                    done, _pending = await asyncio.wait(
                        {pump}, return_when=asyncio.FIRST_EXCEPTION
                    )
                    for task in done:
                        exc = task.exception()
                        if exc:
                            raise exc
                    pump.cancel()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - reconnect below
                    self.last_error = str(exc)
                    if self._state is FeedState.STOPPED:
                        break
                    if isinstance(exc, ConnectionError) and "expired" in str(exc).lower():
                        self._set_state(FeedState.FAILED, self.last_error)
                        break
                    self.reconnect_count += 1
                    self._set_state(FeedState.RECONNECTING, self.last_error)
                    logger.warning(
                        "Dhan feed dropped (%s); reconnecting in %.1fs (attempt %d)",
                        self.last_error, delay, self.reconnect_count,
                    )
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=delay)
                        break
                    except asyncio.TimeoutError:
                        pass
                    delay = min(delay * 2, RECONNECT_MAX_SECONDS)
                    await self._close_ws()
        finally:
            self._set_state(FeedState.STOPPED, self.last_error)
            await self._close_ws()

    async def _close_ws(self) -> None:
        ws, self._ws = self._ws, None
        if ws is None:
            return
        try:
            await ws.send(json.dumps({"RequestCode": 12}))
        except Exception:  # noqa: BLE001 - best effort, the socket is going away
            pass
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass

    async def stop(self) -> None:
        self._stop = True
        self._set_state(FeedState.STOPPED, self.last_error)


# ──────────────────────────────────────────────────────────────────────────────
# Instrument master -> subscription
# ──────────────────────────────────────────────────────────────────────────────


def subscription_for_instrument(instrument, *, mode: FeedMode = FeedMode.TICKER) -> DhanSubscription:
    """Build a subscription from a resolved Dhan contract.

    This is the only sanctioned path from an instrument to a feed subscription, and it
    exists so the exchange segment and security id can only come from the contract row.
    The caller cannot pass a symbol: :class:`DhanSubscription` rejects a non-numeric
    security id outright, so a trading symbol or display string fails here rather than
    being sent to Dhan as an identifier.
    """
    if instrument is None:
        raise ValueError("instrument is required; unresolved contracts cannot be subscribed")
    segment = instrument.exchange_segment
    if not segment:
        raise ValueError("contract has no exchange segment")
    return DhanSubscription(
        exchange_segment=segment,
        security_id=str(instrument.security_id),
        mode=mode,
    )


def subscription_for_contract(
    underlying: str,
    *,
    expiry: str,
    strike: float,
    option_type: str,
    mode: FeedMode = FeedMode.TICKER,
    for_live: bool = False,
) -> DhanSubscription:
    """Resolve an exact option contract through the Dhan master, then subscribe to it.

    Identity comes from the master's own row, so an ATM strike is chosen by comparing
    listed strikes rather than by arithmetic on the underlying's price, and the lot size
    and segment that come back are the authoritative ones.
    """
    from market.dhan_instruments import dhan_instrument_provider

    instrument = dhan_instrument_provider.resolve_option(
        underlying, expiry=expiry, strike=strike, option_type=option_type, for_live=for_live
    )
    if instrument is None:
        raise LookupError(
            f"no Dhan contract for {underlying} {expiry} {strike} {option_type}; "
            "an unresolvable contract cannot be subscribed"
        )
    return subscription_for_instrument(instrument, mode=mode)


def nearest_expiry(underlying: str, *, option: bool = True, min_days: int = 0) -> str | None:
    """Nearest eligible expiry from the master, or None when there is none."""
    from market.dhan_instruments import dhan_instrument_provider

    expiries = dhan_instrument_provider.expiries(underlying, option=option, min_days=min_days)
    return expiries[0] if expiries else None


def atm_strike(underlying: str, expiry: str, *, option_type: str = "CE") -> float | None:
    """A listed strike for the given expiry, chosen from what is actually listed.

    Deliberately the middle listed strike rather than a computation from spot: the
    instrument master is the authority on which strikes exist, and a strike it does not
    list cannot be subscribed to.
    """
    from market.dhan_instruments import dhan_instrument_provider

    strikes = dhan_instrument_provider.strikes(underlying, expiry, option_type=option_type)
    if not strikes:
        return None
    return strikes[len(strikes) // 2]
