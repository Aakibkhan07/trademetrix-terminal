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


@pytest.fixture
def svc(monkeypatch) -> AnalyticsService:
    events: list[dict] = []
    feedback: list[dict] = []
    _install_fake_supabase(monkeypatch, events, feedback)
    return AnalyticsService()


class TestTrackEvent:
    @pytest.mark.asyncio
    async def test_tracks_event(self, svc) -> None:
        result = await svc.track_event("page_view", {"page": "/home"}, session_id="s1", user_id="u1")
        assert result["ok"] is True
        assert result["event"] == "page_view"

    @pytest.mark.asyncio
    async def test_raises_on_empty_event_name(self, svc) -> None:
        with pytest.raises(ValueError, match="event is required"):
            await svc.track_event("")

    @pytest.mark.asyncio
    async def test_server_event_requires_no_session(self, svc) -> None:
        await svc.record_server_event("u1", "strategy.created", {"template": "ema"})
        listed = await svc.list_events()
        assert listed["total"] == 1
        assert listed["events"][0]["event"] == "strategy.created"


class TestListEvents:
    @pytest.mark.asyncio
    async def test_lists_all_events(self, svc) -> None:
        await svc.track_event("a")
        await svc.track_event("b")
        result = await svc.list_events()
        assert result["total"] == 2

    @pytest.mark.asyncio
    async def test_filters_by_event_name(self, svc) -> None:
        await svc.track_event("click")
        await svc.track_event("page_view")
        await svc.track_event("click")
        result = await svc.list_events(event_filter="click")
        assert result["total"] == 2
        assert all(e["event"] == "click" for e in result["events"])


class TestQueries:
    @pytest.mark.asyncio
    async def test_funnel_orders_steps(self, svc) -> None:
        for i, name in enumerate(("signup", "signup", "broker.connected", "strategy.created")):
            await svc.track_event(name, {}, f"s{i}", "", None)
        funnel = await svc.get_funnel(["signup", "broker.connected", "strategy.created"], 30)
        counts = {s["step"]: s["users"] for s in funnel["steps"]}
        assert counts["signup"] == 2
        assert counts["broker.connected"] == 1
        assert funnel["steps"][0]["step"] == "signup"

    @pytest.mark.asyncio
    async def test_feature_usage_ranking(self, svc) -> None:
        for name in ("page.view", "page.view", "page.view", "backtest.run"):
            await svc.track_event(name, {}, "s1", "", None)
        usage = await svc.get_feature_usage(30)
        assert usage["features"][0]["event"] == "page.view"
        assert usage["features"][0]["count"] == 3

    @pytest.mark.asyncio
    async def test_crashes_grouped_by_key(self, svc) -> None:
        for i in range(3):
            await svc.track_event("client_error", {"key": "hash-abc", "message": "boom"}, f"s{i}", "", None)
        await svc.track_event("client_error", {"key": "hash-xyz"}, "s9", "", None)
        crashes = await svc.get_crashes(30)
        assert crashes["total"] == 4
        assert crashes["crashes"][0]["key"] == "hash-abc"
        assert crashes["crashes"][0]["count"] == 3

    @pytest.mark.asyncio
    async def test_session_replay(self, svc) -> None:
        for name in ("session.start", "page.view", "click"):
            await svc.track_event(name, {}, "sess-replay", "", None)
        replay = await svc.get_session_events("sess-replay")
        assert replay["count"] == 3

    @pytest.mark.asyncio
    async def test_feedback_submit_and_filter(self, svc) -> None:
        class U:
            id = "user-1"
            email = "u@test.dev"
            full_name = "Tester"

        await svc.submit_feedback(U(), "bug", "Order issue", "Describe", {"url": "/trade"})
        await svc.submit_feedback(U(), "feature", "", "Add X", {})
        listed = await svc.list_feedback(category="feature")
        assert listed["count"] == 1
        with pytest.raises(ValueError):
            await svc.submit_feedback(U(), "bug", "", "", {})

    @pytest.mark.asyncio
    async def test_feedback_update(self, svc) -> None:
        class U:
            id = "user-1"
            email = "u@test.dev"
            full_name = "Tester"

        res = await svc.submit_feedback(U(), "bug", "T", "D", {})
        feedback = await svc.list_feedback()
        fid = feedback["feedback"][0]["id"]
        await svc.update_feedback(fid, status="triaged", notes="watching")
        listed = await svc.list_feedback(status="triaged")
        assert listed["count"] == 1
