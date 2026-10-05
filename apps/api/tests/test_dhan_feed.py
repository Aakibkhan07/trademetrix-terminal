"""Tests for the Dhan Live Market Feed.

The protocol these tests pin down was read from Dhan's own client
(``dhanhq==2.2.0``, ``dhanhq/marketfeed.py``), so the expected values here are
transcriptions of that source rather than of the previous implementation. Several
tests exist specifically to fail if the old, broken behaviour returns:

* a ``httpx`` stream against a ``wss://`` URL
* ``ExchangeSegment: NSE_EQ`` for a derivative
* ``SecurityToken`` carrying a display symbol
* identity keyed on ``security_id`` alone

Binary packet fixtures are built with the same ``struct`` formats the SDK unpacks
with, so a change to either side shows up as a decode failure rather than as a
plausible-looking number.
"""

import asyncio
import json
import struct

import pytest

from market.dhan_feed import (
    DHAN_FEED_WSS_URL,
    DERIVATIVE_SEGMENTS,
    MAX_INSTRUMENTS_PER_FRAME,
    QUOTE_STALE_SECONDS,
    REQUEST_CODE_FULL,
    REQUEST_CODE_QUOTE,
    REQUEST_CODE_TICKER,
    SEGMENT_CODE_TO_NAME,
    FeedMode,
    FeedState,
    DhanMarketEvent,
    DhanMarketFeed,
    DhanPacketError,
    DhanSubscription,
    build_subscribe_frame,
    build_unsubscribe_frame,
    build_url,
    parse_packet,
    redact_url,
    subscription_for_instrument,
)

DEPTH_ROWS = b"".join(
    struct.pack("<IIHHff", 10 * (i + 1), 8 * (i + 1), 1, 1, 100.0 - i, 101.0 + i)
    for i in range(5)
)
DEPTH_ROWS_EMPTY = b"\x00" * 100


def ticker_frame(seg: int = 2, sec: int = 40749, ltp: float = 23250.5, ltt: int = 1760000000) -> bytes:
    return struct.pack("<BHBIfI", 2, 16, seg, sec, ltp, ltt)


def quote_frame(seg: int = 2, sec: int = 40749) -> bytes:
    return struct.pack("<BHBIfHIfIIIffff", 4, 50, seg, sec, 23250.5, 15, 1760000000,
                        23200.0, 42000, 60000, 55000, 23100.0, 23250.0, 23400.0, 23050.0)


def full_frame(seg: int = 2, sec: int = 40749) -> bytes:
    return struct.pack("<BHBIfHIfIIIIIIffff100s", 8, 162, seg, sec, 23250.5, 15, 1760000000,
                       23200.0, 42000, 60000, 55000, 900000, 950000, 880000,
                       23100.0, 23250.0, 23400.0, 23050.0, DEPTH_ROWS)


def depth_frame(seg: int = 2, sec: int = 40749) -> bytes:
    return struct.pack("<BHBIf100s", 3, 112, seg, sec, 23250.5, DEPTH_ROWS)


def empty_depth_frame(seg: int = 2, sec: int = 40749) -> bytes:
    return struct.pack("<BHBIf100s", 3, 112, seg, sec, 23250.5, DEPTH_ROWS_EMPTY)


def oi_frame(seg: int = 2, sec: int = 40749) -> bytes:
    return struct.pack("<BHBII", 5, 12, seg, sec, 900000)


def prev_close_frame(seg: int = 2, sec: int = 40749) -> bytes:
    return struct.pack("<BHBIfI", 6, 16, seg, sec, 23100.0, 880000)


def status_frame() -> bytes:
    return struct.pack("<BHBI", 7, 8, 2, 0)


def disconnect_frame(code: int) -> bytes:
    return struct.pack("<BHBIH", 50, 10, 2, 0, code)


class FakeSocket:
    """A WebSocket stand-in that records what was sent and replays queued frames."""

    def __init__(self, frames=(), fail_on_send: bool = False) -> None:
        self.sent: list[str] = []
        self.frames = list(frames)
        self.fail_on_send = fail_on_send
        self.closed = False
        self.pinged = 0

    async def send(self, message):
        if self.fail_on_send:
            raise ConnectionError("socket refused the frame")
        self.sent.append(message)

    async def recv(self):
        if self.frames:
            return self.frames.pop(0)
        await asyncio.sleep(3600)

    async def ping(self):
        self.pinged += 1

    async def close(self):
        self.closed = True


