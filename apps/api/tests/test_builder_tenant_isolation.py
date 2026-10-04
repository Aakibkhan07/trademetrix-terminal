"""One tenant must not read or act on another tenant's strategies or backtest runs.

Measured on production before the fix, both of these answered HTTP 200 to a user who had
created nothing of their own:

    GET /api/v1/builder/strategies/<other id>   -> the full DSL: 8 nodes, 8 edges,
                                                    symbol, exchange, interval, risk
    GET /api/v1/backtests/<other run id>        -> net_pnl, trades, a 301-point equity curve

The cause was the same in both: a `current_user` was resolved by the dependency and then
never passed to the layer that reads data, so lookups were by id alone and
`builder_manager.list()` returned the whole deployment.

`builder_strategies` had no ownership column at all, so `author` was being read as one. It
holds three different kinds of value in production — the literal 'user' on 1144 rows, a real
uuid on 23 — so comparing it to a user id matched either everything or nothing.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backtest.manager import BacktestManager
from builder import manager as bm
from builder.models import StrategyDSL

OWNER = "11111111-1111-1111-1111-111111111111"
INTRUDER = "22222222-2222-2222-2222-222222222222"
LEGACY_DEFAULT_AUTHOR = "user"


@pytest.fixture(autouse=True)
def _clean_registry():
    """Each test starts from an empty in-process registry."""
    bm._strategies.clear()
    bm._versions.clear()
    bm._db_loaded = True  # skip the Supabase load; every row here is planted explicitly
    yield
    bm._strategies.clear()
    bm._versions.clear()


def _plant(strategy_id: str, **overrides) -> None:
    dsl = StrategyDSL(
        id=strategy_id,
        name="EMA Crossover",
        author=OWNER,
        status=bm.StrategyStatus.READY,
        version_number=1,
    )
    row = dsl.model_dump(mode="json")
    row.update(overrides)
    bm._strategies[strategy_id] = row
    bm._versions[strategy_id] = [{"version": 1, "data": row, "saved_at": row.get("created_at")}]


# ── the discriminator itself ────────────────────────────────────────────────


def test_author_holding_the_literal_user_is_not_an_owner():
    """The 1144 production rows that made every tenant match every strategy."""
    data = {"author": LEGACY_DEFAULT_AUTHOR}
    assert bm._owner_of(data) is None


def test_an_empty_author_is_not_an_owner():
    assert bm._owner_of({"author": ""}) is None


def test_a_uuid_author_is_recovered_as_the_owner():
    """Ownership that was recorded but never queryable is still usable."""
    assert bm._owner_of({"author": OWNER}) == OWNER


def test_user_id_wins_over_author():
    assert bm._owner_of({"user_id": OWNER, "author": LEGACY_DEFAULT_AUTHOR}) == OWNER


def test_a_non_uuid_author_is_ignored_rather_than_guessed_at():
    """`author=current_user.email` was written by the import flow; an email is not an id."""
    assert bm._owner_of({"author": "someone@example.com"}) is None


# ── reads ───────────────────────────────────────────────────────────────────


async def test_the_owner_can_read_their_strategy():
    _plant("aaaa00000001")
    assert (await bm.builder_manager.get("aaaa00000001", OWNER)) is not None


async def test_another_tenant_cannot_read_it():
    _plant("aaaa00000001")
    assert await bm.builder_manager.get("aaaa00000001", INTRUDER) is None


async def test_an_unowned_strategy_is_visible_to_nobody():
    """Fails closed: no recorded owner means no tenant can claim it."""
    _plant("aaaa00000002", user_id=None, author=LEGACY_DEFAULT_AUTHOR)
    assert await bm.builder_manager.get("aaaa00000002", OWNER) is None
    assert await bm.builder_manager.get("aaaa00000002", INTRUDER) is None


async def test_list_returns_only_the_callers_strategies():
    _plant("bbbb00000001")
    _plant("bbbb00000002", user_id=INTRUDER, author=INTRUDER)

    mine = await bm.builder_manager.list(user_id=OWNER)
    theirs = await bm.builder_manager.list(user_id=INTRUDER)

    assert [s["id"] for s in mine] == ["bbbb00000001"]
    assert [s["id"] for s in theirs] == ["bbbb00000002"]


async def test_list_hides_unowned_rows_from_everyone():
    _plant("bbbb00000003", user_id=None, author=LEGACY_DEFAULT_AUTHOR)
    assert await bm.builder_manager.list(user_id=OWNER) == []
    assert await bm.builder_manager.list(user_id=INTRUDER) == []


# ── writes ──────────────────────────────────────────────────────────────────


async def test_another_tenant_cannot_update_it():
    _plant("cccc00000001")
    assert await bm.builder_manager.update("cccc00000001", {"name": "stolen"}, user_id=INTRUDER) is None
    assert bm._strategies["cccc00000001"]["name"] == "EMA Crossover"


async def test_another_tenant_cannot_delete_it():
    _plant("cccc00000002")
    assert await bm.builder_manager.delete("cccc00000002", user_id=INTRUDER) is False
    assert "cccc00000002" in bm._strategies


async def test_another_tenant_cannot_change_its_status_or_deploy_it():
    _plant("cccc00000003")
    assert await bm.builder_manager.set_status("cccc00000003", bm.StrategyStatus.LIVE, user_id=INTRUDER) is None
    assert await bm.builder_manager.publish("cccc00000003", user_id=INTRUDER) is None
    assert await bm.builder_manager.archive("cccc00000003", user_id=INTRUDER) is None
    assert bm._strategies["cccc00000003"]["status"] == "ready"


async def test_another_tenant_cannot_read_its_version_history():
    _plant("dddd00000001")
    assert await bm.builder_manager.get_versions("dddd00000001", user_id=INTRUDER) == []
    assert await bm.builder_manager.get_version("dddd00000001", 1, user_id=INTRUDER) is None
    assert await bm.builder_manager.compare("dddd00000001", 1, 1, user_id=INTRUDER) is None
    assert await bm.builder_manager.rollback("dddd00000001", 1, user_id=INTRUDER) is None


async def test_the_owner_still_reaches_their_version_history():
    _plant("dddd00000002")
    assert len(await bm.builder_manager.get_versions("dddd00000002", user_id=OWNER)) == 1
    assert await bm.builder_manager.get_version("dddd00000002", 1, user_id=OWNER) is not None


# ── the writer ──────────────────────────────────────────────────────────────


async def test_create_records_the_owner_so_the_new_row_is_visible_to_its_creator():
    with patch.object(bm, "_persist", new=AsyncMock()), patch.object(
        bm, "_persist_version", new=AsyncMock()
    ):
        dsl = await bm.builder_manager.create(name="Mine", owner_id=OWNER)

    assert bm._strategies[dsl.id]["user_id"] == OWNER
    assert await bm.builder_manager.get(dsl.id, OWNER) is not None
    assert await bm.builder_manager.get(dsl.id, INTRUDER) is None


# ── ownership must survive every mutation ───────────────────────────────────
#
# Found by mutation: deleting `user_id` from `StrategyDSL` left every other test green, and
# with it gone each mutating method's `_strategies[id] = dsl.model_dump(...)` dropped the
# owner — so the first time a user validated, published, archived, rolled back or changed the
# status of their own strategy, the row stopped matching their tenant and became invisible to
# the person who created it. The manager took the id, checked it, and then threw it away.


# `author` is planted as the literal 'user' throughout these tests, which is what the API's own
# `create` default is and what 1144 production rows carry. That matters: `_owner_of` falls back
# to `author` when it is uuid-shaped, so planting a uuid there lets the fallback mask the
# ownership being dropped. With `author='user'` there is nothing to fall back to and only
# `user_id` can keep the strategy visible — which is exactly the case that broke.
_PLANTED_AS = {"user_id": OWNER, "author": LEGACY_DEFAULT_AUTHOR}


async def test_the_owner_keeps_their_strategy_after_a_status_change():
    _plant("eeee00000001", **_PLANTED_AS)
    await bm.builder_manager.set_status("eeee00000001", bm.StrategyStatus.READY, user_id=OWNER)

    assert bm._strategies["eeee00000001"].get("user_id") == OWNER
    assert await bm.builder_manager.get("eeee00000001", OWNER) is not None


@pytest.mark.parametrize(
    "transition",
    [
        lambda: bm.builder_manager.publish("eeee00000002", user_id=OWNER),
        lambda: bm.builder_manager.archive("eeee00000002", user_id=OWNER),
        lambda: bm.builder_manager.set_status("eeee00000002", bm.StrategyStatus.PAPER, user_id=OWNER),
        lambda: bm.builder_manager.rollback("eeee00000002", 1, user_id=OWNER),
    ],
    ids=["publish", "archive", "set_status", "rollback"],
)
async def test_no_transition_drops_the_owner(transition):
    """Each of these ends in `model_dump`, which emits only declared fields."""
    _plant("eeee00000002", **_PLANTED_AS)
    await transition()

    assert bm._strategies["eeee00000002"].get("user_id") == OWNER, "ownership was dropped"
    assert await bm.builder_manager.get("eeee00000002", OWNER) is not None


async def test_cloning_carries_the_new_owner_not_the_originals():
    _plant("eeee00000003", **_PLANTED_AS)
    clone = await bm.builder_manager.clone("eeee00000003", user_id=OWNER)

    assert clone is not None
    # A clone is a new strategy; it belongs to whoever made it, and must not be readable as
    # the source strategy's owner by accident.
    assert bm._strategies[clone.id].get("user_id") == OWNER
    assert clone.id != "eeee00000003"


async def test_an_update_that_renames_keeps_the_owner():
    _plant("eeee00000004", **_PLANTED_AS)
    await bm.builder_manager.update("eeee00000004", {"name": "Renamed"}, user_id=OWNER)

    assert bm._strategies["eeee00000004"].get("user_id") == OWNER


# ── backtest runs ───────────────────────────────────────────────────────────


class _Run:
    """Minimal stand-in for a `BacktestResult` — `list_runs` reads these fields."""

    def __init__(self, run_id: str, user_id: str):
        from types import SimpleNamespace

        self.run_id = run_id
        self.user_id = user_id
        self.config = SimpleNamespace(strategy_type="macd_cross", symbol="NIFTY")
        self.status = SimpleNamespace(value="completed")
        self.total_trades = 2
        self.net_pnl = -195.0
        self.win_rate = 0.0
        self.return_pct = -0.1
        self.sharpe_ratio = 0.0
        self.started_at = None
        self.completed_at = None
        self.duration_seconds = 1


def _mgr_with(*runs) -> BacktestManager:
    m = BacktestManager()
    m._history = list(runs)
    return m


async def test_a_backtest_run_is_not_readable_by_another_tenant():
    m = _mgr_with(_Run("run-owner", OWNER))
    assert await m.get_run("run-owner", user_id=INTRUDER) is None
    assert await m.get_run("run-owner", user_id=OWNER) is not None


async def test_list_runs_is_scoped_to_the_caller():
    m = _mgr_with(_Run("run-owner", OWNER), _Run("run-theirs", INTRUDER))
    mine = m.list_runs(user_id=OWNER)
    theirs = m.list_runs(user_id=INTRUDER)
    assert [r["run_id"] for r in mine] == ["run-owner"]
    assert [r["run_id"] for r in theirs] == ["run-theirs"]


async def test_a_run_with_no_owner_is_listed_for_nobody():
    m = _mgr_with(_Run("run-legacy", ""))
    assert m.list_runs(user_id=OWNER) == []


class _RecordingQuery:
    """Captures the `.eq()` filters a PostgREST query was built with.

    The in-process `_history` lookup is only half of `get_run` — the other half is the
    Supabase read, and that is where the ownership filter lives. Removing the filter from the
    query left every other test green, because no test reached it.
    """

    def __init__(self, sink: list):
        self._sink = sink

    def select(self, *a, **k):
        self._sink.append(("select", a))
        return self

    def eq(self, column, value):
        self._sink.append(("eq", column, value))
        return self

    def limit(self, n):
        self._sink.append(("limit", n))
        return self

    def execute(self):
        self._sink.append(("execute", None))
        return SimpleNamespace(data=[])


class _RecordingTable:
    def __init__(self, sink: list):
        self._sink = sink

    def select(self, *a, **k):
        self._sink.append(("select", a))
        return _RecordingQuery(self._sink)


class _RecordingSupabase:
    def __init__(self, sink: list):
        self._sink = sink

    def table(self, name: str):
        self._sink.append(("table", name))
        return _RecordingTable(self._sink)


async def test_the_supabase_read_of_a_run_filters_by_owner(monkeypatch):
    """The database path, not just the in-memory one.

    Found by mutation: deleting `.eq("user_id", ...)` from the query left all 19 tests green,
    because every other case was served by `self._history`.
    """
    import backtest.manager as btm

    sink: list = []

    async def _fake_async_supabase(fn):
        return fn()

    monkeypatch.setattr(btm, "get_supabase", lambda: _RecordingSupabase(sink), raising=False)
    monkeypatch.setattr("core.db.get_supabase", lambda: _RecordingSupabase(sink))
    monkeypatch.setattr("core.db.async_supabase", _fake_async_supabase)

    m = _mgr_with()  # empty history, so the DB branch is the one under test
    assert await m.get_run("run-x", user_id=OWNER) is None

    filters = [entry for entry in sink if entry[0] == "eq"]
    assert ("eq", "id", "run-x") in filters, f"the run id was not constrained: {sink}"
    assert ("eq", "user_id", OWNER) in filters, f"the owner was not constrained: {sink}"


async def test_the_supabase_read_without_a_caller_does_not_filter_by_owner(monkeypatch):
    """Internal callers with no tenant context keep the unfiltered read."""
    import backtest.manager as btm

    sink: list = []

    async def _fake_async_supabase(fn):
        return fn()

    monkeypatch.setattr(btm, "get_supabase", lambda: _RecordingSupabase(sink), raising=False)
    monkeypatch.setattr("core.db.get_supabase", lambda: _RecordingSupabase(sink))
    monkeypatch.setattr("core.db.async_supabase", _fake_async_supabase)

    m = _mgr_with()
    assert await m.get_run("run-x") is None

    assert ("eq", "user_id", OWNER) not in sink
    assert [e for e in sink if e[0] == "eq"] == [("eq", "id", "run-x")]
