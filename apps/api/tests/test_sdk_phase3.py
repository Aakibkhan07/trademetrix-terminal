"""Unit tests for the unified SDK event bus, auth, websocket, and health layers."""
import asyncio
import json
import logging
import time

import pytest

from brokers.sdk.auth import (
    AuthProvider,
    AuthState,
    InMemoryTokenStore,
    ManagedSession,
    ReAuthRequiredError,
    SessionManager,
    Token,
    TokenState,
    token_state,
)
from brokers.sdk.events import (
    AuditEventBus,
    BrokerAuditEvent,
    BrokerEventKind,
    LoggingSink,
)
from brokers.sdk.health import (
    BrokerHealth,
    BrokerHealthService,
    BrokerHealthState,
    derive_health,
)
from brokers.sdk.websocket import WSConfig, WebSocketManager, json_dumps


class FakeSink:
    def __init__(self):
        self.events = []

    def __call__(self, event: BrokerAuditEvent) -> None:
        self.events.append(event)


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------


def test_bus_fanout_and_order():
    bus = AuditEventBus()
    a, b = FakeSink(), FakeSink()
    bus.subscribe(a)
    bus.subscribe(b)
    bus.emit(BrokerEventKind.ORDER_SENT, broker="fyers", message="m1")
    bus.emit(BrokerEventKind.ORDER_FILLED, broker="fyers", message="m2")
    assert [e.sequence for e in a.events] == [1, 2]
    assert [e.sequence for e in b.events] == [1, 2]
    assert a.events[0].kind == BrokerEventKind.ORDER_SENT
    assert a.events[0].broker == "fyers"


def test_bus_missing_required_kinds():
    required = [
        "LOGIN_SUCCESS",
        "TOKEN_REFRESH",
        "ORDER_SENT",
        "ORDER_REJECTED",
        "ORDER_FILLED",
        "POSITION_UPDATED",
        "WEBSOCKET_CONNECTED",
        "WEBSOCKET_DISCONNECTED",
        "RATE_LIMITED",
        "CIRCUIT_OPEN",
        "AUTH_FAILED",
    ]
    for name in required:
        assert getattr(BrokerEventKind, name, None) is not None, name


def test_bus_recent_ring_and_severity():
    bus = AuditEventBus(max_buffered=2000)
    for i in range(5):
        bus.emit(
            BrokerEventKind.TOKEN_REFRESH,
            broker="b",
            severity="bogus",
            message=f"m{i}",
            payload={"i": i},
        )
    recent = bus.recent(3)
    assert len(recent) == 3
    assert recent[-1]["message"] == "m4"
    assert recent[0]["severity"] == "info"  # bogus normalized
    assert recent[0]["payload"]["i"] == 2
    assert bus.buffered == 5
    bus.remove_buffer()
    assert bus.buffered == 0


def test_bus_sink_exception_isolation():
    bus = AuditEventBus()

    def bad(_):
        raise RuntimeError("boom")

    good = FakeSink()
    bus.subscribe(bad)
    bus.subscribe(good)
    bus.emit(BrokerEventKind.AUTH_FAILED, message="x")  # must not raise
    assert len(good.events) == 1


def test_bus_sync_fanout_feeds_breaker_callback_style():
    bus = AuditEventBus()
    seen = []

    def sync_cb(event):  # e.g. set_breaker_state_callback
        seen.append((event.kind, event.message))

    bus.subscribe(sync_cb)
    bus.emit(BrokerEventKind.CIRCUIT_OPEN, broker="faker", message="cb state open")
    assert seen == [(BrokerEventKind.CIRCUIT_OPEN, "cb state open")]


def test_unsubscribe_and_emit_event():
    bus = AuditEventBus()
    sink = FakeSink()
    bus.subscribe(sink)
    bus.unsubscribe(sink)
    bus.emit(BrokerEventKind.ORDER_FILLED, message="x")
    assert sink.events == []