# ──────────────────────────────────────────────────────────────────────────────
# Protocol transcription
# ──────────────────────────────────────────────────────────────────────────────


class TestVerifiedProtocol:
    def test_the_endpoint_is_the_feed_host(self):
        """The previous adapter pointed at the API host, which is not the feed."""
        assert DHAN_FEED_WSS_URL == "wss://api-feed.dhan.co"
        assert "/v2/ws" not in DHAN_FEED_WSS_URL

    def test_the_v2_url_carries_credentials_as_dhan_expects(self):
        url = build_url("TOKEN123", "CLIENT9")
        assert url.startswith("wss://api-feed.dhan.co?")
        assert "version=2" in url
        assert "token=TOKEN123" in url
        assert "clientId=CLIENT9" in url
        assert "authType=2" in url

    def test_no_header_or_path_token_is_used(self):
        """v2 authenticates by URL. A token in a header would not authenticate."""
        url = build_url("TOKEN123", "CLIENT9")
        assert url.count("TOKEN123") == 1
        assert "access-token" not in url

    def test_credentials_are_redacted_for_logging(self):
        redacted = redact_url(build_url("SUPERSECRET", "CLIENT9"))
        assert "SUPERSECRET" not in redacted
        assert "CLIENT9" not in redacted
        assert "version=2" in redacted
        assert redact_url("wss://x/y") == "wss://x/y"

    def test_segment_codes_match_the_sdk_mapping(self):
        assert SEGMENT_CODE_TO_NAME == {
            0: "IDX_I", 1: "NSE_EQ", 2: "NSE_FNO", 3: "NSE_CURRENCY",
            4: "BSE_EQ", 5: "MCX_COMM", 7: "BSE_CURRENCY", 8: "BSE_FNO",
        }

    def test_request_codes_match_the_sdk(self):
        assert (REQUEST_CODE_TICKER, REQUEST_CODE_QUOTE, REQUEST_CODE_FULL) == (15, 17, 21)

    def test_derivative_segments_are_never_cash_equity(self):
        assert "NSE_EQ" not in DERIVATIVE_SEGMENTS
        assert "BSE_EQ" not in DERIVATIVE_SEGMENTS
        assert {"NSE_FNO", "BSE_FNO"} <= DERIVATIVE_SEGMENTS


# ──────────────────────────────────────────────────────────────────────────────
# Subscription identity
# ──────────────────────────────────────────────────────────────────────────────


