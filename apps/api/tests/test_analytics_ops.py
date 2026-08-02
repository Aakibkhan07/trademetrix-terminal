import pytest

from application.services.analytics_service import AnalyticsService


class FakeRes:
    def __init__(self, data=None):
        self.data = data


class FakeTable:
    def __init__(self, name, store):
        self._name = name
        self._store = store
        self._pending_update = None
        self._filters: list[tuple] = []
        self._limit = 1000
        self._sorted = False

    def insert(self, row):
        row = dict(row)
        row.setdefault("id", len(self._store) + 1)
        self._store.append(row)
        return self

    def select(self, *cols):
        return self

    def update(self, patch):
        self._pending_update = dict(patch)
        return self

    def order(self, col, desc=False):
        self._sorted = True
        return self

    def limit(self, n):
        self._limit = n
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def gte(self, col, val):
        self._filters.append(("gte", col, val))
        return self

    async def execute(self):
        rows = list(self._store)
        if self._pending_update is not None:
            for r in rows:
                r.update(self._pending_update)
        for op, col, val in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
            else:
                rows = [r for r in rows if str(r.get(col, "")) >= str(val)]
        return FakeRes(rows[: self._limit])


def _install_fake_supabase(monkeypatch, events, feedback):
    def table(name):
        store = events if name == "analytics_events" else feedback
        return FakeTable(name, store)

    client = type("S", (), {"table": staticmethod(table)})()
    monkeypatch.setattr("application.services.analytics_service.get_supabase", lambda: client)
    monkeypatch.setattr("application.services.analytics_service.async_supabase", lambda fn: fn())


@pytest.mark.asyncio
async def test_track_event_persists(monkeypatch):
    events = []
    _install_fake_supabase(monkeypatch, events, [])
    svc = AnalyticsService()
    res = await svc.track_event("page.view", {"path": "/dashboard"}, "sess-1", "", None)
    assert res["ok"] is True
    assert len(events) == 1
    assert events[0]["event"] == "page.view"
    assert events[0]["session_id"] == "sess-1"


@pytest.mark.asyncio
async def test_track_batch_rejects_empty(monkeypatch):
    events = []
    _install_fake_supabase(monkeypatch, events, [])
    svc = AnalyticsService()
    res = await svc.track_batch([
        {"event": "click", "properties": {"el": "button"}, "session_id": "s1"},
        {"type": "scroll.depth", "properties": {"depth": 50}, "session_id": "s1"},
        {"event": "", "session_id": "s1"},
    ])
    assert res["accepted"] == 2
    assert len(events) == 2


@pytest.mark.asyncio
async def test_track_event_requires_name(monkeypatch):
    _install_fake_supabase(monkeypatch, [], [])
    svc = AnalyticsService()
    with pytest.raises(ValueError):
        await svc.track_event("", {}, "s1", "", None)


@pytest.mark.asyncio
async def test_feedback_submit_and_list(monkeypatch):
    events, feedback = [], []
    _install_fake_supabase(monkeypatch, events, feedback)
    svc = AnalyticsService()

    class U:
        id = "user-1"
        email = "u@test.dev"
        full_name = "Tester"

    res = await svc.submit_feedback(U(), "bug", "Order issue", "Describe", {"url": "/trade"})
    assert res["ok"] is True
    res2 = await svc.submit_feedback(U(), "feature", "", "Add X", {})
    assert res2["ok"] is True

    listed = await svc.list_feedback(category="feature")
    assert listed["count"] == 1
    assert listed["feedback"][0]["title"] == ""


@pytest.mark.asyncio
async def test_feedback_requires_text(monkeypatch):
    _install_fake_supabase(monkeypatch, [], [])
    svc = AnalyticsService()

    class U:
        id = "user-1"

    with pytest.raises(ValueError):
        await svc.submit_feedback(U(), "bug", "", "", {})


@pytest.mark.asyncio
async def test_list_user_feedback_scoped_to_user(monkeypatch):
    events, feedback = [], []
    _install_fake_supabase(monkeypatch, events, feedback)
    svc = AnalyticsService()

    class U:
        id = "user-1"
        email = "u@test.dev"
        full_name = "Tester"

    class U2:
        id = "user-2"
        email = "v@test.dev"
        full_name = "Other"

    await svc.submit_feedback(U(), "bug", "Mine", "desc", {})
    await svc.submit_feedback(U2(), "feature", "Theirs", "desc", {})

    mine = await svc.list_user_feedback("user-1")
    assert mine["count"] == 1
    assert mine["feedback"][0]["title"] == "Mine"
    assert mine["feedback"][0]["user_id"] == "user-1"

    none = await svc.list_user_feedback("user-3")
    assert none["count"] == 0


@pytest.mark.asyncio
async def test_funnel_counts_by_step(monkeypatch):
    events = []
    _install_fake_supabase(monkeypatch, events, [])
    svc = AnalyticsService()
    for i, name in enumerate(("signup", "signup", "broker.connected", "strategy.created", "backtest.run")):
        await svc.track_event(name, {}, f"s{i}", "", None)
    funnel = await svc.get_funnel(["signup", "broker.connected", "strategy.created", "backtest.run"], 30)
    counts = {s["step"]: s["users"] for s in funnel["steps"]}
    assert counts["signup"] == 2
    assert counts["broker.connected"] == 1
    assert counts["backtest.run"] == 1


@pytest.mark.asyncio
async def test_feature_usage_ranking(monkeypatch):
    events = []
    _install_fake_supabase(monkeypatch, events, [])
    svc = AnalyticsService()
    for name in ("page.view", "page.view", "page.view", "backtest.run", "order.placed"):
        await svc.track_event(name, {}, "s1", "", None)
    usage = await svc.get_feature_usage(30)
    assert usage["features"][0]["event"] == "page.view"
    assert usage["features"][0]["count"] == 3


@pytest.mark.asyncio
async def test_crashes_grouped_by_key(monkeypatch):
    events = []
    _install_fake_supabase(monkeypatch, events, [])
    svc = AnalyticsService()
    for i in range(3):
        await svc.track_event("client_error", {"key": "hash-abc", "message": "boom"}, f"s{i}", "", None)
    await svc.track_event("client_error", {"key": "hash-xyz"}, "s9", "", None)
    crashes = await svc.get_crashes(30)
    assert crashes["total"] == 4
    assert crashes["crashes"][0]["key"] == "hash-abc"
    assert crashes["crashes"][0]["count"] == 3


@pytest.mark.asyncio
async def test_session_replay(monkeypatch):
    events = []
    _install_fake_supabase(monkeypatch, events, [])
    svc = AnalyticsService()
    for name in ("session.start", "page.view", "click"):
        await svc.track_event(name, {}, "sess-replay", "", None)
    replay = await svc.get_session_events("sess-replay")
    assert replay["count"] == 3