def test_logging_sink_writes_structured_line(caplog):
    bus = AuditEventBus()
    sink = LoggingSink(logger_name="test.events")
    bus.subscribe(sink)
    with caplog.at_level(logging.INFO, logger="test.events"):
        bus.emit(BrokerEventKind.ORDER_SENT, broker="faker", message="hello", payload={"a": 1})
    assert any("event=order_sent" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------


class DummyProvider(AuthProvider):
    """Credentials-based provider returning a long-lived token that can refresh."""

    broker = "fake"

    def __init__(self, broker: str = "fake", fail_login: bool = False, fail_refresh: bool = False):
        self.broker = broker
        self.fail_login = fail_login
        self.fail_refresh = fail_refresh
        self.login_calls = 0
        self.refresh_calls = 0

    async def login(self, credentials: dict) -> Token:
        self.login_calls += 1
        if self.fail_login:
            raise RuntimeError("bad creds")
        return Token(
            access_token="AT",
            refresh_token="RT",
            expires_at=time.time() + 3600,
            issuer="oauth",
            client_id="c",
        )

    async def refresh(self, token: Token) -> Token:
        self.refresh_calls += 1
        if self.fail_refresh:
            raise ReAuthRequiredError("reauth")
        return Token(
            access_token="AT2",
            refresh_token=token.refresh_token,
            expires_at=time.time() + 3600,
            issuer="oauth",
            client_id=token.client_id,
        )


@pytest.fixture
def bus():
    return AuditEventBus()


def test_token_state_transitions():
    now = time.time()
    assert token_state(Token(access_token="a", expires_at=now + 500)) == TokenState.VALID
    assert token_state(Token(access_token="a", expires_at=now + 100)) == TokenState.EXPIRING_SOON
    assert token_state(Token(access_token="a", expires_at=now - 1)) == TokenState.EXPIRED
    assert token_state(Token(access_token="a", expires_at=0)) == TokenState.EXPIRED
    assert token_state(Token(access_token="a", expires_at=now + 500)) == TokenState.VALID
    assert token_state(Token(access_token="a")) == TokenState.VALID  # None expiry
    assert token_state(Token(access_token="")) == TokenState.INVALID


def test_managed_session_fresh_login_and_cache(bus, tmp_path):
    provider = DummyProvider()
    store = InMemoryTokenStore()
    session = ManagedSession("acc1", provider, store, event_bus=bus, key_prefix="mem:")
    token = asyncio.run(session.get_token())
    assert token.access_token == "AT"
    assert provider.login_calls == 1
    token2 = asyncio.run(session.get_token())
    assert token2.access_token == "AT"
    assert provider.login_calls == 1  # cached, no re-login
    assert session.health().ok is True


def test_managed_session_expired_refreshes():
    bus = AuditEventBus()

    class ExpiringProvider(DummyProvider):
        async def login(self, credentials):
            return Token(
                access_token="ATinit",
                refresh_token="RT",
                expires_at=time.time() + 1,  # expires almost immediately
                issuer="oauth",
            )

    p = ExpiringProvider(broker="primary")
    session = ManagedSession("acc1", p, InMemoryTokenStore(), event_bus=bus, key_prefix="mem:")
    asyncio.run(session.get_token(force_login=True))
    session._token.expires_at = time.time() - 1  # force expiry (bypasses 1s window)
    tok = asyncio.run(session.get_token())
    assert tok.access_token == "AT2"  # refreshed token
    assert p.refresh_calls >= 1


def test_managed_session_refresh_reuses_valid(bus):
    p = DummyProvider(broker="primary")
    session = ManagedSession("acc1", p, InMemoryTokenStore(), event_bus=bus, key_prefix="mem:")
    t1 = asyncio.run(session.get_token())
    t2 = asyncio.run(session.get_token())
    assert t1.access_token == t2.access_token == "AT"
    assert p.refresh_calls == 0  # still valid, never refreshed


def test_managed_session_login_failure_raises_auth_failed(bus):
    p = DummyProvider(broker="primary", fail_login=True)
    sink = FakeSink()
    bus.subscribe(sink)
    session = ManagedSession("acc1", p, InMemoryTokenStore(), event_bus=bus, key_prefix="mem:")
    with pytest.raises(RuntimeError):
        asyncio.run(session.get_token())
    assert session.health().auth_state == AuthState.REFRESH_FAILED
    assert any(e.kind == BrokerEventKind.AUTH_FAILED for e in sink.events)


def test_managed_session_refresh_failure_raises_reauth(bus):
    p = DummyProvider(broker="primary", fail_refresh=True)
    sink = FakeSink()
    bus.subscribe(sink)
    session = ManagedSession("acc1", p, InMemoryTokenStore(), event_bus=bus, key_prefix="mem:")
    asyncio.run(session.get_token(force_login=True))
    session._token = Token(
        access_token="AT",
        refresh_token="RT",
        expires_at=time.time() - 1,
    )  # expired with refresh token -> refresh path
    with pytest.raises(ReAuthRequiredError):
        asyncio.run(session.get_token())
    assert session.health().auth_state == AuthState.REAUTH_REQUIRED
    assert any(e.kind == BrokerEventKind.REAUTH_REQUIRED for e in sink.events)


def test_managed_session_invalidate(bus):
    p = DummyProvider(broker="primary")
    session = ManagedSession("acc1", p, InMemoryTokenStore(), event_bus=bus, key_prefix="mem:")
    asyncio.run(session.get_token())
    asyncio.run(session.invalidate())
    assert session.health().ok is False


def test_session_manager_registry(bus):
    sm = SessionManager(event_bus=bus)
    s1 = sm.register("acc1", DummyProvider(broker="primary"))
    s2 = sm.register("acc1", DummyProvider(broker="primary"))  # same key -> cached
    assert s1 is s2
    sm.register("acc1", DummyProvider(broker="second"))
    assert len(sm.sessions()) == 2
    assert sm.get("acc1", "primary") is s1
    assert sm.get("acc1", "ghost") is None
    snap = sm.snapshot()
    assert len(snap) == 2
    assert all("auth_state" in d for d in snap)


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


def test_derive_health_priority():
    assert derive_health(rest_healthy=True, ws_healthy=True) == BrokerHealthState.CONNECTED
    assert derive_health(ws_healthy=True) == BrokerHealthState.WEBSOCKET_HEALTHY
    assert derive_health(rest_healthy=True) == BrokerHealthState.REST_HEALTHY
    assert derive_health() == BrokerHealthState.DISCONNECTED
    assert derive_health(rest_healthy=True, auth_failed=True) == BrokerHealthState.AUTHENTICATION_FAILED
    assert derive_health(rest_healthy=True, rate_limited=True) == BrokerHealthState.RATE_LIMITED
    assert derive_health(rest_healthy=True, circuit_open=True) == BrokerHealthState.CIRCUIT_OPEN
    assert derive_health(rest_healthy=True, degraded=True) == BrokerHealthState.DEGRADED


def test_health_service_tracks_brokers():
    svc = BrokerHealthService()
    h1 = svc.report_rest_health("faker", True)
    assert isinstance(h1, BrokerHealth)
    h2 = svc.report_ws_health("faker", True)
    assert h2.state == BrokerHealthState.CONNECTED
    assert svc.get("faker") is h2
    assert svc.count() == 1
    snap = svc.snapshot_all()
    assert "faker" in snap
    assert snap["faker"]["state"] == "connected"
    assert snap["faker"]["healthy"] is True


def test_health_service_degrades():
    svc = BrokerHealthService()
    svc.report_rest_health("faker", True)
    svc.report_ws_health("faker", True)
    svc.report_degraded("faker", True)
    assert svc.get("faker").state == BrokerHealthState.DEGRADED
    assert svc.get("faker").degraded is True


def test_health_service_auth_failure():
    svc = BrokerHealthService()
    svc.report_auth("faker", ok=False, error="token expired")
    assert svc.get("faker").state == BrokerHealthState.AUTHENTICATION_FAILED


def test_health_service_event_bus_fanout():
    bus = AuditEventBus()
    svc = BrokerHealthService(event_bus=bus)
    sink = FakeSink()
    bus.subscribe(sink)
    svc.report_circuit("faker", True)
    # state transition publishes a HEALTH_CHANGED event to the bus
    assert any(e.kind == BrokerEventKind.HEALTH_CHANGED for e in sink.events)
    ch = next(e for e in sink.events if e.kind == BrokerEventKind.HEALTH_CHANGED)
    assert ch.payload["to"] == "circuit_open"


def test_health_service_attaches_to_bus(bus):
    svc = BrokerHealthService(event_bus=bus)
    svc.attach_event_listener()
    bus.emit(BrokerEventKind.RATE_LIMITED, broker="faker", message="rl")
    assert svc.get("faker").rate_limited is True
    assert svc.get("faker").state == BrokerHealthState.RATE_LIMITED


def test_health_service_without_bus_ok():
    svc = BrokerHealthService()
    svc.report_auth("faker", ok=False)
    assert svc.get("faker").state == BrokerHealthState.AUTHENTICATION_FAILED


# ---------------------------------------------------------------------------
# websocket manager
# ---------------------------------------------------------------------------


class FakeBackend:
    def __init__(self):
        self.sent = []
        self.closed = False
        self._recv_queue = asyncio.Queue()  # noqa: F821 - bound in _make_fake

    async def connect(self):
        pass

    async def send(self, data):
        self.sent.append(data)

    async def recv(self):
        return await self._recv_queue.get()

    async def close(self):
        self.closed = True


def _make_manager(handlers=None, on_message=None, config=None):
    backends = []

    def factory():
        b = FakeBackend()
        backends.append(b)
        return b

    m = WebSocketManager(
        factory,
        broker="ops",
        subscribe_payload=lambda topics: json_dumps({"cmd": "SUB", "symbols": topics}),
        on_message=on_message,
        handlers=handlers,
        event_bus=AuditEventBus(),
        config=config or WSConfig(read_poll_seconds=0.01, heartbeat_interval=0, jitter=0),
    )
    return m, backends


def test_ws_subscribe_dedup():
    m, _ = _make_manager()
    assert m.subscribe("NSE:NIFTY") is True
    assert m.subscribe("NSE:NIFTY") is False
    assert m.subscribe("NSE:BANKNIFTY") is True
    assert m.topics() == ["NSE:BANKNIFTY", "NSE:NIFTY"]
    assert m.subscribed_count() == 2


def test_ws_unsubscribe():
    m, _ = _make_manager()
    m.subscribe("a")
    assert m.unsubscribe("a") is True
    assert m.unsubscribe("a") is False


def test_ws_connect_resubscribe_and_dispatch():
    import json

    events = []
    m, backends = _make_manager(on_message=lambda d: events.append(d))

    async def run():
        m.subscribe("NSE:NIFTY")
        await m.start()
        for _ in range(50):
            if m.is_connected():
                break
            await asyncio.sleep(0.01)
        backends[0]._recv_queue.put_nowait(json.dumps({"type": "HEARTBEAT"}))
        backends[0]._recv_queue.put_nowait(json.dumps({"type": "QUOTE", "update": "b"}))
        await asyncio.sleep(0.05)
        await m.stop()

    asyncio.run(run())
    assert m.stats.messages_in >= 1
    assert any("SUB" in s for s in backends[0].sent)  # resubscribed on connect


def test_ws_message_routing_to_handler():
    import json

    seen = []
    m, backends = _make_manager(handlers={"MARKET": lambda d: seen.append(d)})

    async def run():
        await m.start()
        for _ in range(50):
            if m.is_connected():
                break
            await asyncio.sleep(0.01)
        backends[0]._recv_queue.put_nowait(json.dumps({"type": "MARKET", "c": 1}))
        await asyncio.sleep(0.05)
        await m.stop()

    asyncio.run(run())
    assert len(seen) == 1
    assert seen[0]["c"] == 1


def test_ws_pong_updates_latency():
    import json

    m, backends = _make_manager()

    async def run():
        await m.start()
        for _ in range(50):
            if m.is_connected():
                break
            await asyncio.sleep(0.01)
        m._pending_ping_ts = time.time() - 0.020
        backends[0]._recv_queue.put_nowait(json.dumps({"type": "pong"}))
        await asyncio.sleep(0.05)
        await m.stop()

    asyncio.run(run())
    assert m.stats.last_pong_at > 0
    assert m.stats.latency_ms > 0


def test_ws_reconnect_after_connection_error():
    import json

    m, backends = _make_manager(config=WSConfig(read_poll_seconds=0.01, heartbeat_interval=0, jitter=0))

    class FailingBackend(FakeBackend):
        async def recv(self):
            return None  # peer close triggers reconnect loop

    def factory():
        return FailingBackend()

    m._factory = factory

    async def run():
        await m.start()
        await asyncio.sleep(0.2)
        await m.stop()

    asyncio.run(run())
    assert m.stats.reconnects >= 1


def test_ws_health_dict():
    m, _ = _make_manager()
    h = m.health()
    assert h["broker"] == "ops"
    assert h["connected"] is False
    assert "messages_in" in h