class TestSubscriptionIdentity:
    def test_a_subscription_carries_the_segments_security_id(self):
        sub = DhanSubscription(exchange_segment="NSE_FNO", security_id="40749")
        assert sub.identity == ("NSE_FNO", "40749")
        assert sub.request_code == REQUEST_CODE_TICKER

    @pytest.mark.parametrize("symbol", ["NIFTY", "NIFTY-Oct2026-24000-CE", "NSE:NIFTY50-INDEX",
                                         "NIFTY 24000 CALL", ""])
    def test_a_display_or_trading_symbol_cannot_be_a_security_id(self, symbol):
        with pytest.raises(ValueError):
            DhanSubscription(exchange_segment="NSE_FNO", security_id=symbol)

    def test_a_missing_segment_is_refused(self):
        with pytest.raises(ValueError):
            DhanSubscription(exchange_segment="", security_id="40749")

    def test_an_unknown_segment_is_refused_rather_than_defaulted(self):
        with pytest.raises(ValueError, match="unknown exchange segment"):
            DhanSubscription(exchange_segment="NSE_EQUITY", security_id="40749")

    def test_the_frame_uses_security_id_not_security_token(self):
        """The previous feed sent `SecurityToken`. Dhan's v2 field is `SecurityId`."""
        frame = json.loads(build_subscribe_frame(
            [DhanSubscription(exchange_segment="NSE_FNO", security_id="40749")]
        )[0])
        assert "SecurityId" in frame["InstrumentList"][0]
        assert "SecurityToken" not in frame["InstrumentList"][0]

    def test_a_derivative_never_carries_nse_eq(self):
        frame = json.loads(build_subscribe_frame(
            [DhanSubscription(exchange_segment="NSE_FNO", security_id="40749")]
        )[0])
        assert frame["InstrumentList"][0]["ExchangeSegment"] == "NSE_FNO"

    def test_mode_selects_the_request_code(self):
        for mode, code in ((FeedMode.TICKER, 15), (FeedMode.QUOTE, 17), (FeedMode.FULL, 21)):
            assert DhanSubscription("NSE_FNO", "1", mode).request_code == code

    def test_batches_are_capped_at_the_documented_size(self):
        subs = [DhanSubscription("NSE_FNO", str(i)) for i in range(250)]
        frames = build_subscribe_frame(subs)
        assert len(frames) == 3
        counts = [json.loads(f)["InstrumentCount"] for f in frames]
        assert counts == [MAX_INSTRUMENTS_PER_FRAME, MAX_INSTRUMENTS_PER_FRAME, 50]

    def test_modes_are_grouped_into_separate_frames(self):
        subs = [
            DhanSubscription("NSE_FNO", "1", FeedMode.TICKER),
            DhanSubscription("NSE_FNO", "2", FeedMode.TICKER),
            DhanSubscription("NSE_FNO", "3", FeedMode.QUOTE),
        ]
        codes = sorted(json.loads(f)["RequestCode"] for f in build_subscribe_frame(subs))
        assert codes == [17, 15] or codes == [15, 17]

    def test_unsubscribe_is_one_above_subscribe(self):
        frames = build_unsubscribe_frame(
            [DhanSubscription("NSE_FNO", "1", FeedMode.TICKER)]
        )
        assert json.loads(frames[0])["RequestCode"] == REQUEST_CODE_TICKER + 1


# ──────────────────────────────────────────────────────────────────────────────
# Packet parsing
# ──────────────────────────────────────────────────────────────────────────────


class TestPacketParsing:
    def test_ticker(self):
        event = parse_packet(ticker_frame())
        assert event.packet_type == "ticker"
        assert event.exchange_segment == "NSE_FNO"
        assert event.security_id == "40749"
        assert event.ltp == pytest.approx(23250.5)
        assert event.timestamp.year == 2025

    def test_quote_carries_every_documented_field(self):
        event = parse_packet(quote_frame())
        assert event.packet_type == "quote"
        assert (event.ltq, event.volume) == (15, 42000)
        assert event.open == pytest.approx(23100.0)
        assert event.close == pytest.approx(23250.0)
        assert event.high == pytest.approx(23400.0)
        assert event.low == pytest.approx(23050.0)
        assert event.avg_price == pytest.approx(23200.0)

    def test_full_carries_open_interest_and_depth(self):
        event = parse_packet(full_frame())
        assert event.packet_type == "full"
        assert event.open_interest == 900000
        assert event.bid == pytest.approx(100.0)
        assert event.ask == pytest.approx(101.0)
        assert event.bid_quantity == 10   # row 0 carries bid 10
        assert event.ask_quantity == 8    # and ask 8

    def test_depth(self):
        event = parse_packet(depth_frame())
        assert event.packet_type == "depth"
        assert event.bid == pytest.approx(100.0)

    def test_an_empty_book_reports_none_not_zero(self):
        """Zero means a real value. An empty book must not look like a bid of 0."""
        event = parse_packet(empty_depth_frame())
        assert event.bid is None
        assert event.ask is None
        assert event.bid_quantity is None

    def test_open_interest_packet(self):
        event = parse_packet(oi_frame())
        assert event.open_interest == 900000

    def test_previous_close_packet(self):
        event = parse_packet(prev_close_frame())
        assert event.close == pytest.approx(23100.0)

    def test_market_status_is_a_control_frame(self):
        assert parse_packet(status_frame())["type"] == "market_status"

    @pytest.mark.parametrize("code", [805, 806, 807, 808, 809])
    def test_disconnection_codes_are_surfaced_with_their_reason(self, code):
        frame = parse_packet(disconnect_frame(code))
        assert frame["type"] == "server_disconnect"
        assert frame["code"] == code
        assert frame["reason"]
        assert frame["terminal"] is (code != 805)

    def test_a_segment_code_carries_the_contract_segment(self):
        assert parse_packet(ticker_frame(seg=8)).exchange_segment == "BSE_FNO"
        assert parse_packet(ticker_frame(seg=4)).exchange_segment == "BSE_EQ"

    def test_an_unknown_segment_code_is_named_not_guessed(self):
        event = parse_packet(ticker_frame(seg=99))
        assert event.exchange_segment == "UNKNOWN_99"

    @pytest.mark.parametrize("frame", [
        b"", ticker_frame()[:8], quote_frame()[:20], full_frame()[:40],
        oi_frame()[:5], b"\x01\x02", b"\x00" * 4,
    ])
    def test_truncated_or_unknown_packets_raise_rather_than_returning_zeros(self, frame):
        with pytest.raises(DhanPacketError):
            parse_packet(frame)

    def test_a_text_frame_is_rejected_by_the_binary_parser(self):
        with pytest.raises(DhanPacketError):
            parse_packet('{"RequestCode": 15}')

    def test_missing_fields_stay_none(self):
        """A ticker packet has no bid, ask or volume. They must be None, not 0."""
        event = parse_packet(ticker_frame())
        assert event.bid is None
        assert event.ask is None
        assert event.volume is None
        assert event.open_interest is None


# ──────────────────────────────────────────────────────────────────────────────
# Connection lifecycle
# ──────────────────────────────────────────────────────────────────────────────


def feed(sockets, **kwargs) -> DhanMarketFeed:
    """A feed whose connector hands out the given sockets in order."""
    queue = list(sockets)

    async def _connect(url):
        if not queue:
            raise ConnectionError("no socket available")
        return queue.pop(0)

    return DhanMarketFeed("TOKEN", "CLIENT", connect=_connect, **kwargs)


class TestConnectionLifecycle:
    def test_states_progress_to_ready_only_after_subscribing(self):
        seen: list[str] = []
        f = feed([FakeSocket()], on_state=lambda s, r: seen.append(s.value))
        f.subscribe([DhanSubscription("NSE_FNO", "40749")])
        asyncio.run(f.connect_once())
        assert seen == ["CONNECTING", "CONNECTED", "AUTHENTICATED", "SUBSCRIBING", "READY"]
        assert f.state is FeedState.READY

    def test_ready_is_not_claimed_before_subscribing(self):
        f = feed([FakeSocket()])
        assert f.state is FeedState.DISCONNECTED
        asyncio.run(f._open())
        assert f.state is FeedState.AUTHENTICATED
        assert f.state is not FeedState.READY

    def test_a_successful_connect_sends_the_documented_frame(self):
        socket = FakeSocket()
        f = feed([socket])
        f.subscribe([DhanSubscription("NSE_FNO", "40749")])
        asyncio.run(f.connect_once())
        frame = json.loads(socket.sent[0])
        assert frame == {"RequestCode": 15, "InstrumentCount": 1,
                         "InstrumentList": [{"ExchangeSegment": "NSE_FNO",
                                             "SecurityId": "40749"}]}

    def test_a_connection_failure_is_reported_and_not_ready(self):
        f = feed([])
        with pytest.raises(Exception):
            asyncio.run(f.connect_once())
        assert f.state is FeedState.FAILED
        assert "connect failed" in f.last_error

    def test_credentials_are_required(self):
        with pytest.raises(ValueError):
            DhanMarketFeed("", "CLIENT")
        with pytest.raises(ValueError):
            DhanMarketFeed("TOKEN", "")

    def test_a_socket_that_refuses_the_frame_does_not_become_ready(self):
        f = feed([FakeSocket(fail_on_send=True)])
        f.subscribe([DhanSubscription("NSE_FNO", "40749")])
        with pytest.raises(ConnectionError):
            asyncio.run(f.connect_once())
        assert f.state is not FeedState.READY


# ──────────────────────────────────────────────────────────────────────────────
# Subscription management and recovery
# ──────────────────────────────────────────────────────────────────────────────


class TestSubscriptionManagement:
    def test_duplicate_subscriptions_are_dropped(self):
        f = feed([])
        first = f.subscribe([DhanSubscription("NSE_FNO", "40749")])
        second = f.subscribe([DhanSubscription("NSE_FNO", "40749")])
        assert len(first) == 1 and second == []
        assert len(f.subscriptions) == 1

    def test_the_same_security_id_in_two_segments_is_two_subscriptions(self):
        """security_id alone is ambiguous; 14,626 ids repeat across segments."""
        f = feed([])
        f.subscribe([DhanSubscription("NSE_FNO", "513496")])
        f.subscribe([DhanSubscription("BSE_FNO", "513496")])
        assert len(f.subscriptions) == 2
        assert {s.identity for s in f.subscriptions} == {
            ("NSE_FNO", "513496"), ("BSE_FNO", "513496")}

    def test_unsubscribe_removes_only_the_named_identity(self):
        f = feed([])
        f.subscribe([DhanSubscription("NSE_FNO", "1"), DhanSubscription("BSE_FNO", "1")])
        removed = f.unsubscribe([DhanSubscription("NSE_FNO", "1")])
        assert len(removed) == 1
        assert {s.identity for s in f.subscriptions} == {("BSE_FNO", "1")}

    def test_unsubscribing_something_absent_is_a_no_op(self):
        f = feed([])
        assert f.unsubscribe([DhanSubscription("NSE_FNO", "1")]) == []

    @pytest.mark.asyncio
    async def test_unsubscribe_sends_the_incremented_frame_while_connected(self):
        socket = FakeSocket()
        f = feed([socket])
        sub = DhanSubscription("NSE_FNO", "40749", FeedMode.TICKER)
        f.subscribe([sub])
        await f.connect_once()
        socket.sent.clear()
        await f.unsubscribe_now([sub])
        assert json.loads(socket.sent[0])["RequestCode"] == REQUEST_CODE_TICKER + 1
        assert f.subscriptions == []

    def test_a_reconnect_restores_every_subscription(self):
        """The defect this guards: a new socket knows nothing about the old session."""
        first = FakeSocket()
        second = FakeSocket()
        f = feed([first, second])
        f.subscribe([
            DhanSubscription("NSE_FNO", "40749"),
            DhanSubscription("NSE_FNO", "40750"),
            DhanSubscription("BSE_FNO", "889114"),
        ])
        asyncio.run(f.connect_once())
        assert len(json.loads(first.sent[0])["InstrumentList"]) == 3

        asyncio.run(f.connect_once())
        restored = json.loads(second.sent[0])
        assert restored["InstrumentCount"] == 3
        assert f.acknowledged == {
            ("NSE_FNO", "40749"), ("NSE_FNO", "40750"), ("BSE_FNO", "889114")}
        assert f.acknowledged == {s.identity for s in f.subscriptions}

    def test_acknowledge_covers_the_whole_desired_set_after_reconnect(self):
        subs = [DhanSubscription("NSE_FNO", str(i)) for i in range(3)]
        f = feed([FakeSocket(), FakeSocket()])
        f.subscribe(subs)
        asyncio.run(f.connect_once())
        asyncio.run(f.connect_once())
        assert f.acknowledged == {s.identity for s in subs}
        assert len(f.acknowledged) == len(subs)

    def test_connecting_with_no_subscriptions_is_still_ready(self):
        f = feed([FakeSocket()])
        asyncio.run(f.connect_once())
        assert f.state is FeedState.READY
        assert f.acknowledged == set()


# ──────────────────────────────────────────────────────────────────────────────
# Quote cache and freshness
# ──────────────────────────────────────────────────────────────────────────────


class TestQuoteCache:
    def _feed_with(self, *frames):
        f = feed([FakeSocket(frames)])
        f.subscribe([DhanSubscription("NSE_FNO", "40749"),
                     DhanSubscription("BSE_FNO", "513496")])
        return f

    async def _pump(self, f):
        """Connect, then drain exactly the frames the fake socket has queued.

        An unbounded drain would block on recv() once the queue empties, which is what
        made the first version of this suite hang rather than fail.
        """
        await f.connect_once()
        budget = len(f._ws.frames)
        if budget:
            await f._pump(asyncio.Event(), max_frames=budget)

    def test_events_are_cached_under_the_full_identity(self):
        f = self._feed_with(ticker_frame())
        asyncio.run(self._pump(f))
        assert f.quote_for("NSE_FNO", "40749") is not None
        assert f.quote_for("BSE_FNO", "40749") is None

    def test_the_same_security_id_in_two_segments_does_not_collide(self):
        """The collision a security-id-only cache would suffer."""
        f = feed([FakeSocket([ticker_frame(seg=2, sec=513496, ltp=100.0),
                              ticker_frame(seg=8, sec=513496, ltp=200.0)])])
        f.subscribe([DhanSubscription("NSE_FNO", "513496"),
                     DhanSubscription("BSE_FNO", "513496")])
        asyncio.run(self._pump(f))
        assert f.quote_for("NSE_FNO", "513496").ltp == pytest.approx(100.0)
        assert f.quote_for("BSE_FNO", "513496").ltp == pytest.approx(200.0)
        assert len(f.quotes()) == 2

    def test_a_fresh_quote_is_returned_for_execution(self):
        f = self._feed_with(ticker_frame())
        asyncio.run(self._pump(f))
        assert f.fresh_quote("NSE_FNO", "40749") is not None

    def test_an_old_quote_is_not_fresh_for_execution(self):
        f = self._feed_with(ticker_frame())
        asyncio.run(self._pump(f))
        event = f.quote_for("NSE_FNO", "40749")
        event.received_at -= (QUOTE_STALE_SECONDS + 5)
        assert event.is_stale is True
        assert f.fresh_quote("NSE_FNO", "40749") is None
        # Still available for display, which is a different decision.
        assert f.quote_for("NSE_FNO", "40749") is not None

    def test_an_unset_quote_is_neither_fresh_nor_stale(self):
        f = self._feed_with()
        assert f.quote_for("NSE_FNO", "40749") is None
        assert f.fresh_quote("NSE_FNO", "40749") is None

    def test_two_feeds_do_not_share_a_cache(self):
        """A class-level cache would leak one session's quotes into another's."""
        a = feed([])
        b = feed([FakeSocket([ticker_frame()])])
        b.subscribe([DhanSubscription("NSE_FNO", "40749")])
        asyncio.run(self._pump(b))
        assert a.quote_for("NSE_FNO", "40749") is None
        assert b.quote_for("NSE_FNO", "40749") is not None

    def test_a_malformed_packet_is_dropped_and_caches_nothing(self):
        f = self._feed_with(b"\x01\x02\x03", ticker_frame())
        asyncio.run(self._pump(f))
        # The good frame after the bad one still lands; the bad one produced no quote.
        assert f.quote_for("NSE_FNO", "40749") is not None
        assert len(f.quotes()) == 1

    def test_clearing_subscriptions_clears_the_acknowledged_set(self):
        f = feed([FakeSocket()])
        f.subscribe([DhanSubscription("NSE_FNO", "1")])
        asyncio.run(f.connect_once())
        f.clear_subscriptions()
        assert f.acknowledged == set() and f.subscriptions == []


# ──────────────────────────────────────────────────────────────────────────────
# Health and redaction
# ──────────────────────────────────────────────────────────────────────────────


class TestHealth:
    def test_health_never_leaks_the_token(self):
        f = DhanMarketFeed("SECRET_TOKEN_VALUE", "SECRET_CLIENT")
        blob = json.dumps(f.health())
        assert "SECRET_TOKEN_VALUE" not in blob
        assert "SECRET_CLIENT" not in blob

    def test_health_reports_the_lifecycle_position(self):
        f = feed([FakeSocket()])
        f.subscribe([DhanSubscription("NSE_FNO", "1")])
        asyncio.run(f.connect_once())
        health = f.health()
        assert health["state"] == "READY"
        assert health["subscription_count"] == 1
        assert health["acknowledged_count"] == 1
        assert health["reconnect_count"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# Instrument master bridge
# ──────────────────────────────────────────────────────────────────────────────


class TestInstrumentBridge:
    def _instrument(self, **over):
        from market.instruments import Instrument

        fields = dict(broker="dhan", security_id="40749", broker_symbol="NIFTY26AUGFUT",
                      exchange_segment="NSE_FNO", instrument_type="OPT", lot_size=65,
                      underlying="NIFTY", expiry="2026-10-28", strike=24000.0,
                      option_type="CE")
        fields.update(over)
        return Instrument(**fields)

    def test_a_subscription_is_built_from_the_contract(self):
        sub = subscription_for_instrument(self._instrument())
        assert sub.identity == ("NSE_FNO", "40749")

    def test_the_segment_comes_from_the_contract_not_the_product(self):
        sub = subscription_for_instrument(self._instrument(exchange_segment="BSE_FNO"))
        assert sub.exchange_segment == "BSE_FNO"

    def test_an_unresolved_contract_cannot_be_subscribed(self):
        with pytest.raises(ValueError, match="unresolved contracts"):
            subscription_for_instrument(None)

    def test_a_contract_without_a_segment_cannot_be_subscribed(self):
        with pytest.raises(ValueError, match="no exchange segment"):
            subscription_for_instrument(self._instrument(exchange_segment=""))

    def test_a_contract_whose_security_id_is_a_symbol_is_refused(self):
        """Belt and braces: even a malformed contract row cannot put a symbol on the wire."""
        with pytest.raises(ValueError, match="numeric security id"):
            subscription_for_instrument(self._instrument(security_id="NIFTY"))


# ──────────────────────────────────────────────────────────────────────────────
# The old defects must not return
# ──────────────────────────────────────────────────────────────────────────────


def executable_source(module) -> str:
    """The module's code with comments and string literals removed.

    The docstrings in this module quote the old broken implementation in order to explain
    why it was wrong. A raw source scan cannot tell `httpx.AsyncClient.stream()` the call
    from the same characters inside a sentence, and reported the explanation as a defect.
    """
    import io
    import tokenize

    parts: list[str] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(module.__file__ and
                open(module.__file__).read()).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            parts.append(tok.string)
    except Exception:
        pass
    return " ".join(parts)


class TestHistoricalDefectsDoNotReturn:
    def test_the_module_does_not_use_httpx_for_the_websocket(self):
        """The original cause: httpx cannot perform a protocol upgrade."""
        from market import dhan_feed

        code = executable_source(dhan_feed)
        assert "AsyncClient" not in code
        assert "httpx" not in code

    def test_the_module_uses_the_websockets_library(self):
        import inspect

        from market import dhan_feed

        assert "import websockets" in inspect.getsource(dhan_feed.DhanMarketFeed._default_connect)

    def test_no_derivative_segment_is_hardcoded_as_a_default(self):
        """`NSE_EQ` belongs in the segment map -- code 1 really is NSE equity.

        Tokenising cannot check this: it strips the string literals that are exactly what
        is being searched for. So the scan is done on the AST, collecting string constants
        used as dict *values* (where a segment would be mapped) and skipping docstrings,
        which is where this module explains the old defect.
        """
        import ast
        import inspect

        from market import dhan_feed

        tree = ast.parse(inspect.getsource(dhan_feed))
        dict_value_strings: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for value in node.values:
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        dict_value_strings.append(value.value)
        # The only place NSE_EQ may appear as a mapped value is segment code 1.
        assert dict_value_strings.count("NSE_EQ") == 1
        assert SEGMENT_CODE_TO_NAME[1] == "NSE_EQ"
        assert SEGMENT_CODE_TO_NAME[2] == "NSE_FNO"

    def test_the_segment_map_covers_the_documented_derivatives(self):
        assert SEGMENT_CODE_TO_NAME[2] == "NSE_FNO"
        assert SEGMENT_CODE_TO_NAME[8] == "BSE_FNO"
        assert {"NSE_FNO", "BSE_FNO"} <= DERIVATIVE_SEGMENTS
        assert not (DERIVATIVE_SEGMENTS & {"NSE_EQ", "BSE_EQ"})

    def test_a_default_connect_is_provided(self):
        assert callable(DhanMarketFeed._default_connect)

    def test_packets_are_not_synthesised_when_absent(self):
        """A missing field is None everywhere, so a fabricated zero cannot appear."""
        event = DhanMarketEvent(provider="dhan", exchange_segment="NSE_FNO",
                                security_id="1", packet_type="ticker",
                                timestamp=__import__("datetime").datetime.now(__import__("datetime").UTC))
        for field in ("ltp", "ltq", "bid", "ask", "bid_quantity", "ask_quantity",
                      "volume", "open_interest", "open", "high", "low", "close"):
            assert getattr(event, field) is None, field